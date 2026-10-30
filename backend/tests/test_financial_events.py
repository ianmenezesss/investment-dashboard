from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import Principal, authenticate
from app.database import Base, get_db
from app.main import app

A = UUID("11111111-1111-4111-8111-111111111111")
B = UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture
def event_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    selected_owner = {"id": A}

    def db_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = db_session
    app.dependency_overrides[authenticate] = lambda: Principal(selected_owner["id"])
    try:
        with TestClient(app) as client:
            yield client, selected_owner
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def payload(kind="CONTRIBUTION", **values):
    data = {"kind": kind, "event_date": "2025-01-05", "source": "Extrato consultado"}
    if kind in ("CONTRIBUTION", "WITHDRAWAL"):
        data["cash_amount"] = "100.12345678"
    elif kind in ("DIVIDEND", "JCP"):
        data.update(ticker="ITUB4", cash_amount="8.00")
    else:
        data.update(ticker="ITUB4", description="Evento indicado no documento")
    data.update(values)
    return data


def create(client, kind="CONTRIBUTION", *, key=None, **values):
    return client.post("/api/financial-events", headers={"Idempotency-Key": str(key or uuid4())}, json=payload(kind, **values))


def test_events_are_manually_recorded_idempotent_and_owner_scoped(event_client):
    client, selected = event_client
    contribution_key = uuid4()
    contribution = create(client, key=contribution_key)
    assert contribution.status_code == 201, contribution.text
    assert Decimal(contribution.json()["cash_amount"]) == Decimal("100.12345678")
    replay = create(client, key=contribution_key)
    assert replay.status_code == 200 and replay.json()["id"] == contribution.json()["id"]
    assert len(client.get("/api/financial-events").json()) == 1

    assert create(client, "WITHDRAWAL", cash_amount="12.50").status_code == 201
    assert create(client, "DIVIDEND", cash_amount="7.10", gross_amount="8.00", tax_withheld="0.90").status_code == 201
    assert create(client, "JCP", cash_amount="2.00").status_code == 201
    assert create(client, "CORPORATE_ACTION").status_code == 201
    summary = client.get("/api/dashboard/financial-events/summary?period=Tudo").json()
    assert Decimal(summary["contributions"]) == Decimal("100.12345678")
    assert Decimal(summary["withdrawals"]) == Decimal("12.50")
    assert Decimal(summary["net_external_cash_flow"]) == Decimal("87.62345678")
    assert Decimal(summary["dividends_received"]) == Decimal("7.10")
    assert Decimal(summary["jcp_received"]) == Decimal("2.00")
    assert summary["event_count"] == 5

    own = client.get("/api/financial-events?owner_id=" + str(B)).json()
    assert len(own) == 5
    selected["id"] = B
    assert client.get("/api/financial-events").json() == []
    assert Decimal(client.get("/api/dashboard/financial-events/summary").json()["contributions"]) == 0


def test_csv_import_is_atomic_and_skips_internal_external_and_replayed_duplicates(event_client):
    client, _ = event_client
    external = create(client, "JCP", cash_amount="4.25", event_date="2025-01-09")
    assert external.status_code == 201
    key = uuid4()
    rows = [
        {"row_number": 2, "event": payload("CONTRIBUTION", cash_amount="100.12345678")},
        {"row_number": 3, "event": payload("CONTRIBUTION", cash_amount="100.12345678")},
        {"row_number": 4, "event": payload("JCP", cash_amount="4.25", event_date="2025-01-09")},
    ]
    first = client.post("/api/financial-events/import", headers={"Idempotency-Key": str(key)}, json={"rows": rows})
    assert first.status_code == 201, first.text
    assert first.json()["imported_count"] == 1
    assert first.json()["duplicate_count"] == 2
    assert len(client.get("/api/financial-events").json()) == 2

    replay = client.post("/api/financial-events/import", headers={"Idempotency-Key": str(key)}, json={"rows": rows})
    assert replay.status_code == 200
    assert replay.json()["imported_count"] == 0
    assert replay.json()["duplicate_count"] == 3
    assert len(client.get("/api/financial-events").json()) == 2


def test_csv_import_rejects_invalid_batch_without_writes(event_client):
    client, _ = event_client
    rows = [
        {"row_number": 2, "event": payload("CONTRIBUTION")},
        {"row_number": 3, "event": payload("CONTRIBUTION", event_date="2999-01-01")},
    ]
    response = client.post("/api/financial-events/import", headers={"Idempotency-Key": str(uuid4())}, json={"rows": rows})
    assert response.status_code == 422
    assert client.get("/api/financial-events").json() == []

    malformed = client.post("/api/financial-events/import", headers={"Idempotency-Key": str(uuid4())}, json={
        "rows": [{"row_number": 2, "event": payload("CONTRIBUTION", cash_amount="0")}],
    })
    assert malformed.status_code == 422
    assert client.get("/api/financial-events").json() == []


def test_csv_import_requires_auth_and_is_scoped_to_the_authenticated_owner(event_client):
    client, selected = event_client
    key = uuid4()
    body = {"rows": [{"row_number": 2, "event": payload("CONTRIBUTION", cash_amount="75.25")}]}
    first = client.post("/api/financial-events/import", headers={"Idempotency-Key": str(key)}, json=body)
    assert first.status_code == 201
    selected["id"] = B
    second = client.post("/api/financial-events/import", headers={"Idempotency-Key": str(key)}, json=body)
    assert second.status_code == 201
    assert len(client.get("/api/financial-events").json()) == 1
    selected["id"] = A
    assert len(client.get("/api/financial-events").json()) == 1


def test_csv_import_rolls_back_every_row_after_mid_batch_failure(event_client, monkeypatch):
    import app.financial_events as events

    client, _ = event_client
    original = events.append_event
    calls = 0

    def fail_second(db, owner, request_id, data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("simulated database conflict")
        return original(db, owner, request_id, data)

    monkeypatch.setattr(events, "append_event", fail_second)
    response = client.post("/api/financial-events/import", headers={"Idempotency-Key": str(uuid4())}, json={
        "rows": [
            {"row_number": 2, "event": payload("CONTRIBUTION", cash_amount="10")},
            {"row_number": 3, "event": payload("WITHDRAWAL", cash_amount="5")},
        ],
    })
    assert response.status_code == 409
    assert "nenhuma linha foi gravada" in response.json()["detail"]
    assert client.get("/api/financial-events").json() == []


def test_replace_and_void_are_append_only_and_change_only_effective_view(event_client):
    client, selected = event_client
    contribution = create(client, key=uuid4())
    jcp = create(client, "JCP", key=uuid4())
    assert contribution.status_code == jcp.status_code == 201
    event_id = contribution.json()["id"]

    replacement = client.post(f"/api/financial-events/{event_id}/revisions", headers={"Idempotency-Key": str(uuid4())}, json={
        "kind": "REPLACE", "expected_revision": 0, "reason": "Valor conferido novamente",
        "replacement": payload("CONTRIBUTION", event_date="2025-01-07", cash_amount="125.25"),
    })
    assert replacement.status_code == 201, replacement.text
    assert Decimal(client.get("/api/dashboard/financial-events/summary").json()["contributions"]) == Decimal("125.25")
    revision_key = replacement.request.headers["Idempotency-Key"]
    replay = client.post(f"/api/financial-events/{event_id}/revisions", headers={"Idempotency-Key": revision_key}, json={
        "kind": "REPLACE", "expected_revision": 0, "reason": "Valor conferido novamente",
        "replacement": payload("CONTRIBUTION", event_date="2025-01-07", cash_amount="125.25"),
    })
    assert replay.status_code == 200

    void = client.post(f"/api/financial-events/{jcp.json()['id']}/revisions", headers={"Idempotency-Key": str(uuid4())}, json={
        "kind": "VOID", "expected_revision": 0, "reason": "Lançamento duplicado", "replacement": None,
    })
    assert void.status_code == 201, void.text
    effective = client.get("/api/financial-events").json()
    assert len(effective) == 1
    assert {key: effective[0][key] for key in ("id", "kind", "event_date", "ticker", "cash_amount", "gross_amount", "tax_withheld", "source", "description", "revision")} == {
        "id": event_id, "kind": "CONTRIBUTION", "event_date": "2025-01-07", "ticker": None,
        "cash_amount": "125.25000000", "gross_amount": None, "tax_withheld": None,
        "source": "Extrato consultado", "description": None, "revision": 1,
    }
    assert Decimal(client.get("/api/dashboard/financial-events/summary").json()["jcp_received"]) == 0
    assert len(client.get(f"/api/financial-events/{event_id}/revisions").json()) == 1
    selected["id"] = B
    assert client.post(f"/api/financial-events/{event_id}/revisions", headers={"Idempotency-Key": str(uuid4())}, json={
        "kind": "VOID", "expected_revision": 1, "reason": "Não autorizado",
    }).status_code == 404


@pytest.mark.parametrize("data", [
    payload("DIVIDEND", gross_amount="8", tax_withheld="1", cash_amount="6"),
    payload("CONTRIBUTION", cash_amount="0"),
    payload("CONTRIBUTION", ticker="ITUB4"),
    payload("CORPORATE_ACTION", cash_amount="100"),
])
def test_invalid_or_inconsistent_manual_event_payloads_are_rejected(event_client, data):
    client, _ = event_client
    response = client.post("/api/financial-events", headers={"Idempotency-Key": str(uuid4())}, json=data)
    assert response.status_code == 422
    assert client.get("/api/financial-events").json() == []


def test_unified_history_includes_effective_events_and_excludes_void_rows(event_client):
    client, _ = event_client
    contribution = create(client, key=uuid4())
    event_id = contribution.json()["id"]
    assert client.post(f"/api/financial-events/{event_id}/revisions", headers={"Idempotency-Key": str(uuid4())}, json={
        "kind": "VOID", "expected_revision": 0, "reason": "Registro incorreto",
    }).status_code == 201
    jcp = create(client, "JCP", key=uuid4())
    assert jcp.status_code == 201
    rows = client.get("/api/dashboard/movements").json()
    assert len(rows) == 1
    assert rows[0]["operation"] == "JCP" and rows[0]["investment_class"] == "PROVENTOS"
    assert rows[0]["financial_value"] == "8.00000000"


def test_summary_periods_filter_by_observed_event_date(event_client):
    client, _ = event_client
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    recent = today - timedelta(days=10)
    older = today - timedelta(days=45)
    assert create(client, event_date=recent.isoformat(), cash_amount="11.25").status_code == 201
    assert create(client, event_date=older.isoformat(), cash_amount="90.75").status_code == 201
    selected = client.get("/api/dashboard/financial-events/summary?period=1M").json()
    all_time = client.get("/api/dashboard/financial-events/summary?period=Tudo").json()
    assert Decimal(selected["contributions"]) == Decimal("11.25")
    assert selected["event_count"] == 1
    assert Decimal(all_time["contributions"]) == Decimal("102.00")
    assert all_time["event_count"] == 2
    assert client.get("/api/dashboard/financial-events/summary?period=13M").status_code == 422


def test_private_endpoints_require_authentication():
    response = TestClient(app).get("/api/financial-events")
    assert response.status_code == 401
    import_response = TestClient(app).post("/api/financial-events/import", headers={"Idempotency-Key": str(uuid4())}, json={"rows": [
        {"row_number": 1, "event": payload("CONTRIBUTION")},
    ]})
    assert import_response.status_code == 401
