from scripts import backup_supabase_011
from scripts.backup_archive import MAGIC_011


def test_v3_backup_requires_head_011_and_new_account_tables():
    configured = backup_supabase_011.configure()
    assert configured.REVISION == "011"
    assert configured.MAGIC == MAGIC_011
    assert {"portfolio_valuation_observations", "account_members", "account_invitations"} <= configured.REQUIRED_TABLES
