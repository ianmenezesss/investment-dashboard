import asyncio
from datetime import datetime, timedelta, timezone
import json
import httpx
import pytest
from app.market_data.brapi import BrapiProvider, ENDPOINT
from app.market_data.service import QuoteService

NOW = datetime(2026, 10, 27, 16, tzinfo=timezone.utc)
TOKEN = "unit-test-provider-secret"


def payload(ticker="ITUB4", **data):
    return {"results": [{"requestedSymbol": ticker, "symbol": ticker, "changed": False,
        "data": {"regularMarketPrice": "24.12345678", "currency": "BRL",
                 "regularMarketTime": NOW.isoformat(), **data}}]}


class Clock:
    def __init__(self):
        self.seconds = 0
    def monotonic(self):
        return self.seconds
    def now(self):
        return NOW + timedelta(seconds=self.seconds)


def test_free_symbols_header_decimal_and_cache(caplog):
    async def run():
        clock = Clock()
        calls = []
        def handler(request):
            assert str(request.url).startswith(ENDPOINT + "?")
            assert request.headers["Authorization"] == "Bearer " + TOKEN
            assert TOKEN not in str(request.url)
            ticker = request.url.params["symbols"]
            assert "," not in ticker
            calls.append(ticker)
            # JSON number must be parsed as Decimal, without float roundtrip.
            body = json.dumps(payload(ticker)).replace('"24.12345678"', '24.12345678')
            return httpx.Response(200, content=body)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True, clock=clock.monotonic, now=clock.now)
            for ticker in ["ITUB4", "BBAS3", "B3SA3", "PETR4"]:
                quote = await service.get(ticker)
                assert quote.price == "24.12345678" and quote.currency == "BRL"
                assert quote.quoted_at == NOW and quote.fetched_at == NOW
                assert quote.status == "ok" and not quote.from_cache
                cached = await service.get(ticker)
                assert cached.from_cache and cached.price == quote.price
            assert len(calls) == 4
            clock.seconds = 1799
            assert (await service.get("ITUB4")).from_cache
            assert len(calls) == 4
            clock.seconds = 1800
            await service.get("ITUB4")
            assert len(calls) == 5
    asyncio.run(run())
    assert TOKEN not in caplog.text


@pytest.mark.parametrize("ticker", ["", "ITUB4.SA", "ITUB4F", "itub4", "ITUB4,PETR4", "https://evil", "../ITUB4", "A" * 100])
def test_invalid_tickers_never_use_network(ticker):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail("unexpected network"))) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True)
            assert (await service.get(ticker)).reason == "invalid_ticker"
    asyncio.run(run())


@pytest.mark.parametrize("enabled,configured,reason", [(False, True, "disabled"), (True, False, "missing_token")])
def test_disabled_or_missing_token_no_network(enabled, configured, reason):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail("unexpected network"))) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=enabled, configured=configured)
            quote = await service.get("ITUB4")
            assert quote.status == "disabled" and quote.reason == reason and quote.price is None
    asyncio.run(run())


@pytest.mark.parametrize("status,reason", [(401, "provider_auth_error"), (403, "provider_forbidden"), (429, "rate_limited"), (500, "provider_http_error"), (302, "provider_http_error")])
def test_provider_errors_are_safe_and_never_follow_redirects(status, reason, caplog):
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(status, headers={"Location": "https://evil.example/", "Retry-After": "300"}, text=TOKEN)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True, now=lambda: NOW)
            result = await service.get("ITUB4")
            assert result.status == "provider_error" and result.reason == reason and result.price is None
            assert TOKEN not in result.model_dump_json()
            await service.get("ITUB4")
            assert len(calls) == 1
            if status in (401, 403, 429):
                await service.get("BBAS3")
                assert len(calls) == 1
    asyncio.run(run())
    assert TOKEN not in caplog.text


@pytest.mark.parametrize("data", [
    {"regularMarketPrice": "NaN"}, {"regularMarketPrice": "Infinity"},
    {"regularMarketPrice": "-1"}, {"regularMarketPrice": "0"},
    {"regularMarketPrice": True}, {"regularMarketPrice": "1e-1000000"},
    {"currency": "USD"}, {"regularMarketTime": "invalid"},
    {"regularMarketTime": "2026-10-27T16:00:00"},
    {"regularMarketTime": (NOW + timedelta(minutes=2)).isoformat()},
])
def test_invalid_prices_currency_and_times_are_not_quotes(data):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload(**data)))) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True, now=lambda: NOW)
            quote = await service.get("ITUB4")
            assert quote.status == "provider_error" and quote.price is None
    asyncio.run(run())


@pytest.mark.parametrize("body", [b"<html>not json</html>", b"x" * 65537, b'{}', b'{"results":{}}'], ids=["html", "too-large", "missing-results", "invalid-results"])
def test_malformed_or_large_response(body):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True)
            assert (await service.get("ITUB4")).reason == "invalid_response"
    asyncio.run(run())


@pytest.mark.parametrize("body,reason", [({"results": []}, "not_found"), (payload(regularMarketPrice=None), "missing_price")])
def test_absent_data_and_negative_cache(body, reason):
    async def run():
        clock, calls = Clock(), []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=body)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True, now=clock.now, clock=clock.monotonic)
            quote = await service.get("ITUB4")
            assert quote.status == "no_data" and quote.reason == reason and quote.price is None
            assert quote.fetched_at == NOW
            await service.get("ITUB4")
            clock.seconds = 60
            await service.get("ITUB4")
            assert len(calls) == 2
    asyncio.run(run())


def test_stale_price_survives_failure_but_never_beyond_max_age():
    async def run():
        clock, failing = Clock(), False
        def handler(request):
            if failing:
                raise httpx.ReadTimeout(TOKEN)
            return httpx.Response(200, json=payload())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True, now=clock.now, clock=clock.monotonic)
            first = await service.get("ITUB4")
            failing = True
            clock.seconds = 1800
            stale = await service.get("ITUB4")
            assert stale.price == first.price and stale.status == "stale" and stale.is_stale
            assert stale.reason == "network_error" and stale.quoted_at == NOW and stale.fetched_at == NOW
            assert TOKEN not in stale.model_dump_json()
            clock.seconds = 96 * 3600 + 1
            assert (await service.get("ITUB4")).price is None
    asyncio.run(run())


def test_successful_refetch_of_old_data_does_not_make_it_fresh():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload()))) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True, now=lambda: NOW + timedelta(hours=2))
            quote = await service.get("ITUB4")
            assert quote.status == "stale" and quote.is_stale and quote.quoted_at == NOW
            assert quote.fetched_at > quote.quoted_at
    asyncio.run(run())


def test_concurrent_requests_deduplicate_and_serialize_free_plan():
    async def run():
        active, maximum, calls = 0, 0, []
        async def handler(request):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            ticker = request.url.params["symbols"]
            calls.append(ticker)
            await asyncio.sleep(0)  # Yield, no real delay or external request.
            active -= 1
            return httpx.Response(200, json=payload(ticker))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True, now=lambda: NOW)
            result = await asyncio.gather(*(service.get(t) for t in ["ITUB4", "ITUB4", "BBAS3", "B3SA3", "PETR4"]))
            assert all(q.price for q in result)
            assert maximum == 1 and len(calls) == 4
    asyncio.run(run())


def test_deadline_cancels_request_releases_lock_and_lru_is_bounded():
    async def run():
        waiting = True
        cancelled = asyncio.Event()
        async def handler(request):
            if waiting:
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return httpx.Response(200, json=payload(request.url.params["symbols"]))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True, now=lambda: NOW, capacity=1)
            assert (await service.get("ITUB4", timeout=0.01)).reason == "deadline_exceeded"
            assert cancelled.is_set() and not service.lock.locked()
            waiting = False
            await service.get("ITUB4")
            await service.get("BBAS3")
            assert list(service.cache) == ["BBAS3"]
    asyncio.run(run())


def test_request_budget_blocks_further_external_requests():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload(r.url.params["symbols"])))) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True, now=lambda: NOW, max_requests=1)
            await service.get("ITUB4")
            assert (await service.get("BBAS3")).reason == "request_budget_exhausted"
            assert service.stats["requests"] == 1
    asyncio.run(run())


def test_many_deduplicates_and_stops_starting_requests_when_deadline_is_spent():
    async def run():
        clock, calls = Clock(), []
        def handler(request):
            calls.append(request.url.params["symbols"])
            clock.seconds += 8
            return httpx.Response(200, json=payload())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True, now=clock.now, clock=clock.monotonic)
            quotes = await service.get_many(["ITUB4", "ITUB4", "BBAS3"])
            assert len(quotes) == 2 and calls == ["ITUB4"]
            assert quotes[1].reason == "deadline_exceeded" and quotes[1].price is None
    asyncio.run(run())


def test_retry_after_cooldown_and_expiry():
    async def run():
        clock, calls = Clock(), []
        def handler(request):
            calls.append(request)
            return httpx.Response(429, headers={"Retry-After": "300"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True, now=clock.now, clock=clock.monotonic)
            first = await service.get("ITUB4")
            assert first.retry_after_seconds == 300
            clock.seconds = 61
            await service.get("BBAS3")
            assert len(calls) == 1
            clock.seconds = 300
            await service.get("ITUB4")
            assert len(calls) == 2
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["changed", "mismatch", "404"])
def test_unknown_changed_or_mismatched_symbols_are_never_priced(kind):
    async def run():
        body = payload()
        if kind == "changed":
            body["results"][0]["changed"] = True
        if kind == "mismatch":
            body["results"][0]["symbol"] = "PETR4"
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(404 if kind == "404" else 200, json=body))) as client:
            service = QuoteService(BrapiProvider(client, TOKEN), enabled=True, configured=True, now=lambda: NOW)
            quote = await service.get("ITUB4")
            assert quote.price is None
            assert quote.status == ("provider_error" if kind == "mismatch" else "no_data")
    asyncio.run(run())
