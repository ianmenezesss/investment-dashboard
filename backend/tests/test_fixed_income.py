from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace
from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth import authenticate, Principal
from app.database import Base, get_db
from app.main import app
from app.fixed_income.ledger import principal_balances, total_principal

A = UUID("11111111-1111-4111-8111-111111111111")
B = UUID("22222222-2222-4222-8222-222222222222")
PATH = "/api/fixed-income/investments"
CONTRACT = dict(issuer="Banco fictício", product_name="CDB exemplo", product_type="CDB",
    remuneration="FIXED", indexer="NONE", contracted_rate="12.34567890",
    application_date="2025-01-01", maturity_date="2027-01-01")


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def fk(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    def db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    try:
        with TestClient(app) as http:
            yield http
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def create(client, **overrides):
    result = client.post(PATH, json=CONTRACT | overrides)
    assert result.status_code == 201, result.text
    return result.json()["id"]


def apply(client, investment, amount="1000", day="2025-01-01"):
    result = client.post(f"{PATH}/{investment}/applications", json={"date": day, "principal_amount": amount})
    assert result.status_code == 201, result.text
    return result.json()


def redeem(client, investment, lot, amount, day="2025-01-03", **extra):
    return client.post(f"{PATH}/{investment}/redemptions", json={"lot_id": lot, "date": day, "principal_amount": amount, **extra})


@pytest.mark.parametrize("remuneration,indexer,rate", [("FIXED", "NONE", "12.34567890"), ("CDI", "CDI", "110.00000001")])
def test_supported_contracts_have_no_invented_balance_or_income(client, remuneration, indexer, rate):
    investment = create(client, remuneration=remuneration, indexer=indexer, contracted_rate=rate)
    data = client.get(f"{PATH}/{investment}").json()
    assert D(data["contracted_rate"]) == D(rate)
    assert data["principal_balance"] == "0" and data["lots"] == []
    assert not {"market_value", "income", "tax", "return_percent"}.intersection(data)
    assert len(client.get(PATH).json()) == 1


def test_multiple_lots_partial_and_total_redemptions_preserve_history_and_cash_distinction(client):
    investment = create(client)
    first = apply(client, investment, "1000.12345678")
    second = apply(client, investment, "200", "2025-01-02")
    assert first["lot_id"] != second["lot_id"] and first["cash_received"] is None
    sale = redeem(client, investment, first["lot_id"], "400.12345678", cash_received="430")
    assert sale.status_code == 201
    detail = client.get(f"{PATH}/{investment}").json()
    assert D(detail["principal_balance"]) == 800
    assert [D(lot["principal_balance"]) for lot in detail["lots"]] == [D(600), D(200)]
    assert redeem(client, investment, first["lot_id"], "600").status_code == 201
    assert redeem(client, investment, first["lot_id"], "0.00000001").status_code == 422
    assert redeem(client, investment, second["lot_id"], "200").status_code == 201
    data = client.get(f"{PATH}/{investment}").json()
    assert D(data["principal_balance"]) == 0 and len(data["lots"]) == 2
    movements = client.get(f"{PATH}/{investment}/movements").json()
    assert len(movements) == 5
    assert D(movements[0]["principal_amount"]) == D("1000.12345678")
    assert D(movements[2]["cash_received"]) == 430 and movements[3]["cash_received"] is None
    assert client.get(f"{PATH}/{investment}/movements/{sale.json()['id']}").json() == movements[2]
    for suffix in (f"/{investment}", f"/{investment}/movements/{first['id']}"):
        assert client.delete(PATH + suffix).status_code == 405
        assert client.put(PATH + suffix, json={}).status_code == 405
        assert client.patch(PATH + suffix, json={}).status_code == 405


@pytest.mark.parametrize("patch", [
    {"issuer": " "}, {"product_name": ""}, {"remuneration": "CDI", "indexer": "NONE"},
    {"product_type": "LCI"}, {"product_type": "TESOURO"}, {"indexer": "IPCA"},
    {"contracted_rate": "0"}, {"contracted_rate": "NaN"}, {"contracted_rate": "Infinity"},
    {"contracted_rate": "1.000000001"}, {"contracted_rate": "10000"},
    {"maturity_date": "2024-12-31"}, {"application_date": "2099-01-01", "maturity_date": "2100-01-01"},
    {"owner_id": str(B)},
])
def test_invalid_or_premature_contract_features_rejected(client, patch):
    assert client.post(PATH, json=CONTRACT | patch).status_code == 422


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity", "0.000000001", "1000000000000"])
def test_invalid_amounts_rejected_without_creating_lots(client, amount):
    investment = create(client)
    assert client.post(f"{PATH}/{investment}/applications", json={"date": "2025-01-01", "principal_amount": amount}).status_code == 422
    assert client.get(f"{PATH}/{investment}").json()["lots"] == []


def test_chronology_and_available_principal_are_checked_per_investment(client):
    investment = create(client, application_date="2025-01-02")
    lot = apply(client, investment, "100", "2025-01-02")["lot_id"]
    assert redeem(client, investment, lot, "101").status_code == 422
    assert redeem(client, investment, lot, "1", "2025-01-01").status_code == 422
    assert redeem(client, investment, lot, "10", "2025-01-04").status_code == 201
    assert client.post(f"{PATH}/{investment}/applications", json={"date": "2025-01-03", "principal_amount": "1"}).status_code == 422
    assert redeem(client, investment, lot, "1", "2099-01-01").status_code == 422
    assert client.post(f"{PATH}/{investment}/applications", json={"date": "2024-12-31", "principal_amount": "1"}).status_code == 422
    assert redeem(client, investment, lot, "1", cash_received="-1").status_code == 422
    assert D(client.get(f"{PATH}/{investment}").json()["principal_balance"]) == 90


def test_maturity_bounds_new_applications_but_not_late_recording_of_redemption(client):
    investment = create(client, maturity_date="2025-01-02")
    lot = apply(client, investment, "100")["lot_id"]
    assert client.post(f"{PATH}/{investment}/applications", json={"date": "2025-01-03", "principal_amount": "1"}).status_code == 422
    assert redeem(client, investment, lot, "100", "2025-01-04", cash_received="103").status_code == 201
    assert D(client.get(f"{PATH}/{investment}").json()["principal_balance"]) == 0


def test_first_application_matches_contract_date(client):
    investment = create(client)
    assert client.post(f"{PATH}/{investment}/applications", json={"date": "2025-01-02", "principal_amount": "1"}).status_code == 422
    assert client.get(f"{PATH}/{investment}").json()["lots"] == []


def test_business_date_uses_brazil_timezone_at_utc_day_boundary(monkeypatch):
    from datetime import datetime, timezone
    from app.fixed_income import schemas
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 29, 1, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(schemas, "datetime", Clock)
    assert schemas.financial_today() == date(2026, 10, 28)
    with pytest.raises(ValueError):
        schemas.ApplicationInput(date="2026-10-29", principal_amount="1")


def test_cannot_transfer_lot_or_access_another_owners_history(client):
    one = create(client)
    first = apply(client, one)
    another = create(client)
    assert redeem(client, another, first["lot_id"], "1").status_code == 404
    app.dependency_overrides[authenticate] = lambda: Principal(B)
    assert client.get(PATH).json() == []
    for suffix in (f"/{one}", f"/{one}/movements", f"/{one}/movements/{first['id']}"):
        assert client.get(PATH + suffix).status_code == 404
    assert redeem(client, one, first["lot_id"], "1").status_code == 404
    assert client.post(f"{PATH}/{one}/applications", json={"date": "2025-01-01", "principal_amount": "1"}).status_code == 404
    own = create(client)
    assert redeem(client, own, first["lot_id"], "1").status_code == 404
    apply(client, own, "50")
    assert D(client.get(f"{PATH}/{own}").json()["principal_balance"]) == 50
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    assert len(client.get(PATH).json()) == 2


def test_endpoints_require_auth_before_database_access(client):
    app.dependency_overrides.pop(authenticate)
    def forbidden_db():
        raise AssertionError("Unauthenticated DB access")
    app.dependency_overrides[get_db] = forbidden_db
    assert client.get(PATH).status_code == 401
    assert client.post(PATH, json=CONTRACT).status_code == 401
    assert client.get(PATH + "/1").status_code == 401
    assert client.get(PATH + "/1/movements").status_code == 401
    assert client.post(PATH + "/1/applications", json={}).status_code == 401
    assert client.post(PATH + "/1/redemptions", json={}).status_code == 401


def test_local_authenticated_alternative_and_pagination(client):
    app.dependency_overrides[authenticate] = lambda: Principal(None)
    investment = create(client)
    apply(client, investment)
    assert len(client.get(PATH + "?limit=1").json()) == 1
    assert client.get(PATH + "?offset=1").json() == []
    assert client.get(PATH + "?limit=1000").status_code == 422
    assert len(client.get(f"{PATH}/{investment}/movements?limit=1").json()) == 1


def test_ledger_decimal_precision_and_cash_not_used_for_principal():
    def row(id, kind, principal, lot=1, cash=None):
        return SimpleNamespace(id=id, date=date(2025, 1, id), kind=kind, principal_amount=D(principal), lot_id=lot, cash_received=cash)
    movements = [row(1, "APPLICATION", "999999999999.12345678"),
        row(2, "REDEMPTION", "0.00000001", cash=D(500)), row(3, "APPLICATION", "0.12345678", lot=2)]
    balances = principal_balances(reversed(movements))
    assert balances == {1: D("999999999999.12345677"), 2: D("0.12345678")}
    assert total_principal(balances) == D("999999999999.24691355")
    with pytest.raises(ValueError):
        principal_balances([row(1, "REDEMPTION", "1")])
