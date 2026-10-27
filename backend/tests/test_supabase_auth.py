from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import jwt
import pytest
from app import auth

USER = UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture
def configured(monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(auth, "settings", SimpleNamespace(auth_mode="supabase", supabase_url="https://project.example", allowed_user_ids=[USER]))
    monkeypatch.setattr(auth, "jwks_client", lambda: SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())))
    now = datetime.now(timezone.utc)
    claims = {"sub": str(USER), "iss": "https://project.example/auth/v1", "aud": "authenticated", "role": "authenticated", "iat": now, "exp": now + timedelta(minutes=5)}
    return key, claims


def credentials(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_authentication_uses_jwks_and_verifies_signature(configured):
    key, claims = configured
    token = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "test-key"})
    assert auth.authenticate(credentials(token)).user_id == USER
    wrong_key = ec.generate_private_key(ec.SECP256R1())
    forged = jwt.encode(claims, wrong_key, algorithm="ES256", headers={"kid": "test-key"})
    with pytest.raises(HTTPException) as error:
        auth.authenticate(credentials(forged))
    assert error.value.status_code == 401


def test_symmetric_tokens_are_rejected_without_fetching_jwks(configured, monkeypatch):
    _, claims = configured
    def forbidden():
        raise AssertionError("HS256 não deve consultar JWKS nem aceitar segredo simétrico")
    monkeypatch.setattr(auth, "jwks_client", forbidden)
    token = jwt.encode(claims, "test-only-symmetric-key-of-at-least-32-bytes", algorithm="HS256")
    with pytest.raises(HTTPException) as error:
        auth.authenticate(credentials(token))
    assert error.value.status_code == 401
    assert "HS256" in error.value.detail


def test_jwks_outage_fails_closed(configured, monkeypatch):
    key, claims = configured
    def unavailable(_):
        raise jwt.PyJWKClientConnectionError("internal provider information")
    monkeypatch.setattr(auth, "jwks_client", lambda: SimpleNamespace(get_signing_key_from_jwt=unavailable))
    token = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "test-key"})
    with pytest.raises(HTTPException) as error:
        auth.authenticate(credentials(token))
    assert error.value.status_code == 503
    assert "internal" not in error.value.detail
