"""Read-only release gate for the runtime role; never prints connection strings."""
from getpass import getpass
import os
from pathlib import Path
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

CORE = ("operations", "fixed_income_investments", "fixed_income_lots",
        "fixed_income_movements", "fixed_income_observations")
NEW = ("fixed_income_investment_archives", "fixed_income_application_revisions")


def parse_url(raw):
    try:
        url = make_url(raw)
        if (url.drivername != "postgresql+psycopg" or not url.password
                or not url.username or not (url.username == "investment_runtime"
                or url.username.startswith("investment_runtime."))
                or not url.host or not url.database or url.query.get("sslmode") != "verify-full"):
            raise ValueError
        return url
    except Exception:
        raise ValueError("URL da role runtime inválida; confira formato, role e sslmode sem exibir a URL") from None


def same_render_configuration(runtime, render):
    return (runtime.username, runtime.host, runtime.port or 5432, runtime.database) == (render.username, render.host, render.port or 5432, render.database)


def check_sql(connection):
    connection.execute(text("SET TRANSACTION READ ONLY"))
    identity = connection.execute(text("""SELECT current_user, session_user, current_database(),
        r.rolcanlogin, r.rolinherit, r.rolsuper, r.rolbypassrls,
        r.rolcreatedb, r.rolcreaterole, r.rolreplication,
        (SELECT count(*) FROM pg_auth_members WHERE member=r.oid)
        FROM pg_roles r WHERE r.rolname=current_user""")).one_or_none()
    identity_ok = bool(identity and identity[0] == "investment_runtime" and identity[2] == "postgres"
                       and identity[3] and not any(identity[4:10]) and identity[10] == 0)
    tables = connection.execute(text("""SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
        pg_get_userbyid(c.relowner),
        (SELECT count(*) FROM pg_policy p WHERE p.polrelid=c.oid)
        FROM pg_class c WHERE c.relnamespace='public'::regnamespace
        AND c.relname IN ('operations','fixed_income_investments','fixed_income_lots',
        'fixed_income_movements','fixed_income_observations',
        'fixed_income_investment_archives','fixed_income_application_revisions')""")).all()
    found = {row[0]: row for row in tables}
    new_count = sum(name in found for name in NEW)
    stage = "008" if new_count == 2 else "partial" if new_count else "004"
    expected = CORE + NEW if stage != "004" else CORE
    rls_ok = all(name in found and found[name][1] and found[name][2]
                 and found[name][3] != "investment_runtime" and found[name][4] > 0
                 for name in expected)
    grants_ok = stage != "partial"
    if stage == "008":
        for table in NEW:
            flags = connection.execute(text("""SELECT
                has_table_privilege(current_user,:table,'SELECT'),
                has_table_privilege(current_user,:table,'INSERT'),
                has_table_privilege(current_user,:table,'UPDATE'),
                has_table_privilege(current_user,:table,'DELETE'),
                has_table_privilege(current_user,:table,'TRUNCATE'),
                has_sequence_privilege(current_user,:sequence,'USAGE')"""),
                {"table": "public." + table, "sequence": "public." + table + "_id_seq"}).one()
            grants_ok &= bool(flags[0] and flags[1] and not any(flags[2:5]) and flags[5])
        grants_ok &= bool(connection.scalar(text("SELECT has_function_privilege(current_user,'public.fi_effective_movements()','EXECUTE')")))
    return identity_ok, rls_ok, grants_ok, stage


def main():
    try:
        runtime = parse_url(getpass("URL independente da role investment_runtime (entrada oculta): "))
        render = parse_url(getpass("DATABASE_URL copiada do painel Render (entrada oculta): "))
        render_ok = same_render_configuration(runtime, render)
        ca = os.environ.get("PGSSLROOTCERT") or input("Caminho da CA oficial local (não secreta): ").strip()
        if not ca or not Path(ca).is_file():
            raise ValueError("CA oficial local ausente")
        # Enforce verify-full even if a caller supplied conflicting libpq variables.
        engine = create_engine(runtime, hide_parameters=True, pool_pre_ping=True,
                               connect_args={"connect_timeout": 5, "sslmode": "verify-full", "sslrootcert": ca})
        try:
            with engine.connect() as connection:
                identity_ok, rls_ok, grants_ok, stage = check_sql(connection)
        finally:
            engine.dispose()
        print(f"SQL_IDENTITY={'PASS' if identity_ok else 'FAIL'}")
        print(f"RLS_FORCE={'PASS' if rls_ok else 'FAIL'}")
        print(f"GRANTS_008={'NOT_APPLICABLE_BEFORE_008' if stage == '004' else 'PASS' if grants_ok else 'FAIL'}")
        print(f"RENDER_CONFIG_MATCH={'PASS' if render_ok else 'FAIL'}")
        print("RENDER_LIVE_PROCESS=NOT_VERIFIED_WITHOUT_SHELL")
        passed = identity_ok and rls_ok and grants_ok and render_ok
        print(f"RUNTIME_ROLE={'PASS' if passed else 'FAIL'}; stage={stage}; proof=runtime_SQL_and_Render_dashboard_value")
        return 0 if passed else 1
    except Exception as exc:
        print("RUNTIME_ROLE=FAIL; reason=" + ("invalid_input" if isinstance(exc, ValueError) else "connection_or_query"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
