import asyncio
import time
from collections import OrderedDict, deque
from datetime import datetime, timedelta, timezone
from .schemas import Period, RateHistory, RateError, SERIES, today


class RateService:
    """Public-rate cache only; bounded RAM, no persistence, no stale fallback or polling."""
    def __init__(self, provider, *, clock=time.monotonic, now=lambda: datetime.now(timezone.utc), timeout=8):
        self.provider, self.clock, self.now = provider, clock, now
        self.cache = OrderedDict()
        self.lock = asyncio.Lock()
        self.requests = deque()
        self.next_request = 0.0
        self.cooldown = 0.0
        self.failure = None
        self.timeout = timeout

    def cached(self, key):
        entry = self.cache.get(key)
        if entry:
            result, expires = entry
            if expires > self.clock():
                self.cache.move_to_end(key)
                return result.model_copy(update={"from_cache": True})
            del self.cache[key]
        return None

    async def get(self, code: int, period: Period):
        if code not in SERIES:
            raise RateError("unsupported_series", 422)
        period = Period(**period.model_dump())
        key = (code, period.start_date, period.end_date)
        result = self.cached(key)
        if result is not None:
            return result
        try:
            async with asyncio.timeout(self.timeout):
                async with self.lock:
                    result = self.cached(key)
                    if result is not None:
                        return result
                    clock = self.clock()
                    if clock < self.cooldown:
                        raise RateError(self.failure.code, self.failure.status, max(1, int(self.cooldown - clock)))
                    while self.requests and self.requests[0] <= clock - 60:
                        self.requests.popleft()
                    if clock < self.next_request or len(self.requests) >= 30:
                        wait = self.next_request - clock if len(self.requests) < 30 else self.requests[0] + 60 - clock
                        raise RateError("local_rate_limited", 429, max(1, int(wait) + 1))
                    self.requests.append(clock)
                    self.next_request = clock + 1
                    try:
                        observations, duplicates = await self.provider.fetch(code, period)
                    except RateError as error:
                        self.failure, self.cooldown = error, self.clock() + error.retry_after
                        raise
                    fetched_at = self.now()
                    ttl = 60 if not observations else 900 if period.end_date >= today() - timedelta(days=7) else 21600
                    result = RateHistory(series_code=code, name=SERIES[code], start_date=period.start_date,
                        end_date=period.end_date, status="ok" if observations else "empty", observations=observations,
                        duplicates_removed=duplicates, last_observation_date=observations[-1].date if observations else None,
                        fetched_at=fetched_at, expires_at=fetched_at + timedelta(seconds=ttl))
                    self.cache[key] = (result, self.clock() + ttl)
                    self.cache.move_to_end(key)
                    while len(self.cache) > 64:
                        self.cache.popitem(last=False)
                    return result
        except TimeoutError:
            raise RateError("request_deadline_exceeded") from None
