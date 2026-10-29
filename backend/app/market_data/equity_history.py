"""Historical B3 prices and share events from brapi, with a bounded process cache."""
import asyncio
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import httpx

from .brapi import valid_ticker
from .types import ProviderError

PRICE_ENDPOINT = "https://brapi.dev/api/v2/stocks/historical"
EVENT_ENDPOINT = "https://brapi.dev/api/v2/stocks/dividends"
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_SYMBOLS_PER_REQUEST = 20


@dataclass(frozen=True)
class DailyPrice:
    day: date
    raw_close: Decimal | None


@dataclass(frozen=True)
class ShareEvent:
    day: date
    factor: Decimal


@dataclass(frozen=True)
class TickerHistory:
    prices: tuple[DailyPrice, ...] = ()
    share_events: tuple[ShareEvent, ...] = ()
    error: str | None = None


def _safe_date(value) -> date:
    if isinstance(value, bool):
        raise ValueError("invalid date")
    if isinstance(value, (int, Decimal)):
        timestamp = int(value)
        if timestamp <= 0:
            raise ValueError("invalid date")
        return datetime.fromtimestamp(timestamp, timezone.utc).astimezone(SAO_PAULO).date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError("invalid date")


def _decimal(value, *, positive=True) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise ValueError("invalid decimal")
    result = Decimal(value)
    if not result.is_finite() or (positive and result <= 0) or result > Decimal("1e12") or result.as_tuple().exponent < -8:
        raise ValueError("invalid decimal")
    return result


class BrapiEquityHistoryProvider:
    """Requests unadjusted daily closes and separate stock-action factors.

    `includeRaw=true` is intentionally required: adjustedClose includes cash
    distributions and is not an appropriate mark-to-market price for shares held.
    """

    def __init__(self, client: httpx.AsyncClient, token: str):
        self.client, self._token = client, token

    async def _request(self, endpoint: str, symbols: list[str], params: dict) -> dict:
        if not symbols or len(symbols) > MAX_SYMBOLS_PER_REQUEST or any(not valid_ticker(t) for t in symbols):
            raise ProviderError("invalid_symbols")
        try:
            async with self.client.stream(
                "GET", endpoint, params={"symbols": ",".join(symbols), **params},
                headers={"Authorization": f"Bearer {self._token}"}, follow_redirects=False,
                timeout=httpx.Timeout(connect=2, read=12, write=2, pool=1),
            ) as response:
                if response.status_code in (401, 403):
                    raise ProviderError("provider_auth_error" if response.status_code == 401 else "raw_history_not_available", 900)
                if response.status_code == 429:
                    raise ProviderError("rate_limited", 300)
                if response.status_code == 404:
                    raise ProviderError("history_not_found")
                if response.status_code != 200:
                    raise ProviderError("provider_http_error")
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ProviderError("response_too_large")
            payload = json.loads(body, parse_float=Decimal, parse_int=Decimal)
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list) or any(not isinstance(item, dict) for item in payload["results"]):
                raise ProviderError("invalid_response")
            return payload
        except httpx.TimeoutException:
            raise ProviderError("provider_timeout", 60) from None
        except httpx.HTTPError:
            raise ProviderError("provider_unavailable", 60) from None
        except (ValueError, TypeError, UnicodeDecodeError):
            raise ProviderError("invalid_response") from None

    async def fetch(self, tickers: list[str], *, price_start: date, event_start: date, end: date) -> dict[str, TickerHistory]:
        tickers = list(dict.fromkeys(tickers))
        result: dict[str, TickerHistory] = {ticker: TickerHistory() for ticker in tickers}
        # brapi supports up to 20 symbols per history call; events are requested
        # separately because cash distributions must never be used as prices.
        for offset in range(0, len(tickers), MAX_SYMBOLS_PER_REQUEST):
            group = tickers[offset:offset + MAX_SYMBOLS_PER_REQUEST]
            try:
                prices_payload = await self._request(PRICE_ENDPOINT, group, {
                    "startDate": price_start.isoformat(), "endDate": end.isoformat(),
                    "interval": "1d", "sortOrder": "asc", "includeRaw": "true",
                })
                by_ticker = {ticker: [] for ticker in group}
                errors = {}
                seen = set()
                for item in prices_payload["results"]:
                    ticker = item.get("requestedSymbol")
                    if ticker not in by_ticker or item.get("symbol") != ticker or item.get("changed") is True:
                        if ticker in by_ticker:
                            errors[ticker] = "symbol_changed"
                        continue
                    if ticker in seen:
                        errors[ticker] = "ambiguous_history"
                        by_ticker[ticker] = []
                        continue
                    seen.add(ticker)
                    bars = item.get("data", {}).get("historicalDataPrice")
                    if not isinstance(bars, list):
                        errors[ticker] = "history_not_found"
                        continue
                    try:
                        for bar in bars:
                            # Never fall back to close/adjustedClose: they can be adjusted.
                            raw = bar.get("rawClose")
                            day = _safe_date(bar.get("date"))
                            close = _decimal(raw) if raw is not None else None
                            if price_start <= day <= end:
                                by_ticker[ticker].append(DailyPrice(day, close))
                        if not any(bar.raw_close is not None for bar in by_ticker[ticker]):
                            errors[ticker] = "raw_price_unavailable"
                    except (ValueError, InvalidOperation, OverflowError, AttributeError):
                        errors[ticker] = "invalid_price_data"
                for ticker in group:
                    if ticker not in seen and ticker not in errors:
                        errors[ticker] = "history_not_found"
                    result[ticker] = TickerHistory(tuple(sorted(by_ticker[ticker], key=lambda p: p.day)), error=errors.get(ticker))
            except ProviderError as error:
                for ticker in tickers[offset:]:
                    result[ticker] = TickerHistory(error=error.reason)
                return result

            try:
                events_payload = await self._request(EVENT_ENDPOINT, group, {
                    "startDate": event_start.isoformat(), "endDate": end.isoformat(), "sortBy": "lastDatePrior", "sortOrder": "asc",
                })
                events_by_ticker: dict[str, list[ShareEvent]] = {ticker: [] for ticker in group}
                event_errors = {}
                seen_events = set()
                for item in events_payload["results"]:
                    ticker = item.get("requestedSymbol")
                    if ticker not in events_by_ticker or item.get("symbol") != ticker or item.get("changed") is True:
                        if ticker in events_by_ticker:
                            event_errors[ticker] = "symbol_changed"
                        continue
                    if ticker in seen_events:
                        event_errors[ticker] = "ambiguous_corporate_actions"
                        events_by_ticker[ticker] = []
                        continue
                    seen_events.add(ticker)
                    data = item.get("data")
                    if not isinstance(data, dict) or not isinstance(data.get("stockDividends"), list):
                        event_errors[ticker] = "corporate_actions_unavailable"
                        continue
                    try:
                        for event in data["stockDividends"]:
                            # Brapi defines factor as new shares per existing share;
                            # exDate is the first date whose close uses the new count.
                            day = _safe_date(event.get("exDate"))
                            factor = _decimal(event.get("factor"))
                            if event_start <= day <= end:
                                events_by_ticker[ticker].append(ShareEvent(day, factor))
                    except (ValueError, InvalidOperation, OverflowError, AttributeError):
                        event_errors[ticker] = "invalid_corporate_action"
                for ticker in group:
                    prior = result[ticker]
                    if ticker not in seen_events and ticker not in event_errors:
                        event_errors[ticker] = "corporate_actions_unavailable"
                    result[ticker] = TickerHistory(prior.prices, tuple(sorted(events_by_ticker[ticker], key=lambda e: e.day)),
                                                   prior.error or event_errors.get(ticker))
            except ProviderError as error:
                for ticker in group:
                    prior = result[ticker]
                    result[ticker] = TickerHistory(prior.prices, (), prior.error or error.reason)
                for ticker in tickers[offset + len(group):]:
                    result[ticker] = TickerHistory(error=error.reason)
                return result
        return result


class EquityHistoryService:
    """Coalesces concurrent reads and caches only public source data per query."""
    def __init__(self, provider: BrapiEquityHistoryProvider, *, enabled=False, configured=False,
                 clock=time.monotonic, ttl=1800, capacity=24):
        self.provider, self.enabled, self.configured = provider, enabled, configured
        self.clock, self.ttl, self.capacity = clock, ttl, capacity
        self.cache: dict[tuple, tuple[float, dict[str, TickerHistory]]] = {}
        self.lock = asyncio.Lock()
        self.cooldown_until = 0.0
        self.cooldown_reason = "provider_unavailable"

    async def get(self, tickers: list[str], *, price_start: date, event_start: date, end: date) -> dict[str, TickerHistory]:
        unique = tuple(sorted(set(tickers)))
        if not self.enabled or not self.configured:
            reason = "disabled" if not self.enabled else "missing_token"
            return {ticker: TickerHistory(error=reason) for ticker in unique}
        if any(not valid_ticker(ticker) for ticker in unique):
            return {ticker: TickerHistory(error="invalid_ticker") for ticker in unique}
        key = (unique, price_start, event_start, end)
        cached = self.cache.get(key)
        if cached and cached[0] > self.clock():
            return cached[1]
        async with self.lock:
            cached = self.cache.get(key)
            if cached and cached[0] > self.clock():
                return cached[1]
            if self.cooldown_until > self.clock():
                return {ticker: TickerHistory(error=self.cooldown_reason) for ticker in unique}
            values = await self.provider.fetch(list(unique), price_start=price_start, event_start=event_start, end=end)
            reasons = {value.error for value in values.values()}
            if "rate_limited" in reasons:
                self.cooldown_until, self.cooldown_reason = self.clock() + 300, "rate_limited"
            elif "provider_auth_error" in reasons or "raw_history_not_available" in reasons:
                self.cooldown_until, self.cooldown_reason = self.clock() + 900, next(
                    reason for reason in ("raw_history_not_available", "provider_auth_error") if reason in reasons)
            cache_for = self.ttl if all(value.error is None for value in values.values()) else min(self.ttl, 60)
            self.cache[key] = (self.clock() + cache_for, values)
            while len(self.cache) > self.capacity:
                self.cache.pop(next(iter(self.cache)))
            return values
