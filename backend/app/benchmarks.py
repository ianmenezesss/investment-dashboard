"""Monthly, source-aligned reference indices; never labelled portfolio return."""
import calendar
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from .auth import authenticate
from .bcb_rates.schemas import Period, RateError, RateHistory, today
from .individual_equity_history import IndividualEquityPriceHistory

BenchmarkPeriod = Literal["1M", "3M"]
SERIES_NAMES = ("CDI", "IBOVESPA", "IPCA")


class BenchmarkPoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    month: date
    values: dict[str, str]


class BenchmarkComparison(BaseModel):
    model_config = ConfigDict(frozen=True)
    period: BenchmarkPeriod
    coverage_start: date | None
    coverage_end: date | None
    availability: Literal["available", "partial", "disabled", "unavailable", "empty"]
    reason: Literal["feature_disabled", "provider_not_configured", "provider_unavailable", "source_coverage", "incompatible_data", "insufficient_common_period"] | None = None
    source: str = "BCB/SGS e brapi"
    bases: dict[str, str]
    points: list[BenchmarkPoint]


def _month_key(day: date) -> str:
    return day.strftime("%Y-%m")


def _month_bounds(key: str):
    year, month = (int(part) for part in key.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _month_number(key: str) -> int:
    year, month = (int(part) for part in key.split("-"))
    return year * 12 + month


def _longest_contiguous(keys: list[str]) -> list[str]:
    if not keys:
        return []
    runs, current = [], [keys[0]]
    for key in keys[1:]:
        if _month_number(key) == _month_number(current[-1]) + 1:
            current.append(key)
        else:
            runs.append(current)
            current = [key]
    runs.append(current)
    return max(runs, key=lambda run: (len(run), run[-1]))


def _daily_month_factor(observations, start_date: date, end_date: date):
    grouped: dict[str, list[tuple[date, Decimal]]] = {}
    for row in observations:
        if row.series_code != 12 or row.unit != "% ao dia":
            raise ValueError("CDI series/unit mismatch")
        grouped.setdefault(_month_key(row.date), []).append((row.date, row.value))
    result = {}
    with localcontext() as ctx:
        ctx.prec = 64
        for key, rows in grouped.items():
            first, last = _month_bounds(key)
            # Drop clipped first/last months and keep complete calendar months only.
            if first < start_date or last > end_date:
                continue
            ordered = sorted(rows)
            if ordered[0][0] > date(first.year, first.month, min(7, last.day)) or ordered[-1][0] < date(last.year, last.month, max(1, last.day - 7)):
                continue
            if any((right[0] - left[0]).days > 7 for left, right in zip(ordered, ordered[1:])):
                continue
            factor = Decimal(1)
            for _, rate in ordered:
                daily_factor = Decimal(1) + rate / Decimal(100)
                if daily_factor <= 0:
                    raise ValueError("invalid CDI factor")
                factor *= daily_factor
            result[key] = factor
    return result


def _ipca_month_factors(history: RateHistory, start_date: date, end_date: date):
    if history.series_code != 433 or history.unit != "% ao mês":
        raise ValueError("IPCA series/unit mismatch")
    result = {}
    for row in history.observations:
        if row.series_code != 433 or row.unit != "% ao mês":
            raise ValueError("IPCA observation mismatch")
        key = _month_key(row.date)
        first, last = _month_bounds(key)
        if row.date == first and first >= start_date and last <= end_date:
            factor = Decimal(1) + row.value / Decimal(100)
            if factor <= 0:
                raise ValueError("invalid IPCA factor")
            result[key] = factor
    return result


def _ibovespa_month_closes(history: IndividualEquityPriceHistory, start_date: date, end_date: date):
    if history.ticker != "^BVSP" or history.currency != "BRL" or not history.source or history.price_basis == "unknown":
        raise ValueError("Ibovespa source mismatch")
    grouped: dict[str, list[tuple[date, Decimal]]] = {}
    for point in history.points:
        value = Decimal(point.close)
        if not value.is_finite() or value <= 0:
            raise ValueError("invalid index point")
        grouped.setdefault(_month_key(point.date), []).append((point.date, value))
    result = {}
    for key, rows in grouped.items():
        first, last = _month_bounds(key)
        days = sorted(rows)
        if first >= start_date and last <= end_date and days[0][0] <= first.replace(day=min(7, last.day)) and days[-1][0] >= date(last.year, last.month, max(1, last.day - 7)):
            result[key] = days[-1][1]
    return result


def build_benchmark_comparison(period: BenchmarkPeriod, start_date: date, end_date: date,
                               cdi: RateHistory, ipca: RateHistory,
                               ibovespa: IndividualEquityPriceHistory) -> BenchmarkComparison:
    try:
        cdi_factors = _daily_month_factor(cdi.observations, start_date, end_date)
        ipca_factors = _ipca_month_factors(ipca, start_date, end_date)
        ibov_closes = _ibovespa_month_closes(ibovespa, start_date, end_date)
    except (ValueError, InvalidOperation, ArithmeticError, TypeError):
        return BenchmarkComparison(period=period, coverage_start=None, coverage_end=None,
            availability="unavailable", reason="incompatible_data", bases={}, points=[])
    common = sorted(set(cdi_factors) & set(ipca_factors) & set(ibov_closes))
    run = _longest_contiguous(common)
    if period == "1M":
        # One monthly change needs a base month and an end month.
        run = run[-2:]
    if len(run) < 2:
        return BenchmarkComparison(period=period, coverage_start=None, coverage_end=None,
            availability="empty", reason="insufficient_common_period", bases={}, points=[])
    first_key = run[0]
    with localcontext() as ctx:
        ctx.prec = 64
        cdi_level = ipca_level = Decimal(100)
        points = []
        for index, key in enumerate(run):
            if index:
                cdi_level *= cdi_factors[key]
                ipca_level *= ipca_factors[key]
            ibov_level = ibov_closes[key] / ibov_closes[first_key] * Decimal(100)
            points.append(BenchmarkPoint(month=_month_bounds(key)[0], values={
                "CDI": format(cdi_level.normalize(), "f"),
                "IBOVESPA": format(ibov_level.normalize(), "f"),
                "IPCA": format(ipca_level.normalize(), "f"),
            }))
    # A complete N-month change needs N+1 month marks; short coverage is partial.
    expected_months = 2 if period == "1M" else 4
    partial = len(run) < expected_months or ibovespa.availability == "partial"
    return BenchmarkComparison(period=period, coverage_start=points[0].month, coverage_end=points[-1].month,
        availability="partial" if partial else "available", reason="source_coverage" if partial else None,
        bases={"CDI": "% ao dia acumulado por mês", "IBOVESPA": "índice de preços base 100; sem proventos", "IPCA": "% de variação mensal acumulada"},
        points=points)


router = APIRouter(prefix="/api/dashboard", tags=["benchmarks"], dependencies=[Depends(authenticate)])


def benchmark_services(request: Request):
    rates = getattr(request.app.state, "bcb_rates_service", None)
    equity_history = getattr(request.app.state, "individual_equity_price_history_service", None)
    if rates is None or equity_history is None:
        raise HTTPException(503, detail={"code": "benchmark_service_unavailable"})
    return rates, equity_history


def _unavailable(period, reason, state="unavailable"):
    return BenchmarkComparison(period=period, coverage_start=None, coverage_end=None,
        availability=state, reason=reason, bases={}, points=[])


@router.get("/benchmarks", response_model=BenchmarkComparison)
async def compare_benchmarks(period: BenchmarkPeriod = Query("3M"), services=Depends(benchmark_services)):
    rates, equity_history = services
    end_date = today()
    # Pull one consistent free three-month window; IPCA needs a baseline month.
    months = 3
    month_index = end_date.year * 12 + end_date.month - 1 - months
    year, month = divmod(month_index, 12)
    start_date = date(year, month + 1, min(end_date.day, calendar.monthrange(year, month + 1)[1]))
    query_period = Period(start_date=start_date, end_date=end_date)
    try:
        cdi = await rates.get(12, query_period)
        ipca = await rates.get(433, query_period)
        ibovespa = await equity_history.get("^BVSP", "3M")
    except RateError:
        return _unavailable(period, "provider_unavailable")
    if ibovespa.availability == "disabled":
        return _unavailable(period, "feature_disabled", "disabled")
    if ibovespa.availability == "unavailable":
        reason = "provider_not_configured" if ibovespa.reason == "provider_not_configured" else "provider_unavailable"
        return _unavailable(period, reason)
    if not cdi.observations or not ipca.observations or not ibovespa.points:
        return _unavailable(period, "source_coverage", "empty")
    return build_benchmark_comparison(period, start_date, end_date, cdi, ipca, ibovespa)
