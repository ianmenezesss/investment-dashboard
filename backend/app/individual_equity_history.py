"""Provider-neutral, owner-scoped daily price history for one equity position.

No external provider is configured in this phase. The service and response
contract are deliberately independent of the existing quote and portfolio-history
services so a later source can be added only after data and license validation.
"""
import calendar
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .access import private_db
from .finance import summarize
from .market_data.brapi import valid_ticker
from .models import Operation

HistoryPeriod = Literal["1M", "3M", "6M", "1A", "MAX"]
PriceBasis = Literal["raw_close", "adjusted_close", "unknown"]
Availability = Literal["available", "disabled", "unavailable", "empty"]
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
MAX_DAILY_POINTS = 20_000


class DailyPricePoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: date
    close: str

    @field_validator("close")
    @classmethod
    def valid_close(cls, value: str) -> str:
        try:
            amount = Decimal(value)
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("invalid close") from None
        if not amount.is_finite() or amount <= 0 or amount > Decimal("1e12") or amount.as_tuple().exponent < -8:
            raise ValueError("invalid close")
        return format(amount, "f")


class IndividualEquityPriceHistory(BaseModel):
    model_config = ConfigDict(frozen=True)
    ticker: str
    period: HistoryPeriod
    currency: str = "BRL"
    source: str | None = None
    price_basis: PriceBasis = "unknown"
    period_start: date | None = None
    period_end: date
    coverage_start: date | None = None
    coverage_end: date | None = None
    points: list[DailyPricePoint]
    availability: Availability
    reason: Literal[
        "feature_disabled", "provider_not_configured", "provider_unavailable",
        "ticker_not_found", "invalid_provider_response",
    ] | None = None

    @model_validator(mode="after")
    def consistent_coverage(self):
        dates = [point.date for point in self.points]
        if dates != sorted(dates) or len(dates) != len(set(dates)):
            raise ValueError("price points must be uniquely ordered by date")
        if self.points:
            if self.coverage_start != dates[0] or self.coverage_end != dates[-1]:
                raise ValueError("coverage must match returned points")
        elif self.coverage_start is not None or self.coverage_end is not None:
            raise ValueError("empty points cannot have coverage dates")
        if self.availability == "available" and not self.points:
            raise ValueError("available history requires points")
        if self.availability == "empty" and self.points:
            raise ValueError("empty history cannot have points")
        return self


@dataclass(frozen=True)
class ProviderDailyPrice:
    date: date
    close: Decimal


@dataclass(frozen=True)
class ProviderPriceHistory:
    ticker: str
    source: str
    currency: str
    price_basis: PriceBasis
    points: tuple[ProviderDailyPrice, ...]


class PriceHistoryProvider(Protocol):
    async def fetch(self, ticker: str, *, start: date | None, end: date) -> ProviderPriceHistory: ...


class PriceHistoryUnavailable(Exception):
    def __init__(self, reason: Literal["provider_unavailable", "ticker_not_found"]):
        self.reason = reason
        super().__init__(reason)


def _subtract_months(day: date, months: int) -> date:
    month_index = day.year * 12 + day.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _period_start(period: HistoryPeriod, end: date) -> date | None:
    months = {"1M": 1, "3M": 3, "6M": 6, "1A": 12}.get(period)
    return _subtract_months(end, months) if months is not None else None


class EquityPriceHistoryService:
    def __init__(self, provider: PriceHistoryProvider | None, *, enabled: bool,
                 today=lambda: datetime.now(SAO_PAULO).date()):
        self.provider = provider
        self.enabled = enabled
        self.today = today

    async def get(self, ticker: str, period: HistoryPeriod) -> IndividualEquityPriceHistory:
        end = self.today()
        start = _period_start(period, end)
        if not self.enabled:
            return IndividualEquityPriceHistory(ticker=ticker, period=period, period_start=start,
                period_end=end, points=[], availability="disabled", reason="feature_disabled")
        if self.provider is None:
            return IndividualEquityPriceHistory(ticker=ticker, period=period, period_start=start,
                period_end=end, points=[], availability="unavailable", reason="provider_not_configured")
        try:
            history = await self.provider.fetch(ticker, start=start, end=end)
        except PriceHistoryUnavailable as error:
            return IndividualEquityPriceHistory(ticker=ticker, period=period, period_start=start,
                period_end=end, points=[], availability="unavailable", reason=error.reason)
        if (not isinstance(history.ticker, str) or history.ticker != ticker
                or not isinstance(history.source, str) or not history.source.strip()
                or history.currency != "BRL" or history.price_basis not in ("raw_close", "adjusted_close", "unknown")
                or not isinstance(history.points, (tuple, list))):
            return IndividualEquityPriceHistory(ticker=ticker, period=period, period_start=start,
                period_end=end, points=[], availability="unavailable", reason="invalid_provider_response")
        if len(history.points) > MAX_DAILY_POINTS:
            return IndividualEquityPriceHistory(ticker=ticker, period=period, period_start=start,
                period_end=end, points=[], availability="unavailable", reason="invalid_provider_response")
        try:
            bars = sorted(history.points, key=lambda point: point.date)
            if len({point.date for point in bars}) != len(bars):
                raise ValueError("duplicate daily point")
            filtered = [point for point in bars if point.date <= end and (start is None or point.date >= start)]
            points = []
            for point in filtered:
                if not isinstance(point.close, Decimal):
                    raise ValueError("close must be Decimal")
                points.append(DailyPricePoint(date=point.date, close=format(point.close, "f")))
        except (InvalidOperation, TypeError, ValueError, AttributeError):
            return IndividualEquityPriceHistory(ticker=ticker, period=period, period_start=start,
                period_end=end, points=[], availability="unavailable", reason="invalid_provider_response")
        return IndividualEquityPriceHistory(ticker=ticker, period=period, currency=history.currency,
            source=history.source, price_basis=history.price_basis, period_start=start, period_end=end,
            coverage_start=points[0].date if points else None, coverage_end=points[-1].date if points else None,
            points=points, availability="available" if points else "empty")


router = APIRouter()


def individual_equity_price_history_service(request: Request) -> EquityPriceHistoryService:
    service = getattr(request.app.state, "individual_equity_price_history_service", None)
    if service is None:
        raise HTTPException(503, "Serviço de histórico individual não inicializado")
    return service


@router.get(
    "/api/dashboard/equities/{ticker}/price-history",
    response_model=IndividualEquityPriceHistory,
)
async def individual_equity_price_history(
    ticker: str = Path(pattern=r"^[A-Z0-9]{4}[0-9]{1,2}$"),
    period: HistoryPeriod = Query("MAX"),
    db: Session = Depends(private_db),
    service: EquityPriceHistoryService = Depends(individual_equity_price_history_service),
):
    if not valid_ticker(ticker):
        raise HTTPException(422, "Ticker inválido")
    owner = db.info.get("owner_id")
    operations = list(db.scalars(select(Operation).where(Operation.owner_id == owner)
        .order_by(Operation.date, Operation.id)))
    held_tickers = {item["ticker"] for item in summarize(operations)["holdings"]}
    if ticker not in held_tickers:
        # 404 intentionally does not reveal whether another owner's ticker exists.
        raise HTTPException(404, "Ativo não encontrado na carteira")
    # Future provider I/O must not hold a database transaction/connection open.
    db.rollback()
    return await service.get(ticker, period)
