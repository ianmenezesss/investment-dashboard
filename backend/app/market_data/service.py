import asyncio
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from .brapi import valid_ticker
from .provider import MarketDataProvider
from .types import ProviderError, Quote


@dataclass
class Entry:
    result: Quote
    good: Quote | None
    expires: float


class QuoteService:
    """One provider, B3/BRL/v2, one process. No private financial data in the cache."""
    def __init__(self, provider: MarketDataProvider, *, enabled=False, configured=False,
                 clock=time.monotonic, now=lambda: datetime.now(timezone.utc),
                 capacity=256, max_requests=12000):
        self.provider = provider
        self.enabled, self.configured = enabled, configured
        self.clock, self.now = clock, now
        self.capacity, self.max_requests = capacity, max_requests
        self.cache: OrderedDict[str, Entry] = OrderedDict()
        self.lock = asyncio.Lock()
        self.cooldown = 0.0
        self.cooldown_reason = "rate_limited"
        self.stats = Counter()

    def _view(self, quote: Quote, *, cached=False) -> Quote:
        if quote.price is None:
            return quote.model_copy(update={"from_cache": cached})
        age = (self.now() - quote.quoted_at).total_seconds()
        if age > 96 * 3600:
            return quote.model_copy(update={"price": None, "status": "unavailable", "reason": "quote_too_old", "is_stale": True, "from_cache": cached})
        stale = quote.is_stale or age > 75 * 60
        return quote.model_copy(update={"status": "stale" if stale else "ok", "is_stale": stale, "from_cache": cached})

    def _failure(self, ticker, reason, good=None, wait=None, status="provider_error"):
        if good and self._view(good).price is not None:
            return self._view(good.model_copy(update={"status": "stale", "is_stale": True, "reason": reason, "retry_after_seconds": wait}), cached=True)
        return Quote(ticker=ticker, status=status, reason=reason, retry_after_seconds=wait)

    def _save(self, ticker, result, good, ttl):
        self.cache[ticker] = Entry(result, good, self.clock() + ttl)
        self.cache.move_to_end(ticker)
        while len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def _cached(self, ticker):
        entry = self.cache.get(ticker)
        if entry and entry.expires > self.clock():
            self.cache.move_to_end(ticker)
            self.stats["hits"] += 1
            return self._view(entry.result, cached=True)
        return None

    async def get(self, ticker: str, *, timeout=8) -> Quote:
        if not valid_ticker(ticker):
            return Quote(ticker=ticker, status="unavailable", reason="invalid_ticker")
        if not self.enabled or not self.configured:
            return Quote(ticker=ticker, status="disabled", reason="disabled" if not self.enabled else "missing_token")
        cached = self._cached(ticker)
        if cached is not None:
            return cached
        if timeout <= 0:
            entry = self.cache.get(ticker)
            return self._failure(ticker, "deadline_exceeded", entry.good if entry else None)
        try:
            async with asyncio.timeout(timeout):
                # Serializes the whole free-plan account and deduplicates concurrent misses.
                async with self.lock:
                    cached = self._cached(ticker)
                    if cached is not None:
                        return cached
                    entry = self.cache.get(ticker)
                    good = entry.good if entry else None
                    if self.clock() < self.cooldown:
                        return self._failure(ticker, self.cooldown_reason, good, max(1, int(self.cooldown - self.clock())))
                    if self.stats["requests"] >= self.max_requests:
                        return self._failure(ticker, "request_budget_exhausted", good)
                    self.stats["misses"] += 1
                    self.stats["requests"] += 1
                    try:
                        quote = await self.provider.fetch(ticker, self.now())
                    except ProviderError as error:
                        self.stats["errors"] += 1
                        if error.reason in ("rate_limited", "provider_auth_error", "provider_forbidden"):
                            self.cooldown, self.cooldown_reason = self.clock() + error.retry_after, error.reason
                        result = self._failure(ticker, error.reason, good, error.retry_after)
                        self._save(ticker, result, good, 60)
                        return result
                    if quote.price is not None:
                        self._save(ticker, quote, quote, 1800)
                        return self._view(quote)
                    result = self._failure(ticker, quote.reason, good, status=quote.status) if good else quote
                    self._save(ticker, result, good, 60)
                    return result
        except TimeoutError:
            self.stats["errors"] += 1
            entry = self.cache.get(ticker)
            return self._failure(ticker, "deadline_exceeded", entry.good if entry else None)

    async def get_many(self, tickers: list[str]) -> list[Quote]:
        deadline = self.clock() + 8
        return [await self.get(ticker, timeout=max(0, deadline - self.clock())) for ticker in dict.fromkeys(tickers)]
