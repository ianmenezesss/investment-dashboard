"""Checks the disposable Docker command contract without starting Docker."""
import pytest
import subprocess

from run_postgres import (container_run_args, network_create_args, parse_loopback_port,
                          run_restore_role_setup, wait_for_postgres)


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
