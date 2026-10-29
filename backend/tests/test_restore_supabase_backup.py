"""Selection of the backup to restore; no Docker or financial data access."""
from pathlib import Path

import pytest

import restore_supabase_backup as restore


def test_selects_only_existing_nonempty_dump_in_backup_directory(tmp_path, monkeypatch):
    old = tmp_path / "old.dump"
    old.write_bytes(b"PGDMPold")
    current = tmp_path / "current.dump"
    current.write_bytes(b"PGDMPcurrent")
    monkeypatch.setattr(restore, "BACKUP", old)
    assert restore.select_backup_path([]) == old
    assert restore.select_backup_path(["--backup", str(current)]) == current

    empty = tmp_path / "empty.dump"
    empty.touch()
    outside = tmp_path.parent / "outside.dump"
    with pytest.raises(RuntimeError, match="inexistente ou vazio"):
        restore.select_backup_path(["--backup", str(empty)])
    with pytest.raises(RuntimeError, match="pasta de backups permitida"):
        restore.select_backup_path(["--backup", str(outside)])
    with pytest.raises(RuntimeError, match="pasta de backups permitida"):
        restore.select_backup_path(["--backup", str(tmp_path / "wrong.txt")])
