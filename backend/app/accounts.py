"""Invite-only account lifecycle. Admins can manage access, never financial rows."""
from datetime import datetime, timedelta, timezone
import re
import time
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, DateTime, Integer, String, Uuid, func, select, text
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


class AccountInvitation(Base):
    __tablename__ = "account_invitations"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    invited_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


router = APIRouter(tags=["accounts"])
admin_router = APIRouter(prefix="/api/admin", tags=["account-invitations"])


def _admin(principal: Principal):
    if principal.user_id is None or principal.user_id not in settings.invitation_admin_ids:
        raise HTTPException(403, "Ação administrativa não autorizada")
    return principal.user_id


def _email(value: str):
    normalized = value.strip().lower()
    if len(normalized) > 320 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", normalized):
        raise HTTPException(422, "Informe um e-mail válido")
    return normalized


def _admin_context(db: Session, admin_id: UUID):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.admin_id', :admin, true)"), {"admin": str(admin_id)})


def _serialize(row: AccountInvitation):
    return {"id": str(row.id), "email": row.email, "created_at": row.created_at.isoformat(),
            "expires_at": row.expires_at.isoformat(), "accepted": row.accepted_user_id is not None,
            "revoked": row.revoked_at is not None}


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


@router.post("/api/account/activate")
def activate_account(principal: Principal = Depends(authenticate_identity), db: Session = Depends(get_db)):
    if principal.user_id is None or not principal.email:
        raise HTTPException(403, "O convite precisa corresponder ao e-mail autenticado")
    email = _email(principal.email)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(principal.user_id)})
    existing_status = db.scalar(select(AccountMember.status).where(AccountMember.user_id == principal.user_id))
    if existing_status == "active":
        db.rollback()
        return {"status": "active"}
    db.rollback()
    _verify_supabase_email(principal, email)

    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.user_id', :user_id, true), set_config('app.user_email', :email, true)"),
                   {"user_id": str(principal.user_id), "email": email})
        accepted = db.scalar(text("SELECT public.accept_dashboard_invitation(:user_id, :email)"),
                             {"user_id": principal.user_id, "email": email})
    else:
        now = datetime.now(timezone.utc)
        invite = db.scalar(select(AccountInvitation).where(AccountInvitation.email == email,
            AccountInvitation.accepted_user_id.is_(None), AccountInvitation.revoked_at.is_(None), AccountInvitation.expires_at > now))
        if invite:
            invite.accepted_user_id = principal.user_id
            member = db.get(AccountMember, principal.user_id)
            if member is None:
                db.add(AccountMember(user_id=principal.user_id, email=invite.email, status="active", created_at=now))
            else:
                member.email = invite.email
                member.status = "active"
            accepted = True
        else:
            accepted = False
    if accepted:
        db.commit()
        return {"status": "active"}
    db.rollback()
    raise HTTPException(403, "Convite ausente, expirado, revogado ou já utilizado")


@admin_router.get("/invitations")
def list_invitations(principal: Principal = Depends(authenticate), db: Session = Depends(get_db)):
    admin_id = _admin(principal)
    _admin_context(db, admin_id)
    rows = db.scalars(select(AccountInvitation).order_by(AccountInvitation.created_at.desc()).limit(100))
    return [_serialize(row) for row in rows]


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
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(8, connect=3)) as client:
            response = await client.post(f"{settings.supabase_url}/auth/v1/invite",
                params={"redirect_to": f"{settings.app_public_url}/invite/accept"},
                headers={"apikey": settings.supabase_service_role_key.get_secret_value(),
                         "Authorization": f"Bearer {settings.supabase_service_role_key.get_secret_value()}",
                         "Content-Type": "application/json"}, json={"email": email})
        if response.status_code not in (200, 201):
            raise RuntimeError("supabase_invite_failed")
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
    row = db.scalar(select(AccountInvitation).where(AccountInvitation.id == invitation_id))
    if row is None or row.revoked_at is not None:
        raise HTTPException(404, "Convite não encontrado")
    now = datetime.now(timezone.utc)
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
