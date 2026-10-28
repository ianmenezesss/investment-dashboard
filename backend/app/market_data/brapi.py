import json
import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import httpx
from .types import ProviderError, Quote

ENDPOINT = "https://brapi.dev/api/v2/stocks/quote"


def valid_ticker(ticker: str) -> bool:
    # B3SA3 contains a digit in its four-character issuer code. No URLs, suffixes or lists.
    return isinstance(ticker, str) and re.fullmatch(r"[A-Z0-9]{4}[0-9]{1,2}", ticker) is not None


def retry_after(value: str | None, now: datetime) -> int:
    try:
        seconds = int(value) if value and value.isdigit() else int((parsedate_to_datetime(value) - now).total_seconds())
        return max(60, min(seconds, 86400))
    except (ValueError, TypeError, OverflowError):
        return 60


class BrapiProvider:
    def __init__(self, client: httpx.AsyncClient, token: str):
        self.client = client
        self._token = token

    async def fetch(self, ticker: str, now: datetime) -> Quote:
        if not valid_ticker(ticker):
            return Quote(ticker=ticker, status="unavailable", reason="invalid_ticker")
        try:
            async with self.client.stream(
                "GET", ENDPOINT, params={"symbols": ticker},
                headers={"Authorization": f"Bearer {self._token}"},
                follow_redirects=False,
                timeout=httpx.Timeout(connect=1, read=2, write=2, pool=0.5),
            ) as response:
                if response.status_code in (401, 403):
                    raise ProviderError("provider_auth_error" if response.status_code == 401 else "provider_forbidden", 900)
                if response.status_code == 429:
                    raise ProviderError("rate_limited", retry_after(response.headers.get("Retry-After"), now))
                if response.status_code == 404:
                    return Quote(ticker=ticker, status="no_data", reason="not_found", fetched_at=now)
                if response.status_code != 200:
                    raise ProviderError("provider_http_error")
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise ProviderError("invalid_response")
            payload = json.loads(body, parse_float=Decimal)
            results = payload["results"]
            if not isinstance(results, list):
                raise ProviderError("invalid_response")
            if not results:
                return Quote(ticker=ticker, status="no_data", reason="not_found", fetched_at=now)
            if len(results) != 1:
                raise ProviderError("invalid_response")
            item = results[0]
            if item.get("changed") is True:
                return Quote(ticker=ticker, status="no_data", reason="symbol_changed", fetched_at=now)
            if item["requestedSymbol"] != ticker or item["symbol"] != ticker:
                raise ProviderError("invalid_response")
            data = item["data"]
            raw = data.get("regularMarketPrice")
            if raw is None:
                return Quote(ticker=ticker, status="no_data", reason="missing_price", fetched_at=now)
            if isinstance(raw, bool) or not isinstance(raw, (Decimal, int, str)):
                raise ProviderError("invalid_response")
            price = Decimal(raw)
            if not price.is_finite() or price <= 0 or price > Decimal("1e12") or price.as_tuple().exponent < -8:
                raise ProviderError("invalid_response")
            if data["currency"] != "BRL":
                raise ProviderError("unsupported_currency")
            quoted_at = datetime.fromisoformat(data["regularMarketTime"])
            if quoted_at.tzinfo is None or quoted_at > now + timedelta(seconds=60):
                raise ProviderError("invalid_response")
            return Quote(ticker=ticker, price=format(price, "f"), status="ok",
                         quoted_at=quoted_at.astimezone(timezone.utc), fetched_at=now)
        except httpx.HTTPError:
            raise ProviderError("network_error") from None
        except (ValueError, TypeError, KeyError, AttributeError, InvalidOperation, OverflowError):
            raise ProviderError("invalid_response") from None
