"""Current-schema backup checks use synthetic URLs and archive entries only."""
import io

from scripts import backup_supabase_009 as base
from scripts import backup_supabase_010 as current
from scripts.backup_archive import MAGIC_010, encrypt_stream, sha256_file
from restore_supabase_backup import archive_version, validate_backup


def configured_v010():
    old = base.REVISION, base.MAGIC, base.REQUIRED_TABLES
    current.configure()
    return old


def test_v010_backup_requires_snapshot_table_and_matching_revision():
    old = configured_v010()
    try:
        assert base.REVISION == "010" and base.MAGIC == MAGIC_010
        assert "portfolio_valuation_observations" in base.REQUIRED_TABLES
        assert base.preflight_failures(("postgres", "17", "010", "backup_reader"), "postgres") == []
        assert base.preflight_failures(("postgres", "17", "009", "backup_reader"), "postgres") == ["alembic_version"]
        archived = "COPY public.alembic_version (version_num) FROM stdin;\n010\n\\.\n"
        assert base.parse_archived_alembic_version(archived) == "010"
    finally:
        base.REVISION, base.MAGIC, base.REQUIRED_TABLES = old


def test_v010_restore_accepts_only_matching_versioned_archive(tmp_path):
    backup = tmp_path / "synthetic-v2.idbackup"
    with backup.open("wb") as target:
        encrypt_stream(io.BytesIO(b"synthetic postgres custom archive"), target,
                       "Synthetic-only-passphrase-2026", magic=MAGIC_010)
    assert validate_backup(backup, sha256_file(backup)) == backup.resolve()
    assert archive_version(backup) == "010"
