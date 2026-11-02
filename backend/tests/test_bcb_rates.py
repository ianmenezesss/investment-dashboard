import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import httpx
import pytest
from pydantic import ValidationError
from app.bcb_rates.provider import SGSProvider, MAX_BYTES, retry_seconds
from app.bcb_rates.schemas import Period, RateError, Observation
from app.bcb_rates.service import RateService

PERIOD = Period(start_date=date(2025, 1, 1), end_date=date(2025, 1, 5))
ROWS = [{"data": "02/01/2025", "valor": "0.012345678901"}, {"data": "03/01/2025", "valor": "0.05"}]


def fetch(response, code=12):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)) as http:
            return await SGSProvider(http).fetch(code, PERIOD)
    return asyncio.run(run())


@pytest.mark.parametrize("code", [11, 12])
def test_provider_exact_units_dates_filters_and_decimal_without_invented_days(code):
    async def run():
        def handler(request):
            assert str(request.url).startswith(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados?")
            assert dict(request.url.params) == {"formato": "json", "dataInicial": "01/01/2025", "dataFinal": "05/01/2025"}
            assert "authorization" not in request.headers
            return httpx.Response(200, json=list(reversed(ROWS)))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            points, duplicates = await SGSProvider(http).fetch(code, PERIOD)
            assert duplicates == 0 and len(points) == 2
            assert points[0].date == date(2025, 1, 2)
            assert points[0].value == Decimal("0.012345678901")
            assert all(p.unit == "% ao dia" and p.series_code == code for p in points)
    asyncio.run(run())


@pytest.mark.parametrize("payload", [
    {}, None, "error", [{"data": "2025-01-02", "valor": "1"}],
    [{"data": "31/02/2025", "valor": "1"}], [{"data": "01/01/2024", "valor": "1"}],
    [{"data": "02/01/2025", "valor": "NaN"}], [{"data": "02/01/2025", "valor": "Infinity"}],
    [{"data": "02/01/2025", "valor": "0,05"}], [{"data": "02/01/2025", "valor": "1e-2"}],
    [{"data": "02/01/2025", "valor": "0.0000000000001"}], [{"data": "02/01/2025", "valor": True}],
    [{"data": "02/01/2025"}], [None], ROWS + [{"data": "02/01/2025", "valor": "0.07"}],
])
def test_invalid_or_conflicting_payload_rejected_in_full(payload):
    with pytest.raises(RateError) as error:
        fetch(httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type": "application/json"}))
    assert error.value.code == "invalid_payload" and error.value.status == 502


def test_empty_identical_duplicates_and_numeric_json_values():
    assert fetch(httpx.Response(200, json=[])) == ((), 0)
    points, duplicates = fetch(httpx.Response(200, json=ROWS + [ROWS[0]]))
    assert len(points) == 2 and duplicates == 1
    points, _ = fetch(httpx.Response(200, content=b'[{"data":"02/01/2025","valor":0.012345678901}]', headers={"content-type": "application/json"}))
    assert points[0].value == Decimal("0.012345678901")


@pytest.mark.parametrize("body", [b"not json", b'[{"data":"02/01/2025","valor":NaN}]',
    b'[{"data":"02/01/2025","valor":"0.05","other":NaN}]',
    b'[{"data":"02/01/2025","valor":"1","valor":"2"}]', b"[" * 2000])
def test_bad_json_constants_duplicate_keys_and_deep_payload(body):
    with pytest.raises(RateError):
        fetch(httpx.Response(200, content=body, headers={"content-type": "application/json"}))


@pytest.mark.parametrize("status", [204, 301, 400, 404, 406, 500, 503])
def test_unexpected_http_is_not_misreported_as_empty_history(status):
    with pytest.raises(RateError) as error:
        fetch(httpx.Response(status, json=[]))
    assert error.value.code == "unexpected_http_status"


def test_http_limits_and_payload_size():
    with pytest.raises(RateError) as error:
        fetch(httpx.Response(429, headers={"retry-after": "120"}))
    assert error.value.code == "upstream_rate_limited" and error.value.retry_after == 120
    for response in (httpx.Response(200, content=b"[]", headers={"content-type": "text/html"}),
                     httpx.Response(200, content=b" " * (MAX_BYTES + 1), headers={"content-type": "application/json"})):
        with pytest.raises(RateError):
            fetch(response)


@pytest.mark.parametrize("exception,code", [(httpx.ConnectError, "upstream_network_error"), (httpx.ReadTimeout, "upstream_timeout")])
def test_network_errors_sanitized(exception, code):
    async def run():
        def handler(request):
            raise exception("private transport details", request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(RateError) as error:
                await SGSProvider(http).fetch(12, PERIOD)
            assert error.value.code == code and "private" not in str(error.value)
    asyncio.run(run())


@pytest.mark.parametrize("start,end", [("2025-01-02", "2025-01-01"), ("2099-01-01", "2099-01-02"),
    ("2024-01-01", "2025-01-01")])
def test_invalid_future_or_oversized_periods(start, end):
    with pytest.raises(ValidationError):
        Period(start_date=start, end_date=end)


def test_cache_expiry_no_stale_fallback_cooldown_and_deduplication():
    async def run():
        clock, calls, fail = [0.0], [], [False]
        class Provider:
            async def fetch(self, code, period):
                calls.append(code)
                await asyncio.sleep(0)
                if fail[0]:
                    raise RateError("upstream_network_error")
                return (Observation(date=period.start_date, value=Decimal("0.05"), series_code=code),), 0
        service = RateService(Provider(), clock=lambda: clock[0])
        first, second = await asyncio.gather(service.get(12, PERIOD), service.get(12, PERIOD))
        assert len(calls) == 1 and not first.from_cache and second.from_cache
        assert second.fetched_at == first.fetched_at and second.expires_at == first.expires_at
        clock[0] = 21601
        fail[0] = True
        for _ in range(2):
            with pytest.raises(RateError) as error:
                await service.get(12, PERIOD)
            assert error.value.code == "upstream_network_error"
        assert len(calls) == 2  # failed refresh + cooldown; no expired value returned
        clock[0] += 31
        fail[0] = False
        assert not (await service.get(12, PERIOD)).from_cache
    asyncio.run(run())


def test_cache_empty_recent_ttls_and_lru_bound():
    async def run():
        clock, empty = [0.0], [True]
        class Provider:
            async def fetch(self, code, period):
                return (() if empty[0] else (Observation(date=period.end_date, value=Decimal(0), series_code=code),)), 0
        now = datetime.now(timezone.utc)
        service = RateService(Provider(), clock=lambda: clock[0], now=lambda: now)
        result = await service.get(11, PERIOD)
        assert result.status == "empty" and result.last_observation_date is None
        assert result.expires_at - result.fetched_at == timedelta(seconds=60)
        clock[0] = 61
        empty[0] = False
        from app.bcb_rates.schemas import today
        recent = Period(start_date=today(), end_date=today())
        result = await service.get(11, recent)
        assert result.expires_at - result.fetched_at == timedelta(seconds=900)
        for index in range(65):
            clock[0] += 61
            day = date(2020, 1, 1) + timedelta(days=index)
            await service.get(11, Period(start_date=day, end_date=day))
        assert len(service.cache) == 64
    asyncio.run(run())


def test_local_request_limit_and_upstream_retry_after():
    async def run():
        clock, calls = [0.0], []
        class Provider:
            async def fetch(self, code, period):
                calls.append(code)
                return (), 0
        service = RateService(Provider(), clock=lambda: clock[0])
        await service.get(12, PERIOD)
        with pytest.raises(RateError) as error:
            await service.get(11, PERIOD)
        assert error.value.code == "local_rate_limited" and len(calls) == 1
        for index in range(1, 30):
            clock[0] = index
            day = date(2020, 1, 1) + timedelta(days=index)
            await service.get(11, Period(start_date=day, end_date=day))
        clock[0] = 30
        with pytest.raises(RateError) as error:
            await service.get(11, PERIOD)
        assert error.value.code == "local_rate_limited" and len(calls) == 30
        assert (await service.get(12, PERIOD)).from_cache
    asyncio.run(run())


def test_total_timeout_releases_lock_and_unsupported_series_never_fetches():
    async def run():
        calls, blocked, clock = [], [True], [0.0]
        class Provider:
            async def fetch(self, code, period):
                calls.append(code)
                if blocked[0]:
                    await asyncio.Event().wait()
                return (), 0
        service = RateService(Provider(), timeout=0.01, clock=lambda: clock[0])
        with pytest.raises(RateError) as error:
            await service.get(12, PERIOD)
        assert error.value.code == "request_deadline_exceeded" and not service.lock.locked()
        blocked[0] = False
        clock[0] = 2
        assert (await service.get(12, PERIOD)).status == "empty"
        with pytest.raises(RateError) as error:
            await service.get(432, PERIOD)
        assert error.value.code == "unsupported_series" and len(calls) == 2
    asyncio.run(run())


def test_retry_after_never_shortens_a_valid_long_provider_wait():
    assert retry_seconds("7200") == 7200
    assert retry_seconds("bad header") == 60
    from email.utils import format_datetime
    assert retry_seconds(format_datetime(datetime.now(timezone.utc) + timedelta(hours=2))) >= 7190
