from datetime import datetime
from typing import Protocol
from .types import Quote


class MarketDataProvider(Protocol):
    async def fetch(self, ticker: str, now: datetime) -> Quote: ...
