import asyncio
from datetime import date
from decimal import Decimal as D
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import Principal, authenticate
from app.database import Base, get_db
from app.individual_equity_history import (
    EquityPriceHistoryService, PriceHistoryUnavailable, ProviderDailyPrice,
    ProviderPriceHistory, individual_equity_price_history_service,
)
from app.main import app
from app.models import Operation

A = UUID("11111111-1111-4111-8111-111111111111")
B = UUID("22222222-2222-4222-8222-222222222222")
TODAY = date(2026, 10, 29)


class SimulatedProvider:
    def __init__(self, points=()):
        self.points = tuple(points)
        self.calls = []

    async def fetch(self, ticker, *, start, end):
        self.calls.append((ticker, start, end))
        return ProviderPriceHistory(ticker=ticker, source="provider-test-double", currency="BRL",
            price_basis="raw_close", points=self.points)


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    def db_session():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = db_session
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    provider = SimulatedProvider([
        ProviderDailyPrice(date(2026, 10, 28), D("12.34000001")),
        ProviderDailyPrice(date(2026, 10, 1), D("10.125")),
        ProviderDailyPrice(date(2026, 10, 30), D("99.99")),
    ])
    service = EquityPriceHistoryService(provider, enabled=True, today=lambda: TODAY)
    app.dependency_overrides[individual_equity_price_history_service] = lambda: service
    try:
        with Session(engine) as session:
            session.add_all([
                Operation(owner_id=A, ticker="ITUB4", kind="BUY", date=date(2026, 1, 2), quantity=D("2"), price=D("10"), fees=D("0")),
                Operation(owner_id=B, ticker="PETR4", kind="BUY", date=date(2026, 1, 2), quantity=D("3"), price=D("20"), fees=D("0")),
            ])
            session.commit()
        with TestClient(app) as client:
            yield client, provider
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_private_endpoint_returns_typed_daily_history_sorted_and_exact(api):
    client, provider = api
    response = client.get("/api/dashboard/equities/ITUB4/price-history?period=1M")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "ITUB4"
    assert payload["period"] == "1M"
    assert payload["currency"] == "BRL"
    assert payload["source"] == "provider-test-double"
    assert payload["price_basis"] == "raw_close"
    assert payload["availability"] == "available"
    assert payload["coverage_start"] == "2026-10-01"
    assert payload["coverage_end"] == "2026-10-28"
    assert payload["points"] == [
        {"date": "2026-10-01", "close": "10.125"},
        {"date": "2026-10-28", "close": "12.34000001"},
    ]
    assert provider.calls == [("ITUB4", date(2026, 9, 29), TODAY)]
    assert response.headers["cache-control"] == "no-store"


def test_endpoint_requires_authentication_before_database_access():
    def forbidden_db():
        raise AssertionError("database should not be accessed before authentication")
    app.dependency_overrides[get_db] = forbidden_db
    app.dependency_overrides.pop(authenticate, None)
    try:
        with TestClient(app) as client:
            assert client.get("/api/dashboard/equities/ITUB4/price-history").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_endpoint_hides_other_owners_tickers_and_does_not_call_provider(api):
    client, provider = api
    assert client.get("/api/dashboard/equities/PETR4/price-history").status_code == 404
    assert provider.calls == []
    app.dependency_overrides[authenticate] = lambda: Principal(B)
    assert client.get("/api/dashboard/equities/ITUB4/price-history").status_code == 404
    assert provider.calls == []


def test_invalid_ticker_and_period_are_rejected(api):
    client, provider = api
    assert client.get("/api/dashboard/equities/ITUB/price-history").status_code == 422
    assert client.get("/api/dashboard/equities/ITUB4/price-history?period=2Y").status_code == 422
    assert provider.calls == []


def test_disabled_service_never_calls_simulated_provider():
    provider = SimulatedProvider([ProviderDailyPrice(TODAY, D("1.23"))])
    async def run():
        result = await EquityPriceHistoryService(provider, enabled=False, today=lambda: TODAY).get("ITUB4", "MAX")
        assert result.availability == "disabled"
        assert result.reason == "feature_disabled"
        assert result.source is None and result.points == []
    asyncio.run(run())
    assert provider.calls == []


def test_unconfigured_and_empty_states_are_explicit():
    async def run():
        absent = await EquityPriceHistoryService(None, enabled=True, today=lambda: TODAY).get("ITUB4", "MAX")
        assert absent.availability == "unavailable" and absent.reason == "provider_not_configured"
        empty = await EquityPriceHistoryService(SimulatedProvider(), enabled=True, today=lambda: TODAY).get("ITUB4", "MAX")
        assert empty.availability == "empty" and empty.coverage_start is None and empty.points == []
    asyncio.run(run())


def test_max_period_uses_no_start_and_provider_errors_are_sanitized():
    class UnavailableProvider:
        async def fetch(self, ticker, *, start, end):
            assert start is None and end == TODAY
            raise PriceHistoryUnavailable("provider_unavailable")
    async def run():
        result = await EquityPriceHistoryService(UnavailableProvider(), enabled=True,
            today=lambda: TODAY).get("ITUB4", "MAX")
        assert result.period_start is None
        assert result.availability == "unavailable" and result.reason == "provider_unavailable"
        assert "token" not in result.model_dump_json().lower()
    asyncio.run(run())


def test_invalid_or_duplicate_provider_values_never_become_prices():
    bad = SimulatedProvider([ProviderDailyPrice(TODAY, D("NaN"))])
    duplicate = SimulatedProvider([ProviderDailyPrice(TODAY, D("1")), ProviderDailyPrice(TODAY, D("2"))])
    async def run():
        for provider in (bad, duplicate):
            result = await EquityPriceHistoryService(provider, enabled=True, today=lambda: TODAY).get("ITUB4", "1M")
            assert result.availability == "unavailable"
            assert result.reason == "invalid_provider_response"
            assert result.points == []
    asyncio.run(run())
