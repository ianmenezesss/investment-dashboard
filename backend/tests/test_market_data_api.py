import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
import httpx
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


def test_quotes_requires_auth_before_database_or_provider():
    def forbidden_db():
        raise AssertionError("Database must not be accessed")
    app.dependency_overrides[get_db] = forbidden_db
    try:
        with TestClient(app) as client:
            assert client.get("/api/quotes").status_code == 401
            assert client.get("/api/quotes", headers={"Authorization": "Bearer wrong"}).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_quotes_only_open_positions_of_owner_and_no_database_transaction_during_http():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for owner, ticker, kind, day in [(A, "ITUB4", "BUY", 1), (A, "PETR4", "BUY", 1),
                (A, "PETR4", "SELL", 2), (B, "BBAS3", "BUY", 1)]:
            db.add(Operation(owner_id=owner, ticker=ticker, kind=kind, date=date(2026, 1, day),
                quantity=Decimal(1), price=Decimal(10), fees=Decimal(0)))
        db.commit()
    sessions, calls = [], []
    def db_session():
        with Session(engine) as db:
            sessions.append(db)
            yield db
    def handler(request):
        assert not sessions[-1].in_transaction()
        assert dict(request.url.params).keys() == {"symbols"}
        ticker = request.url.params["symbols"]
        calls.append(ticker)
        now = datetime.now(timezone.utc).isoformat()
        return httpx.Response(200, json={"results": [{"requestedSymbol": ticker, "symbol": ticker,
            "data": {"regularMarketPrice": 25, "currency": "BRL", "regularMarketTime": now}}]})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = QuoteService(BrapiProvider(http, "unit-test-only"), enabled=True, configured=True)
    app.dependency_overrides[get_db] = db_session
    app.dependency_overrides[quote_service] = lambda: service
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    try:
        with TestClient(app) as client:
            # Existing read paths must not fetch market data.
            assert client.get("/health").status_code == 200
            summary = client.get("/api/dashboard").json()
            assert summary["market_value"] is None
            assert client.get("/api/export").status_code == 200
            assert client.get("/api/operations").status_code == 200
            assert calls == []
            result = client.get("/api/quotes?symbols=PETR4,BBAS3")
            assert result.status_code == 200
            assert [q["ticker"] for q in result.json()["quotes"]] == ["ITUB4"]
            assert result.headers["cache-control"] == "no-store"
            assert calls == ["ITUB4"]
            client.get("/api/quotes")
            assert calls == ["ITUB4"]
            app.dependency_overrides[authenticate] = lambda: Principal(B)
            assert [q["ticker"] for q in client.get("/api/quotes").json()["quotes"]] == ["BBAS3"]
            app.dependency_overrides[authenticate] = lambda: Principal(UUID(int=3))
            assert client.get("/api/quotes").json() == {"quotes": []}
            assert calls == ["ITUB4", "BBAS3"]
    finally:
        app.dependency_overrides.clear()
        asyncio.run(http.aclose())
        engine.dispose()


def test_provider_401_is_quote_metadata_not_application_401():
    from app.main import held_tickers
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(401, text="private-provider-error")))
    service = QuoteService(BrapiProvider(http, "private-provider-token"), enabled=True, configured=True)
    # Auth contract is covered above; this isolates HTTP error translation at the route boundary.
    app.dependency_overrides[held_tickers] = lambda: ["ITUB4"]
    app.dependency_overrides[quote_service] = lambda: service
    try:
        with TestClient(app) as client:
            result = client.get("/api/quotes")
            assert result.status_code == 200
            assert result.json()["quotes"][0]["reason"] == "provider_auth_error"
            assert "private-provider" not in result.text
    finally:
        app.dependency_overrides.clear()
        asyncio.run(http.aclose())
