"""Encrypted, read-only backup for invited-account schema 011."""
try:
    from . import backup_supabase_010 as backup
    from .backup_archive import MAGIC_011
except ImportError:
    import backup_supabase_010 as backup
    from backup_archive import MAGIC_011

def configure():
    configured = backup.configure()
    configured.REVISION = "011"
    configured.MAGIC = MAGIC_011
    configured.REQUIRED_TABLES = configured.REQUIRED_TABLES | {"account_members", "account_invitations"}
    return configured

def main(argv=None):
    return configure().main(argv)

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("Backup NÃO aprovado: " + backup.safe_text(str(exc)), file=__import__("sys").stderr)
        raise SystemExit(1)
