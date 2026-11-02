from types import SimpleNamespace
from uuid import UUID
import time

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app import accounts
from app.auth import Principal


USER = UUID("22222222-2222-4222-8222-222222222222")
EMAIL = "person@example.test"


class FakeDb:
    def __init__(self, results):
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        self.results = iter(results)
        self.calls = []
    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
    def scalar(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        return next(self.results)
    def commit(self): pass
    def rollback(self): pass


def principal(*, auth_time=None):
    return Principal(USER, EMAIL, True, int(time.time()) if auth_time is None else auth_time)


def supabase_settings():
    from pydantic import SecretStr
    return SimpleNamespace(auth_mode="supabase", supabase_url="https://project.example",
                           supabase_service_role_key=SecretStr("fictional-service-key"))


def test_delete_requires_exact_confirmation_and_fresh_authentication():
    for confirmation, auth_time, expected in (
        ("delete", int(time.time()), 400),
        ("EXCLUIR MINHA CONTA", int(time.time()) - 301, 403),
    ):
        with pytest.raises(HTTPException) as error:
            accounts._require_recent_delete_confirmation(principal(auth_time=auth_time), confirmation)
        assert error.value.status_code == expected
    with pytest.raises(HTTPException) as error:
        accounts._require_recent_delete_confirmation(Principal(None), "EXCLUIR MINHA CONTA")
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        accounts._require_recent_delete_confirmation(Principal(USER, EMAIL, True, None), "EXCLUIR MINHA CONTA")
    assert error.value.status_code == 403


def test_delete_body_cannot_select_another_account():
    with pytest.raises(ValidationError):
        accounts.DeleteAccountInput.model_validate({
            "confirmation": "EXCLUIR MINHA CONTA", "user_id": "11111111-1111-4111-8111-111111111111"})


def test_deletion_fails_closed_outside_postgresql_and_in_local_auth(monkeypatch):
    monkeypatch.setattr(accounts, "settings", supabase_settings())
    sqlite_db = FakeDb([])
    sqlite_db.bind.dialect.name = "sqlite"
    with pytest.raises(HTTPException) as error:
        accounts._run_deletion_function(sqlite_db, "dashboard_account_deletion_state", principal())
    assert error.value.status_code == 503
    monkeypatch.setattr(accounts, "settings", SimpleNamespace(auth_mode="local"))
    with pytest.raises(HTTPException) as error:
        accounts.delete_own_account(accounts.DeleteAccountInput(confirmation="EXCLUIR MINHA CONTA"), principal(), FakeDb([]))
    assert error.value.status_code == 403


def test_deletion_runs_only_ordered_self_scoped_phases(monkeypatch):
    monkeypatch.setattr(accounts, "settings", supabase_settings())
    monkeypatch.setattr(accounts, "_verify_supabase_email", lambda *_: None)
    auth_deletions = []
    def delete_identity(user_id):
        auth_deletions.append(user_id)
        return True
    monkeypatch.setattr(accounts, "_delete_supabase_identity", delete_identity)
    db = FakeDb([None, "requested", "financial_data_deleted", "auth_identity_deleted", True])
    result = accounts.delete_own_account(accounts.DeleteAccountInput(confirmation="EXCLUIR MINHA CONTA"), principal(), db)
    assert result == {"status": "deleted"}
    functions = [sql.split("public.", 1)[1].split("(", 1)[0]
                 for sql, _ in db.calls if "SELECT public." in sql]
    assert functions == ["dashboard_account_deletion_state", "begin_dashboard_account_deletion",
                        "purge_dashboard_account_data", "mark_dashboard_auth_identity_deleted",
                        "finish_dashboard_account_deletion"]
    assert auth_deletions == [USER]
    for sql, parameters in db.calls:
        if "SELECT public." in sql and parameters and "user_id" in parameters:
            assert parameters["user_id"] == USER


def test_partial_auth_failure_leaves_a_job_that_can_be_resumed(monkeypatch):
    monkeypatch.setattr(accounts, "settings", supabase_settings())
    monkeypatch.setattr(accounts, "_verify_supabase_email", lambda *_: None)
    calls = 0
    def delete_identity(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPException(503, "retomável")
        return False  # Supabase confirms it was already deleted.
    monkeypatch.setattr(accounts, "_delete_supabase_identity", delete_identity)

    first_db = FakeDb([None, "requested", "financial_data_deleted"])
    with pytest.raises(HTTPException) as error:
        accounts.delete_own_account(accounts.DeleteAccountInput(confirmation="EXCLUIR MINHA CONTA"), principal(), first_db)
    assert error.value.status_code == 503
    assert "mark_dashboard_auth_identity_deleted" not in str(first_db.calls)

    retry_db = FakeDb(["financial_data_deleted", "auth_identity_deleted", True])
    result = accounts.delete_own_account(accounts.DeleteAccountInput(confirmation="EXCLUIR MINHA CONTA"), principal(), retry_db)
    assert result == {"status": "deleted"}
    assert calls == 2
    assert "begin_dashboard_account_deletion" not in str(retry_db.calls)
    assert "purge_dashboard_account_data" not in str(retry_db.calls)
