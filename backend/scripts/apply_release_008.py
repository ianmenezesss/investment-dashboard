"""Manually invoked 004->008 upgrade; never runs from the read-only preflight."""
from getpass import getpass
import os
from pathlib import Path
import sys

from preflight_release_004 import validate_url, ca_path, check

BACKEND = Path(__file__).resolve().parents[1]


def main():
    try:
        url = validate_url(getpass("URL da role DDL (entrada oculta): "))
        ca = ca_path(url)
        check(url, ca)
        print("DDL_PREFLIGHT=PASS; alembic=004; sslmode=verify-full")
        if input("Escritas bloqueadas e autorização concedida? Digite APLICAR_005_008: ").strip() != "APLICAR_005_008":
            print("MIGRATION=NOT_RUN; confirmação ausente")
            return 1
        migration_url = url.update_query_dict({"sslmode": "verify-full", "sslrootcert": ca})
        os.environ.update({"DATABASE_URL": migration_url.render_as_string(hide_password=False),
                           "MIGRATION_DATABASE_URL": migration_url.render_as_string(hide_password=False),
                           "ENVIRONMENT": "test", "AUTH_MODE": "local",
                           "API_TOKEN": "migration-process-only", "CORS_ORIGIN": "http://localhost:5173",
                           "PGSSLROOTCERT": ca})
        os.chdir(BACKEND)
        sys.path.insert(0, str(BACKEND))
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        cfg = Config(str(BACKEND / "alembic.ini"))
        if ScriptDirectory.from_config(cfg).get_heads() != ["008"]:
            raise RuntimeError("LOCAL_HEAD_NOT_008")
        command.upgrade(cfg, "head")
        from sqlalchemy import create_engine, text
        engine = create_engine(migration_url, hide_parameters=True, connect_args={
            "connect_timeout": 10, "sslmode": "verify-full", "sslrootcert": ca})
        try:
            with engine.connect() as conn:
                versions = conn.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all()
            if versions != ["008"]:
                raise RuntimeError("ALEMBIC_NOT_008_AFTER_UPGRADE")
        finally:
            engine.dispose()
        print("MIGRATION=PASS; alembic=008; next=check_runtime_role.py")
        return 0
    except ValueError as exc:
        print("MIGRATION=NOT_RUN_OR_FAILED; reason=" + str(exc))
        return 1
    except Exception as exc:
        print("MIGRATION=FAIL; error_class=" + type(exc).__name__ + "; do_not_retry_automatically")
        return 1
    finally:
        for key in ("DATABASE_URL", "MIGRATION_DATABASE_URL", "API_TOKEN"):
            os.environ.pop(key, None)


if __name__ == "__main__":
    sys.exit(main())
