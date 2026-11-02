"""Invite-only account lifecycle. Admins can manage access, never financial rows."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import re
import secrets
import time
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, String, Uuid, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import Principal, authenticate, authenticate_identity
from .database import Base, get_db, settings


class AccountMember(Base):
    __tablename__ = "account_members"
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccountInvitation(Base):
    __tablename__ = "account_invitations"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    invited_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    access_duration_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    target_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    claim_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccountAccessRequest(Base):
    __tablename__ = "account_access_requests"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    invitation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    processing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccountAccessRequestLimit(Base):
    __tablename__ = "account_access_request_limits"
    scope_key: Mapped[str] = mapped_column(String(72), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AccountDeletionJob(Base):
    __tablename__ = "account_deletion_jobs"
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    email: Mapped[str] = mapped_column(String(320))
    state: Mapped[str] = mapped_column(String(32))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccountDeletionAudit(Base):
    __tablename__ = "account_deletion_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid)
    event_code: Mapped[str] = mapped_column(String(40))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccountFixtureLoad(Base):
    __tablename__ = "account_fixture_loads"
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(80))
    fixture_sha256: Mapped[str] = mapped_column(String(64))
    loaded_by: Mapped[UUID] = mapped_column(Uuid)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeleteAccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str = Field(min_length=1, max_length=40)


class InvitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    expires_in_days: int = Field(default=7, ge=1, le=7)


class AcceptInvitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invitation_id: UUID
    claim_token: str = Field(min_length=40, max_length=128)


class ReleaseInvitationClaimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_token: str = Field(min_length=40, max_length=128)


class AccessRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)


router = APIRouter(tags=["accounts"])
admin_router = APIRouter(prefix="/api/admin", tags=["account-invitations"])
access_request_response = {"message": "Se sua solicitação puder ser processada, ela será analisada. Caso seja aprovada, você receberá um convite por e-mail."}


def _admin(principal: Principal):
    if principal.user_id is None or principal.user_id not in settings.invitation_admin_ids:
        raise HTTPException(403, "Ação administrativa não autorizada")
    return principal.user_id


def _email(value: str):
    normalized = value.strip().lower()
    if len(normalized) > 320 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", normalized):
        raise HTTPException(422, "Informe um e-mail válido")
    return normalized


def _request_ip(request: Request) -> str:
    if settings.environment == "production":
        raw_ip = request.headers.get("cf-connecting-ip", "").strip()
    else:
        raw_ip = request.client.host if request.client else ""
    try:
        return str(ipaddress.ip_address(raw_ip))
    except ValueError:
        raise HTTPException(503, "Proteção contra abuso indisponível") from None


def _request_ip_hash(ip: str) -> str:
    key = settings.supabase_service_role_key.get_secret_value().strip().encode()
    if not key:
        key = settings.api_token.get_secret_value().strip().encode()
    if not key:
        raise HTTPException(503, "Proteção contra abuso não configurada")
    return hmac.new(key, b"dashboard-trial-access-v1:" + ip.encode(), hashlib.sha256).hexdigest()


def _increment_local_request_limit(db: Session, scope_key: str, now: datetime) -> int:
    row = db.get(AccountAccessRequestLimit, scope_key)
    if row is None:
        row = AccountAccessRequestLimit(scope_key=scope_key, window_started_at=now, attempts=1)
        db.add(row)
        db.flush()
        return 1
    window_start = row.window_started_at
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    if window_start + timedelta(hours=24) <= now:
        row.window_started_at = now
        row.attempts = 1
    else:
        row.attempts += 1
    return row.attempts


@router.post("/api/access-requests", status_code=202)
def submit_access_request(body: AccessRequestInput, request: Request, db: Session = Depends(get_db)):
    email = _email(body.email)
    ip_hash = _request_ip_hash(_request_ip(request))
    try:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT set_config('app.access_request_submit','true',true)"))
            db.execute(text("SELECT public.submit_dashboard_trial_access_request(:email,:ip_hash)"),
                       {"email": email, "ip_hash": ip_hash})
        else:
            now = datetime.now(timezone.utc)
            total = _increment_local_request_limit(db, "global", now)
            if total <= 100:
                from_ip = _increment_local_request_limit(db, "ip:" + ip_hash, now)
                duplicate = db.scalar(select(AccountAccessRequest.id).where(AccountAccessRequest.email == email,
                    AccountAccessRequest.status.in_(("pending", "approving", "approved"))).limit(1))
                if from_ip <= 3 and duplicate is None:
                    db.add(AccountAccessRequest(id=uuid4(), email=email, ip_hash=ip_hash, status="pending", requested_at=now))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Não foi possível registrar a solicitação") from None
    # Identical response for new, duplicate, and rate-limited e-mails prevents enumeration.
    return access_request_response


def _admin_context(db: Session, admin_id: UUID):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.admin_id', :admin, true)"), {"admin": str(admin_id)})


def _serialize(row: AccountInvitation):
    return {"id": str(row.id), "email": row.email, "created_at": row.created_at.isoformat(),
            "expires_at": row.expires_at.isoformat(), "accepted": row.accepted_user_id is not None,
            "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
            "access_duration_days": row.access_duration_days,
            "target_user_id": str(row.target_user_id) if row.target_user_id else None,
            "revoked": row.revoked_at is not None}


def _utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _access_payload(member: AccountMember, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    expiry = _utc(member.access_expires_at)
    activated = _utc(member.activated_at)
    state = "revoked" if member.status == "revoked" else "expired" if expiry and expiry <= now else "active"
    return {"status": state, "access_type": "trial" if expiry else "permanent",
            "activated_at": activated.isoformat() if activated else None,
            "trial_expires_at": expiry.isoformat() if expiry else None}


def _verify_supabase_email(principal: Principal, email: str) -> None:
    """Require Supabase's server-side confirmation state before accepting a new invite."""
    if settings.auth_mode != "supabase":
        return
    service_key = settings.supabase_service_role_key.get_secret_value().strip()
    if not service_key:
        raise HTTPException(503, "A validação de convite não está configurada")
    try:
        with httpx.Client(trust_env=False, timeout=httpx.Timeout(8, connect=3)) as client:
            response = client.get(
                f"{settings.supabase_url}/auth/v1/admin/users/{principal.user_id}",
                headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            )
        if response.status_code == 404:
            raise HTTPException(403, "Convite precisa ser aceito por uma conta Supabase válida")
        response.raise_for_status()
        body = response.json()
        user = body.get("user", body) if isinstance(body, dict) else None
        if not isinstance(user, dict):
            raise ValueError("invalid user response")
    except HTTPException:
        raise
    except httpx.HTTPError:
        raise HTTPException(503, "Não foi possível validar o convite com o Supabase") from None
    except (ValueError, TypeError):
        raise HTTPException(503, "Não foi possível validar o convite com o Supabase") from None

    raw_email = user.get("email")
    if not isinstance(raw_email, str):
        raise HTTPException(403, "Convite precisa corresponder ao e-mail confirmado")
    try:
        confirmed_email = _email(raw_email)
    except HTTPException:
        raise HTTPException(403, "Convite precisa corresponder ao e-mail confirmado") from None
    if (str(user.get("id", "")) != str(principal.user_id)
            or confirmed_email != email
            or not user.get("email_confirmed_at")):
        raise HTTPException(403, "Convite precisa corresponder ao e-mail confirmado")


def _require_recent_delete_confirmation(principal: Principal, confirmation: str) -> None:
    if principal.user_id is None or not principal.email:
        raise HTTPException(403, "A exclusão exige uma conta Supabase autenticada")
    if confirmation != "EXCLUIR MINHA CONTA":
        raise HTTPException(400, "Digite EXCLUIR MINHA CONTA para confirmar")
    now = int(time.time())
    if principal.auth_time is None or principal.auth_time > now + 30 or now - principal.auth_time > 300:
        raise HTTPException(403, "Confirme sua senha novamente antes de excluir a conta")


def _run_deletion_function(db: Session, function: str, principal: Principal, *, email: str | None = None):
    """Call only fixed migration functions; each phase commits independently for safe retry."""
    if db.bind.dialect.name != "postgresql":
        raise HTTPException(503, "Exclusão de conta exige o procedimento PostgreSQL instalado")
    parameters = {"user_id": principal.user_id}
    if email is not None:
        parameters["email"] = email
    arguments = ":user_id" + (", :email" if email is not None else "")
    try:
        db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(principal.user_id)})
        if email is not None:
            db.execute(text("SELECT set_config('app.user_email', :email, true)"), {"email": email})
        result = db.scalar(text(f"SELECT public.{function}({arguments})"), parameters)
        db.commit()
        return result
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "A exclusão foi interrompida com segurança; tente novamente após verificar a conexão") from None


def _delete_supabase_identity(user_id: UUID) -> bool:
    """Delete only the JWT subject; returns false only when Supabase already removed it."""
    service_key = settings.supabase_service_role_key.get_secret_value().strip()
    if not service_key:
        raise HTTPException(503, "A exclusão da identidade Supabase não está configurada; a solicitação pode ser retomada")
    try:
        with httpx.Client(trust_env=False, timeout=httpx.Timeout(8, connect=3)) as client:
            response = client.delete(
                f"{settings.supabase_url}/auth/v1/admin/users/{user_id}",
                headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            )
    except httpx.HTTPError:
        raise HTTPException(503, "A identidade Supabase ainda não foi removida; a exclusão pode ser retomada") from None
    if response.status_code in (200, 204):
        return True
    if response.status_code == 404:
        return False
    raise HTTPException(503, "A identidade Supabase ainda não foi removida; a exclusão pode ser retomada")


@router.post("/api/account/delete")
def delete_own_account(
    body: DeleteAccountInput,
    principal: Principal = Depends(authenticate_identity),
    db: Session = Depends(get_db),
):
    """Self-service, recent-auth deletion. No target account ID is accepted from the caller."""
    if settings.auth_mode != "supabase":
        raise HTTPException(403, "A exclusão integral está disponível apenas para contas Supabase")
    _require_recent_delete_confirmation(principal, body.confirmation)
    if not settings.supabase_service_role_key.get_secret_value().strip():
        raise HTTPException(503, "A exclusão da identidade Supabase não está configurada")
    email = _email(principal.email or "")

    state = _run_deletion_function(db, "dashboard_account_deletion_state", principal)
    if state is None:
        # Verify project identity before creating an irreversible, resumable job.
        _verify_supabase_email(principal, email)
        state = _run_deletion_function(db, "begin_dashboard_account_deletion", principal, email=email)
    if state == "requested":
        state = _run_deletion_function(db, "purge_dashboard_account_data", principal)
    if state == "financial_data_deleted":
        _delete_supabase_identity(principal.user_id)
        state = _run_deletion_function(db, "mark_dashboard_auth_identity_deleted", principal)
    if state == "auth_identity_deleted":
        finished = _run_deletion_function(db, "finish_dashboard_account_deletion", principal)
        if not finished:
            raise HTTPException(503, "A exclusão aguarda finalização e pode ser retomada")
    elif state not in ("requested", "financial_data_deleted"):
        raise HTTPException(503, "Estado de exclusão inesperado; nenhuma outra conta foi alterada")
    return {"status": "deleted"}


@router.get("/api/account/fixture-status")
def account_fixture_status(
    principal: Principal = Depends(authenticate),
    db: Session = Depends(get_db),
):
    """Expose only the current owner's fictional-fixture marker to the private UI."""
    if principal.user_id is None:
        return {"fictional_fixture_loaded": False}
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.user_id', :user_id, true), set_config('app.auth_mode', :mode, true)"),
                   {"user_id": str(principal.user_id), "mode": settings.auth_mode})
    fixture_id = db.scalar(select(AccountFixtureLoad.fixture_id).where(AccountFixtureLoad.user_id == principal.user_id))
    return {"fictional_fixture_loaded": fixture_id is not None}


@router.post("/api/account/invitations/{invitation_id}/claim")
def claim_invitation(invitation_id: UUID, principal: Principal = Depends(authenticate_identity), db: Session = Depends(get_db)):
    if principal.user_id is None or not principal.email:
        raise HTTPException(403, "Convite inválido ou expirado. Solicite um novo ao administrador.")
    email = _email(principal.email)
    _verify_supabase_email(principal, email)
    now = datetime.now(timezone.utc)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.user_id', :user_id, true), set_config('app.user_email', :email, true)"),
                   {"user_id": str(principal.user_id), "email": email})
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": f"dashboard-invitation-claim:{invitation_id}"})
    invite = db.scalar(select(AccountInvitation).where(AccountInvitation.id == invitation_id,
        AccountInvitation.email == email, AccountInvitation.accepted_user_id.is_(None),
        AccountInvitation.revoked_at.is_(None), AccountInvitation.expires_at > now,
        (AccountInvitation.target_user_id.is_(None) | (AccountInvitation.target_user_id == principal.user_id))).with_for_update())
    member = db.get(AccountMember, principal.user_id)
    eligible = bool(invite and ((member is None and invite.target_user_id is None) or
        (member is not None and invite.target_user_id == principal.user_id and
         (member.status == "revoked" or (_utc(member.access_expires_at) and _utc(member.access_expires_at) <= now)))))
    if not eligible:
        db.rollback()
        raise HTTPException(403, "Convite inválido ou expirado. Solicite um novo ao administrador.")
    claim_expiry = _utc(invite.claim_expires_at)
    if invite.claim_token_hash and claim_expiry and claim_expiry > now:
        db.rollback()
        raise HTTPException(409, "Este convite já está em processo de ativação. Aguarde alguns minutos ou solicite ajuda ao administrador.")
    claim_token = secrets.token_urlsafe(48)
    invite.claim_user_id = principal.user_id
    invite.claim_token_hash = hashlib.sha256(claim_token.encode()).hexdigest()
    invite.claim_expires_at = min(now + timedelta(minutes=10), _utc(invite.expires_at))
    claim_expires_at = invite.claim_expires_at.isoformat()
    db.commit()
    return {"claim_token": claim_token, "expires_at": claim_expires_at}


@router.delete("/api/account/invitations/{invitation_id}/claim")
def release_invitation_claim(invitation_id: UUID, body: ReleaseInvitationClaimInput,
    principal: Principal = Depends(authenticate_identity), db: Session = Depends(get_db)):
    if principal.user_id is None:
        raise HTTPException(403, "Sessão inválida")
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.user_id', :user_id, true), set_config('app.user_email', :email, true)"),
                   {"user_id": str(principal.user_id), "email": _email(principal.email or "")})
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": f"dashboard-invitation-claim:{invitation_id}"})
    invite = db.scalar(select(AccountInvitation).where(AccountInvitation.id == invitation_id,
        AccountInvitation.claim_user_id == principal.user_id,
        AccountInvitation.claim_token_hash == hashlib.sha256(body.claim_token.encode()).hexdigest()).with_for_update())
    if invite:
        invite.claim_user_id = None
        invite.claim_token_hash = None
        invite.claim_expires_at = None
    db.commit()
    return {"released": invite is not None}


@router.post("/api/account/activate")
def activate_account(principal: Principal = Depends(authenticate_identity), db: Session = Depends(get_db), body: AcceptInvitationInput | None = None):
    if principal.user_id is None or not principal.email:
        raise HTTPException(403, "O convite precisa corresponder ao e-mail autenticado")
    email = _email(principal.email)
    invitation_id = body.invitation_id if body else None
    claim_hash = hashlib.sha256(body.claim_token.encode()).hexdigest() if body else None
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(principal.user_id)})
    existing_member = db.execute(select(AccountMember)
                                  .where(AccountMember.user_id == principal.user_id)).first()
    if existing_member and existing_member[0].status == "active":
        member = existing_member[0]
        payload = _access_payload(member)
        if payload["status"] == "active":
            db.rollback()
            return payload
        if invitation_id is None:
            db.rollback()
            return payload
    elif invitation_id is None:
        db.rollback()
        raise HTTPException(403, "Convite ausente, expirado, revogado ou já utilizado")
    db.rollback()
    _verify_supabase_email(principal, email)

    if db.bind.dialect.name == "postgresql":
        if invitation_id is None:
            raise HTTPException(403, "Convite ausente, expirado, revogado ou já utilizado")
        db.execute(text("SELECT set_config('app.user_id', :user_id, true), set_config('app.user_email', :email, true), set_config('app.invitation_id', :invitation_id, true), set_config('app.claim_user_id', :claim_user_id, true), set_config('app.claim_token_hash', :claim_token_hash, true)"),
                   {"user_id": str(principal.user_id), "email": email, "invitation_id": str(invitation_id),
                    "claim_user_id": str(principal.user_id), "claim_token_hash": claim_hash or ""})
        accepted = db.scalar(text("SELECT public.accept_dashboard_invitation(:user_id, :email)"),
                             {"user_id": principal.user_id, "email": email})
    else:
        now = datetime.now(timezone.utc)
        invite = db.scalar(select(AccountInvitation).where(AccountInvitation.id == invitation_id,
            AccountInvitation.email == email, AccountInvitation.accepted_user_id.is_(None),
            AccountInvitation.revoked_at.is_(None), AccountInvitation.expires_at > now,
            AccountInvitation.claim_user_id == principal.user_id,
            AccountInvitation.claim_token_hash == claim_hash,
            AccountInvitation.claim_expires_at > now,
            (AccountInvitation.target_user_id.is_(None) | (AccountInvitation.target_user_id == principal.user_id))))
        if invite:
            member = db.get(AccountMember, principal.user_id)
            member_expiry = _utc(member.access_expires_at) if member else None
            if member and not (member.status == "revoked" or (member_expiry and member_expiry <= now)):
                db.rollback()
                raise HTTPException(403, "Convite ausente, expirado, revogado ou já utilizado")
            if member and invite.target_user_id != principal.user_id:
                db.rollback()
                raise HTTPException(403, "Convite ausente, expirado, revogado ou já utilizado")
            if not member and invite.target_user_id is not None:
                db.rollback()
                raise HTTPException(403, "Convite ausente, expirado, revogado ou já utilizado")
            invite.accepted_user_id = principal.user_id
            invite.accepted_at = now
            invite.claim_user_id = None
            invite.claim_token_hash = None
            invite.claim_expires_at = None
            access_expires_at = now + timedelta(days=7) if invite.access_duration_days == 7 else None
            if member is None:
                db.add(AccountMember(user_id=principal.user_id, email=invite.email, status="active", created_at=now,
                                     access_expires_at=access_expires_at, activated_at=now))
            else:
                member.email = invite.email
                member.status = "active"
                member.access_expires_at = access_expires_at
                member.activated_at = now
            accepted = True
        else:
            accepted = False
    if accepted:
        member = db.get(AccountMember, principal.user_id)
        db.commit()
        return _access_payload(member)
    db.rollback()
    raise HTTPException(403, "Convite ausente, expirado, revogado ou já utilizado")


@router.get("/api/account/invitations/{invitation_id}/eligibility")
def invitation_eligibility(invitation_id: UUID, principal: Principal = Depends(authenticate_identity), db: Session = Depends(get_db)):
    """Check a single invitation against the verified identity before password changes."""
    if principal.user_id is None or not principal.email:
        raise HTTPException(403, "Convite inválido ou expirado. Solicite um novo ao administrador.")
    email = _email(principal.email)
    _verify_supabase_email(principal, email)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.user_id', :user_id, true), set_config('app.user_email', :email, true)"),
                   {"user_id": str(principal.user_id), "email": email})
    now = datetime.now(timezone.utc)
    invite = db.scalar(select(AccountInvitation).where(AccountInvitation.id == invitation_id,
        AccountInvitation.email == email, AccountInvitation.accepted_user_id.is_(None),
        AccountInvitation.revoked_at.is_(None), AccountInvitation.expires_at > now,
        (AccountInvitation.target_user_id.is_(None) | (AccountInvitation.target_user_id == principal.user_id))))
    member = db.get(AccountMember, principal.user_id)
    eligible = bool(invite and ((member is None and invite.target_user_id is None) or
        (member is not None and invite.target_user_id == principal.user_id and
         (member.status == "revoked" or (member.access_expires_at is not None and member.access_expires_at <= now)))))
    if not eligible:
        db.rollback()
        raise HTTPException(403, "Convite inválido ou expirado. Solicite um novo ao administrador.")
    db.rollback()
    return {"eligible": True}


def _serialize_member(member: AccountMember, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    expiry = _utc(member.access_expires_at)
    return {"user_id": str(member.user_id), "email": member.email, **_access_payload(member, now),
            "can_reactivate": member.status == "revoked" or bool(expiry and expiry <= now)}


@admin_router.get("/members")
def list_members(principal: Principal = Depends(authenticate), db: Session = Depends(get_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(AccountMember).order_by(AccountMember.created_at.desc()))
    return [_serialize_member(member, now) for member in rows]


@admin_router.post("/members/{user_id}/reactivate", status_code=202)
async def reactivate_member(user_id: UUID, principal: Principal = Depends(authenticate), db: Session = Depends(get_db)):
    admin_id = _admin(principal)
    if not settings.supabase_service_role_key.get_secret_value().strip() or not settings.app_public_url:
        raise HTTPException(503, "Reativação não está configurada")
    _admin_context(db, admin_id)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": f"dashboard-invitations:{admin_id}"})
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": f"dashboard-reactivation:{user_id}"})
    member = db.scalar(select(AccountMember).where(AccountMember.user_id == user_id).with_for_update())
    if member is None:
        db.rollback()
        raise HTTPException(404, "Conta não encontrada")
    now = datetime.now(timezone.utc)
    if not _serialize_member(member, now)["can_reactivate"]:
        db.rollback()
        raise HTTPException(409, "A conta ainda possui acesso. Uma nova concessão não é necessária.")
    recent = db.scalar(select(func.count()).select_from(AccountInvitation).where(
        AccountInvitation.invited_by == admin_id, AccountInvitation.created_at >= now - timedelta(days=1))) or 0
    active_pending = db.scalar(select(func.count()).select_from(AccountInvitation).where(
        AccountInvitation.invited_by == admin_id, AccountInvitation.revoked_at.is_(None),
        AccountInvitation.accepted_user_id.is_(None), AccountInvitation.expires_at > now)) or 0
    if recent >= 10 or active_pending >= 10:
        db.rollback()
        raise HTTPException(429, "Limite diário ou de convites pendentes atingido")
    auth_email = _confirmed_auth_email(user_id)
    if member.email and _email(member.email) != auth_email:
        db.rollback()
        raise HTTPException(409, "O e-mail da conta diverge da identidade Auth confirmada")
    existing = db.scalar(select(AccountInvitation.id).where(AccountInvitation.target_user_id == user_id,
        AccountInvitation.accepted_user_id.is_(None), AccountInvitation.revoked_at.is_(None),
        AccountInvitation.expires_at > now).limit(1))
    if existing:
        db.rollback()
        raise HTTPException(409, "Já existe uma reativação pendente para esta conta")
    expired = db.scalars(select(AccountInvitation).where(AccountInvitation.email == auth_email,
        AccountInvitation.accepted_user_id.is_(None), AccountInvitation.revoked_at.is_(None),
        AccountInvitation.expires_at <= now)).all()
    for prior in expired:
        prior.revoked_at = now
    invitation = AccountInvitation(id=uuid4(), email=auth_email, invited_by=admin_id, created_at=now,
        expires_at=now + timedelta(days=7), access_duration_days=7, target_user_id=user_id)
    db.add(invitation)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "A reativação não pôde ser reservada") from None
    try:
        await _send_supabase_recovery(auth_email, invitation.id)
    except (httpx.HTTPError, RuntimeError):
        _admin_context(db, admin_id)
        failed = db.get(AccountInvitation, invitation.id)
        if failed and failed.accepted_user_id is None:
            failed.revoked_at = datetime.now(timezone.utc)
            db.commit()
        else:
            db.rollback()
        raise HTTPException(502, "Não foi possível enviar o link; a reativação foi invalidada") from None
    return {"status": "reactivation_email_sent", "invitation": _serialize(invitation)}


@admin_router.get("/invitations")
def list_invitations(principal: Principal = Depends(authenticate), db: Session = Depends(get_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    rows = db.scalars(select(AccountInvitation).order_by(AccountInvitation.created_at.desc()).limit(100))
    return [_serialize(row) for row in rows]


def _serialize_access_request(row: AccountAccessRequest):
    return {"id": str(row.id), "email": row.email, "requested_at": row.requested_at.isoformat(),
            "status": "pending" if row.status == "approving" else row.status,
            "processing": row.status == "approving"}


@admin_router.get("/access-requests")
def list_access_requests(principal: Principal = Depends(authenticate), db: Session = Depends(get_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    rows = db.scalars(select(AccountAccessRequest).order_by(AccountAccessRequest.requested_at.desc()))
    return [_serialize_access_request(row) for row in rows]


async def _send_supabase_invitation(email: str, invitation_id: UUID) -> None:
    service_key = settings.supabase_service_role_key.get_secret_value().strip()
    if not service_key or not settings.app_public_url:
        raise RuntimeError("invitation_not_configured")
    async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(8, connect=3)) as client:
        response = await client.post(f"{settings.supabase_url}/auth/v1/invite",
            params={"redirect_to": f"{settings.app_public_url}/invite/accept?invitation_id={invitation_id}"},
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}",
                     "Content-Type": "application/json"}, json={"email": email})
    if response.status_code not in (200, 201):
        # Supabase's invite endpoint rejects an email that already has a
        # confirmed Auth identity. For that explicit case only, send a recovery
        # link tied to this same admin-created invitation. This preserves the
        # normal new-user invite path and never turns a public request into access.
        try:
            error_code = response.json().get("code")
        except (ValueError, AttributeError):
            error_code = None
        if error_code not in ("user_already_exists", "email_exists"):
            raise RuntimeError("supabase_invite_failed")
        recovery = await client.post(f"{settings.supabase_url}/auth/v1/recover",
            params={"redirect_to": f"{settings.app_public_url}/invite/accept?invitation_id={invitation_id}"},
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}",
                     "Content-Type": "application/json"}, json={"email": email})
        if recovery.status_code not in (200, 202):
            raise RuntimeError("supabase_invite_failed")


async def _send_supabase_recovery(email: str, invitation_id: UUID) -> None:
    """Send a Supabase recovery email for an already-existing, admin-targeted identity."""
    service_key = settings.supabase_service_role_key.get_secret_value().strip()
    if not service_key or not settings.app_public_url:
        raise RuntimeError("invitation_not_configured")
    async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(8, connect=3)) as client:
        response = await client.post(f"{settings.supabase_url}/auth/v1/recover",
            params={"redirect_to": f"{settings.app_public_url}/invite/accept?invitation_id={invitation_id}"},
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}",
                     "Content-Type": "application/json"}, json={"email": email})
    if response.status_code not in (200, 202):
        raise RuntimeError("supabase_recovery_failed")


def _confirmed_auth_email(user_id: UUID) -> str:
    service_key = settings.supabase_service_role_key.get_secret_value().strip()
    if not service_key:
        raise HTTPException(503, "Reativação não está configurada")
    try:
        with httpx.Client(trust_env=False, timeout=httpx.Timeout(8, connect=3)) as client:
            response = client.get(f"{settings.supabase_url}/auth/v1/admin/users/{user_id}",
                headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"})
        if response.status_code == 404:
            raise HTTPException(409, "A identidade Auth não está disponível para reativação")
        response.raise_for_status()
        body = response.json()
        user = body.get("user", body) if isinstance(body, dict) else None
        if not isinstance(user, dict) or str(user.get("id", "")) != str(user_id) or not user.get("email_confirmed_at"):
            raise HTTPException(409, "A identidade Auth não está confirmada para reativação")
        return _email(user.get("email", ""))
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, "Não foi possível validar a identidade Auth para reativação") from None


@admin_router.post("/access-requests/{request_id}/approve")
async def approve_access_request(request_id: UUID, principal: Principal = Depends(authenticate), db: Session = Depends(get_db)):
    admin_id = _admin(principal)
    if not settings.supabase_service_role_key.get_secret_value().strip() or not settings.app_public_url:
        raise HTTPException(503, "Convites não estão configurados")
    now = datetime.now(timezone.utc)
    _admin_context(db, admin_id)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": f"dashboard-trial-approval:{request_id}"})
    item = db.scalar(select(AccountAccessRequest).where(AccountAccessRequest.id == request_id).with_for_update())
    if item is None:
        db.rollback()
        raise HTTPException(404, "Solicitação não encontrada")
    if item.status != "pending":
        db.rollback()
        raise HTTPException(409, "A solicitação já está sendo processada ou já foi decidida")
    email = item.email
    # Reserve the request and the exact seven-day invitation before sending.
    item.status = "approving"; item.processing_at = now
    expired = db.scalars(select(AccountInvitation).where(AccountInvitation.email == email,
        AccountInvitation.accepted_user_id.is_(None), AccountInvitation.revoked_at.is_(None),
        AccountInvitation.expires_at <= now)).all()
    for previous in expired:
        previous.revoked_at = now
    recent = db.scalar(select(func.count()).select_from(AccountInvitation).where(
        AccountInvitation.invited_by == admin_id, AccountInvitation.created_at >= now - timedelta(days=1))) or 0
    active_pending = db.scalar(select(func.count()).select_from(AccountInvitation).where(
        AccountInvitation.invited_by == admin_id, AccountInvitation.revoked_at.is_(None),
        AccountInvitation.accepted_user_id.is_(None), AccountInvitation.expires_at > now)) or 0
    if recent >= 10 or active_pending >= 10:
        db.rollback()
        raise HTTPException(429, "Limite diário ou de convites pendentes atingido")
    invitation = AccountInvitation(id=uuid4(), email=email, invited_by=admin_id, created_at=now,
        expires_at=now + timedelta(days=7), access_duration_days=7)
    item.invitation_id = invitation.id
    db.add(invitation)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "A solicitação não pôde ser reservada para aprovação") from None
    try:
        await _send_supabase_invitation(email, invitation.id)
    except (httpx.HTTPError, RuntimeError):
        try:
            _admin_context(db, admin_id)
            item = db.get(AccountAccessRequest, request_id)
            invitation = db.get(AccountInvitation, invitation.id)
            if item and item.status == "approving" and item.invitation_id == invitation.id:
                invitation.revoked_at = datetime.now(timezone.utc)
                item.status = "pending"; item.processing_at = None; item.invitation_id = None
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise HTTPException(502, "O convite não foi confirmado pelo Supabase; a solicitação permanece pendente") from None
    _admin_context(db, admin_id)
    item = db.get(AccountAccessRequest, request_id)
    if item is None or item.status != "approving" or item.invitation_id != invitation.id:
        db.rollback()
        raise HTTPException(503, "O convite foi enviado, mas a decisão precisa de reconciliação administrativa")
    item.status = "approved"; item.reviewed_at = datetime.now(timezone.utc); item.reviewed_by = admin_id; item.processing_at = None
    db.commit()
    return {"status": "approved"}


@admin_router.post("/access-requests/{request_id}/reject")
def reject_access_request(request_id: UUID, principal: Principal = Depends(authenticate), db: Session = Depends(get_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": f"dashboard-trial-approval:{request_id}"})
    item = db.scalar(select(AccountAccessRequest).where(AccountAccessRequest.id == request_id).with_for_update())
    if item is None:
        db.rollback()
        raise HTTPException(404, "Solicitação não encontrada")
    if item.status not in ("pending", "approving"):
        db.rollback()
        raise HTTPException(409, "A solicitação já foi decidida")
    if item.status == "approving" and item.invitation_id:
        invitation = db.get(AccountInvitation, item.invitation_id)
        if invitation and invitation.accepted_user_id is None:
            invitation.revoked_at = datetime.now(timezone.utc)
    item.status = "rejected"; item.reviewed_at = datetime.now(timezone.utc); item.reviewed_by = admin_id; item.processing_at = None
    db.commit()
    return {"status": "rejected"}


@admin_router.post("/invitations", status_code=201)
async def create_invitation(body: InvitationInput, principal: Principal = Depends(authenticate), db: Session = Depends(get_db)):
    admin_id = _admin(principal)
    if not settings.supabase_service_role_key.get_secret_value() or not settings.app_public_url:
        raise HTTPException(503, "Convites não estão configurados")
    email = _email(body.email)
    now = datetime.now(timezone.utc)
    _admin_context(db, admin_id)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": f"dashboard-invitations:{admin_id}"})
    expired = db.scalars(select(AccountInvitation).where(AccountInvitation.email == email,
        AccountInvitation.accepted_user_id.is_(None), AccountInvitation.revoked_at.is_(None),
        AccountInvitation.expires_at <= now)).all()
    for previous in expired:
        previous.revoked_at = now
    recent = db.scalar(select(func.count()).select_from(AccountInvitation).where(
        AccountInvitation.invited_by == admin_id,
        AccountInvitation.created_at >= now - timedelta(days=1))) or 0
    active_pending = db.scalar(select(func.count()).select_from(AccountInvitation).where(
        AccountInvitation.invited_by == admin_id, AccountInvitation.revoked_at.is_(None),
        AccountInvitation.accepted_user_id.is_(None), AccountInvitation.expires_at > now)) or 0
    if recent >= 10 or active_pending >= 10:
        raise HTTPException(429, "Limite diário ou de convites pendentes atingido")
    row = AccountInvitation(id=uuid4(), email=email, invited_by=admin_id, created_at=now,
                            expires_at=now + timedelta(days=body.expires_in_days))
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "Já existe convite pendente para esse e-mail") from None
    try:
        await _send_supabase_invitation(email, row.id)
    except (httpx.HTTPError, RuntimeError):
        _admin_context(db, admin_id)
        row.revoked_at = now
        db.commit()
        raise HTTPException(502, "Não foi possível enviar o convite; ele foi invalidado") from None
    return _serialize(row)


@admin_router.delete("/invitations/{invitation_id}")
def revoke_invitation(invitation_id: UUID, principal: Principal = Depends(authenticate), db: Session = Depends(get_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    row = db.scalar(select(AccountInvitation).where(AccountInvitation.id == invitation_id).with_for_update())
    if row is None or row.revoked_at is not None:
        raise HTTPException(404, "Convite não encontrado")
    now = datetime.now(timezone.utc)
    claim_expiry = _utc(row.claim_expires_at)
    if row.claim_token_hash and claim_expiry and claim_expiry > now:
        db.rollback()
        raise HTTPException(409, "Este convite está em processo de ativação; tente revogar novamente após alguns minutos")
    if row.accepted_user_id:
        if db.bind.dialect.name == "postgresql":
            revoked = db.scalar(text("SELECT public.revoke_dashboard_account(:user_id,:admin_id)"),
                                {"user_id": row.accepted_user_id, "admin_id": admin_id})
        else:
            member = db.get(AccountMember, row.accepted_user_id)
            if member:
                member.status = "revoked"
            row.revoked_at = now
            revoked = member is not None
        if not revoked:
            db.rollback()
            raise HTTPException(409, "A conta não pôde ser revogada")
    else:
        row.revoked_at = now
    db.commit()
    return {"status": "revoked"}
