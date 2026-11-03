"""Production-shaped Auth contracts and durable application grant transitions."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import SQLAlchemyError

from app import accounts, supabase_invitations
from app.auth import Principal
from app.database import Base, Settings

ADMIN = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def config(monkeypatch):
    config = SimpleNamespace(auth_mode="local", environment="test", invitation_admin_ids=[ADMIN],
        supabase_service_role_key=SecretStr("fictional-contract-key"),
        supabase_url="https://auth.example.test", app_public_url="https://private.example.test",
        cors_origin="https://private.example.test", invitation_emails_per_hour=30,
        invitation_max_send_attempts=5, invitation_send_cooldown_seconds=60)
    monkeypatch.setattr(accounts, "settings", config)
    return config


def install_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(supabase_invitations.httpx, "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


@pytest.mark.parametrize("existing", [False, True])
def test_provider_contract_binds_new_and_existing_identity_to_same_private_callback(monkeypatch, config, existing):
    requests = []
    invitation_id = uuid4()
    def provider(request):
        requests.append(request)
        assert request.url.params["redirect_to"] == f"https://private.example.test/invite/accept?invitation_id={invitation_id}"
        assert request.headers["authorization"] == "Bearer fictional-contract-key"
        assert request.content == b'{"email":"person@example.test"}'
        if existing and request.url.path.endswith("/invite"):
            return httpx.Response(422, json={"code": "email_exists", "msg": "Identity exists"})
        return httpx.Response(200, json={"id": str(USER)})
    install_transport(monkeypatch, provider)
    result = asyncio.run(supabase_invitations.send_invitation(config, "person@example.test", invitation_id))
    assert result == ("recovery" if existing else "invite", 200)
    assert [r.url.path for r in requests] == (["/auth/v1/invite", "/auth/v1/recover"] if existing else ["/auth/v1/invite"])


@pytest.mark.parametrize("failure", ["unauthorized_email", "timeout", "server_error"])
def test_approval_is_durable_when_provider_rejects_or_outcome_is_unknown(monkeypatch, db_engine, config, failure):
    request_id = uuid4()
    with Session(db_engine) as db:
        db.add(accounts.AccountAccessRequest(id=request_id, email="person@example.test", ip_hash="a" * 64,
               status="pending", requested_at=datetime.now(timezone.utc)))
        db.commit()
    calls = []
    def provider(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("fictional secret must not be persisted", request=request)
        if failure == "server_error":
            return httpx.Response(502, text="gateway")
        return httpx.Response(400, json={"code": "email_address_not_authorized", "msg": "private provider body"})
    install_transport(monkeypatch, provider)
    with Session(db_engine) as db, pytest.raises(HTTPException) as error:
        asyncio.run(accounts.approve_access_request(request_id, Principal(ADMIN), db))
    assert error.value.status_code == 502
    assert error.value.detail["delivery_confirmed"] is False
    with Session(db_engine) as db:
        item = db.get(accounts.AccountAccessRequest, request_id)
        invite = db.get(accounts.AccountInvitation, item.invitation_id)
        attempt = db.scalar(select(accounts.AccountInvitationSendAttempt))
        assert item.status == "approved" and item.reviewed_by == ADMIN
        assert invite.revoked_at is None and invite.accepted_user_id is None
        assert db.get(accounts.AccountMember, USER) is None
        assert attempt.outcome == ("failed" if failure == "unauthorized_email" else "uncertain")
        # Approval retries acknowledge the same recorded grant without sending again.
        repeated = asyncio.run(accounts.approve_access_request(request_id, Principal(ADMIN), db))
        assert repeated["invitation_id"] == str(invite.id)
        assert len(calls) == 1
        assert "private provider body" not in str(error.value.detail)


def test_public_request_approval_activation_and_trial_preserve_observation_time(monkeypatch, db_engine, config):
    request_id = uuid4()
    now = datetime.now(timezone.utc)
    install_transport(monkeypatch, lambda request: httpx.Response(200, json={"id": str(USER)}))
    with Session(db_engine) as db:
        db.add(accounts.AccountAccessRequest(id=request_id, email="person@example.test", ip_hash="b" * 64,
               status="pending", requested_at=now - timedelta(days=3)))
        db.commit()
        approved = asyncio.run(accounts.approve_access_request(request_id, Principal(ADMIN), db))
        assert approved["status"] == "approved" and approved["delivery_confirmed"] is False
        invitation_id = UUID(approved["invitation_id"])
        assert db.get(accounts.AccountMember, USER) is None
        claim = accounts.claim_invitation(invitation_id, Principal(USER, "person@example.test"), db)
        payload = accounts.AcceptInvitationInput(invitation_id=invitation_id, claim_token=claim["claim_token"])
        active = accounts.activate_account(Principal(USER, "person@example.test"), db, payload)
        activated = datetime.fromisoformat(active["activated_at"])
        expiry = datetime.fromisoformat(active["trial_expires_at"])
        assert activated >= now and expiry - activated == timedelta(days=7)
        repeated = accounts.activate_account(Principal(USER, "person@example.test"), db, payload)
        assert repeated == active
        # The same transition is recorded once even when approval is submitted twice.
        assert list(db.scalars(select(accounts.AccountAccessAudit.event_code))).count("request_approved") == 1


def test_custom_smtp_limit_can_be_raised_but_builtin_quota_is_not_bypassed():
    base = dict(_env_file=None, database_url="sqlite://", api_token="test-token")
    with pytest.raises(ValidationError, match="SMTP"):
        Settings(**base, invitation_emails_per_hour=30)
    assert Settings(**base, invitation_smtp_mode="custom", invitation_emails_per_hour=30).invitation_emails_per_hour == 30


def test_provider_rate_limit_is_audited_without_retry_and_returns_retry_after(monkeypatch, db_engine, config):
    calls = []
    def provider(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "180"}, json={"code": "over_email_send_rate_limit"})
    install_transport(monkeypatch, provider)
    with Session(db_engine) as db, pytest.raises(HTTPException) as error:
        asyncio.run(accounts.create_invitation(accounts.InvitationInput(email="person@example.test"), Principal(ADMIN), db))
    assert len(calls) == 1 and error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "180"
    assert error.value.detail["provider_code"] == "over_email_send_rate_limit"
    with Session(db_engine) as db:
        assert db.scalar(select(accounts.AccountInvitation)).revoked_at is None
        assert db.scalar(select(accounts.AccountInvitationSendAttempt)).outcome == "failed"


def test_admin_database_credential_cannot_alias_runtime_or_another_database():
    base = dict(_env_file=None, database_url="postgresql+psycopg://runtime:synthetic@db.example.test/investment", api_token="test-token")
    with pytest.raises(ValidationError, match="login distinto"):
        Settings(**base, admin_database_url="postgresql+psycopg://runtime:synthetic@db.example.test/investment")
    with pytest.raises(ValidationError, match="mesmo banco"):
        Settings(**base, admin_database_url="postgresql+psycopg://access:synthetic@another.example.test/investment")
    config = Settings(**base, admin_database_url="postgresql+psycopg://access:synthetic@db.example.test/investment")
    assert config.admin_database_url.get_secret_value()


def test_lost_database_audit_after_provider_acceptance_preserves_pending_grant(monkeypatch, db_engine, config):
    calls = []
    def provider(request):
        calls.append(request)
        return httpx.Response(200, json={"id": str(USER)})
    install_transport(monkeypatch, provider)
    with Session(db_engine) as db:
        commit = db.commit
        commits = 0
        def interrupted_commit():
            nonlocal commits
            commits += 1
            if commits == 3:
                raise SQLAlchemyError("synthetic lost audit transaction")
            return commit()
        monkeypatch.setattr(db, "commit", interrupted_commit)
        with pytest.raises(HTTPException) as error:
            asyncio.run(accounts.create_invitation(accounts.InvitationInput(email="person@example.test"), Principal(ADMIN), db))
        assert error.value.status_code == 503
        assert error.value.detail["email_send_status"] == "uncertain"
        assert error.value.detail["provider_code"] == "audit_unavailable"
    with Session(db_engine) as db:
        invitation = db.scalar(select(accounts.AccountInvitation))
        attempt = db.scalar(select(accounts.AccountInvitationSendAttempt))
        assert invitation.revoked_at is None and attempt.outcome == "started"
        assert error.value.detail["invitation_id"] == str(invitation.id)
        assert len(calls) == 1


def test_reservation_of_same_email_is_explicit_and_does_not_create_second_grant(monkeypatch, db_engine, config):
    install_transport(monkeypatch, lambda request: httpx.Response(200, json={"id": str(USER)}))
    with Session(db_engine) as db:
        first = asyncio.run(accounts.create_invitation(accounts.InvitationInput(email="person@example.test"), Principal(ADMIN), db))
        with pytest.raises(HTTPException) as duplicate:
            asyncio.run(accounts.create_invitation(accounts.InvitationInput(email="PERSON@example.test"), Principal(ADMIN), db))
        assert duplicate.value.status_code == 409
        assert duplicate.value.detail["invitation_id"] == first["id"]
        assert len(list(db.scalars(select(accounts.AccountInvitation)))) == 1


def test_http_lifecycle_request_admin_decision_activation_revocation_reactivation_and_expiry(monkeypatch, config):
    """Real FastAPI routes/transactions with synthetic identity and provider boundaries."""
    from fastapi import Request
    from fastapi.testclient import TestClient
    from app import auth, database
    from app.database import get_db
    from app.main import app

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    monkeypatch.setattr(database, "SessionLocal", sessions)
    monkeypatch.setattr(accounts, "_confirmed_auth_email", lambda user_id: "person@example.test")
    calls = []
    def provider(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"id": str(USER)})
    install_transport(monkeypatch, provider)
    now = datetime.now(timezone.utc)
    with sessions() as db:
        db.add(accounts.AccountMember(user_id=ADMIN, email="admin@example.test", status="active", created_at=now))
        db.commit()

    def identity(request: Request):
        return Principal(ADMIN, "admin@example.test") if request.headers.get("authorization") == "Bearer admin" else Principal(USER, "person@example.test")
    def active_identity(request: Request):
        return auth.require_active_account(identity(request))
    def request_db():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = request_db
    app.dependency_overrides[auth.authenticate] = active_identity
    app.dependency_overrides[auth.authenticate_identity] = identity
    admin = {"Authorization": "Bearer admin"}
    person = {"Authorization": "Bearer person"}
    try:
        with TestClient(app, client=("198.51.100.40", 1234)) as client:
            assert client.post("/api/access-requests", json={"email": "person@example.test"}).status_code == 202
            requests = client.get("/api/admin/access-requests", headers=admin).json()
            assert requests["total"] == 1 and requests["items"][0]["status"] == "pending"
            assert client.get("/api/operations", headers=person).status_code == 403
            request_id = requests["items"][0]["id"]
            approved = client.post(f"/api/admin/access-requests/{request_id}/approve", headers=admin)
            assert approved.status_code == 200
            assert calls == ["/auth/v1/invite"]

            def activate(invitation_id):
                claim = client.post(f"/api/account/invitations/{invitation_id}/claim", headers=person)
                assert claim.status_code == 200
                response = client.post("/api/account/activate", headers=person,
                    json={"invitation_id": invitation_id, "claim_token": claim.json()["claim_token"]})
                assert response.status_code == 200 and response.json()["status"] == "active"
                return response.json()

            first = activate(approved.json()["invitation_id"])
            assert first["access_type"] == "trial"
            assert client.get("/api/operations", headers=person).status_code == 200
            assert client.post(f"/api/admin/members/{USER}/revoke", headers=admin).status_code == 200
            assert client.post(f"/api/admin/members/{USER}/revoke", headers=admin).status_code == 200
            assert client.get("/api/operations", headers=person).status_code == 403
            renewed = client.post(f"/api/admin/members/{USER}/reactivate", headers=admin)
            assert renewed.status_code == 202
            assert renewed.json()["email_send_status"] == "requested" and calls[-1] == "/auth/v1/recover"
            second = activate(renewed.json()["invitation"]["id"])
            assert datetime.fromisoformat(second["activated_at"]) >= datetime.fromisoformat(first["activated_at"])
            with sessions() as db:
                db.get(accounts.AccountMember, USER).access_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                db.commit()
            assert client.get("/api/operations", headers=person).status_code == 403
            history = client.get("/api/admin/access-history", headers=admin).json()
            assert history["total"] >= 6
            assert client.post(f"/api/admin/members/{ADMIN}/revoke", headers=admin).status_code == 403
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
