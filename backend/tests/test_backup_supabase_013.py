from scripts import backup_supabase_013
from scripts.backup_archive import MAGIC_013


def test_v3_trial_requests_backup_requires_head_013_and_private_requests_table():
    configured = backup_supabase_013.configure()
    assert configured.REVISION == "013"
    assert configured.MAGIC == MAGIC_013
    assert {"account_deletion_jobs", "account_deletion_audit", "account_fixture_loads",
            "account_access_requests", "account_access_request_limits"} <= configured.REQUIRED_TABLES
