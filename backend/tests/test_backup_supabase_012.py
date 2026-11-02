from scripts import backup_supabase_012
from scripts.backup_archive import MAGIC_012


def test_v3_backup_requires_head_012_and_deletion_fixture_tables():
    configured = backup_supabase_012.configure()
    assert configured.REVISION == "012"
    assert configured.MAGIC == MAGIC_012
    assert {"account_deletion_jobs", "account_deletion_audit", "account_fixture_loads"} <= configured.REQUIRED_TABLES
