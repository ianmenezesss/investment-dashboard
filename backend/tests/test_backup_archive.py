import io
from pathlib import Path
import sys

import pytest

from scripts.backup_archive import MAGIC, decrypt_stream, encrypt_stream
from scripts.backup_supabase_009 import parse_database_url, preflight_failures
sys.path.insert(0, str(Path(__file__).resolve().parent))
from restore_supabase_backup import validate_backup


def test_encrypted_archive_round_trip_and_digest():
    payload = (b"synthetic postgres custom archive fixture\x00" * 50_000)
    encrypted = io.BytesIO()
    size, encrypted_hash = encrypt_stream(io.BytesIO(payload), encrypted, "Synthetic-only-passphrase-2026")
    assert size == len(encrypted.getvalue())
    assert encrypted.getvalue().startswith(MAGIC)

    restored = io.BytesIO()
    restored_size, plaintext_hash = decrypt_stream(io.BytesIO(encrypted.getvalue()), restored, "Synthetic-only-passphrase-2026")
    assert restored.getvalue() == payload
    assert restored_size == len(payload)
    assert len(encrypted_hash) == len(plaintext_hash) == 64


@pytest.mark.parametrize("password", ["wrong-synthetic-passphrase", "Short"])
def test_wrong_or_short_passphrase_fails_without_accepting_archive(password):
    encrypted = io.BytesIO()
    encrypt_stream(io.BytesIO(b"synthetic fixture"), encrypted, "Synthetic-only-passphrase-2026")
    with pytest.raises(ValueError):
        decrypt_stream(io.BytesIO(encrypted.getvalue()), io.BytesIO(), password)


def test_modified_ciphertext_fails_authentication():
    encrypted = io.BytesIO()
    encrypt_stream(io.BytesIO(b"synthetic postgres archive"), encrypted, "Synthetic-only-passphrase-2026")
    changed = bytearray(encrypted.getvalue())
    changed[-20] ^= 1
    with pytest.raises(ValueError, match="Autenticação"):
        decrypt_stream(io.BytesIO(changed), io.BytesIO(), "Synthetic-only-passphrase-2026")


def test_unknown_or_truncated_archive_fails():
    with pytest.raises(ValueError, match="Formato"):
        decrypt_stream(io.BytesIO(b"not a backup file"), io.BytesIO(), "Synthetic-only-passphrase-2026")
    with pytest.raises(ValueError, match="truncado"):
        decrypt_stream(io.BytesIO(MAGIC + b"x" * 28), io.BytesIO(), "Synthetic-only-passphrase-2026")


def test_supabase_session_pooler_accepts_region_specific_hosts_and_requires_009():
    parsed = parse_database_url(
        "postgresql://postgres.synthetic-project:fictional-password@"
        "aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=verify-full"
    )
    assert parsed[0] == "aws-0-us-east-1.pooler.supabase.com"
    assert preflight_failures(("postgres", "17", "009", "backup_reader"), "postgres") == []
    assert "alembic_version" in preflight_failures(("postgres", "17", "008", "backup_reader"), "postgres")
    direct = parse_database_url("postgresql://postgres:fictional-password@db.abc123.supabase.co:5432/postgres?sslmode=verify-full")
    assert direct[0] == "db.abc123.supabase.co"


def test_backup_url_rejects_transaction_pooler_and_non_verifying_tls():
    with pytest.raises(ValueError):
        parse_database_url(
            "postgresql://postgres.synthetic-project:fictional-password@"
            "aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=verify-full"
        )
    with pytest.raises(ValueError):
        parse_database_url(
            "postgresql+psycopg://postgres.synthetic-project:fictional-password@"
            "aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require"
        )


def test_restorer_accepts_only_external_encrypted_archive_and_valid_optional_hash(tmp_path):
    encrypted = tmp_path / "fictional.idbackup"
    with encrypted.open("wb") as destination:
        encrypt_stream(io.BytesIO(b"synthetic fixture"), destination, "Synthetic-only-passphrase-2026")
    from scripts.backup_archive import sha256_file
    assert validate_backup(encrypted, sha256_file(encrypted)) == encrypted.resolve()
    with pytest.raises(RuntimeError, match="SHA-256"):
        validate_backup(encrypted, "0" * 64)
    with pytest.raises(RuntimeError, match=r"\.idbackup"):
        validate_backup(tmp_path / "not-a-dump.sql")
