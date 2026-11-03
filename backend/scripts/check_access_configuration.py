"""Read-only access metadata probe. Never prints credentials, identities or financial rows."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def inspect_configuration(env_path: Path, connect: bool = False) -> dict:
    values = dotenv_values(env_path)
    result = {"environment_file_found": env_path.is_file(),
              "admin_connection_configured": bool(values.get("ADMIN_DATABASE_URL")),
              "auth_admin_key_configured": bool(values.get("SUPABASE_SERVICE_ROLE_KEY")),
              "smtp_mode": values.get("INVITATION_SMTP_MODE", "builtin"),
              "private_origin_matches_cors": bool(values.get("APP_PUBLIC_URL")) and
                    values.get("APP_PUBLIC_URL") == values.get("CORS_ORIGIN")}
    # Only an origin is printed; query/fragment/userinfo never leave this process.
    for key in ("APP_PUBLIC_URL", "CORS_ORIGIN"):
        parsed = urlsplit(values.get(key) or "")
        result[key.lower()] = f"{parsed.scheme}://{parsed.hostname}" if parsed.scheme in ("http", "https") and parsed.hostname else None
    if not connect:
        return result
    dsn = values.get("DATABASE_URL")
    if not dsn:
        result["database_probe"] = "not_configured"
        return result
    engine = None
    try:
        url = make_url(dsn)
        if url.drivername != "postgresql+psycopg":
            result["database_probe"] = "postgresql_required"
            return result
        result["database_target"] = "local" if url.host in ("localhost", "127.0.0.1", "::1") else "remote"
        # Enforce read-only and bounded execution before the connection starts.
        options = str(url.query.get("options", ""))
        url = url.update_query_dict({"options": options + " -c default_transaction_read_only=on -c statement_timeout=5000"})
        engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5})
        with engine.connect() as connection:
            result["transaction_read_only"] = connection.scalar(text("SHOW transaction_read_only")) == "on"
            result["database_head"] = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            result["runtime_role_flags"] = dict(connection.execute(text("""SELECT rolsuper AS superuser,
                rolbypassrls AS bypass_rls, rolcreaterole AS create_role FROM pg_roles WHERE rolname=current_user""")).mappings().one())
            result["access_admin_group_exists"] = bool(connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='investment_access_admin')")))
            connection.rollback()
        result["database_probe"] = "read_only_metadata_ok"
    except Exception:
        result["database_probe"] = "unavailable_or_not_authorized"
    finally:
        if engine is not None:
            engine.dispose()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parents[2] / ".env")
    parser.add_argument("--connect-read-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(inspect_configuration(args.env_file, args.connect_read_only), indent=2, ensure_ascii=False))
