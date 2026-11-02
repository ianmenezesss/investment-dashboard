from typing import Literal
from uuid import UUID
from urllib.parse import urlsplit
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Settings(BaseSettings):
    database_url: SecretStr
    api_token: SecretStr = SecretStr("")
    cors_origin: str = "http://localhost:5173"
    environment: Literal["development", "production", "test"] = "development"
    auth_mode: Literal["local", "supabase"] = "local"
    supabase_url: str = ""
    allowed_user_ids: list[UUID] = Field(default_factory=list)
    invitation_admin_ids: list[UUID] = Field(default_factory=list)
    supabase_service_role_key: SecretStr = SecretStr("")
    app_public_url: str = ""
    migration_database_url: SecretStr = SecretStr("")
    market_data_enabled: bool = False
    equity_history_enabled: bool = False
    individual_equity_history_enabled: bool = False
    brapi_token: SecretStr = SecretStr("")
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "qwen/qwen3.8-27b"
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore", hide_input_in_errors=True)

    @model_validator(mode="after")
    def safe_configuration(self):
        origin = urlsplit(self.cors_origin)
        if origin.scheme not in ("http", "https") or not origin.netloc or origin.path or origin.query or origin.fragment or origin.username or "*" in self.cors_origin:
            raise ValueError("CORS_ORIGIN deve conter uma origem exata, sem caminho ou curinga")
        if self.auth_mode == "local" and not self.api_token.get_secret_value().strip():
            raise ValueError("API_TOKEN é obrigatório no modo local")
        if self.environment == "production":
            if self.auth_mode != "supabase" or origin.scheme != "https":
                raise ValueError("Produção exige Supabase Auth e CORS HTTPS exato")
            if not self.database_url.get_secret_value().startswith("postgresql+psycopg://"):
                raise ValueError("Produção exige PostgreSQL com psycopg")
            if make_url(self.database_url.get_secret_value()).query.get("sslmode") != "verify-full":
                raise ValueError("Produção exige conexão TLS com verificação do certificado PostgreSQL")
        if self.auth_mode == "supabase":
            url = urlsplit(self.supabase_url)
            if url.scheme != "https" or not url.hostname or url.path or url.query or url.fragment or url.username:
                raise ValueError("Supabase exige URL HTTPS sem caminho")
        if self.environment == "production" and self.auth_mode == "supabase":
            app_url = urlsplit(self.app_public_url)
            if not self.invitation_admin_ids or not self.supabase_service_role_key.get_secret_value().strip():
                raise ValueError("Produção com convites exige admins e chave administrativa Supabase no backend")
            if app_url.scheme != "https" or not app_url.netloc or app_url.path or app_url.query or app_url.fragment or app_url.username:
                raise ValueError("APP_PUBLIC_URL deve ser uma origem HTTPS exata")
        return self


settings = Settings()
database_url = settings.database_url.get_secret_value()
engine = create_engine(database_url, pool_pre_ping=True, hide_parameters=True,
                       connect_args={"connect_timeout": 5} if database_url.startswith("postgresql") else {})
SessionLocal = sessionmaker(engine)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session


def ensure_production_role(db):
    if settings.environment != "production":
        return
    row = db.execute(text("""SELECT r.rolsuper OR r.rolbypassrls OR c.relowner = r.oid AS unsafe,
        c.relrowsecurity AND c.relforcerowsecurity AS rls
        FROM pg_roles r JOIN pg_class c ON c.oid = 'public.operations'::regclass
        WHERE r.rolname = current_user""")).one()
    if row.unsafe or not row.rls:
        raise HTTPException(503, "Configuração de acesso ao banco requer revisão")
