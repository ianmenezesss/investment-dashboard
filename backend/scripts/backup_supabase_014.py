"""Encrypted, read-only backup for Alembic head 014."""
try:
    from .backup_supabase import BackupConfig, run_backup
    from .backup_archive import MAGIC_014
except ImportError:
    from backup_supabase import BackupConfig, run_backup
    from backup_archive import MAGIC_014


def main():
    configured = BackupConfig()
    configured.REVISION = "014"
    configured.MAGIC = MAGIC_014
    run_backup(configured)


if __name__ == "__main__":
    main()
