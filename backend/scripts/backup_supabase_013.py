"""Encrypted, read-only backup for Alembic head 013."""
try:
    from . import backup_supabase_012 as backup
    from .backup_archive import MAGIC_013
except ImportError:
    import backup_supabase_012 as backup
    from backup_archive import MAGIC_013


def configure():
    configured = backup.configure()
    configured.REVISION = "013"
    configured.MAGIC = MAGIC_013
    configured.REQUIRED_TABLES = configured.REQUIRED_TABLES | {"account_access_requests", "account_access_request_limits"}
    return configured


def main(argv=None):
    return configure().main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        import sys
        print("Backup NÃO aprovado: " + backup.safe_text(str(exc)), file=sys.stderr)
        raise SystemExit(1)
