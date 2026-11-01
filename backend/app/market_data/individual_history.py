"""Brapi Free daily adjusted closes for one symbol per request."""
import json
import calendar
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import httpx

from .brapi import valid_ticker
from .request_gate import BrapiRequestGate, request_slot
from .types import ProviderError
from ..individual_equity_history import (
    PriceHistoryProvider, PriceHistoryUnavailable, ProviderDailyPrice, ProviderPriceHistory,
)

ENDPOINT = "https://brapi.dev/api/v2/stocks/historical"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def _subtract_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 - months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _date(value) -> date:
    if isinstance(value, bool):
        raise ValueError("invalid date")
    if isinstance(value, (int, Decimal)):
        stamp = int(value)
        if stamp <= 0:
            raise ValueError("invalid date")
        return datetime.fromtimestamp(stamp, timezone.utc).astimezone(SAO_PAULO).date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError("invalid date")


def _price(value) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise ValueError("invalid adjusted close")
    result = Decimal(value)
    if not result.is_finite() or result <= 0 or result > Decimal("1e12") or result.as_tuple().exponent < -8:
        raise ValueError("invalid adjusted close")
    return result


class BrapiIndividualHistoryProvider(PriceHistoryProvider):
    def __init__(self, client: httpx.AsyncClient, token: str, request_gate: BrapiRequestGate | None = None,
                 *, clock=time.monotonic, cache_ttl=1800, cache_capacity=128):
        self.client, self._token, self.request_gate = client, token, request_gate
        self.clock, self.cache_ttl, self.cache_capacity = clock, cache_ttl, cache_capacity
        self.cache: dict[tuple, tuple[float, tuple[ProviderDailyPrice, ...]]] = {}

    async def fetch(self, ticker: str, *, start: date | None, end: date) -> ProviderPriceHistory:
        if not valid_ticker(ticker):
            raise PriceHistoryUnavailable("ticker_not_found")
        free_start = _subtract_months(end, 3)
        actual_start = max(start, free_start) if start is not None else free_start
        params = {
            "symbols": ticker,
            "startDate": actual_start.isoformat(),
            "endDate": end.isoformat(),
            "interval": "1d",
            "sortOrder": "asc",
        }
        key = (ticker, actual_start, end)
        cached = self.cache.get(key)
        if cached and cached[0] > self.clock():
            return ProviderPriceHistory(
                ticker=ticker, source="brapi", currency="BRL", price_basis="adjusted_close",
                points=cached[1], partial=(start is None or start < free_start),
            )
        try:
            async with request_slot(self.request_gate):
                async with self.client.stream(
                    "GET", ENDPOINT, params=params,
                    headers={"Authorization": f"Bearer {self._token}"},
                    follow_redirects=False,
                    timeout=httpx.Timeout(connect=2, read=12, write=2, pool=1),
                ) as response:
                    if response.status_code == 401:
                        raise PriceHistoryUnavailable("provider_auth_error")
                    if response.status_code == 403:
                        raise PriceHistoryUnavailable("provider_forbidden")
                    if response.status_code == 429:
                        raise PriceHistoryUnavailable("provider_rate_limited")
                    if response.status_code == 404:
                        raise PriceHistoryUnavailable("ticker_not_found")
                    if response.status_code != 200:
                        raise PriceHistoryUnavailable("provider_unavailable")
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise PriceHistoryUnavailable("invalid_provider_response")
            payload = json.loads(body, parse_float=Decimal, parse_int=Decimal)
            results = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(results, list):
                raise ValueError("invalid results")
            if not results:
                raise PriceHistoryUnavailable("ticker_not_found")
            if len(results) != 1:
                raise ValueError("expected one symbol")
            item = results[0]
            if (not isinstance(item, dict) or item.get("requestedSymbol") != ticker
                    or item.get("symbol") != ticker or item.get("changed") is True):
                raise PriceHistoryUnavailable("ticker_not_found")
            data = item.get("data")
            bars = data.get("historicalDataPrice") if isinstance(data, dict) else None
            if not isinstance(bars, list) or len(bars) > 20_000:
                raise ValueError("invalid bars")
            points = []
            seen = set()
            for bar in bars:
                if not isinstance(bar, dict):
                    raise ValueError("invalid bar")
                day = _date(bar.get("date"))
                if day in seen:
                    raise ValueError("duplicate date")
                seen.add(day)
                raw = bar.get("adjustedClose")
                if raw is None:
                    continue
                if actual_start <= day <= end:
                    points.append(ProviderDailyPrice(day, _price(raw)))
            points.sort(key=lambda point: point.date)
            self.cache[key] = (self.clock() + self.cache_ttl, tuple(points))
            while len(self.cache) > self.cache_capacity:
                self.cache.pop(next(iter(self.cache)))
            return ProviderPriceHistory(
                ticker=ticker, source="brapi", currency="BRL", price_basis="adjusted_close",
                points=tuple(points), partial=(start is None or start < free_start),
            )
        except PriceHistoryUnavailable:
            raise
        except ProviderError as error:
            reason = "request_budget_exhausted" if error.reason == "request_budget_exhausted" else "provider_unavailable"
            raise PriceHistoryUnavailable(reason) from None
        except httpx.TimeoutException:
            raise PriceHistoryUnavailable("provider_unavailable") from None
        except httpx.HTTPError:
            raise PriceHistoryUnavailable("provider_unavailable") from None
        except (ValueError, TypeError, KeyError, AttributeError, InvalidOperation, OverflowError, UnicodeDecodeError):
            raise PriceHistoryUnavailable("invalid_provider_response") from None
