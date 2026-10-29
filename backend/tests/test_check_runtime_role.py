"""Focused offline checks for the runtime-role gate."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_runtime_role.py"
SPEC = importlib.util.spec_from_file_location("check_runtime_role", SCRIPT)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def test_rejects_admin_role_and_weak_tls_without_echoing_url():
    good = "postgresql+psycopg://investment_runtime.project:fictional@pooler.example:5432/postgres?sslmode=verify-full"
    assert checker.parse_url(good).username == "investment_runtime.project"
    for bad in (good.replace("investment_runtime", "postgres"),
                good.replace("verify-full", "require")):
        with pytest.raises(ValueError) as error:
            checker.parse_url(bad)
        assert "fictional" not in str(error.value)


def test_render_comparison_checks_role_host_port_database_but_not_password():
    first = checker.parse_url("postgresql+psycopg://investment_runtime.project:first@pooler.example:5432/postgres?sslmode=verify-full")
    second = checker.parse_url("postgresql+psycopg://investment_runtime.project:second@pooler.example:5432/postgres?sslmode=verify-full")
    wrong_host = checker.parse_url("postgresql+psycopg://investment_runtime.project:second@another.example:5432/postgres?sslmode=verify-full")
    assert checker.same_render_configuration(first, second)
    assert not checker.same_render_configuration(first, wrong_host)
