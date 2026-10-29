"""Checks the disposable Docker command contract without starting Docker."""
import pytest
import subprocess

from run_postgres import (container_run_args, network_create_args, parse_loopback_port,
                          run_restore_role_setup, wait_for_postgres)
from restore_supabase_backup import (docker_run_args, expected_tables_for_revision,
                                     parse_archive_index, postgres_restore_args, safe_output,
                                     validate_archive_schema)


def test_disposable_network_and_both_containers_bind_only_loopback():
    network = "investment-homologation-net-fictional"
    assert network_create_args(network) == (
        "network", "create", "--driver", "bridge", "--opt",
        "com.docker.network.bridge.host_binding_ipv4=127.0.0.1", network,
    )
    for name, db in (("source-fictional", "source_fictional"),
                     ("restore-fictional", "restore_fictional")):
        args = container_run_args(name, network, db, "fictional-password", "fictional")
        assert "--publish=127.0.0.1::5432/tcp" in args
        assert "--pull=never" in args
        assert "--rm" in args
        assert "--tmpfs" in args
        assert "/var/lib/postgresql/data" in args
        assert "--network" in args and args[args.index("--network") + 1] == network
        assert "--volume" not in args and "-v" not in args
        assert not any("0.0.0.0:" in arg for arg in args)


def test_port_mapping_requires_exactly_one_ipv4_loopback_binding():
    assert parse_loopback_port("127.0.0.1:49152") == 49152
    for bad in ("", "0.0.0.0:49152", "[::1]:49152", "127.0.0.1:0",
                "127.0.0.1:65536", "127.0.0.1:49152\n0.0.0.0:49152"):
        with pytest.raises(ValueError):
            parse_loopback_port(bad)


def test_role_setup_failure_reports_exit_stdout_stderr_and_redacts_secrets(monkeypatch):
    password = "fictional-db-secret"

    def failed_psql(*args, **kwargs):
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert args[0][args[0].index("-h") + 1] == "127.0.0.1"
        assert args[0][args[0].index("-d") + 1] == "postgres"
        return subprocess.CompletedProcess(
            args[0], 3, stdout="NOTICE password=fictional-db-secret",
            stderr="ERROR: role creation failed\nDETAIL: token=fictional-token"
        )

    monkeypatch.setattr(subprocess, "run", failed_psql)
    with pytest.raises(RuntimeError) as error:
        run_restore_role_setup("docker", "restore-fictional", "postgres", "CREATE ROLE", password)
    message = str(error.value)
    assert "psql exit code=3" in message
    assert "stdout=NOTICE password=[REDACTED]" in message
    assert "ERROR: role creation failed" in message
    assert "DETAIL: token=[REDACTED]" in message
    assert password not in message
    assert "fictional-token" not in message


def test_restore_readiness_uses_tcp_and_waits_until_pg_is_ready(monkeypatch):
    calls = []
    outcomes = [1, 0]

    def probe(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, outcomes.pop(0), stdout="", stderr="starting")

    monkeypatch.setattr(subprocess, "run", probe)
    monkeypatch.setattr("run_postgres.time.sleep", lambda _: None)
    wait_for_postgres("docker", "restore-fictional", "restore_db", "fictional-password", attempts=2)
    assert len(calls) == 2
    assert calls[0][calls[0].index("-h") + 1] == "127.0.0.1"
    assert calls[0][calls[0].index("-p") + 1] == "5432"


def test_real_dump_restore_uses_disposable_isolated_container_and_read_only_backup():
    run = docker_run_args("restore-fixture", "db_fixture", "secret-fixture", r"E:\fixture.dump", "run-fixture")
    assert "--network" in run and run[run.index("--network") + 1] == "none"
    assert run[run.index("--label") + 1] == "com.investment-dashboard.realbackup=run-fixture"
    assert run[-1] == "postgres:17-alpine"
    assert "--tmpfs" in run
    assert "--mount" in run
    mount = run[run.index("--mount") + 1]
    assert "source=E:\\fixture.dump" in mount and "readonly" in mount
    assert '"' not in mount and "'" not in mount
    assert "--volume" not in run and "-v" not in run
    assert not any("0.0.0.0" in arg or "--publish" in arg for arg in run)

    restore = postgres_restore_args("restore-fixture", "db_fixture", "secret-fixture")
    assert restore[restore.index("-e") + 1] == "PGPASSWORD=secret-fixture"
    assert restore[restore.index("-h") + 1] == "127.0.0.1"
    assert "--exit-on-error" in restore
    assert "--schema=public" in restore
    assert "--no-owner" in restore and "--no-privileges" in restore
    assert restore[-1] == "/backup/input.dump"


def test_restore_diagnostics_redact_credentials_and_possible_financial_details():
    diagnostic = safe_output(
        'ERROR: restore failed\nDETAIL: Key (amount)=12345.67\n'
        'password=secret token=abc Authorization: Bearer fictional-token '
        'postgres://user:pass@localhost/db', "other-secret"
    )
    assert "ERROR: restore failed" in diagnostic
    assert "12345.67" not in diagnostic
    assert "pass@localhost" not in diagnostic
    assert "password=[REDACTED]" in diagnostic
    assert "token=[REDACTED]" in diagnostic
    assert "fictional-token" not in diagnostic


def test_archive_index_and_expected_schema_follow_stored_alembic_revision():
    toc = "\n".join((
        "; 10; 0 100 TABLE public operations postgres",
        "; 11; 0 100 TABLE DATA public operations postgres",
        "; 12; 0 200 TABLE public fixed_income_investments postgres",
        "; 13; 0 200 TABLE DATA public fixed_income_investments postgres",
        "; 14; 0 300 TABLE public fixed_income_lots postgres",
        "; 15; 0 400 TABLE public fixed_income_movements postgres",
        "; 16; 0 500 TABLE public alembic_version postgres",
        "; 17; 0 501 TABLE public auth_users postgres",
    ))
    tables, table_data = parse_archive_index(toc)
    assert tables == {"operations", "fixed_income_investments", "fixed_income_lots", "fixed_income_movements", "alembic_version"}
    assert table_data == {"operations", "fixed_income_investments"}
    assert expected_tables_for_revision("003") == tables - {"alembic_version"}
    assert "fixed_income_observations" not in expected_tables_for_revision("003")
    assert "fixed_income_observations" in expected_tables_for_revision("004")
    assert validate_archive_schema("003", tables, tables) == tables - {"alembic_version"}
    with pytest.raises(RuntimeError, match="Alembic 004.*fixed_income_observations"):
        validate_archive_schema("004", tables, tables)
    incomplete = tables - {"fixed_income_movements"}
    with pytest.raises(RuntimeError, match="Restore incompleto.*fixed_income_movements"):
        validate_archive_schema("003", tables, incomplete)


def test_archive_index_parses_exact_real_backup_toc_lines():
    toc = """376; 1259 17674 TABLE public alembic_version postgres
380; 1259 17771 TABLE public fixed_income_investments postgres
382; 1259 17783 TABLE public fixed_income_lots postgres
384; 1259 17797 TABLE public fixed_income_movements postgres
378; 1259 17680 TABLE public operations postgres
4392; 0 17674 TABLE DATA public alembic_version postgres
4396; 0 17771 TABLE DATA public fixed_income_investments postgres
4398; 0 17783 TABLE DATA public fixed_income_lots postgres
4400; 0 17797 TABLE DATA public fixed_income_movements postgres
4394; 0 17680 TABLE DATA public operations postgres"""
    tables, table_data = parse_archive_index(toc)
    expected = {
        "alembic_version", "fixed_income_investments", "fixed_income_lots",
        "fixed_income_movements", "operations",
    }
    assert tables == expected
    assert table_data == expected
