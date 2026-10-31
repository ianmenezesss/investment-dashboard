"""Production backup CLI checks; all URLs and archive entries are synthetic."""
from pathlib import Path

import pytest

from scripts import backup_supabase_009 as backup


def test_supabase_urls_require_tls_and_accept_supported_endpoints():
    pooler = backup.parse_database_url(
        "postgresql+psycopg://postgres.projectref:fictional%3Asecret@"
        "aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=verify-full"
    )
    assert pooler[:5] == (
        "aws-0-us-east-1.pooler.supabase.com", 5432, "postgres",
        "postgres.projectref", "fictional:secret",
    )
    direct = backup.parse_database_url(
        "postgresql://postgres:fictional-password@db.abc123.supabase.co:5432/postgres?sslmode=verify-full"
    )
    assert direct[0] == "db.abc123.supabase.co"
    with pytest.raises(ValueError):
        backup.parse_database_url(
            "postgresql://postgres.projectref:fictional-password@"
            "aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=verify-full"
        )
    with pytest.raises(ValueError):
        backup.parse_database_url(
            "postgresql://postgres.projectref:fictional-password@"
            "aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require"
        )


def test_preflight_requires_postgres17_and_alembic009_without_connection_details():
    assert backup.preflight_failures(("postgres", "17", "009", "backup_reader"), "postgres") == []
    assert backup.preflight_failures(("postgres", "17", "008", "backup_reader"), "postgres") == [
        "alembic_version"
    ]
    assert backup.preflight_failures(("other", "16", "007", "backup_reader"), "postgres") == [
        "database", "server_major", "alembic_version"
    ]
    assert backup.preflight_failures(("malformed",), "postgres") == ["response_format"]


def test_tls_confirmation_requires_modern_client_connection():
    assert backup.client_tls_confirmed(
        "You are connected to database postgres\n"
        "SSL connection (protocol: TLSv1.3, cipher: TLS_AES_256_GCM_SHA384, compression: off)\n"
    )
    assert not backup.client_tls_confirmed("You are connected to database postgres\n")
    assert not backup.client_tls_confirmed("SSL connection (protocol: SSLv3, cipher: old)\n")


def test_dump_toc_requires_each_table_and_data_entry_for_009():
    names = sorted(backup.REQUIRED_TABLES)
    toc = "\n".join(
        [f"{100+i}; 1259 10 TABLE public {name} postgres" for i, name in enumerate(names)]
        + [f"{200+i}; 0 10 TABLE DATA public {name} postgres" for i, name in enumerate(names)]
    )
    tables, data = backup.parse_toc(toc)
    assert tables == data == backup.REQUIRED_TABLES
    assert "financial_events" in tables and "financial_event_revisions" in data


def test_archived_alembic_revision_must_be_009():
    sql = (
        "-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public\n"
        "COPY public.alembic_version (version_num) FROM stdin;\n009\n\\.\n"
    )
    assert backup.parse_archived_alembic_version(sql) == "009"
    with pytest.raises(ValueError):
        backup.parse_archived_alembic_version(sql.replace("\n009\n", "\n008\n"))


def test_diagnostics_redact_database_url_and_secrets():
    output = backup.safe_text(
        "connection postgresql://fictional-user:fictional-secret@host/db password=another-secret",
        ("fictional-secret",),
    )
    assert "fictional-secret" not in output
    assert "another-secret" not in output
    assert "[DATABASE_URL REDACTED]" in output


def test_output_must_be_new_idbackup_outside_repository(tmp_path):
    valid = backup.validate_output(tmp_path / "one-off.idbackup")
    assert valid.name == "one-off.idbackup"
    with pytest.raises(ValueError, match=r"\.idbackup"):
        backup.validate_output(tmp_path / "plain.sql")
    existing = tmp_path / "already-there.idbackup"
    existing.touch()
    with pytest.raises(ValueError, match="não sobrescreve"):
        backup.validate_output(existing)


def test_repository_path_is_rejected(tmp_path):
    repository = Path(__file__).resolve().parents[2]
    with pytest.raises(ValueError, match="fora do repositório"):
        backup.validate_output(repository / "should-not-be-created.idbackup")
