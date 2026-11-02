"""Encrypted, read-only backup for Alembic head 012."""
try:
    from . import backup_supabase_011 as backup
    from .backup_archive import MAGIC_012
except ImportError:
    import backup_supabase_011 as backup
    from backup_archive import MAGIC_012


def configure():
    configured = backup.configure()
    configured.REVISION = "012"
    configured.MAGIC = MAGIC_012
    configured.REQUIRED_TABLES = configured.REQUIRED_TABLES | {
        "account_deletion_jobs", "account_deletion_audit", "account_fixture_loads",
    }
    return configured


def main(argv=None):
    return configure().main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("Backup NÃO aprovado: " + backup.safe_text(str(exc)), file=__import__("sys").stderr)
        raise SystemExit(1)
