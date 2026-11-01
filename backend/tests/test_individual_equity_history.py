import asyncio
from datetime import date
from decimal import Decimal as D
from uuid import UUID

import pytest
import httpx
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
from app.market_data.individual_history import BrapiIndividualHistoryProvider, ENDPOINT
from app.market_data.request_gate import BrapiRequestGate

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


def test_source_coverage_marks_truncated_start_and_end_as_partial():
    cases = [
        [ProviderDailyPrice(date(2026, 10, 10), D("10")), ProviderDailyPrice(date(2026, 10, 28), D("11"))],
        [ProviderDailyPrice(date(2026, 9, 30), D("10")), ProviderDailyPrice(date(2026, 10, 15), D("11"))],
    ]
    async def run():
        for points in cases:
            result = await EquityPriceHistoryService(SimulatedProvider(points), enabled=True,
                today=lambda: TODAY).get("ITUB4", "1M")
            assert result.availability == "partial"
            assert result.reason == "source_coverage"
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


def test_brapi_free_fetches_one_symbol_uses_adjusted_close_and_caps_window():
    calls = []
    async def handler(request):
        calls.append(request)
        assert request.url.path == "/api/v2/stocks/historical"
        assert request.url.params["symbols"] == "ITUB4"
        assert request.url.params["startDate"] == "2026-07-29"
        assert request.url.params["endDate"] == TODAY.isoformat()
        assert request.url.params["interval"] == "1d"
        assert "includeRaw" not in request.url.params
        assert request.headers["authorization"] == "Bearer token-for-test-only"
        assert "token-for-test-only" not in str(request.url)
        return httpx.Response(200, json={"results": [{"requestedSymbol": "ITUB4", "symbol": "ITUB4", "data": {
            "historicalDataPrice": [
                {"date": "2026-07-28", "rawClose": 777, "adjustedClose": 7},
                {"date": "2026-07-29", "rawClose": 888, "adjustedClose": 10.25},
                {"date": "2026-10-28", "rawClose": 999, "adjustedClose": 11},
            ]}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
            result = await BrapiIndividualHistoryProvider(client, "token-for-test-only").fetch(
                "ITUB4", start=date(2026, 4, 29), end=TODAY)
        assert result.price_basis == "adjusted_close"
        assert result.partial is True
        assert [(point.date, point.close) for point in result.points] == [
            (date(2026, 7, 29), D("10.25")), (date(2026, 10, 28), D("11")),
        ]
    asyncio.run(run())
    assert len(calls) == 1


def test_brapi_individual_history_never_falls_back_to_raw_close():
    async def handler(_request):
        return httpx.Response(200, json={"results": [{"requestedSymbol": "ITUB4", "symbol": "ITUB4", "data": {
            "historicalDataPrice": [{"date": "2026-10-28", "rawClose": 123.45}]}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
            result = await BrapiIndividualHistoryProvider(client, "test").fetch("ITUB4", start=TODAY, end=TODAY)
            displayed = await EquityPriceHistoryService(SimulatedProvider(result.points), enabled=True,
                today=lambda: TODAY).get("ITUB4", "1M") if result.points else None
        assert result.points == ()
        assert displayed is None
    asyncio.run(run())


@pytest.mark.parametrize(("status", "reason"), [(401, "provider_auth_error"), (403, "provider_forbidden"), (429, "provider_rate_limited")])
def test_brapi_plan_and_rate_errors_are_sanitized(status, reason):
    async def handler(_request):
        return httpx.Response(status, text="provider token body must never escape")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
            provider = BrapiIndividualHistoryProvider(client, "test-token")
            with pytest.raises(PriceHistoryUnavailable) as exc:
                await provider.fetch("ITUB4", start=date(2026, 10, 1), end=TODAY)
        assert exc.value.reason == reason
        assert "test-token" not in str(exc.value)
        assert "provider token body" not in str(exc.value)
    asyncio.run(run())


def test_brapi_free_window_is_reported_partial_and_cached():
    calls = []
    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"results": [{"requestedSymbol": "ITUB4", "symbol": "ITUB4", "data": {
            "historicalDataPrice": [
                {"date": "2026-07-29", "adjustedClose": 9},
                {"date": "2026-10-28", "adjustedClose": 10},
            ]}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
            service = EquityPriceHistoryService(BrapiIndividualHistoryProvider(client, "test"), enabled=True,
                today=lambda: TODAY)
            three_months = await service.get("ITUB4", "3M")
            six_months = await service.get("ITUB4", "6M")
            one_year = await service.get("ITUB4", "1A")
            maximum = await service.get("ITUB4", "MAX")
        assert three_months.availability == "available"
        assert three_months.coverage_start == date(2026, 7, 29)
        for result in (six_months, one_year, maximum):
            assert result.availability == "partial" and result.reason == "plan_limit"
            assert result.coverage_start == date(2026, 7, 29)
    asyncio.run(run())
    assert len(calls) == 1


def test_brapi_gate_serializes_requests_and_stops_at_its_budget():
    async def run():
        gate = BrapiRequestGate(max_requests=2)
        active = 0
        maximum = 0
        async def task():
            nonlocal active, maximum
            async with gate.request():
                active += 1
                maximum = max(maximum, active)
                await asyncio.sleep(0)
                active -= 1
        await asyncio.gather(task(), task())
        assert maximum == 1
        exhausted = BrapiRequestGate(max_requests=1)
        async with exhausted.request():
            pass
        with pytest.raises(Exception, match="request_budget_exhausted"):
            async with exhausted.request():
                raise AssertionError("exhausted budget must not enter")
    asyncio.run(run())
