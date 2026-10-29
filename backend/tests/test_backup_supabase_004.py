"""Focused checks for the production backup command; no network or Docker calls."""
import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup_supabase_004.py"
SPEC = importlib.util.spec_from_file_location("backup_supabase_004", SCRIPT)
backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup)


def test_parse_postgres17_session_pooler_url_without_exposing_password():
    connection = (
        "postgresql+psycopg://postgres.projectref:p%3Aa%40ss@"
        "aws-1-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=verify-full"
    )
    host, port, database, user, password, query = backup.parse_database_url(connection)
    assert (host, port, database, user, password) == (
        backup.POOLER_HOST, 5432, "postgres", "postgres.projectref", "p:a@ss"
    )
    assert query["sslmode"] == ["verify-full"]
    with pytest.raises(ValueError) as error:
        backup.parse_database_url(connection.replace("verify-full", "require"))
    assert "p:a@ss" not in str(error.value)


def test_pgpass_escaping_and_environment_never_place_password_in_docker_args(monkeypatch):
    assert backup.pgpass_field(r"a:b\c") == r"a\:b\\c"
    args = backup.exec_env_args(backup.POOLER_HOST, 5432, "postgres", "fictional.user")
    assert not any("password" in arg.lower() or "fictional-secret" in arg for arg in args)
    assert not any("fictional.user" in arg or backup.POOLER_HOST in arg for arg in args)
    service = backup.service_file_contents(backup.POOLER_HOST, 5432, "postgres", "fictional.user")
    assert "sslmode=verify-full" in service
    assert "sslrootcert=/run/backup-certs/supabase-root.crt" in service
    assert "password" not in service.lower()
    dump_args = backup.pg_dump_exec_args(args, "fictional-container")
    assert "fictional-container" in dump_args
    assert "fictional.user" not in dump_args and backup.POOLER_HOST not in dump_args
    assert not any("fictional-secret" in arg or "p:a@ss" in arg for arg in dump_args)
    monkeypatch.setenv("DATABASE_URL", "fictional-database-secret")
    monkeypatch.setenv("PRODUCTION_RUNTIME_URL", "fictional-runtime-secret")
    monkeypatch.setenv("DB_PASSWORD", "fictional-password")
    inherited = backup.docker_environment()
    assert "DATABASE_URL" not in inherited and "PRODUCTION_RUNTIME_URL" not in inherited and "DB_PASSWORD" not in inherited
    assert "fictional-database-secret" not in inherited.values()
    assert "fictional-runtime-secret" not in inherited.values()
    assert "fictional-password" not in inherited.values()


def test_archive_index_distinguishes_table_definitions_and_data_entries():
    toc = """376; 1259 17674 TABLE public alembic_version postgres
380; 1259 17771 TABLE public fixed_income_investments postgres
382; 1259 17783 TABLE public fixed_income_lots postgres
384; 1259 17797 TABLE public fixed_income_movements postgres
378; 1259 17680 TABLE public operations postgres
386; 1259 17810 TABLE public fixed_income_observations postgres
4392; 0 17674 TABLE DATA public alembic_version postgres
4396; 0 17771 TABLE DATA public fixed_income_investments postgres
4398; 0 17783 TABLE DATA public fixed_income_lots postgres
4400; 0 17797 TABLE DATA public fixed_income_movements postgres
4394; 0 17680 TABLE DATA public operations postgres
4402; 0 17810 TABLE DATA public fixed_income_observations postgres"""
    tables, data = backup.parse_toc(toc)
    assert tables == backup.REQUIRED_TABLES
    assert data == backup.REQUIRED_TABLES


def test_backup_alembic_revision_is_read_from_dump_data():
    sql = """-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public
COPY public.alembic_version (version_num) FROM stdin;
004
\\.
"""
    assert backup.parse_archived_alembic_version(sql) == "004"
    assert backup.parse_archived_alembic_version(sql.replace("\n004\n", "\n003\n")) == "003"


def test_safe_diagnostics_redact_url_password_and_sensitive_fields():
    diagnostic = backup.safe_text(
        "could not connect to postgresql+psycopg://u:very-secret@pooler.example/db "
        "password=another-secret", ("very-secret",)
    )
    assert "very-secret" not in diagnostic and "another-secret" not in diagnostic
    assert "[DATABASE_URL REDACTED]" in diagnostic



def test_preflight_reports_failed_checks_without_connection_details():
    assert backup.preflight_failures(["postgres", "17", "004", "admin"], "postgres") == []
    assert backup.preflight_failures(["other", "16", "003", "admin"], "postgres") == [
        "database", "server_major", "alembic_version"
    ]
    assert backup.preflight_failures(["unexpected"], "postgres") == ["response_format"]


def test_client_tls_checks_psql_connection_not_server_pooler_hop():
    assert backup.client_tls_confirmed("You are connected to database postgres\nSSL connection (protocol: TLSv1.3, cipher: TLS_AES_256_GCM_SHA384, compression: off)\n")
    assert not backup.client_tls_confirmed("You are connected to database postgres\n")
    assert not backup.client_tls_confirmed("SSL connection (protocol: SSLv3, cipher: old)\n")


def test_pg_restore_reads_archive_from_stdin_without_dash_filename():
    for options in (("--list", "--file=/dev/stdout"), ("--file=/dev/null",),
                    ("--data-only", "--table=alembic_version", "--file=/dev/stdout")):
        args = backup.pg_restore_stdin_args("fictional-container", *options)
        assert args[:4] == ("exec", "-i", "fictional-container", "pg_restore")
        assert args[4:] == options
        assert "-" not in args
        assert any(option.startswith("--file=") for option in args)
