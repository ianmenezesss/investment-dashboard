import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
import httpx
from pydantic import ValidationError
from .schemas import Observation, Period, RateError, SERIES

BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
MAX_BYTES = 256 * 1024


def retry_seconds(value):
    try:
        if value and len(value) > 64:
            return 86400
        seconds = int(value) if value and value.isdigit() else int((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        return max(60, seconds)
    except (ValueError, TypeError, OverflowError):
        return 60


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("Non-standard JSON numeric constant")


def parse_payload(payload: bytes, code: int, period: Period):
    try:
        rows = json.loads(payload, parse_float=Decimal, parse_int=Decimal,
                          parse_constant=reject_constant, object_pairs_hook=unique_keys)
        if not isinstance(rows, list) or len(rows) > 732:
            raise ValueError()
        points, duplicates = {}, 0
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("data"), str) or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", row["data"]):
                raise ValueError()
            day = datetime.strptime(row["data"], "%d/%m/%Y").date()
            if not period.start_date <= day <= period.end_date:
                raise ValueError()
            value = row.get("valor")
            if isinstance(value, str):
                if len(value) > 32 or not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
                    raise ValueError()
                value = Decimal(value)
            elif not isinstance(value, Decimal):
                raise ValueError()
            point = Observation(date=day, value=value, series_code=code)
            if day in points:
                if points[day].value != point.value:
                    raise ValueError()
                duplicates += 1
            points[day] = point
        return tuple(points[day] for day in sorted(points)), duplicates
    except (ValueError, TypeError, ArithmeticError, ValidationError, RecursionError):
        raise RateError("invalid_payload", 502) from None


class SGSProvider:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def fetch(self, code: int, period: Period):
        if code not in SERIES:
            raise RateError("unsupported_series", 422)
        # Revalidate at the boundary even if invoked outside FastAPI.
        period = Period(**period.model_dump())
        try:
            async with self.client.stream("GET", BASE_URL.format(code=code),
                params={"formato": "json", "dataInicial": period.start_date.strftime("%d/%m/%Y"),
                        "dataFinal": period.end_date.strftime("%d/%m/%Y")},
                follow_redirects=False, timeout=httpx.Timeout(connect=2, read=5, write=2, pool=1)) as response:
                if response.status_code == 429:
                    raise RateError("upstream_rate_limited", 429, retry_seconds(response.headers.get("Retry-After")))
                if response.status_code != 200:
                    raise RateError("unexpected_http_status", 502)
                if response.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                    raise RateError("invalid_content_type", 502)
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise RateError("payload_too_large", 502)
            return parse_payload(bytes(data), code, period)
        except httpx.TimeoutException:
            raise RateError("upstream_timeout") from None
        except httpx.HTTPError:
            raise RateError("upstream_network_error") from None
