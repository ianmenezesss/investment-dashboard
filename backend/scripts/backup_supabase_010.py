"""Create an encrypted, read-only backup for Alembic head 010.

This reuses the hardened 009 workflow while requiring the v2.0 observation table
and the matching IDBKP010 archive marker.
"""
try:
    from . import backup_supabase_009 as backup
    from .backup_archive import MAGIC_010
except ImportError:  # Direct execution from any working directory.
    import backup_supabase_009 as backup
    from backup_archive import MAGIC_010

def configure():
    backup.REVISION = "010"
    backup.MAGIC = MAGIC_010
    backup.REQUIRED_TABLES = backup.REQUIRED_TABLES | {"portfolio_valuation_observations"}
    return backup


def main(argv=None):
    return configure().main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("Backup NÃO aprovado: " + backup.safe_text(str(exc)), file=__import__("sys").stderr)
        raise SystemExit(1)
