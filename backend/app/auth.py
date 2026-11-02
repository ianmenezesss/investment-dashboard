"""Modo local preservado; JWT Supabase opt-in com allowlist de identidades."""
import secrets
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .database import settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: UUID | None
    email: str | None = None
    email_verified: bool = False
    auth_time: int | None = None


@lru_cache(maxsize=1)
def jwks_client():
    return jwt.PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json", timeout=5, lifespan=300)


def verify_jwt(token: str, key) -> Principal:
    try:
        claims = jwt.decode(
            token, key, algorithms=["ES256", "RS256"],
            issuer=f"{settings.supabase_url}/auth/v1", audience="authenticated",
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
        user_id = UUID(claims["sub"])
        if claims.get("role") != "authenticated":
            raise HTTPException(403, "Conta não autorizada")
        email = claims.get("email")
        if not isinstance(email, str) or len(email) > 320:
            email = None
        auth_time = claims.get("auth_time")
        if isinstance(auth_time, bool) or not isinstance(auth_time, int):
            auth_time = None
        return Principal(user_id, email, claims.get("email_verified") is True, auth_time)
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(401, "Sessão inválida ou expirada") from None


def authenticate_identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if credentials is None:
        raise HTTPException(401, "Autenticação obrigatória", headers={"WWW-Authenticate": "Bearer"})
    token = credentials.credentials
    if len(token) > 16384:
        raise HTTPException(401, "Credencial inválida")
    if settings.auth_mode == "local":
        if not secrets.compare_digest(token, settings.api_token.get_secret_value()):
            raise HTTPException(401, "Token inválido")
        return Principal(None, None, True)
    try:
        # Não aceitar URL de chave indicada pelo token, apenas JWKS configurado.
        header = jwt.get_unverified_header(token)
        if header.get("alg") == "HS256":
            raise HTTPException(401, "Assinatura HS256 não suportada. Configure uma chave assimétrica ES256 ou RS256 no Supabase.")
        if header.get("alg") not in ("ES256", "RS256") or not header.get("kid"):
            raise HTTPException(401, "Credencial inválida")
        key = jwks_client().get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(503, "Serviço de autenticação temporariamente indisponível") from None
    except jwt.PyJWTError:
        raise HTTPException(401, "Credencial inválida") from None
    return verify_jwt(token, key)


def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    principal = authenticate_identity(credentials)
    return require_active_account(principal)


def require_active_account(principal: Principal) -> Principal:
    if principal.user_id is None:
        return principal
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError
    from .database import SessionLocal
    try:
        if not account_is_active(principal.user_id):
            raise HTTPException(403, "Conta não autorizada")
    except HTTPException:
        raise
    except SQLAlchemyError:
        raise HTTPException(503, "Não foi possível validar o acesso à conta") from None
    return principal


def account_is_active(user_id: UUID) -> bool:
    from sqlalchemy import text
    from .database import SessionLocal
    with SessionLocal() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(user_id)})
        return db.scalar(text("SELECT status = 'active' FROM account_members WHERE user_id = :user_id"),
                         {"user_id": user_id}) is True
