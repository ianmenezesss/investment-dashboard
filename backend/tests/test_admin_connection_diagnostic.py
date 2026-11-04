from types import SimpleNamespace

from pydantic import SecretStr
from sqlalchemy.engine import make_url

from scripts.diagnose_admin_connection import configuration_checks, safe_error


def test_driver_diagnostics_never_echo_connection_credentials():
    secret = "postgresql://private:never-print@secret-host/db"
    for message, category in (
        (f"root certificate file {secret} does not exist", "tls_ca_file"),
        (f"certificate verify failed {secret}", "tls_verification"),
        (f"password authentication failed {secret}", "authentication"),
        (f"could not translate host name {secret}", "dns"),
        (f"connection timeout {secret}", "timeout"),
    ):
        result = safe_error(RuntimeError(message))
        assert result == {"category": category, "sqlstate": None}
        assert "secret-host" not in str(result) and "never-print" not in str(result)


def test_explicit_ca_overrides_environment_without_exposing_either_path(monkeypatch):
    monkeypatch.setenv("PGSSLROOTCERT", "/hidden-valid-environment-file")
    raw = "postgresql+psycopg://operator.project:synthetic@tenant.pooler.supabase.com:5432/postgres?sslmode=verify-full&sslrootcert=C%3A%5Chidden-cert.pem"
    settings = SimpleNamespace(admin_database_url=SecretStr(raw), invitation_admin_ids=["synthetic-id"])
    result = configuration_checks(settings, SimpleNamespace(url=make_url(raw)))
    assert result["ca_source"] == "url" and result["verify_full"]
    assert result["session_pooler_endpoint"]
    assert "hidden" not in str(result) and "tenant" not in str(result)


def test_missing_engine_diagnostic_does_not_connect():
    settings = SimpleNamespace(admin_database_url=SecretStr(""))
    assert configuration_checks(settings, None) == {
        "admin_url_present": False, "admin_engine_created": False, "admin_url_outer_whitespace": False}
