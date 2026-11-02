"""Encrypted, read-only backup for Alembic head 015."""
try:
    from .backup_supabase import BackupConfig, run_backup
    from .backup_archive import MAGIC_015
except ImportError:
    from backup_supabase import BackupConfig, run_backup
    from backup_archive import MAGIC_015


def main():
    configured = BackupConfig()
    configured.REVISION = "015"
    configured.MAGIC = MAGIC_015
    run_backup(configured)


if __name__ == "__main__":
    main()
