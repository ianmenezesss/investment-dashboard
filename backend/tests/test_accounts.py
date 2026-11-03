from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from pydantic import SecretStr
from fastapi import HTTPException
import pytest

from app import accounts
from app.auth import Principal
from app.database import Base

ADMIN = UUID("11111111-1111-4111-8111-111111111111")
INVITEE = UUID("22222222-2222-4222-8222-222222222222")


def setup_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def accept_by_claim(invitation_id, principal, db):
    claim = accounts.claim_invitation(invitation_id, principal, db)
    return accounts.activate_account(principal, db,
        accounts.AcceptInvitationInput(invitation_id=invitation_id, claim_token=claim["claim_token"]))


def run_mocked(coroutine):
    """Drive the no-I/O async endpoint against immediate mocked HTTP clients."""
    try:
        coroutine.send(None)
    except StopIteration as complete:
        return complete.value
    coroutine.close()
    raise AssertionError("Mocked endpoint unexpectedly awaited external I/O")


def test_invitation_activation_is_email_bound_single_use_and_revocable(monkeypatch):
    engine = setup_db()
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        invitation_id = uuid4()
        db.add(accounts.AccountInvitation(id=invitation_id, email="person@example.com", invited_by=ADMIN,
            created_at=now, expires_at=now + timedelta(days=7)))
        db.commit()
    with Session(engine) as db:
        principal = Principal(INVITEE, "person@example.com", True)
        assert accept_by_claim(invitation_id, principal, db)["status"] == "active"
        assert accounts.activate_account(principal, db)["status"] == "active"
        assert db.get(accounts.AccountMember, INVITEE).status == "active"
        invitation = db.query(accounts.AccountInvitation).one()
        assert invitation.accepted_user_id == INVITEE
        assert invitation.accepted_at is not None and invitation.claim_token_hash is None
        replay = accounts.claim_invitation(invitation_id, principal, db) if invitation.accepted_user_id is None else None
        assert replay is None
    engine.dispose()


def test_invitation_activation_rejects_expired_and_wrong_email():
    engine = setup_db()
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add_all([
            accounts.AccountInvitation(id=uuid4(), email="expired@example.com", invited_by=ADMIN, created_at=now-timedelta(days=9), expires_at=now-timedelta(days=1)),
            accounts.AccountInvitation(id=uuid4(), email="right@example.com", invited_by=ADMIN, created_at=now, expires_at=now+timedelta(days=1)),
        ])
        db.commit()
    with Session(engine) as db:
        for email in ("wrong@example.com", "expired@example.com"):
            try:
                accounts.activate_account(Principal(INVITEE, email, True), db)
                assert False, "expected invitation rejection"
            except HTTPException as exc:
                assert exc.status_code == 403
    engine.dispose()


def test_supabase_activation_requires_server_confirmed_email(monkeypatch):
    engine = setup_db()
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        invitation_id = uuid4()
        db.add(accounts.AccountInvitation(id=invitation_id, email="person@example.com", invited_by=ADMIN,
            created_at=now, expires_at=now + timedelta(days=7)))
        db.commit()

    requests = []
    class Response:
        status_code = 200
        def __init__(self, confirmed): self.confirmed = confirmed
        def raise_for_status(self): pass
        def json(self):
            return {"id": str(INVITEE), "email": "person@example.com",
                    "email_confirmed_at": "2026-11-01T00:00:00Z" if self.confirmed else None}
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            requests.append((url, kwargs))
            return Response(confirmed=True)
    monkeypatch.setattr(accounts.httpx, "Client", Client)
    monkeypatch.setattr(accounts, "settings", SimpleNamespace(
        auth_mode="supabase", supabase_service_role_key=SecretStr("fictional-admin-test-key"),
        supabase_url="https://project.example"))
    with Session(engine) as db:
        # The standard Supabase access JWT need not contain an email_verified claim;
        # activation trusts the server-side Admin API confirmation record instead.
        result = accept_by_claim(invitation_id, Principal(INVITEE, "Person@Example.com", False), db)
        assert result["status"] == "active" and result["access_type"] == "permanent"
        assert "fictional-admin-test-key" not in str(result)
    url, request = requests[0]
    assert url.endswith(f"/auth/v1/admin/users/{INVITEE}")
    assert request["headers"]["Authorization"] == "Bearer fictional-admin-test-key"

    class UnconfirmedClient(Client):
        def get(self, url, **kwargs): return Response(confirmed=False)
    monkeypatch.setattr(accounts.httpx, "Client", UnconfirmedClient)
    new_user = UUID("33333333-3333-4333-8333-333333333333")
    with Session(engine) as db:
        from fastapi import HTTPException
        try:
            accounts.claim_invitation(invitation_id, Principal(new_user, "person@example.com", False), db)
            assert False, "unconfirmed Supabase identity must not consume an invitation"
        except HTTPException as exc:
            assert exc.status_code == 403
        assert db.get(accounts.AccountMember, new_user) is None
    engine.dispose()


def test_invitation_claim_is_unique_user_bound_and_stale_links_cannot_reset_password():
    engine = setup_db()
    now = datetime.now(timezone.utc)
    invite_id = uuid4()
    with Session(engine) as db:
        db.add(accounts.AccountInvitation(id=invite_id, email="person@example.com", invited_by=ADMIN,
            created_at=now, expires_at=now + timedelta(days=7)))
        db.commit()
    with Session(engine) as db:
        principal = Principal(INVITEE, "person@example.com")
        claim = accounts.claim_invitation(invite_id, principal, db)
        assert len(claim["claim_token"]) >= 40
        with pytest.raises(HTTPException) as conflict:
            accounts.claim_invitation(invite_id, principal, db)
        assert conflict.value.status_code == 409
        wrong_user = Principal(UUID("33333333-3333-4333-8333-333333333333"), "person@example.com")
        with pytest.raises(HTTPException) as wrong_identity:
            accounts.activate_account(wrong_user, db, accounts.AcceptInvitationInput(invitation_id=invite_id, claim_token=claim["claim_token"]))
        assert wrong_identity.value.status_code == 403
        assert db.get(accounts.AccountMember, INVITEE) is None
        result = accounts.activate_account(principal, db, accounts.AcceptInvitationInput(invitation_id=invite_id, claim_token=claim["claim_token"]))
        assert result["status"] == "active"
        expiry = result["trial_expires_at"]
        with pytest.raises(HTTPException) as stale_claim:
            accounts.claim_invitation(invite_id, principal, db)
        assert stale_claim.value.status_code == 403
        assert accounts.activate_account(principal, db, accounts.AcceptInvitationInput(invitation_id=invite_id, claim_token=claim["claim_token"]))["trial_expires_at"] == expiry
    engine.dispose()


def test_administrator_cannot_revoke_an_invitation_during_its_active_claim(monkeypatch):
    engine = setup_db()
    invite_id = uuid4()
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(accounts.AccountInvitation(id=invite_id, email="person@example.com", invited_by=ADMIN,
            created_at=now, expires_at=now + timedelta(days=7)))
        db.commit()
        accounts.claim_invitation(invite_id, Principal(INVITEE, "person@example.com"), db)
        monkeypatch.setattr(accounts, "settings", SimpleNamespace(invitation_admin_ids=[ADMIN]))
        with pytest.raises(HTTPException) as conflict:
            accounts.revoke_invitation(invite_id, Principal(ADMIN), db)
        assert conflict.value.status_code == 409
        db.expire_all()
        assert db.get(accounts.AccountInvitation, invite_id).revoked_at is None
    engine.dispose()


def test_revoked_member_can_rejoin_only_after_a_new_invitation():
    engine = setup_db()
    now = datetime.now(timezone.utc)
    first_id = uuid4()
    with Session(engine) as db:
        db.add(accounts.AccountInvitation(id=first_id, email="person@example.com", invited_by=ADMIN,
            created_at=now, expires_at=now + timedelta(days=7)))
        db.commit()
        assert accept_by_claim(first_id, Principal(INVITEE, "person@example.com"), db)["status"] == "active"
        monkeypatch_settings = SimpleNamespace(invitation_admin_ids=[ADMIN])
    from fastapi import HTTPException
    with Session(engine) as db:
        # This unit path models the API's already-authenticated admin authorization.
        from unittest.mock import patch
        with patch.object(accounts, "settings", monkeypatch_settings):
            assert accounts.revoke_member(INVITEE, Principal(ADMIN), db) == {"status": "revoked", "user_id": str(INVITEE)}
        second_id = uuid4()
        db.add(accounts.AccountInvitation(id=second_id, email="person@example.com", invited_by=ADMIN,
            created_at=now + timedelta(minutes=1), expires_at=now + timedelta(days=8),
            access_duration_days=7, target_user_id=INVITEE))
        db.commit()
        result = accept_by_claim(second_id, Principal(INVITEE, "person@example.com"), db)
        assert result["status"] == "active" and result["access_type"] == "trial"
        assert db.get(accounts.AccountMember, INVITEE).status == "active"
        assert db.query(accounts.AccountInvitation).count() == 2
    engine.dispose()


def test_admin_api_requires_active_authorized_admin_before_invite_send(monkeypatch):
    engine = setup_db()
    from fastapi import HTTPException
    with Session(engine) as db:
        try:
            accounts._admin(Principal(INVITEE, "guest@example.com", True))
            assert False, "expected admin rejection"
        except HTTPException as exc:
            assert exc.status_code == 403
    engine.dispose()


def test_fixture_status_exposes_only_the_authenticated_owners_fictional_marker():
    engine = setup_db()
    other = UUID("33333333-3333-4333-8333-333333333333")
    with Session(engine) as db:
        db.add(accounts.AccountFixtureLoad(user_id=INVITEE, fixture_id="v2-demo-scenario",
            fixture_sha256="a" * 64, loaded_by=ADMIN, loaded_at=datetime.now(timezone.utc)))
        db.commit()
    with Session(engine) as db:
        assert accounts.account_fixture_status(Principal(INVITEE), db) == {"fictional_fixture_loaded": True}
        assert accounts.account_fixture_status(Principal(other), db) == {"fictional_fixture_loaded": False}
    engine.dispose()


def test_admin_invitation_is_sent_server_side_limited_and_revocable(monkeypatch):
    engine = setup_db()
    captured = []
    class Response:
        status_code = 200
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            captured.append((url, kwargs))
            return Response()
    monkeypatch.setattr(accounts.httpx, "AsyncClient", Client)
    monkeypatch.setattr(accounts, "settings", SimpleNamespace(
        invitation_admin_ids=[ADMIN], supabase_service_role_key=SecretStr("fake-test-admin-key"),
        supabase_url="https://project.example", app_public_url="https://private.example",
        invitation_max_send_attempts=3))
    with Session(engine) as db:
        result = run_mocked(accounts.create_invitation(accounts.InvitationInput(email="Person@Example.com"), Principal(ADMIN), db))
        assert result["email"] == "person@example.com" and result["accepted"] is False
        assert "fake-test-admin-key" not in str(result)
        url, request = captured[0]
        assert url == "https://project.example/auth/v1/invite"
        assert request["headers"]["Authorization"] == "Bearer fake-test-admin-key"
        assert request["json"] == {"email": "person@example.com"}
        assert request["params"]["redirect_to"] == f"https://private.example/invite/accept?invitation_id={result['id']}"
        attempt = db.query(accounts.AccountInvitationSendAttempt).one()
        assert attempt.outcome == "requested" and attempt.http_status == 200
        attempt.attempted_at = datetime.now(timezone.utc) - timedelta(seconds=61)
        db.commit()
        resent = run_mocked(accounts.resend_invitation(UUID(result["id"]), Principal(ADMIN), db))
        assert resent["status"] == "requested" and resent["delivery_confirmed"] is False
        assert len(captured) == 2
        assert result["delivery_confirmed"] is False
        with pytest.raises(HTTPException) as cooldown:
            run_mocked(accounts.resend_invitation(UUID(result["id"]), Principal(ADMIN), db))
        assert cooldown.value.status_code == 429 and cooldown.value.detail["provider_code"] == "cooldown"
        assert 1 <= cooldown.value.detail["retry_after_seconds"] <= 60
        attempts = db.query(accounts.AccountInvitationSendAttempt).order_by(accounts.AccountInvitationSendAttempt.attempted_at).all()
        attempts[0].attempted_at = datetime.now(timezone.utc) - timedelta(hours=2)
        attempts[1].attempted_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        third = run_mocked(accounts.resend_invitation(UUID(result["id"]), Principal(ADMIN), db))
        assert third["status"] == "requested" and len(captured) == 3
        latest = db.query(accounts.AccountInvitationSendAttempt).order_by(accounts.AccountInvitationSendAttempt.attempted_at.desc()).first()
        latest.attempted_at = datetime.now(timezone.utc) - timedelta(seconds=61)
        db.commit()
        with pytest.raises(HTTPException) as cap:
            run_mocked(accounts.resend_invitation(UUID(result["id"]), Principal(ADMIN), db))
        assert cap.value.status_code == 429 and cap.value.detail["provider_code"] == "attempt_limit"
        assert cap.value.detail["retryable"] is False
        assert accounts.revoke_invitation(UUID(result["id"]), Principal(ADMIN), db) == {"status": "invitation_revoked"}
        assert db.query(accounts.AccountInvitation).one().revoked_at is not None
        assert db.query(accounts.AccountInvitationSendAttempt).count() == 3
    engine.dispose()


def test_invitation_for_existing_confirmed_auth_identity_uses_recovery_for_same_invite(monkeypatch):
    captured = []
    recovery_status = {"code": 200}
    class Response:
        def __init__(self, status_code, body=None):
            self.status_code = status_code
            self.body = body or {}
        def json(self): return self.body
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            captured.append((url, kwargs))
            if url.endswith("/invite"):
                return Response(422, {"code": "user_already_exists"})
            return Response(recovery_status["code"], {"code": "over_email_send_rate_limit"} if recovery_status["code"] != 200 else {})
    monkeypatch.setattr(accounts.httpx, "AsyncClient", Client)
    monkeypatch.setattr(accounts, "settings", SimpleNamespace(
        invitation_admin_ids=[ADMIN],
        supabase_service_role_key=SecretStr("fictional-admin-test-key"),
        supabase_url="https://project.example", app_public_url="https://private.example"))
    invite_id = uuid4()
    run_mocked(accounts._send_supabase_invitation("person@example.com", invite_id))
    assert [url.rsplit("/", 1)[-1] for url, _ in captured] == ["invite", "recover"]
    assert all(req["params"]["redirect_to"] ==
               f"https://private.example/invite/accept?invitation_id={invite_id}"
               for _, req in captured)
    assert all(req["json"] == {"email": "person@example.com"} for _, req in captured)
    recovery_status["code"] = 429
    engine = setup_db()
    with Session(engine) as db:
        db.add(accounts.AccountInvitation(id=invite_id, email="person@example.com", invited_by=ADMIN,
            created_at=datetime.now(timezone.utc), expires_at=datetime.now(timezone.utc) + timedelta(days=7)))
        db.commit()
        with pytest.raises(HTTPException) as error:
            run_mocked(accounts.resend_invitation(invite_id, Principal(ADMIN), db))
        assert error.value.status_code == 429
        assert error.value.headers["Retry-After"] == "60"
        attempt = db.query(accounts.AccountInvitationSendAttempt).one()
        assert (attempt.outcome, attempt.method, attempt.http_status, attempt.provider_code) == (
            "failed", "recovery", 429, "over_email_send_rate_limit")
    engine.dispose()


def test_admin_lists_are_filtered_searched_and_paginated_with_safe_legacy_identity(monkeypatch):
    engine = setup_db()
    monkeypatch.setattr(accounts, "settings", SimpleNamespace(
        auth_mode="local", invitation_admin_ids=[ADMIN], supabase_service_role_key=SecretStr("")))
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        for index in range(7):
            db.add(accounts.AccountMember(user_id=UUID(f"00000000-0000-4000-8000-{index+1:012d}"),
                email=None if index == 1 else f"member{index}@example.test", status="active",
                created_at=now - timedelta(minutes=index),
                access_expires_at=now - timedelta(days=1) if index == 2 else None,
                activated_at=None if index == 1 else now - timedelta(days=3)))
        db.add(accounts.AccountMember(user_id=ADMIN, email="admin@example.test", status="active", created_at=now))
        for index in range(7):
            db.add(accounts.AccountInvitation(id=uuid4(), email=f"invite{index}@example.test", invited_by=ADMIN,
                created_at=now - timedelta(minutes=index), expires_at=now + timedelta(days=2)))
            db.add(accounts.AccountAccessRequest(id=uuid4(), email=f"request{index}@example.test", ip_hash="a"*64,
                status="pending", requested_at=now - timedelta(minutes=index)))
        db.commit()
        members = accounts.list_members(page=1, page_size=5, search="", status="all", principal=Principal(ADMIN), db=db)
        assert len(members["items"]) == 5 and members["total"] == 8 and members["total_pages"] == 2
        missing = accounts.list_members(page=1, page_size=5, search="000000000002", status="all", principal=Principal(ADMIN), db=db)
        legacy = missing["items"][0]
        assert missing["total"] == 1
        assert legacy["account_label"].startswith("Conta · ") and legacy["email_source"] == "unavailable"
        assert legacy["activated_at"] is None
        filtered = accounts.list_members(page=1, page_size=5, search="member2@", status="expired", principal=Principal(ADMIN), db=db)
        assert filtered["total"] == 1 and filtered["items"][0]["status"] == "expired"
        escaped = accounts.list_members(page=1, page_size=5, search="%", status="all", principal=Principal(ADMIN), db=db)
        assert escaped["total"] == 0
        invites = accounts.list_invitations(page=2, page_size=5, search="invite", status="pending", principal=Principal(ADMIN), db=db)
        assert len(invites["items"]) == 2 and invites["total"] == 7 and invites["page"] == 2
        requests = accounts.list_access_requests(page=1, page_size=5, search="request6", status="pending", principal=Principal(ADMIN), db=db)
        assert requests["total"] == 1 and requests["items"][0]["email"] == "request6@example.test"
    engine.dispose()


def test_membership_revocation_is_separate_from_invitation_revocation_and_protects_admin(monkeypatch):
    engine = setup_db()
    monkeypatch.setattr(accounts, "settings", SimpleNamespace(invitation_admin_ids=[ADMIN]))
    now = datetime.now(timezone.utc)
    member_id = UUID("33333333-3333-4333-8333-333333333333")
    legacy_id = UUID("44444444-4444-4444-8444-444444444444")
    invite_id = uuid4()
    with Session(engine) as db:
        db.add(accounts.AccountMember(user_id=member_id, email="member@example.test", status="active", created_at=now))
        db.add(accounts.AccountMember(user_id=legacy_id, email=None, status="active", created_at=now))
        db.add(accounts.AccountInvitation(id=invite_id, email="member@example.test", invited_by=ADMIN,
            created_at=now, expires_at=now+timedelta(days=2), accepted_user_id=member_id))
        db.commit()
        with pytest.raises(HTTPException) as protected:
            accounts.revoke_member(ADMIN, Principal(ADMIN), db)
        assert protected.value.status_code == 403
        with pytest.raises(HTTPException) as wrong_state:
            accounts.revoke_invitation(invite_id, Principal(ADMIN), db)
        assert wrong_state.value.status_code == 409
        assert db.get(accounts.AccountMember, member_id).status == "active"
        assert accounts.revoke_member(member_id, Principal(ADMIN), db) == {"status": "revoked", "user_id": str(member_id)}
        assert db.get(accounts.AccountMember, member_id).status == "revoked"
        assert db.get(accounts.AccountInvitation, invite_id).revoked_at is not None
        assert accounts.revoke_member(legacy_id, Principal(ADMIN), db) == {"status": "revoked", "user_id": str(legacy_id)}
        assert db.query(accounts.AccountInvitation).count() == 1
        assert db.get(accounts.AccountMember, legacy_id).status == "revoked"
    from app import auth, database as database_module
    from sqlalchemy.orm import sessionmaker
    monkeypatch.setattr(database_module, "SessionLocal", sessionmaker(engine))
    with pytest.raises(HTTPException) as blocked_session:
        auth.require_active_account(Principal(legacy_id, "legacy@example.test"))
    assert blocked_session.value.status_code == 403
    engine.dispose()


def test_admin_reactivation_targets_existing_auth_identity_and_starts_no_period_before_acceptance(monkeypatch):
    engine = setup_db()
    settings = SimpleNamespace(auth_mode="local", invitation_admin_ids=[ADMIN], supabase_service_role_key=SecretStr("fictional-admin-test-key"),
        supabase_url="https://project.example", app_public_url="https://private.example")
    monkeypatch.setattr(accounts, "settings", settings)
    class AuthResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"id": str(INVITEE), "email": "person@example.com", "email_confirmed_at": "2026-11-01T00:00:00Z"}
    class SyncClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs): return AuthResponse()
    captured = []
    class AsyncResponse:
        status_code = 200
    class AsyncClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            captured.append((url, kwargs)); return AsyncResponse()
    monkeypatch.setattr(accounts.httpx, "Client", SyncClient)
    monkeypatch.setattr(accounts.httpx, "AsyncClient", AsyncClient)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(accounts.AccountMember(user_id=INVITEE, email="person@example.com", status="revoked",
            created_at=now - timedelta(days=14), activated_at=now - timedelta(days=14), access_expires_at=now - timedelta(days=7)))
        db.commit()
        result = run_mocked(accounts.reactivate_member(INVITEE, Principal(ADMIN), db))
        assert result["status"] == "reactivation_email_requested" and result["delivery_confirmed"] is False
        invite = db.query(accounts.AccountInvitation).one()
        assert invite.invited_by == ADMIN and invite.target_user_id == INVITEE
        assert invite.access_duration_days == 7 and invite.accepted_user_id is None
        assert accounts._utc(db.get(accounts.AccountMember, INVITEE).access_expires_at) < datetime.now(timezone.utc)
        principal = Principal(INVITEE, "person@example.com")
        assert accounts.invitation_eligibility(invite.id, principal, db) == {"eligible": True}
        claim = accounts.claim_invitation(invite.id, principal, db)
        activated = accounts.activate_account(principal, db,
            accounts.AcceptInvitationInput(invitation_id=invite.id, claim_token=claim["claim_token"]))
        assert activated["status"] == "active" and activated["access_type"] == "trial"
        assert datetime.fromisoformat(activated["trial_expires_at"]) - datetime.fromisoformat(activated["activated_at"]) == timedelta(hours=168)
        url, request = captured[0]
        assert url == "https://project.example/auth/v1/recover"
        assert request["json"] == {"email": "person@example.com"}
        assert request["params"]["redirect_to"] == f"https://private.example/invite/accept?invitation_id={invite.id}"
        with pytest.raises(HTTPException) as duplicate:
            run_mocked(accounts.reactivate_member(INVITEE, Principal(ADMIN), db))
        assert duplicate.value.status_code == 409
        assert db.query(accounts.AccountInvitation).count() == 1
    engine.dispose()
