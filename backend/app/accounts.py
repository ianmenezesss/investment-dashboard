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
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, SmallInteger, String, Uuid, case, cast, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import Principal, authenticate, authenticate_identity
from .database import Base, get_admin_db, get_db, settings
from .supabase_invitations import (InvitationNetworkError, InvitationProviderError,
                                   provider_code as _provider_code, send_invitation, send_recovery)


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


class AccountInvitationSendAttempt(Base):
    __tablename__ = "account_invitation_send_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invitation_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("account_invitations.id", ondelete="CASCADE"), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    http_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    provider_code: Mapped[str | None] = mapped_column(String(40), nullable=True)


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


class AccountAccessAudit(Base):
    __tablename__ = "account_access_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    event_code: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    invitation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    request_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    # ASGI's peer is authoritative. Forwarded headers must be processed only by
    # a server configured with the deployment's trusted proxy IPs, never by a
    # caller-controlled Cloudflare header on a public Render URL.
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
        context = db.execute(text("""SELECT public.dashboard_admin_authorized() AS authorized,
            r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb
              OR has_table_privilege(session_user,'public.operations','SELECT')
              OR has_table_privilege(session_user,'public.account_members','UPDATE') AS unsafe
            FROM pg_roles r WHERE r.rolname=session_user""")).one()
        if not context.authorized or context.unsafe:
            db.rollback()
            raise HTTPException(503, "Revise o login administrativo restrito e o cadastro protegido de administradores")


def _limit(name: str, default: int) -> int:
    return int(getattr(settings, name, default))


def _audit(db: Session, actor_id: UUID, event_code: str, *, subject_user_id: UUID | None = None,
           invitation_id: UUID | None = None, request_id: UUID | None = None):
    db.add(AccountAccessAudit(actor_id=actor_id, event_code=event_code,
        subject_user_id=subject_user_id, invitation_id=invitation_id, request_id=request_id,
        occurred_at=datetime.now(timezone.utc)))


def _lock_invitation_reservation(db: Session, admin_id: UUID, email: str):
    if db.bind.dialect.name == "postgresql":
        # Fixed lock order across all grant paths; serializes both per-admin
        # quotas and same-email requests from different administrators.
        for key in (f"dashboard-invitations:{admin_id}", f"dashboard-invitation-email:{email}"):
            db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": key})


def _reserve_invitation(db: Session, admin_id: UUID, email: str, *, duration: int | None = None,
                        expires_in_days: int = 7) -> AccountInvitation:
    """Reserve an application grant atomically, independent of Auth delivery."""
    _lock_invitation_reservation(db, admin_id, email)
    now = datetime.now(timezone.utc)
    member = db.scalar(select(AccountMember).where(func.lower(AccountMember.email) == email).limit(1))
    if member is not None:
        raise HTTPException(409, "Este e-mail já possui uma conta. Gerencie o acesso na aba Contas.")
    pending = db.scalar(select(AccountInvitation).where(AccountInvitation.email == email,
        AccountInvitation.accepted_user_id.is_(None), AccountInvitation.revoked_at.is_(None),
        AccountInvitation.expires_at > now).limit(1))
    if pending:
        raise HTTPException(409, {"message": "Já existe um convite pendente. Utilize Reenviar na aba Convites.",
                                  "invitation_id": str(pending.id)})
    recent = db.scalar(select(func.count()).select_from(AccountInvitation).where(
        AccountInvitation.invited_by == admin_id, AccountInvitation.created_at >= now - timedelta(days=1))) or 0
    active_pending = db.scalar(select(func.count()).select_from(AccountInvitation).where(
        AccountInvitation.invited_by == admin_id, AccountInvitation.revoked_at.is_(None),
        AccountInvitation.accepted_user_id.is_(None), AccountInvitation.expires_at > now)) or 0
    if recent >= _limit("invitation_daily_limit", 50) or active_pending >= _limit("invitation_pending_limit", 50):
        raise HTTPException(429, "Limite diário ou de convites pendentes atingido")
    for previous in db.scalars(select(AccountInvitation).where(AccountInvitation.email == email,
            AccountInvitation.accepted_user_id.is_(None), AccountInvitation.revoked_at.is_(None),
            AccountInvitation.expires_at <= now)).all():
        previous.revoked_at = now
    row = AccountInvitation(id=uuid4(), email=email, invited_by=admin_id, created_at=now,
                            expires_at=now + timedelta(days=expires_in_days), access_duration_days=duration)
    db.add(row)
    _audit(db, admin_id, "invitation_prepared", invitation_id=row.id)
    return row


def _serialize(row: AccountInvitation):
    return {"id": str(row.id), "email": row.email, "created_at": row.created_at.isoformat(),
            "expires_at": row.expires_at.isoformat(), "accepted": row.accepted_user_id is not None,
            "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
            "access_duration_days": row.access_duration_days,
            "target_user_id": str(row.target_user_id) if row.target_user_id else None,
            "revoked": row.revoked_at is not None}


def _invitation_status(row: AccountInvitation, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if row.accepted_user_id is not None:
        return "accepted"
    if row.revoked_at is not None:
        return "revoked"
    if _utc(row.expires_at) <= now:
        return "expired"
    return "pending"


def _status_filter(status: str, accepted: set[str]):
    if status not in accepted:
        raise HTTPException(422, "Filtro de status inválido")
    return status


def _like_pattern(value: str) -> str:
    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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
         (member.status == "revoked" or (_utc(member.access_expires_at) is not None and _utc(member.access_expires_at) <= now)))))
    if not eligible:
        db.rollback()
        raise HTTPException(403, "Convite inválido ou expirado. Solicite um novo ao administrador.")
    db.rollback()
    return {"eligible": True}


def _serialize_member(member: AccountMember, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    expiry = _utc(member.access_expires_at)
    access = _access_payload(member, now)
    email = member.email
    # Lists read the authorization database only. A legacy missing email remains
    # unknown; resolve Auth identity explicitly during reactivation, not five
    # sequential network calls which could hold every admin list for 40 seconds.
    email_source = "membership" if email else "unavailable"
    admin_identity = member.user_id in settings.invitation_admin_ids
    return {"user_id": str(member.user_id), "email": email,
            "account_label": email or f"Conta · {str(member.user_id)[-8:]}",
            "email_source": email_source, **access,
            "can_reactivate": access["status"] in ("revoked", "expired") and not admin_identity,
            "can_revoke": access["status"] == "active" and not admin_identity,
            "protected_admin": admin_identity}


@admin_router.get("/members")
def list_members(page: int = Query(1, ge=1), page_size: int = Query(5, ge=1, le=50),
                 search: str = Query("", max_length=320), status: str = Query("all"),
                 principal: Principal = Depends(authenticate), db: Session = Depends(get_admin_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    now = datetime.now(timezone.utc)
    _status_filter(status, {"all", "active", "expired", "revoked"})
    state = case((AccountMember.status == "revoked", "revoked"),
                 (AccountMember.access_expires_at.is_not(None) & (AccountMember.access_expires_at <= now), "expired"),
                 else_="active")
    query = select(AccountMember)
    filters = []
    if status != "all":
        filters.append(state == status)
    if search.strip():
        pattern = _like_pattern(search)
        filters.append(or_(AccountMember.email.ilike(pattern, escape="\\"),
                           cast(AccountMember.user_id, String).ilike(pattern, escape="\\")))
    if filters:
        query = query.where(*filters)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(query.order_by(AccountMember.created_at.desc(), AccountMember.user_id.asc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_serialize_member(member, now) for member in rows], "page": page,
            "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size}


@admin_router.post("/members/{user_id}/revoke")
def revoke_member(user_id: UUID, principal: Principal = Depends(authenticate), db: Session = Depends(get_admin_db)):
    admin_id = _admin(principal)
    if user_id == admin_id or user_id in settings.invitation_admin_ids:
        raise HTTPException(403, "A conta administrativa está protegida contra revogação")
    _admin_context(db, admin_id)
    member_query = select(AccountMember).where(AccountMember.user_id == user_id)
    if db.bind.dialect.name != "postgresql":
        member_query = member_query.with_for_update()
    # On PostgreSQL the SECURITY DEFINER function takes the row lock. A runtime
    # SELECT FOR UPDATE itself requires UPDATE privilege on account_members.
    member = db.scalar(member_query)
    if member is None:
        db.rollback()
        raise HTTPException(404, "Conta não encontrada")
    state = _access_payload(member)["status"]
    if state == "revoked":
        db.rollback()
        return {"status": "revoked", "user_id": str(user_id)}
    if state != "active":
        db.rollback()
        raise HTTPException(409, "A conta não está ativa; use a ação correspondente ao estado exibido")
    if db.bind.dialect.name == "postgresql":
        revoked = db.scalar(text("SELECT public.revoke_dashboard_account(:user_id,:admin_id)"),
                            {"user_id": user_id, "admin_id": admin_id})
    else:
        member.status = "revoked"
        now = datetime.now(timezone.utc)
        for invite in db.scalars(select(AccountInvitation).where(or_(
                AccountInvitation.accepted_user_id == user_id, AccountInvitation.target_user_id == user_id),
                AccountInvitation.revoked_at.is_(None))).all():
            invite.revoked_at = now
        revoked = True
        _audit(db, admin_id, "membership_revoked", subject_user_id=user_id)
    if not revoked:
        db.rollback()
        raise HTTPException(409, "A conta não pôde ser revogada")
    db.commit()
    return {"status": "revoked", "user_id": str(user_id)}


@admin_router.post("/members/{user_id}/reactivate", status_code=202)
async def reactivate_member(user_id: UUID, principal: Principal = Depends(authenticate), db: Session = Depends(get_admin_db)):
    admin_id = _admin(principal)
    if user_id in settings.invitation_admin_ids:
        raise HTTPException(403, "A conta administrativa está protegida")
    if not settings.supabase_service_role_key.get_secret_value().strip() or not settings.app_public_url:
        raise HTTPException(503, "Reativação não está configurada")
    # Validate Auth before acquiring transactional database locks. Membership
    # eligibility is rechecked below and again inside the privileged function.
    auth_email = _confirmed_auth_email(user_id)
    _admin_context(db, admin_id)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": f"dashboard-invitations:{admin_id}"})
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": f"dashboard-reactivation:{user_id}"})
    # PostgreSQL locks and rechecks eligibility inside the restricted database
    # function; runtime SELECT FOR UPDATE would require the intentionally absent
    # UPDATE privilege on account_members.
    member_query = select(AccountMember).where(AccountMember.user_id == user_id)
    if db.bind.dialect.name != "postgresql":
        member_query = member_query.with_for_update()
    member = db.scalar(member_query)
    if member is None:
        db.rollback()
        raise HTTPException(404, "Conta não encontrada")
    now = datetime.now(timezone.utc)
    if _access_payload(member, now)["status"] not in ("revoked", "expired"):
        db.rollback()
        raise HTTPException(409, "A conta ainda possui acesso. Uma nova concessão não é necessária.")
    recent = db.scalar(select(func.count()).select_from(AccountInvitation).where(
        AccountInvitation.invited_by == admin_id, AccountInvitation.created_at >= now - timedelta(days=1))) or 0
    active_pending = db.scalar(select(func.count()).select_from(AccountInvitation).where(
        AccountInvitation.invited_by == admin_id, AccountInvitation.revoked_at.is_(None),
        AccountInvitation.accepted_user_id.is_(None), AccountInvitation.expires_at > now)) or 0
    if recent >= _limit("invitation_daily_limit", 50) or active_pending >= _limit("invitation_pending_limit", 50):
        db.rollback()
        raise HTTPException(429, "Limite diário ou de convites pendentes atingido")
    if member.email and _email(member.email) != auth_email:
        db.rollback()
        raise HTTPException(409, "O e-mail da conta diverge da identidade Auth confirmada")
    existing = db.scalar(select(AccountInvitation.id).where(AccountInvitation.target_user_id == user_id,
        AccountInvitation.accepted_user_id.is_(None), AccountInvitation.revoked_at.is_(None),
        AccountInvitation.expires_at > now).limit(1))
    if existing:
        db.rollback()
        raise HTTPException(409, "Já existe uma reativação pendente para esta conta")
    invitation = AccountInvitation(id=uuid4(), email=auth_email, invited_by=admin_id, created_at=now,
        expires_at=now + timedelta(days=7), access_duration_days=7, target_user_id=user_id)
    try:
        if db.bind.dialect.name == "postgresql":
            reserved = db.scalar(text("SELECT public.reserve_dashboard_reactivation(:user_id,:admin_id,:invitation_id,:email)"),
                {"user_id": user_id, "admin_id": admin_id, "invitation_id": invitation.id, "email": auth_email})
            if not reserved:
                db.rollback()
                raise HTTPException(409, "A reativação não pôde ser reservada; atualize a situação da conta e tente novamente")
        else:
            expired = db.scalars(select(AccountInvitation).where(AccountInvitation.email == auth_email,
                AccountInvitation.accepted_user_id.is_(None), AccountInvitation.revoked_at.is_(None),
                AccountInvitation.expires_at <= now)).all()
            for prior in expired:
                prior.revoked_at = now
            db.add(invitation)
            _audit(db, admin_id, "reactivation_prepared", subject_user_id=user_id, invitation_id=invitation.id)
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(409, "A reativação não pôde ser reservada") from None
    result = await _attempt_invitation_send(db, admin_id, invitation.id, method="recovery")
    _admin_context(db, admin_id)
    refreshed = db.get(AccountInvitation, invitation.id)
    return {**result, "status": "reactivation_email_requested", "email_send_status": result["status"], "delivery_confirmed": False,
            "invitation": _serialize(refreshed) if refreshed else _serialize(invitation)}


@admin_router.get("/invitations")
def list_invitations(page: int = Query(1, ge=1), page_size: int = Query(5, ge=1, le=50),
                     search: str = Query("", max_length=320), status: str = Query("all"),
                     principal: Principal = Depends(authenticate), db: Session = Depends(get_admin_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    _status_filter(status, {"all", "pending", "accepted", "expired", "revoked"})
    now = datetime.now(timezone.utc)
    state = case((AccountInvitation.accepted_user_id.is_not(None), "accepted"),
                 (AccountInvitation.revoked_at.is_not(None), "revoked"),
                 (AccountInvitation.expires_at <= now, "expired"), else_="pending")
    query = select(AccountInvitation)
    filters = []
    if status != "all":
        filters.append(state == status)
    if search.strip():
        filters.append(AccountInvitation.email.ilike(_like_pattern(search), escape="\\"))
    if filters:
        query = query.where(*filters)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(query.order_by(AccountInvitation.created_at.desc(), AccountInvitation.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    ids = [row.id for row in rows]
    attempts = db.scalars(select(AccountInvitationSendAttempt).where(AccountInvitationSendAttempt.invitation_id.in_(ids))
                          .order_by(AccountInvitationSendAttempt.attempted_at.desc(), AccountInvitationSendAttempt.id.desc())).all() if ids else []
    history: dict[UUID, list[AccountInvitationSendAttempt]] = {}
    for attempt in attempts:
        group = history.setdefault(attempt.invitation_id, [])
        group.append(attempt)
    items = []
    for row in rows:
        event_list = history.get(row.id, [])
        item = _serialize(row)
        latest_outcome = _send_state(event_list[0], now) if event_list else "not_requested"
        count = sum(1 for event in attempts if event.invitation_id == row.id)
        remaining = (max(0, int((_utc(event_list[0].attempted_at) + timedelta(
            seconds=_limit("invitation_send_cooldown_seconds", 60)) - now).total_seconds()))
                     if event_list else 0)
        claim_active = bool(row.claim_token_hash and _utc(row.claim_expires_at) and _utc(row.claim_expires_at) > now)
        item.update({"status": _invitation_status(row, now), "email_send_status": latest_outcome,
                     "email_send_attempts": count,
                     "max_send_attempts": _limit("invitation_max_send_attempts", 5),
                     "retry_after_seconds": remaining,
                     "can_resend": _invitation_status(row, now) == "pending" and not claim_active
                                   and count < _limit("invitation_max_send_attempts", 5)
                                   and remaining == 0 and latest_outcome != "started",
                     "delivery_confirmed": False,
                     "send_history": [{"attempted_at": event.attempted_at.isoformat(),
                                       "outcome": "uncertain" if event.outcome == "started" and _utc(event.attempted_at) <= now - timedelta(minutes=5) else event.outcome,
                                       "method": event.method, "http_status": event.http_status,
                                       "provider_code": event.provider_code} for event in event_list]})
        items.append(item)
    return {"items": items, "page": page, "page_size": page_size,
            "total": total, "total_pages": (total + page_size - 1) // page_size}


def _serialize_access_request(row: AccountAccessRequest):
    return {"id": str(row.id), "email": row.email, "requested_at": row.requested_at.isoformat(),
            "status": "pending" if row.status == "approving" else row.status,
            "processing": row.status == "approving",
            "invitation_id": str(row.invitation_id) if row.invitation_id else None,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None}


@admin_router.get("/access-requests")
def list_access_requests(page: int = Query(1, ge=1), page_size: int = Query(5, ge=1, le=50),
                         search: str = Query("", max_length=320), status: str = Query("all"),
                         principal: Principal = Depends(authenticate), db: Session = Depends(get_admin_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    _status_filter(status, {"all", "pending", "approved", "rejected"})
    query = select(AccountAccessRequest)
    filters = []
    if status == "pending":
        filters.append(AccountAccessRequest.status.in_(("pending", "approving")))
    elif status != "all":
        filters.append(AccountAccessRequest.status == status)
    if search.strip():
        filters.append(AccountAccessRequest.email.ilike(_like_pattern(search), escape="\\"))
    if filters:
        query = query.where(*filters)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(query.order_by(AccountAccessRequest.requested_at.desc(), AccountAccessRequest.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    invitation_ids = [row.invitation_id for row in rows if row.invitation_id]
    attempts = db.scalars(select(AccountInvitationSendAttempt).where(
        AccountInvitationSendAttempt.invitation_id.in_(invitation_ids)).order_by(
            AccountInvitationSendAttempt.attempted_at.desc(), AccountInvitationSendAttempt.id.desc())).all() if invitation_ids else []
    latest = {}
    for attempt in attempts:
        latest.setdefault(attempt.invitation_id, _send_state(attempt))
    return {"items": [{**_serialize_access_request(row),
                       "email_send_status": latest.get(row.invitation_id, "not_requested"),
                       "delivery_confirmed": False} for row in rows], "page": page,
            "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size}


async def _send_supabase_invitation(email: str, invitation_id: UUID) -> tuple[str, int]:
    return await send_invitation(settings, email, invitation_id)


async def _send_supabase_recovery(email: str, invitation_id: UUID) -> int:
    return await send_recovery(settings, email, invitation_id)


def _attempt_history(db: Session, invitation_id: UUID):
    return db.scalars(select(AccountInvitationSendAttempt).where(
        AccountInvitationSendAttempt.invitation_id == invitation_id).order_by(
            AccountInvitationSendAttempt.attempted_at.desc(), AccountInvitationSendAttempt.id.desc())).all()


def _send_state(attempt: AccountInvitationSendAttempt, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if attempt.outcome == "started" and _utc(attempt.attempted_at) <= now - timedelta(minutes=5):
        return "uncertain"
    return attempt.outcome


def _send_failure(invitation_id: UUID, outcome: str, code: str | None, *, status_code: int = 502,
                  retry_after: int = 0) -> HTTPException:
    return HTTPException(status_code, {
        "message": "O convite foi preservado. O Supabase não confirmou o envio; consulte o histórico na aba Convites antes de reenviar.",
        "invitation_id": str(invitation_id), "email_send_status": outcome,
        "provider_code": code, "delivery_confirmed": False,
        "retryable": code not in ("attempt_limit", "not_configured", "email_address_not_authorized",
                                  "email_provider_disabled", "email_address_invalid", "validation_failed"),
        "retry_after_seconds": retry_after,
    }, headers={"Retry-After": str(retry_after)} if retry_after else None)


async def _attempt_invitation_send(db: Session, admin_id: UUID, invitation_id: UUID,
                                  method: str = "invite") -> dict:
    """Durable dispatch ledger; no automatic retries across the provider boundary."""
    if method not in ("invite", "recovery"):
        raise HTTPException(400, "Tipo de envio inválido")
    _admin_context(db, admin_id)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('dashboard-auth-email-send-project',0))"))
    row = db.scalar(select(AccountInvitation).where(AccountInvitation.id == invitation_id).with_for_update())
    now = datetime.now(timezone.utc)
    if row is None or _invitation_status(row, now) != "pending":
        db.rollback()
        raise HTTPException(409, "O convite não está mais pendente")
    claim_expires = _utc(row.claim_expires_at)
    if row.claim_token_hash and claim_expires and claim_expires > now:
        db.rollback()
        raise HTTPException(409, "O convite está em processo de ativação")
    history = _attempt_history(db, invitation_id)
    max_attempts = _limit("invitation_max_send_attempts", 5)
    cooldown = _limit("invitation_send_cooldown_seconds", 60)
    if len(history) >= max_attempts:
        state = _send_state(history[0])
        db.rollback()
        raise _send_failure(invitation_id, state, "attempt_limit", status_code=429)
    if history:
        last = history[0]
        last_at = _utc(last.attempted_at)
        if last.outcome == "started" and last_at > now - timedelta(minutes=5):
            db.rollback()
            raise HTTPException(409, "Já existe um envio em processamento")
        if last_at > now - timedelta(seconds=cooldown):
            state = _send_state(last)
            db.rollback()
            raise _send_failure(invitation_id, state, "cooldown", status_code=429,
                                retry_after=max(1, int((last_at + timedelta(seconds=cooldown) - now).total_seconds())))
        if last.outcome == "started":
            last.outcome = "uncertain"
            last.provider_code = "worker_interrupted"
    hourly = db.scalar(select(func.count()).select_from(AccountInvitationSendAttempt).where(
        AccountInvitationSendAttempt.attempted_at >= now - timedelta(hours=1))) or 0
    if hourly >= _limit("invitation_emails_per_hour", 2):
        db.rollback()
        raise _send_failure(invitation_id, "not_requested", "project_email_limit", status_code=429, retry_after=3600)
    email = row.email
    attempt = AccountInvitationSendAttempt(invitation_id=invitation_id, requested_by=admin_id,
        attempted_at=now, outcome="started", method=method)
    db.add(attempt)
    _audit(db, admin_id, "email_dispatch_started", invitation_id=invitation_id)
    db.flush()
    attempt_id = attempt.id
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "O envio não foi iniciado porque a tentativa não pôde ser registrada") from None
    retry_after = 0
    try:
        if method == "recovery":
            provider_status = await _send_supabase_recovery(email, invitation_id)
            actual_method = "recovery"
        else:
            actual_method, provider_status = await _send_supabase_invitation(email, invitation_id)
        outcome, error_code = "requested", None
    except InvitationProviderError as error:
        provider_status, error_code, outcome, actual_method = error.http_status, error.provider_code, "failed", error.method
        retry_after = error.retry_after
    except InvitationNetworkError as error:
        provider_status, error_code, outcome, actual_method = None, "network_or_timeout", "uncertain", error.method
    except httpx.HTTPError:
        provider_status, error_code, outcome, actual_method = None, "network_or_timeout", "uncertain", method
    except RuntimeError:
        provider_status, error_code, outcome, actual_method = None, "not_configured", "failed", method
    try:
        _admin_context(db, admin_id)
        saved_attempt = db.get(AccountInvitationSendAttempt, attempt_id)
        if saved_attempt is None:
            raise SQLAlchemyError("missing_dispatch_attempt")
        saved_attempt.outcome = outcome
        saved_attempt.method = actual_method
        saved_attempt.http_status = provider_status
        saved_attempt.provider_code = error_code
        _audit(db, admin_id, "email_dispatch_" + outcome, invitation_id=invitation_id)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise _send_failure(invitation_id, "uncertain", "audit_unavailable", status_code=503) from None
    if outcome != "requested":
        raise _send_failure(invitation_id, outcome, error_code,
                            status_code=429 if provider_status == 429 else 502, retry_after=retry_after)
    return {"status": "requested", "method": actual_method, "http_status": provider_status,
            "delivery_confirmed": False}


@admin_router.get("/access-configuration")
def access_configuration(principal: Principal = Depends(authenticate)):
    _admin(principal)
    return {"app_public_url": settings.app_public_url,
            "smtp_mode": getattr(settings, "invitation_smtp_mode", "builtin"),
            "emails_per_hour": _limit("invitation_emails_per_hour", 2),
            "max_send_attempts": _limit("invitation_max_send_attempts", 5),
            "cooldown_seconds": _limit("invitation_send_cooldown_seconds", 60),
            "delivery_confirmation_available": False}


@admin_router.get("/access-history")
def access_history(page: int = Query(1, ge=1), page_size: int = Query(5, ge=1, le=50),
                   invitation_id: UUID | None = None, request_id: UUID | None = None,
                   subject_user_id: UUID | None = None,
                   principal: Principal = Depends(authenticate), db: Session = Depends(get_admin_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    query = select(AccountAccessAudit)
    for column, value in ((AccountAccessAudit.invitation_id, invitation_id),
                           (AccountAccessAudit.request_id, request_id),
                           (AccountAccessAudit.subject_user_id, subject_user_id)):
        if value is not None:
            query = query.where(column == value)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(AccountAccessAudit.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"id": row.id, "actor_id": str(row.actor_id), "event_code": row.event_code,
                       "subject_user_id": str(row.subject_user_id) if row.subject_user_id else None,
                       "invitation_id": str(row.invitation_id) if row.invitation_id else None,
                       "request_id": str(row.request_id) if row.request_id else None,
                       "occurred_at": row.occurred_at.isoformat()} for row in rows],
            "page": page, "page_size": page_size, "total": total,
            "total_pages": (total + page_size - 1) // page_size}


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
async def approve_access_request(request_id: UUID, principal: Principal = Depends(authenticate), db: Session = Depends(get_admin_db)):
    admin_id = _admin(principal)
    if not settings.supabase_service_role_key.get_secret_value().strip() or not settings.app_public_url:
        raise HTTPException(503, "Convites não estão configurados")
    _admin_context(db, admin_id)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": f"dashboard-trial-approval:{request_id}"})
    item = db.scalar(select(AccountAccessRequest).where(AccountAccessRequest.id == request_id).with_for_update())
    if item is None:
        raise HTTPException(404, "Solicitação não encontrada")
    if item.status == "approved" and item.invitation_id:
        # Repeated approval is read-only and must not duplicate the provider side effect.
        history = _attempt_history(db, item.invitation_id)
        result = {"status": "approved", "invitation_id": str(item.invitation_id),
                  "email_send_status": _send_state(history[0]) if history else "not_requested",
                  "delivery_confirmed": False}
        db.rollback()
        return result
    if item.status != "pending":
        raise HTTPException(409, "A solicitação já foi decidida")
    try:
        invitation = _reserve_invitation(db, admin_id, item.email, duration=7)
        item.status = "approved"
        item.reviewed_at = datetime.now(timezone.utc)
        item.reviewed_by = admin_id
        item.processing_at = None
        item.invitation_id = invitation.id
        invitation_id = invitation.id
        _audit(db, admin_id, "request_approved", invitation_id=invitation_id, request_id=request_id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(409, "A aprovação não pôde ser registrada; atualize a listagem") from None
    # Delivery is a separate durable operation. Its failure NEVER rolls back or
    # revokes an already committed administrative grant.
    result = await _attempt_invitation_send(db, admin_id, invitation_id)
    return {"status": "approved", "invitation_id": str(invitation_id),
            "email_send_status": result["status"], "delivery_confirmed": False}


@admin_router.post("/access-requests/{request_id}/reject")
def reject_access_request(request_id: UUID, principal: Principal = Depends(authenticate), db: Session = Depends(get_admin_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": f"dashboard-trial-approval:{request_id}"})
    item = db.scalar(select(AccountAccessRequest).where(AccountAccessRequest.id == request_id).with_for_update())
    if item is None:
        db.rollback()
        raise HTTPException(404, "Solicitação não encontrada")
    if item.status == "rejected":
        db.rollback()
        return {"status": "rejected"}
    if item.status not in ("pending", "approving"):
        db.rollback()
        raise HTTPException(409, "A solicitação já foi decidida")
    if item.status == "approving" and item.invitation_id:
        invitation = db.get(AccountInvitation, item.invitation_id)
        if invitation and invitation.accepted_user_id is None:
            invitation.revoked_at = datetime.now(timezone.utc)
    _audit(db, admin_id, "request_rejected", request_id=request_id, invitation_id=item.invitation_id)
    item.status = "rejected"; item.reviewed_at = datetime.now(timezone.utc); item.reviewed_by = admin_id; item.processing_at = None
    db.commit()
    return {"status": "rejected"}


@admin_router.post("/invitations", status_code=201)
async def create_invitation(body: InvitationInput, principal: Principal = Depends(authenticate), db: Session = Depends(get_admin_db)):
    admin_id = _admin(principal)
    if not settings.supabase_service_role_key.get_secret_value() or not settings.app_public_url:
        raise HTTPException(503, "Convites não estão configurados")
    email = _email(body.email)
    _admin_context(db, admin_id)
    try:
        row = _reserve_invitation(db, admin_id, email, expires_in_days=body.expires_in_days)
        invitation_id = row.id
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(409, "O convite não pôde ser registrado; atualize a listagem") from None
    result = await _attempt_invitation_send(db, admin_id, invitation_id)
    _admin_context(db, admin_id)
    refreshed = db.get(AccountInvitation, invitation_id)
    return {**_serialize(refreshed), **result, "delivery_confirmed": False}


@admin_router.post("/invitations/{invitation_id}/resend")
async def resend_invitation(invitation_id: UUID, principal: Principal = Depends(authenticate), db: Session = Depends(get_admin_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    row = db.get(AccountInvitation, invitation_id)
    if row is None:
        raise HTTPException(404, "Convite não encontrado")
    method = "recovery" if row.target_user_id is not None else "invite"
    result = await _attempt_invitation_send(db, admin_id, invitation_id, method=method)
    _admin_context(db, admin_id)
    refreshed = db.get(AccountInvitation, invitation_id)
    return {"status": "requested", "delivery_confirmed": False,
            "invitation": _serialize(refreshed) if refreshed else None, **result}


@admin_router.delete("/invitations/{invitation_id}")
def revoke_invitation(invitation_id: UUID, principal: Principal = Depends(authenticate), db: Session = Depends(get_admin_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    row = db.scalar(select(AccountInvitation).where(AccountInvitation.id == invitation_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Convite não encontrado")
    if row.revoked_at is not None:
        db.rollback()
        return {"status": "invitation_revoked"}
    now = datetime.now(timezone.utc)
    claim_expiry = _utc(row.claim_expires_at)
    if row.claim_token_hash and claim_expiry and claim_expiry > now:
        db.rollback()
        raise HTTPException(409, "Este convite está em processo de ativação; tente revogar novamente após alguns minutos")
    if row.accepted_user_id is not None:
        db.rollback()
        raise HTTPException(409, "Este convite já foi aceito; revogue o acesso na aba Contas")
    row.revoked_at = now
    _audit(db, admin_id, "invitation_revoked", invitation_id=invitation_id)
    db.commit()
    return {"status": "invitation_revoked"}
