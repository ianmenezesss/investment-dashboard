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
        if claims.get("role") != "authenticated" or user_id not in settings.allowed_user_ids:
            raise HTTPException(403, "Conta não autorizada")
        return Principal(user_id)
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(401, "Sessão inválida ou expirada") from None


def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if credentials is None:
        raise HTTPException(401, "Autenticação obrigatória", headers={"WWW-Authenticate": "Bearer"})
    token = credentials.credentials
    if len(token) > 16384:
        raise HTTPException(401, "Credencial inválida")
    if settings.auth_mode == "local":
        if not secrets.compare_digest(token, settings.api_token.get_secret_value()):
            raise HTTPException(401, "Token inválido")
        return Principal(None)
    try:
        # Não aceitar URL de chave indicada pelo token, apenas JWKS configurado.
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in ("ES256", "RS256") or not header.get("kid"):
            raise HTTPException(401, "Credencial inválida")
        key = jwks_client().get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(503, "Serviço de autenticação temporariamente indisponível") from None
    except jwt.PyJWTError:
        raise HTTPException(401, "Credencial inválida") from None
    return verify_jwt(token, key)
