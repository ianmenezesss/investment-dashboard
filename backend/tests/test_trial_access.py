from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import accounts, auth
from app.auth import Principal
from app.database import Base

ADMIN = uuid4()
USER = uuid4()


def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def request(ip="203.0.113.8"):
    from starlette.requests import Request
    return Request({"type": "http", "method": "POST", "path": "/api/access-requests", "headers": [],
                    "client": (ip, 4321), "server": ("testserver", 80), "scheme": "http"})


def run_immediate(coroutine):
    """Drive the mocked async invite sender without opening a network event loop."""
    try:
        coroutine.send(None)
    except StopIteration as complete:
        return complete.value
    raise AssertionError("the mocked coroutine unexpectedly yielded")


def access_settings(monkeypatch, **overrides):
    values = dict(environment="test", supabase_service_role_key=SecretStr("fictional-hmac-key"),
                  api_token=SecretStr("fictional-api-token"), auth_mode="local",
                  invitation_admin_ids=frozenset({ADMIN}), app_public_url="https://dashboard.example.test")
    values.update(overrides)
    monkeypatch.setattr(accounts, "settings", SimpleNamespace(**values))


def test_public_request_normalizes_email_hides_duplicates_and_limits_ip(monkeypatch):
    access_settings(monkeypatch)
    engine = database()
    with Session(engine) as db:
        expected = accounts.submit_access_request(accounts.AccessRequestInput(email="  Person@Example.Test "), request(), db)
        assert expected == accounts.access_request_response
        accounts.submit_access_request(accounts.AccessRequestInput(email="person@example.test"), request(), db)
        accounts.submit_access_request(accounts.AccessRequestInput(email="person0@example.test"), request(), db)
        accounts.submit_access_request(accounts.AccessRequestInput(email="person1@example.test"), request(), db)
        rows = db.scalars(select(accounts.AccountAccessRequest)).all()
        assert len(rows) == 2
        assert rows[0].email == "person@example.test"
        assert rows[0].ip_hash != "203.0.113.8"
        limits = {row.scope_key: row.attempts for row in db.scalars(select(accounts.AccountAccessRequestLimit)).all()}
        assert limits["global"] == 4 and limits["ip:" + rows[0].ip_hash] == 4
    engine.dispose()


def test_public_request_rejects_malformed_email(monkeypatch):
    access_settings(monkeypatch)
    engine = database()
    with Session(engine) as db, pytest.raises(HTTPException) as error:
        accounts.submit_access_request(accounts.AccessRequestInput(email="not-an-email"), request(), db)
    assert error.value.status_code == 422
    engine.dispose()


def test_public_request_global_daily_limit_is_enforced(monkeypatch):
    access_settings(monkeypatch)
    engine = database()
    with Session(engine) as db:
        for index in range(100):
            accounts.submit_access_request(accounts.AccessRequestInput(email=f"person{index}@example.test"),
                                           request(f"198.51.100.{index + 1}"), db)
        accounts.submit_access_request(accounts.AccessRequestInput(email="over-limit@example.test"), request("198.51.100.8"), db)
        assert db.scalar(select(accounts.AccountAccessRequest.id).where(accounts.AccountAccessRequest.email == "over-limit@example.test")) is None
    engine.dispose()


def test_only_admin_can_list_or_process_requests(monkeypatch):
    access_settings(monkeypatch)
    engine = database()
    with Session(engine) as db:
        with pytest.raises(HTTPException) as error:
            accounts.list_access_requests(Principal(USER), db)
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            run_immediate(accounts.approve_access_request(uuid4(), Principal(USER), db))
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            accounts.list_access_requests(Principal(None), db)
        assert error.value.status_code == 403
    engine.dispose()


def test_admin_authentication_rejects_missing_session_and_non_admin(monkeypatch):
    settings = SimpleNamespace(auth_mode="local", api_token=SecretStr("fictional-local-test-token"))
    monkeypatch.setattr(auth, "settings", settings)
    with pytest.raises(HTTPException) as error:
        auth.authenticate_identity(None)
    assert error.value.status_code == 401
    principal = auth.authenticate_identity(HTTPAuthorizationCredentials(scheme="Bearer", credentials="fictional-local-test-token"))
    with pytest.raises(HTTPException) as error:
        accounts._admin(principal)
    assert error.value.status_code == 403


def test_admin_approval_creates_seven_day_invite_and_records_status(monkeypatch):
    access_settings(monkeypatch, supabase_service_role_key=SecretStr("fictional-service-key"))
    engine = database()
    item_id = uuid4()
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(accounts.AccountAccessRequest(id=item_id, email="person@example.test", ip_hash="a" * 64,
            status="pending", requested_at=now))
        db.commit()
    sent = []
    async def send(email): sent.append(email)
    monkeypatch.setattr(accounts, "_send_supabase_invitation", send)
    with Session(engine) as db:
        assert run_immediate(accounts.approve_access_request(item_id, Principal(ADMIN), db)) == {"status": "approved"}
    with Session(engine) as db:
        item = db.get(accounts.AccountAccessRequest, item_id)
        invite = db.scalar(select(accounts.AccountInvitation))
        assert item.status == "approved" and item.reviewed_by == ADMIN
        assert invite.access_duration_days == 7
        assert invite.expires_at - invite.created_at == timedelta(days=7)
    assert sent == ["person@example.test"]
    engine.dispose()


def test_failed_supabase_invite_reverts_request_and_revokes_pending_invite(monkeypatch):
    access_settings(monkeypatch, supabase_service_role_key=SecretStr("fictional-service-key"))
    engine = database()
    item_id = uuid4(); now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(accounts.AccountAccessRequest(id=item_id, email="person@example.test", ip_hash="b" * 64,
            status="pending", requested_at=now)); db.commit()
    async def fail(_email): raise RuntimeError("fictional delivery failure")
    monkeypatch.setattr(accounts, "_send_supabase_invitation", fail)
    with Session(engine) as db, pytest.raises(HTTPException) as error:
        run_immediate(accounts.approve_access_request(item_id, Principal(ADMIN), db))
    assert error.value.status_code == 502
    with Session(engine) as db:
        item = db.get(accounts.AccountAccessRequest, item_id)
        invite = db.scalar(select(accounts.AccountInvitation))
        assert item.status == "pending" and item.invitation_id is None
        assert invite.revoked_at is not None
    engine.dispose()


def test_admin_can_cancel_stuck_approval_and_revoke_its_local_invitation(monkeypatch):
    access_settings(monkeypatch)
    engine = database()
    item_id = uuid4(); invite_id = uuid4(); now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(accounts.AccountInvitation(id=invite_id, email="stuck@example.test", invited_by=ADMIN,
            created_at=now, expires_at=now + timedelta(days=7), access_duration_days=7))
        db.add(accounts.AccountAccessRequest(id=item_id, email="stuck@example.test", ip_hash="c" * 64,
            status="approving", requested_at=now, processing_at=now, invitation_id=invite_id))
        db.commit()
    with Session(engine) as db:
        assert accounts.reject_access_request(item_id, Principal(ADMIN), db) == {"status": "rejected"}
    with Session(engine) as db:
        assert db.get(accounts.AccountAccessRequest, item_id).status == "rejected"
        assert db.get(accounts.AccountInvitation, invite_id).revoked_at is not None
    engine.dispose()


def test_trial_starts_on_activation_and_expires_without_affecting_permanent_members(monkeypatch):
    access_settings(monkeypatch)
    engine = database()
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add_all([
            accounts.AccountInvitation(id=uuid4(), email="trial@example.test", invited_by=ADMIN, created_at=now,
                expires_at=now + timedelta(days=8), access_duration_days=7),
            accounts.AccountInvitation(id=uuid4(), email="permanent@example.test", invited_by=ADMIN, created_at=now,
                expires_at=now + timedelta(days=8)),
        ])
        db.commit()
    with Session(engine) as db:
        accounts.activate_account(Principal(USER, "trial@example.test"), db)
        expiry = db.get(accounts.AccountMember, USER).access_expires_at
        expiry = expiry.replace(tzinfo=timezone.utc) if expiry and expiry.tzinfo is None else expiry
        assert expiry is not None and abs((expiry - datetime.now(timezone.utc) - timedelta(days=7)).total_seconds()) < 2
    with Session(engine) as db:
        member = db.get(accounts.AccountMember, USER)
        member.access_expires_at = datetime.now(timezone.utc) - timedelta(microseconds=1)
        db.commit()
        assert accounts.activate_account(Principal(USER, "trial@example.test"), db) == {"status": "trial_expired"}
    permanent_user = uuid4()
    with Session(engine) as db:
        accounts.activate_account(Principal(permanent_user, "permanent@example.test"), db)
        assert db.get(accounts.AccountMember, permanent_user).access_expires_at is None
    engine.dispose()


def test_expired_account_is_blocked_from_private_auth_but_keeps_identity_auth(monkeypatch):
    monkeypatch.setattr(auth, "account_access_state", lambda _user_id: "trial_expired")
    with pytest.raises(HTTPException) as error:
        auth.require_active_account(Principal(USER, "expired@example.test"))
    assert error.value.status_code == 403 and "período de teste terminou" in error.value.detail
    # Account deletion depends on authenticate_identity, not the active-membership guard.
    assert auth.authenticate_identity.__name__ == "authenticate_identity"


def test_expired_account_can_still_use_self_service_deletion(monkeypatch):
    access_settings(monkeypatch, auth_mode="supabase", supabase_service_role_key=SecretStr("fictional-service-key"),
                    supabase_url="https://supabase.example.test")
    states = iter(("requested", "financial_data_deleted", "auth_identity_deleted", True))
    calls = []
    monkeypatch.setattr(accounts, "_run_deletion_function", lambda db, function, principal, **kwargs: (calls.append(function), next(states))[1])
    monkeypatch.setattr(accounts, "_verify_supabase_email", lambda *_: None)
    monkeypatch.setattr(accounts, "_delete_supabase_identity", lambda *_: True)
    principal = Principal(USER, "expired@example.test", True, int(datetime.now(timezone.utc).timestamp()))
    assert accounts.delete_own_account(accounts.DeleteAccountInput(confirmation="EXCLUIR MINHA CONTA"), principal, object()) == {"status": "deleted"}
    assert calls == ["dashboard_account_deletion_state", "purge_dashboard_account_data",
                     "mark_dashboard_auth_identity_deleted", "finish_dashboard_account_deletion"]
