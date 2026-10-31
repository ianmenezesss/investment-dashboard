"""Validation of the encrypted 009 restore input; no Docker or database access."""
from pathlib import Path

import pytest

import restore_supabase_backup as restore
from scripts.backup_archive import encrypt_stream, sha256_file
import io


def make_archive(path):
    with path.open("wb") as destination:
        encrypt_stream(io.BytesIO(b"synthetic-only custom archive"), destination,
                       "Synthetic-only-passphrase-2026")
    return path


def test_restore_accepts_only_existing_external_encrypted_archive(tmp_path):
    archive = make_archive(tmp_path / "one-backup.idbackup")
    assert restore.validate_backup(archive) == archive.resolve()
    assert restore.validate_backup(archive, sha256_file(archive)) == archive.resolve()

    with pytest.raises(RuntimeError, match="SHA-256"):
        restore.validate_backup(archive, "0" * 64)
    with pytest.raises(RuntimeError, match="64 dígitos"):
        restore.validate_backup(archive, "not-a-digest")

    bad_format = tmp_path / "invalid.idbackup"
    bad_format.write_bytes(b"not-an-IDBKP009-archive" * 3)
    with pytest.raises(RuntimeError, match="IDBKP009"):
        restore.validate_backup(bad_format)

    with pytest.raises(RuntimeError, match="fora do repositório"):
        restore.validate_backup(Path(__file__).resolve().parents[2] / "not-a-backup.idbackup")


def test_restore_cli_has_no_destination_or_database_url_option():
    args = restore.parse_args(["--backup", "C:/safe/one-backup.idbackup", "--sha256", "a" * 64])
    assert args.backup.name == "one-backup.idbackup"
    assert args.sha256 == "a" * 64
    with pytest.raises(SystemExit):
        restore.parse_args(["--backup", "C:/safe/one-backup.idbackup", "--database-url", "production"])


def test_restore_diagnostics_redact_credentials_and_financial_details():
    output = restore.safe_output(
        "ERROR: restore failed\nDETAIL: Key (amount)=12345.67\n"
        "password=secret token=fictional-token Authorization: Bearer fictional-token "
        "postgres://user:pass@localhost/db",
        "other-secret",
    )
    assert "ERROR: restore failed" in output
    assert "12345.67" not in output
    assert "pass@localhost" not in output
    assert "password=[REDACTED]" in output
    assert "token=[REDACTED]" in output
    assert "fictional-token" not in output
