"""Offline preflight checks; no PostgreSQL connection or migration."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "preflight_release_004.py"
SPEC = importlib.util.spec_from_file_location("preflight_release_004", SCRIPT)
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def test_accepts_only_verified_ddl_url_without_leaking_password():
    good = "postgresql+psycopg://postgres.project:fictional@pooler.example:5432/postgres?sslmode=verify-full"
    assert preflight.validate_url(good).username == "postgres.project"
    for bad in (good.replace("postgres.project", "investment_runtime.project"),
                good.replace("verify-full", "require"),
                good.replace("/postgres?", "/other?")):
        with pytest.raises(ValueError) as error:
            preflight.validate_url(bad)
        assert "fictional" not in str(error.value)


def test_preflight_file_has_no_migration_entrypoint():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "command.upgrade" not in source
    assert "SET TRANSACTION READ ONLY" in source
