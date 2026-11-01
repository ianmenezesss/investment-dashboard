from datetime import date, datetime, timezone
from decimal import Decimal as D

from app.bcb_rates.schemas import Observation, RateHistory
from app.benchmarks import build_benchmark_comparison
from app.individual_equity_history import DailyPricePoint, IndividualEquityPriceHistory


def rate_history(code, name, unit, observations):
    return RateHistory(series_code=code, name=name, unit=unit, start_date=date(2026, 1, 1), end_date=date(2026, 4, 30),
        status="ok", observations=tuple(observations), duplicates_removed=0,
        last_observation_date=observations[-1].date if observations else None,
        fetched_at=datetime(2026, 5, 1, tzinfo=timezone.utc), expires_at=datetime(2026, 5, 1, tzinfo=timezone.utc))


def test_benchmark_comparison_compounds_rates_and_compares_same_complete_months():
    daily = []
    for month in (2, 3, 4):
        last = date(2026, month, 28 if month == 2 else 30)
        days = list(range(2, last.day, 4)) + [last.day]
        daily += [Observation(date=date(2026, month, day), value=D("0.1"), series_code=12, unit="% ao dia")
                  for day in days]
    cdi = rate_history(12, "CDI", "% ao dia", daily)
    ipca = rate_history(433, "IPCA", "% ao mês", [
        Observation(date=date(2026, month, 1), value=D("0.5"), series_code=433, unit="% ao mês")
        for month in (2, 3, 4)
    ])
    bars = []
    for month, close in ((2, "100"), (3, "110"), (4, "121")):
        bars += [DailyPricePoint(date=date(2026, month, 2), close=close),
                 DailyPricePoint(date=date(2026, month, 28 if month == 2 else 30), close=close)]
    ibov = IndividualEquityPriceHistory(ticker="^BVSP", period="3M", currency="BRL", source="brapi",
        price_basis="adjusted_close", period_start=date(2026, 2, 1), period_end=date(2026, 4, 30),
        coverage_start=bars[0].date, coverage_end=bars[-1].date, points=bars, availability="available")
    result = build_benchmark_comparison("3M", date(2026, 1, 1), date(2026, 4, 30), cdi, ipca, ibov)
    assert result.availability == "partial"  # three month marks cover only two monthly changes
    assert [point.month.isoformat() for point in result.points] == ["2026-02-01", "2026-03-01", "2026-04-01"]
    assert result.points[0].values == {"CDI": "100", "IBOVESPA": "100", "IPCA": "100"}
    assert D(result.points[1].values["IBOVESPA"]) == D("110")
    assert D(result.points[1].values["IPCA"]) == D("100.5")
    assert "sem proventos" in result.bases["IBOVESPA"]
    one_month = build_benchmark_comparison("1M", date(2026, 1, 1), date(2026, 4, 30), cdi, ipca, ibov)
    assert one_month.availability == "available"
    assert [point.month.isoformat() for point in one_month.points] == ["2026-03-01", "2026-04-01"]


def test_benchmarks_do_not_bridge_missing_months_or_invent_values():
    daily = []
    for month in (2, 3, 4):
        last = date(2026, month, 28 if month == 2 else 30)
        days = list(range(2, last.day, 4)) + [last.day]
        daily += [Observation(date=date(2026, month, day), value=D("0.1"), series_code=12, unit="% ao dia")
                  for day in days]
    cdi = rate_history(12, "CDI", "% ao dia", daily)
    ipca = rate_history(433, "IPCA", "% ao mês", [
        Observation(date=date(2026, month, 1), value=D("0.5"), series_code=433, unit="% ao mês")
        for month in (2, 4)
    ])
    bars = [DailyPricePoint(date=date(2026, month, day), close=str(month * 100))
        for month in (2, 3, 4) for day in (2, 28 if month == 2 else 30)]
    ibov = IndividualEquityPriceHistory(ticker="^BVSP", period="3M", currency="BRL", source="brapi",
        price_basis="adjusted_close", period_start=date(2026, 2, 1), period_end=date(2026, 4, 30),
        coverage_start=bars[0].date, coverage_end=bars[-1].date, points=bars, availability="available")
    result = build_benchmark_comparison("3M", date(2026, 1, 1), date(2026, 4, 30), cdi, ipca, ibov)
    assert result.availability == "empty" and result.points == []
    assert result.reason == "insufficient_common_period"


def test_benchmark_endpoint_requires_auth_and_uses_no_financial_database(monkeypatch):
    from fastapi.testclient import TestClient
    from uuid import UUID
    from app.auth import Principal, authenticate
    from app.bcb_rates.schemas import today
    from app.benchmarks import benchmark_services
    from app.database import get_db
    from app.main import app

    daily = []
    for month in (2, 3, 4):
        last = date(2026, month, 28 if month == 2 else 30)
        days = list(range(2, last.day, 4)) + [last.day]
        daily.extend(Observation(date=date(2026, month, day), value=D("0.1"), series_code=12, unit="% ao dia") for day in days)
    cdi = rate_history(12, "CDI", "% ao dia", daily)
    ipca = rate_history(433, "IPCA", "% ao mês", [
        Observation(date=date(2026, month, 1), value=D("0.5"), series_code=433, unit="% ao mês")
        for month in (2, 3, 4)
    ])
    bars = [DailyPricePoint(date=date(2026, month, day), close=str(month * 100))
        for month in (2, 3, 4) for day in (2, 28 if month == 2 else 30)]
    ibov = IndividualEquityPriceHistory(ticker="^BVSP", period="3M", currency="BRL", source="brapi",
        price_basis="adjusted_close", period_start=date(2026, 1, 30), period_end=date(2026, 4, 30),
        coverage_start=bars[0].date, coverage_end=bars[-1].date, points=bars, availability="available")

    class Rates:
        async def get(self, code, period):
            return cdi if code == 12 else ipca

    class EquityHistory:
        requested = []
        async def get(self, ticker, period):
            self.requested.append((ticker, period))
            return ibov

    equity = EquityHistory()
    app.dependency_overrides[benchmark_services] = lambda: (Rates(), equity)
    app.dependency_overrides[get_db] = lambda: (_ for _ in ()).throw(AssertionError("benchmark DB access"))
    try:
        with TestClient(app) as client:
            assert client.get("/api/dashboard/benchmarks?period=1M").status_code == 401
            app.dependency_overrides[authenticate] = lambda: Principal(UUID("11111111-1111-4111-8111-111111111111"))
            monkeypatch.setattr("app.benchmarks.today", lambda: date(2026, 4, 30))
            response = client.get("/api/dashboard/benchmarks?period=1M")
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["availability"] == "available"
            assert len(data["points"]) == 2
            assert equity.requested == [("^BVSP", "3M")]
    finally:
        app.dependency_overrides.clear()
