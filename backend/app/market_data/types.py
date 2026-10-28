from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict


class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)
    ticker: str
    price: str | None = None
    currency: str = "BRL"
    provider: str = "brapi"
    status: Literal["ok", "stale", "no_data", "provider_error", "unavailable", "disabled"]
    reason: str | None = None
    quoted_at: datetime | None = None
    fetched_at: datetime | None = None
    from_cache: bool = False
    is_stale: bool = False
    expected_delay_seconds: int = 1800
    retry_after_seconds: int | None = None


class ProviderError(Exception):
    def __init__(self, reason: str, retry_after: int = 60):
        super().__init__(reason)  # Only controlled codes, never HTTP exceptions/payloads.
        self.reason = reason
        self.retry_after = retry_after
