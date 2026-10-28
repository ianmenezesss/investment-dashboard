import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth import Principal, authenticate
from app.database import Base, get_db
from app.main import app, quote_service
from app.models import Operation
from app.market_data.brapi import BrapiProvider
from app.market_data.service import QuoteService

A = UUID("11111111-1111-4111-8111-111111111111")
B = UUID("22222222-2222-4222-8222-222222222222")


def test_valuation_requires_auth_before_accessing_database_or_provider():
    def forbidden_db():
        raise AssertionError("Database accessed without authentication")
    app.dependency_overrides[get_db] = forbidden_db
    try:
        with TestClient(app) as client:
            assert client.get("/api/dashboard/valuation").status_code == 401
            assert client.get("/api/dashboard/valuation", headers={"Authorization": "Bearer wrong"}).status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("provider_status", [200, 500])
def test_valuation_snapshot_isolated_by_owner_with_shared_quote_cache(provider_status):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for owner, ticker, kind, qty, price, fees, day in [
            (A, "ITUB4", "BUY", "10", "20", "2", 1),
            (A, "ITUB4", "SELL", "4", "25", "1", 2),
            (A, "PETR4", "BUY", "1", "10", "0", 1),
            (A, "PETR4", "SELL", "1", "10", "0", 2),
            (B, "ITUB4", "BUY", "2", "10", "0", 1),
        ]:
            db.add(Operation(owner_id=owner, ticker=ticker, kind=kind, quantity=Decimal(qty),
                price=Decimal(price), fees=Decimal(fees), date=date(2026, 1, day)))
        db.commit()
    sessions, calls = [], []
    def db_session():
        with Session(engine) as db:
            sessions.append(db)
            yield db
    def handler(request):
        assert not sessions[-1].in_transaction()
        ticker = request.url.params["symbols"]
        calls.append(ticker)
        return httpx.Response(provider_status, json={"results": [{"symbol": ticker, "requestedSymbol": ticker,
            "data": {"regularMarketPrice": 24, "currency": "BRL", "regularMarketTime": datetime.now(timezone.utc).isoformat()}}]})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = QuoteService(BrapiProvider(http, "unit-test-token"), enabled=True, configured=True)
    app.dependency_overrides[get_db] = db_session
    app.dependency_overrides[quote_service] = lambda: service
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    try:
        with TestClient(app) as client:
            before = client.get("/api/dashboard").json()
            assert calls == [] and before["market_value"] is None
            result = client.get(f"/api/dashboard/valuation?owner_id={B}")
            assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
            data = result.json()
            assert data["realized_profit"] == before["realized_profit"]
            assert Decimal(data["realized_profit"]) == Decimal("18.2")
            assert [h["ticker"] for h in data["holdings"]] == ["ITUB4"]
            assert Decimal(data["holdings"][0]["quantity"]) == 6
            assert data["ledger_as_of"] and data["valuation"]["calculated_at"]
            if provider_status == 200:
                assert Decimal(data["market_value"]) == 144
                assert Decimal(data["valuation"]["unrealized_profit"]) == Decimal("22.8")
                assert data["valuation"]["status"] == "complete"
                assert isinstance(data["holdings"][0]["cost"], str)
            else:
                assert data["market_value"] is None
                assert data["valuation"]["status"] == "unavailable"
                assert data["valuation"]["unrealized_profit"] is None
            app.dependency_overrides[authenticate] = lambda: Principal(B)
            other = client.get("/api/dashboard/valuation").json()
            assert Decimal(other["holdings"][0]["quantity"]) == 2
            if provider_status == 200:
                assert Decimal(other["market_value"]) == 48
                assert Decimal(other["valuation"]["unrealized_profit"]) == 28
            assert calls == ["ITUB4"]  # Public price cache, not a cached private portfolio.
            app.dependency_overrides[authenticate] = lambda: Principal(UUID(int=3))
            empty = client.get("/api/dashboard/valuation").json()
            assert empty["holdings"] == [] and Decimal(empty["market_value"]) == 0
            assert empty["valuation"]["status"] == "empty"
            assert calls == ["ITUB4"]
            app.dependency_overrides[authenticate] = lambda: Principal(A)
            service.enabled = False
            assert client.get("/api/dashboard/valuation").json()["market_value"] is None
            assert client.get("/api/dashboard").json() == before
    finally:
        app.dependency_overrides.clear()
        asyncio.run(http.aclose())
        engine.dispose()
