"""Encrypted, read-only public-schema backup for access reconstruction head 018."""
try:
    from .backup_profiles import configure_backup
    from .backup_supabase_009 import safe_text
except ImportError:
    from backup_profiles import configure_backup
    from backup_supabase_009 import safe_text


def configure():
    return configure_backup("018")


def main(argv=None):
    return configure().main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("Backup NÃO aprovado: " + safe_text(str(exc)), file=__import__("sys").stderr)
        raise SystemExit(1)
