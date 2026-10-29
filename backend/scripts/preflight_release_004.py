"""Read-only preflight for the authorized 004->008 production migration.

The DDL URL is entered without echo; no URL, password, SQL row or traceback is printed.
"""
from getpass import getpass
import os
from pathlib import Path
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def validate_url(raw):
    try:
        url = make_url(raw)
        if (url.drivername != "postgresql+psycopg" or not url.host or not url.username
                or not url.password or url.database != "postgres"
                or url.query.get("sslmode") != "verify-full"):
            raise ValueError
        if url.username == "investment_runtime" or url.username.startswith("investment_runtime."):
            raise ValueError
        return url
    except Exception:
        raise ValueError("DDL_URL_INVALID") from None


def ca_path(url):
    candidate = os.environ.get("PGSSLROOTCERT") or url.query.get("sslrootcert")
    if not candidate or not Path(candidate).is_file():
        candidate = input("Caminho da CA oficial local (sem credenciais): ").strip()
    if not candidate or not Path(candidate).is_file():
        raise ValueError("CA_MISSING")
    return str(Path(candidate).resolve())


def check(url, ca):
    engine = create_engine(url, hide_parameters=True, connect_args={
        "connect_timeout": 10, "sslmode": "verify-full", "sslrootcert": ca})
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            row = connection.execute(text("""SELECT current_user, current_database(),
                current_setting('server_version_num')::int / 10000,
                (SELECT count(*) FROM public.alembic_version),
                (SELECT min(version_num) FROM public.alembic_version),
                (SELECT max(version_num) FROM public.alembic_version),
                has_schema_privilege(current_user,'public','CREATE'),
                (SELECT rolsuper FROM pg_roles WHERE rolname=current_user)""")).one()
            role, database, major, count, first, last, can_create, superuser = row
            if role in {"investment_runtime", "anon", "authenticated", "service_role"}:
                raise ValueError("DDL_ROLE_INVALID")
            if database != "postgres" or major != 17 or count != 1 or first != "004" or last != "004":
                raise ValueError("DATABASE_OR_ALEMBIC_NOT_004")
            if not can_create:
                raise ValueError("DDL_SCHEMA_CREATE_MISSING")
            ownership = connection.scalar(text("""SELECT bool_and(pg_get_userbyid(relowner)=current_user)
                FROM pg_class WHERE relnamespace='public'::regnamespace AND relname IN
                ('operations','fixed_income_investments','fixed_income_lots',
                 'fixed_income_movements','fixed_income_observations')"""))
            function_ownership = connection.scalar(text("""SELECT bool_and(pg_get_userbyid(proowner)=current_user)
                FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname IN
                ('fi_validate_lot','fi_validate_movement','fi_validate_observation')"""))
            if not (superuser or ownership and function_ownership):
                raise ValueError("DDL_OWNERSHIP_MISSING")
    finally:
        engine.dispose()
    return True


def main():
    try:
        url = validate_url(getpass("URL da role DDL (entrada oculta): "))
        ca = ca_path(url)
        check(url, ca)
        print("DDL_PREFLIGHT=PASS; sslmode=verify-full; role=DDL; database=postgres; alembic=004; ownership=PASS")
        return 0
    except ValueError as exc:
        print("DDL_PREFLIGHT=FAIL; reason=" + str(exc))
        return 1
    except Exception:
        print("DDL_PREFLIGHT=FAIL; reason=CONNECTION_OR_QUERY")
        return 1


if __name__ == "__main__":
    sys.exit(main())
