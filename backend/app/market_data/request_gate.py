"""One bounded request slot and process budget shared by Brapi providers."""
import asyncio
from contextlib import asynccontextmanager
from .types import ProviderError


@asynccontextmanager
async def request_slot(gate):
    if gate is None:
        yield
    else:
        async with gate.request():
            yield


class BrapiRequestGate:
    def __init__(self, max_requests: int = 12_000):
        self._semaphore = asyncio.Semaphore(1)
        self._max_requests = max_requests
        self.requests = 0

    @asynccontextmanager
    async def request(self):
        async with self._semaphore:
            if self.requests >= self._max_requests:
                raise ProviderError("request_budget_exhausted", 3600)
            self.requests += 1
            yield
