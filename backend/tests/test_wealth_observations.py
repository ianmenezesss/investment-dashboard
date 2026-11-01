from datetime import date
from decimal import Decimal as D
from uuid import UUID, uuid4

from app.auth import authenticate, Principal
from app.database import get_db
from app.fixed_income.models import Investment, InvestmentArchive
from app.fixed_income.observations import PositionObservation
from app.main import app
from test_fixed_income import A, B, client as client_fixture
import pytest

PATH = "/api/dashboard/wealth-observations"
DAY = date(2026, 10, 30)


def create_cdb(client, name):
    response = client.post("/api/fixed-income/investments", json={
        "issuer": "Banco de teste", "product_name": name, "product_type": "CDB",
        "remuneration": "FIXED", "indexer": "NONE", "contracted_rate": "10",
        "application_date": "2025-01-01", "maturity_date": "2027-01-01",
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def client(client_fixture):
    return client_fixture


def add_observation(client, investment_id, *, owner=A, gross="120", net="110", source="Extrato do CDB"):
    session = next(app.dependency_overrides[get_db]())
    session.add(PositionObservation(investment_id=investment_id, owner_id=owner, kind="OBSERVATION",
        reason="POSITION", as_of=DAY, gross_value=D(gross), net_value=D(net), source=source))
    session.commit()
    session.close()


def post(client, *, key=None, **values):
    return client.post(PATH, json={"as_of": DAY.isoformat(), "equities_market_value": "250.00",
        "equities_source": "Extrato da corretora", **values}, headers={"Idempotency-Key": str(key or uuid4())})


def test_snapshot_uses_exact_date_cdb_observations_and_reports_sources(client):
    first, second, missing = create_cdb(client, "CDB um"), create_cdb(client, "CDB dois"), create_cdb(client, "Sem observação")
    add_observation(client, first, gross="120", net="110", source="Extrato A")
    add_observation(client, second, gross="80", net="70", source="Extrato B")
    response = post(client)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["as_of"] == DAY.isoformat()
    assert D(data["equities_market_value"]) == D("250")
    assert data["equities_source"] == "Extrato da corretora"
    assert D(data["fixed_income_gross_value"]) == D("200")
    assert D(data["fixed_income_net_value"]) == D("180")
    assert data["fixed_income_coverage"] == "partial"
    assert data["missing_fixed_income"] == ["Sem observação"]
    assert data["consolidated_net_value"] is None and data["consolidated_coverage"] == "partial"
    assert {row["source"] for row in data["fixed_income_sources"]} == {"Extrato A", "Extrato B"}
    assert client.get(PATH).json() == [data]


def test_complete_same_day_classes_can_be_consolidated_but_cash_is_not_added(client):
    investment = create_cdb(client, "CDB coberto")
    add_observation(client, investment, gross="120", net="110")
    data = post(client).json()
    assert data["fixed_income_coverage"] == "complete"
    assert D(data["consolidated_gross_value"]) == D("370")
    assert D(data["consolidated_net_value"]) == D("360")


def test_empty_fixed_income_class_is_zero_and_total_does_not_need_cdb(client):
    data = post(client).json()
    assert data["fixed_income_coverage"] == "empty"
    assert D(data["fixed_income_net_value"]) == 0
    assert D(data["consolidated_net_value"]) == D("250")


def test_observations_are_owner_isolated_and_latest_same_day_entry_wins(client):
    post(client, equities_market_value="250", equities_source="Extrato 1")
    post(client, equities_market_value="275", equities_source="Extrato corrigido")
    own = client.get(PATH).json()
    assert len(own) == 1 and D(own[0]["equities_market_value"]) == D("275")
    app.dependency_overrides[authenticate] = lambda: Principal(B)
    other = client.get(PATH)
    assert other.status_code == 200 and other.json() == []


def test_idempotency_and_validation_prevent_duplicate_or_future_values(client):
    key = uuid4()
    first = post(client, key=key)
    replay = post(client, key=key)
    assert first.status_code == 201 and replay.status_code == 200 and replay.json()["id"] == first.json()["id"]
    assert post(client, key=key, equities_market_value="251").status_code == 409
    assert client.post(PATH, json={"as_of": "2099-01-01", "equities_market_value": "1",
        "equities_source": "Extrato"}, headers={"Idempotency-Key": str(uuid4())}).status_code == 422
    assert client.post(PATH, json={"as_of": DAY.isoformat(), "equities_market_value": "-1",
        "equities_source": "Extrato"}, headers={"Idempotency-Key": str(uuid4())}).status_code == 422


def test_authentication_precedes_database_access(client):
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = lambda: (_ for _ in ()).throw(AssertionError("DB accessed before auth"))
    with __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app) as unauthenticated:
        assert unauthenticated.get(PATH).status_code == 401
