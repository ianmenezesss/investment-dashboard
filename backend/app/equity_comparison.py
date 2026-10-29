"""Owner-scoped comparison of real daily equity prices using a common base date."""
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .access import private_db
from .finance import summarize
from .individual_equity_history import (
    EquityPriceHistoryService,
    HistoryPeriod,
    PriceBasis,
    individual_equity_price_history_service,
)
from .market_data.brapi import valid_ticker
from .models import Operation

ComparisonAvailability = Literal["available", "disabled", "unavailable", "empty"]
ComparisonReason = Literal[
    "feature_disabled", "provider_not_configured", "provider_unavailable",
    "ticker_not_found", "invalid_provider_response", "incompatible_data",
    "no_common_date", "empty_history",
]


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


class ComparisonPoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: date
    values: dict[str, str | None]


class ComparisonCoverage(BaseModel):
    model_config = ConfigDict(frozen=True)
    ticker: str
    coverage_start: date
    coverage_end: date
    base_price: str


class EquityComparison(BaseModel):
    model_config = ConfigDict(frozen=True)
    tickers: list[str]
    period: HistoryPeriod
    currency: str | None
    source: str | None
    price_basis: PriceBasis | None
    period_start: date | None
    period_end: date
    common_start_date: date | None
    coverage: list[ComparisonCoverage]
    points: list[ComparisonPoint]
    availability: ComparisonAvailability
    reason: ComparisonReason | None = None

    @model_validator(mode="after")
    def validate_comparison(self):
        dates = [point.date for point in self.points]
        if dates != sorted(dates) or len(dates) != len(set(dates)):
            raise ValueError("comparison dates must be uniquely ordered")
        if self.availability == "available":
            if self.common_start_date is None or not self.points or self.points[0].date != self.common_start_date:
                raise ValueError("available comparison requires a common first date")
            if [entry.ticker for entry in self.coverage] != self.tickers:
                raise ValueError("coverage must match requested tickers")
            first_values = self.points[0].values
            if any(first_values.get(ticker) != "100" for ticker in self.tickers):
                raise ValueError("all series must start at base 100")
            if any(set(point.values) != set(self.tickers) for point in self.points):
                raise ValueError("each point must include every ticker")
        elif self.points or self.coverage or self.common_start_date is not None:
            raise ValueError("unavailable comparison cannot contain normalized prices")
        return self


def _unavailable(
    tickers: list[str], period: HistoryPeriod, period_start: date | None, period_end: date,
    availability: ComparisonAvailability, reason: ComparisonReason,
) -> EquityComparison:
    return EquityComparison(
        tickers=tickers, period=period, currency=None, source=None, price_basis=None,
        period_start=period_start, period_end=period_end, common_start_date=None,
        coverage=[], points=[], availability=availability, reason=reason,
    )


def normalize_comparison(
    tickers: list[str], period: HistoryPeriod, histories: list,
) -> EquityComparison:
    """Normalize only actual closes. Dates missing from a series remain null."""
    if len(histories) != len(tickers):
        raise ValueError("one history response is required per ticker")
    first = histories[0]
    if any(history.availability == "disabled" for history in histories):
        return _unavailable(tickers, period, first.period_start, first.period_end, "disabled", "feature_disabled")
    unavailable = next((history for history in histories if history.availability == "unavailable"), None)
    if unavailable is not None:
        reason = unavailable.reason or "provider_unavailable"
        if reason not in {"provider_not_configured", "provider_unavailable", "ticker_not_found", "invalid_provider_response"}:
            reason = "provider_unavailable"
        return _unavailable(tickers, period, first.period_start, first.period_end, "unavailable", reason)
    if any(history.availability == "empty" or not history.points for history in histories):
        return _unavailable(tickers, period, first.period_start, first.period_end, "empty", "empty_history")

    signatures = {(history.currency, history.source, history.price_basis) for history in histories}
    if len(signatures) != 1 or any(not history.source or history.price_basis == "unknown" for history in histories):
        return _unavailable(tickers, period, first.period_start, first.period_end, "unavailable", "incompatible_data")

    prices_by_ticker = {
        ticker: {point.date: Decimal(point.close) for point in history.points}
        for ticker, history in zip(tickers, histories, strict=True)
    }
    common_dates = set.intersection(*(set(prices) for prices in prices_by_ticker.values()))
    if not common_dates:
        return _unavailable(tickers, period, first.period_start, first.period_end, "empty", "no_common_date")

    base_date = min(common_dates)
    bases = {ticker: prices[base_date] for ticker, prices in prices_by_ticker.items()}
    actual_dates = set.union(*(set(prices) for prices in prices_by_ticker.values()))
    dates = sorted(day for day in actual_dates if day >= base_date)
    points = [ComparisonPoint(
        date=day,
        values={
            ticker: _decimal_text(prices[day] / bases[ticker] * Decimal(100)) if day in prices else None
            for ticker, prices in prices_by_ticker.items()
        },
    ) for day in dates]
    coverage = [ComparisonCoverage(
        ticker=ticker,
        coverage_start=max(min(prices), base_date),
        coverage_end=max(prices),
        base_price=_decimal_text(bases[ticker]),
    ) for ticker, prices in prices_by_ticker.items()]
    currency, source, price_basis = next(iter(signatures))
    return EquityComparison(
        tickers=tickers, period=period, currency=currency, source=source,
        price_basis=price_basis, period_start=first.period_start, period_end=first.period_end,
        common_start_date=base_date, coverage=coverage, points=points,
        availability="available",
    )


router = APIRouter()


@router.get("/api/dashboard/equities/compare", response_model=EquityComparison)
async def compare_equities(
    tickers: list[str] = Query(..., description="Selecione de 2 a 4 tickers em posições abertas"),
    period: HistoryPeriod = Query("1M"),
    db: Session = Depends(private_db),
    service: EquityPriceHistoryService = Depends(individual_equity_price_history_service),
):
    if not 2 <= len(tickers) <= 4 or len(set(tickers)) != len(tickers):
        raise HTTPException(422, "Selecione de 2 a 4 ativos diferentes")
    if any(not valid_ticker(ticker) for ticker in tickers):
        raise HTTPException(422, "Ticker inválido")

    owner = db.info.get("owner_id")
    operations = list(db.scalars(select(Operation).where(Operation.owner_id == owner)
        .order_by(Operation.date, Operation.id)))
    held_tickers = {item["ticker"] for item in summarize(operations)["holdings"]}
    if any(ticker not in held_tickers for ticker in tickers):
        # Never reveal whether an unheld ticker belongs to a different owner.
        raise HTTPException(404, "Ativo não encontrado na carteira")

    # Release the read transaction before any future provider I/O.
    db.rollback()
    histories = []
    for ticker in tickers:
        histories.append(await service.get(ticker, period))
    return normalize_comparison(tickers, period, histories)
