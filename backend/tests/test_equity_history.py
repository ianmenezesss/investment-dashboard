import asyncio
from datetime import date, datetime
from decimal import Decimal as D
from types import SimpleNamespace as Row
from zoneinfo import ZoneInfo

import httpx
import pytest
from pydantic import SecretStr

from app.auth import Principal, authenticate
from app.database import get_db, settings
from app.equity_history import aggregate_equity_history, equity_history_service
from app.main import app, lifespan
from app.market_data.equity_history import (
    BrapiEquityHistoryProvider, EVENT_ENDPOINT, PRICE_ENDPOINT, DailyPrice, EquityHistoryService,
    ShareEvent, TickerHistory,
)
from app.models import Operation
from test_fixed_income import A, B, client

TZ = ZoneInfo("America/Sao_Paulo")
TOKEN = "test-history-token"


def op(id, ticker, kind, day, quantity, price, fees="0"):
    return Row(id=id, ticker=ticker, kind=kind, date=date.fromisoformat(day), quantity=D(quantity), price=D(price), fees=D(fees))


def test_history_feature_flag_disabled_does_not_call_provider():
    class Provider:
        async def fetch(self, *args, **kwargs):
            raise AssertionError("provider must not be called while history is disabled")

    async def run():
        service = EquityHistoryService(Provider(), enabled=False, configured=True)
        result = await service.get(["ITUB4"], price_start=date(2025, 1, 1), event_start=date(2025, 1, 1), end=date(2025, 1, 2))
        assert result["ITUB4"].error == "disabled"

    asyncio.run(run())


def test_history_flag_does_not_disable_current_quotes(monkeypatch):
    async def run():
        monkeypatch.setattr(settings, "market_data_enabled", True)
        monkeypatch.setattr(settings, "equity_history_enabled", False)
        monkeypatch.setattr(settings, "brapi_token", SecretStr(TOKEN))
        async with lifespan(app):
            assert app.state.quote_service.enabled is True
            assert app.state.equity_history_service.enabled is False

    asyncio.run(run())


def test_rebuilds_quantities_at_daily_close_and_uses_decimal_raw_price():
    operations = [op(1, "ITUB4", "BUY", "2025-01-02", "2", "10.10", "0.03"),
                  op(2, "ITUB4", "BUY", "2025-01-03", "1", "20", "0"),
                  op(3, "ITUB4", "SELL", "2025-01-06", "1", "30", "0.07"),
                  op(4, "ITUB4", "SELL", "2025-01-07", "2", "30", "0")]
    prices = [DailyPrice(date.fromisoformat(day), D(price)) for day, price in [
        ("2025-01-02", "10.12345678"), ("2025-01-03", "20.00000001"),
        ("2025-01-06", "30"), ("2025-01-07", "30")]]
    result = aggregate_equity_history(operations, {"ITUB4": TickerHistory(tuple(prices))},
                                      start=date(2025, 1, 2), end=date(2025, 1, 7))
    assert [D(point["market_value"]) for point in result["points"]] == [D("20.24691356"), D("60.00000003"), D("60"), D("0")]
    assert [D(point["net_invested"]) for point in result["points"]] == [D("20.23"), D("40.23"), D("10.30"), D("-49.70")]
    assert [len(point["holdings"]) for point in result["points"]] == [1, 1, 1, 0]
    assert result["coverage"] == "complete" and result["price_basis"] == "raw_close"
    assert result["points"][0]["difference_over_net_flows"] == "0.01691356"


def test_split_is_applied_on_ex_date_before_that_dates_buy_and_raw_price():
    operations = [op(1, "ITUB4", "BUY", "2025-01-02", "10", "10"),
                  op(2, "ITUB4", "BUY", "2025-01-03", "1", "5")]
    history = TickerHistory(
        (DailyPrice(date(2025, 1, 2), D("10")), DailyPrice(date(2025, 1, 3), D("5"))),
        (ShareEvent(date(2025, 1, 3), D("2")),),
    )
    result = aggregate_equity_history(operations, {"ITUB4": history}, start=date(2025, 1, 2), end=date(2025, 1, 3))
    assert D(result["points"][0]["market_value"]) == D("100")
    assert result["points"][1]["holdings"][0]["quantity"] == "21"
    assert D(result["points"][1]["market_value"]) == D("105")


def test_history_before_first_recorded_purchase_is_not_claimed_as_covered():
    operations = [op(1, "ITUB4", "BUY", "2025-01-03", "1", "10")]
    result = aggregate_equity_history(operations, {"ITUB4": TickerHistory((
        DailyPrice(date(2025, 1, 2), D("9")), DailyPrice(date(2025, 1, 3), D("10"))))},
        start=date(2025, 1, 1), end=date(2025, 1, 3))
    assert [p["date"] for p in result["points"]] == ["2025-01-03"]
    assert result["coverage"] == "partial" and result["period_start"] == "2025-01-01"


def test_missing_raw_close_is_an_explicit_chart_gap_not_forward_filled():
    operations = [op(1, "ITUB4", "BUY", "2025-01-02", "1", "10")]
    history = TickerHistory((DailyPrice(date(2025, 1, 2), D("10")), DailyPrice(date(2025, 1, 3), None),
                             DailyPrice(date(2025, 1, 6), D("12"))))
    result = aggregate_equity_history(operations, {"ITUB4": history}, start=date(2025, 1, 2), end=date(2025, 1, 6))
    assert result["points"][1]["market_value"] is None
    assert result["points"][1]["partial_market_value"] == "0"
    assert result["points"][2]["market_value"] == "12"


def test_missing_ticker_price_produces_partial_coverage_and_null_total():
    operations = [op(1, "ITUB4", "BUY", "2025-01-02", "1", "10"), op(2, "PETR4", "BUY", "2025-01-02", "1", "20")]
    result = aggregate_equity_history(operations, {
        "ITUB4": TickerHistory((DailyPrice(date(2025, 1, 2), D("11")), DailyPrice(date(2025, 1, 3), D("11")))),
        "PETR4": TickerHistory((DailyPrice(date(2025, 1, 3), D("21")),)),
    }, start=date(2025, 1, 2), end=date(2025, 1, 3))
    assert result["points"][0]["market_value"] is None
    assert result["points"][0]["partial_market_value"] == "11"
    assert result["points"][0]["missing_tickers"] == ["PETR4"]
    assert result["coverage"] == "partial"


def test_provider_requires_raw_close_parses_decimal_dates_actions_and_uses_cache():
    async def run():
        calls = []
        timestamp = int(datetime(2025, 1, 2, 16, tzinfo=TZ).timestamp())
        def handler(request):
            calls.append(request)
            assert request.headers["Authorization"] == f"Bearer {TOKEN}"
            assert TOKEN not in str(request.url)
            if str(request.url).startswith(PRICE_ENDPOINT):
                assert request.url.params["includeRaw"] == "true"
                return httpx.Response(200, json={"results": [{"requestedSymbol": "ITUB4", "symbol": "ITUB4", "changed": False,
                    "data": {"historicalDataPrice": [{"date": timestamp, "close": 999, "adjustedClose": 999, "rawClose": "10.12345678"}]}}]})
            assert str(request.url).startswith(EVENT_ENDPOINT)
            return httpx.Response(200, json={"results": [{"requestedSymbol": "ITUB4", "symbol": "ITUB4", "changed": False,
                "data": {"stockDividends": [{"factor": 2, "exDate": "2025-01-03T03:00:00.000Z"}], "cashDividends": []}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            service = EquityHistoryService(BrapiEquityHistoryProvider(http, TOKEN), enabled=True, configured=True)
            first = await service.get(["ITUB4"], price_start=date(2025, 1, 1), event_start=date(2025, 1, 1), end=date(2025, 1, 10))
            second = await service.get(["ITUB4"], price_start=date(2025, 1, 1), event_start=date(2025, 1, 1), end=date(2025, 1, 10))
            assert first == second and len(calls) == 2
            assert first["ITUB4"].prices[0].raw_close == D("10.12345678")
            assert first["ITUB4"].share_events[0] == ShareEvent(date(2025, 1, 3), D("2"))
    asyncio.run(run())


@pytest.mark.parametrize("status,reason", [(401, "provider_auth_error"), (403, "raw_history_not_available"), (429, "rate_limited"), (500, "provider_http_error")])
def test_provider_failures_are_controlled_and_safe(status, reason):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status, text=TOKEN))) as http:
            provider = BrapiEquityHistoryProvider(http, TOKEN)
            data = await provider.fetch(["ITUB4"], price_start=date(2025, 1, 1), event_start=date(2025, 1, 1), end=date(2025, 1, 10))
            assert data["ITUB4"].error == reason and TOKEN not in repr(data)
    asyncio.run(run())


def test_provider_does_not_fall_back_to_adjusted_close_when_raw_missing():
    async def run():
        def handler(request):
            if request.url.path == "/api/v2/stocks/historical":
                return httpx.Response(200, json={"results": [{"requestedSymbol": "ITUB4", "symbol": "ITUB4", "changed": False,
                    "data": {"historicalDataPrice": [{"date": 1735844400, "close": 100, "adjustedClose": 100}]}}]})
            return httpx.Response(200, json={"results": [{"requestedSymbol": "ITUB4", "symbol": "ITUB4", "changed": False,
                "data": {"stockDividends": [], "cashDividends": []}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            values = await BrapiEquityHistoryProvider(http, TOKEN).fetch(["ITUB4"], price_start=date(2025, 1, 1), event_start=date(2025, 1, 1), end=date(2025, 1, 10))
            assert len(values["ITUB4"].prices) == 1 and values["ITUB4"].prices[0].raw_close is None
            assert values["ITUB4"].error == "raw_price_unavailable"
    asyncio.run(run())


def test_provider_timeout_is_safe_and_cached_without_exposing_error_details():
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("private provider details")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            service = EquityHistoryService(BrapiEquityHistoryProvider(http, TOKEN), enabled=True, configured=True)
            first = await service.get(["ITUB4"], price_start=date(2025, 1, 1), event_start=date(2025, 1, 1), end=date(2025, 1, 10))
            second = await service.get(["ITUB4"], price_start=date(2025, 1, 1), event_start=date(2025, 1, 1), end=date(2025, 1, 10))
            assert first["ITUB4"].error == "provider_timeout"
            assert second["ITUB4"].error == "provider_timeout"
            assert len(calls) == 1 and TOKEN not in repr(first)
    asyncio.run(run())


def test_rate_limit_cooldown_applies_across_different_period_queries():
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(429, headers={"Retry-After": "120"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            service = EquityHistoryService(BrapiEquityHistoryProvider(http, TOKEN), enabled=True, configured=True)
            first = await service.get(["ITUB4"], price_start=date(2025, 1, 1), event_start=date(2025, 1, 1), end=date(2025, 1, 10))
            second = await service.get(["ITUB4"], price_start=date(2025, 2, 1), event_start=date(2025, 1, 1), end=date(2025, 2, 10))
            assert first["ITUB4"].error == second["ITUB4"].error == "rate_limited"
            assert len(calls) == 1
    asyncio.run(run())


def test_endpoint_is_authenticated_and_reads_only_callers_operations(client):
    class FakeService:
        async def get(self, tickers, *, price_start, event_start, end):
            return {ticker: TickerHistory((DailyPrice(date(2025, 1, 2), D("10")),)) for ticker in tickers}

    session = next(app.dependency_overrides[get_db]())
    session.add_all([
        Operation(owner_id=A, ticker="ITUB4", kind="BUY", date=date(2025, 1, 2), quantity=D("2"), price=D("9"), fees=D("0")),
        Operation(owner_id=B, ticker="PETR4", kind="BUY", date=date(2025, 1, 2), quantity=D("5"), price=D("8"), fees=D("0")),
    ])
    session.commit(); session.close()
    app.dependency_overrides[equity_history_service] = lambda: FakeService()
    try:
        a = client.get("/api/dashboard/equity-history?period=Tudo")
        assert a.status_code == 200 and D(a.json()["points"][0]["market_value"]) == D("20")
        app.dependency_overrides[authenticate] = lambda: Principal(B)
        b = client.get("/api/dashboard/equity-history?period=Tudo")
        assert b.status_code == 200 and b.json()["points"][0]["holdings"][0]["ticker"] == "PETR4"
        app.dependency_overrides[authenticate] = lambda: Principal(A)
        app.dependency_overrides.pop(authenticate)
        assert client.get("/api/dashboard/equity-history?period=Tudo").status_code == 401
    finally:
        app.dependency_overrides.clear()
