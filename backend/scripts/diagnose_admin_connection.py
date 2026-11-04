"""Bounded Render diagnostics. No URL, identity, password or raw error output.

Default: configuration only, no connection. --connect-read-only opens at most
one connection per engine and checks only access-control/schema metadata.
"""
import argparse
import json
import os
from pathlib import Path, PureWindowsPath
import re
import ssl
import sys


def safe_error(error):
    original = getattr(error, "orig", error)
    state = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    state = state if isinstance(state, str) and re.fullmatch(r"[A-Z0-9]{5}", state) else None
    # Inspect locally, emit ONLY fixed labels. libpq errors often contain DSNs.
    message = str(original).lower()
    category = "unclassified"
    for needles, label in (
        (("root certificate file", "could not load root certificate"), "tls_ca_file"),
        (("certificate verify failed", "certificate verification failed", "does not match host name"), "tls_verification"),
        (("password authentication failed", "tenant or user not found", "authentication failed"), "authentication"),
        (("could not translate host name", "name or service not known", "getaddrinfo failed"), "dns"),
        (("network is unreachable", "no route to host"), "network_route"),
        (("connection refused",), "connection_refused"),
        (("maxclients", "too many clients", "remaining connection slots", "max client connections"), "connection_capacity"),
        (("queuepool limit",), "application_pool_timeout"),
        (("timeout", "timed out"), "timeout"),
    ):
        if any(needle in message for needle in needles):
            category = label
            break
    if state == "42501":
        category = "database_permission"
    elif state and state.startswith("28"):
        category = "authentication"
    elif state and state.startswith("42"):
        category = "schema_or_sql"
    return {"category": category, "sqlstate": state}


def configuration_checks(settings, admin_engine):
    raw = settings.admin_database_url.get_secret_value()
    result = {"admin_url_present": bool(raw.strip()), "admin_engine_created": admin_engine is not None,
              "admin_url_outer_whitespace": raw != raw.strip()}
    if admin_engine is None:
        return result
    url = admin_engine.url
    ca = url.query.get("sslrootcert", os.environ.get("PGSSLROOTCERT", ""))
    result.update({"driver_expected": url.drivername == "postgresql+psycopg",
        "verify_full": url.query.get("sslmode") == "verify-full",
        "session_pooler_endpoint": bool(url.host and url.host.endswith(".pooler.supabase.com") and url.port == 5432),
        "username_pooler_suffix_present": bool(url.username and "." in url.username),
        "admin_ids_configured": bool(settings.invitation_admin_ids),
        "ca_source": "url" if "sslrootcert" in url.query else "environment" if "PGSSLROOTCERT" in os.environ else "libpq_default",
        "ca_system": ca == "system", "ca_file_readable": False, "ca_pem_parseable": False,
        "ca_windows_path_on_linux": bool(os.name != "nt" and PureWindowsPath(str(ca)).is_absolute())})
    if ca and ca != "system":
        try:
            with open(ca, "rb") as certificate:
                certificate.read(1)
            result["ca_file_readable"] = True
            ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cafile=ca)
            result["ca_pem_parseable"] = True
        except (OSError, ValueError, ssl.SSLError):
            pass
    return result


def probe(engine, admin_id=None):
    from sqlalchemy import text
    phase = "connect"
    try:
        with engine.connect() as connection:
            connection = connection.execution_options(postgresql_readonly=True)
            with connection.begin():
                connection.execute(text("SET LOCAL statement_timeout='5s'"))
                phase = "select_1"
                connection.execute(text("SELECT 1"))
                result = {"ok": True, "transaction_read_only": connection.scalar(text("SHOW transaction_read_only")) == "on"}
                if not result["transaction_read_only"]:
                    return {"ok": False, "phase": "read_only_guard"}
                if admin_id is not None:
                    phase = "admin_context"
                    connection.execute(text("SELECT set_config('app.admin_id',:id,true)"), {"id": str(admin_id)})
                    result.update(dict(connection.execute(text("""SELECT
                        session_user='investment_access_operator' AS session_user_expected,
                        pg_has_role(session_user,'investment_access_admin','MEMBER') AS admin_group_member,
                        public.dashboard_admin_authorized() AS admin_context_authorized,
                        r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb
                          OR has_table_privilege(session_user,'public.operations','SELECT')
                          OR has_table_privilege(session_user,'public.account_members','UPDATE') AS unsafe_login
                        FROM pg_roles r WHERE r.rolname=session_user""")).mappings().one()))
                    for table in ("account_members", "account_invitations", "account_access_requests"):
                        phase = "schema_" + table
                        connection.execute(text(f"SELECT 1 FROM public.{table} LIMIT 0"))
                # Never retain a transaction, session GUC or write.
                connection.rollback()
                return result
    except Exception as error:
        return {"ok": False, "phase": phase, **safe_error(error)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connect-read-only", action="store_true")
    args = parser.parse_args(argv)
    root = Path.cwd() if (Path.cwd() / "app" / "database.py").is_file() else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    try:
        from app.database import settings, engine, admin_engine
    except Exception:
        print(json.dumps({"ok": False, "phase": "settings_or_engine_initialization", "details_omitted": True}))
        return 1
    result = {"configuration": configuration_checks(settings, admin_engine)}
    if args.connect_read_only:
        if engine.dialect.name != "postgresql":
            result["probe"] = "postgresql_required"
        else:
            result["runtime"] = probe(engine)
            result["admin"] = probe(admin_engine, settings.invitation_admin_ids[0]) if admin_engine is not None and settings.invitation_admin_ids else {"ok": False, "phase": "admin_configuration_missing"}
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
