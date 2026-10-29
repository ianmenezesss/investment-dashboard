from datetime import date
from decimal import Decimal as D
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import Principal, authenticate
from app.database import Base, get_db
from app.individual_equity_history import (
    EquityPriceHistoryService,
    PriceHistoryUnavailable,
    ProviderDailyPrice,
    ProviderPriceHistory,
    individual_equity_price_history_service,
)
from app.main import app
from app.models import Operation

A = UUID("11111111-1111-4111-8111-111111111111")
B = UUID("22222222-2222-4222-8222-222222222222")
TODAY = date(2026, 10, 29)
DAY_0 = date(2026, 9, 30)
DAY_1 = date(2026, 10, 1)
DAY_2 = date(2026, 10, 2)
DAY_3 = date(2026, 10, 3)


def history(ticker, points, *, source="provider-test-double", currency="BRL", price_basis="raw_close"):
    return ProviderPriceHistory(
        ticker=ticker,
        source=source,
        currency=currency,
        price_basis=price_basis,
        points=tuple(ProviderDailyPrice(day, D(close)) for day, close in points),
    )


class SimulatedProvider:
    def __init__(self, histories=None, error=None):
        self.histories = histories or {
            "ITUB4": history("ITUB4", [(DAY_0, "9"), (DAY_1, "10"), (DAY_3, "12")]),
            "BBAS3": history("BBAS3", [(DAY_1, "20"), (DAY_2, "22")]),
            "B3SA3": history("B3SA3", [(DAY_1, "40"), (DAY_3, "44")]),
            "VALE3": history("VALE3", [(DAY_1, "50"), (DAY_2, "45")]),
        }
        self.error = error
        self.calls = []

    async def fetch(self, ticker, *, start, end):
        self.calls.append((ticker, start, end))
        if self.error:
            raise self.error
        return self.histories[ticker]


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def db_session():
        with Session(engine) as session:
            yield session

    provider = SimulatedProvider()
    service = EquityPriceHistoryService(provider, enabled=True, today=lambda: TODAY)
    app.dependency_overrides[get_db] = db_session
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    app.dependency_overrides[individual_equity_price_history_service] = lambda: service
    try:
        with Session(engine) as session:
            for ticker, owner in (("ITUB4", A), ("BBAS3", A), ("B3SA3", A), ("VALE3", A), ("PETR4", B)):
                session.add(Operation(owner_id=owner, ticker=ticker, kind="BUY", date=DAY_1,
                    quantity=D("1"), price=D("10"), fees=D("0")))
            session.commit()
        with TestClient(app) as client:
            yield client, provider
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def compare_url(tickers=("ITUB4", "BBAS3"), period="1M"):
    return "/api/dashboard/equities/compare?" + "&".join(
        [*(f"tickers={ticker}" for ticker in tickers), f"period={period}"]
    )


def test_comparison_normalizes_on_shared_real_date_and_preserves_missing_days(api):
    client, provider = api
    response = client.get(compare_url())
    assert response.status_code == 200
    payload = response.json()
    assert payload["tickers"] == ["ITUB4", "BBAS3"]
    assert payload["period"] == "1M"
    assert payload["availability"] == "available"
    assert payload["source"] == "provider-test-double"
    assert payload["currency"] == "BRL"
    assert payload["price_basis"] == "raw_close"
    assert payload["common_start_date"] == "2026-10-01"
    assert payload["coverage"] == [
        {"ticker": "ITUB4", "coverage_start": "2026-10-01", "coverage_end": "2026-10-03", "base_price": "10"},
        {"ticker": "BBAS3", "coverage_start": "2026-10-01", "coverage_end": "2026-10-02", "base_price": "20"},
    ]
    assert payload["points"] == [
        {"date": "2026-10-01", "values": {"ITUB4": "100", "BBAS3": "100"}},
        {"date": "2026-10-02", "values": {"ITUB4": None, "BBAS3": "110"}},
        {"date": "2026-10-03", "values": {"ITUB4": "120", "BBAS3": None}},
    ]
    assert [call[0] for call in provider.calls] == ["ITUB4", "BBAS3"]


def test_comparison_accepts_four_open_positions(api):
    client, _provider = api
    response = client.get(compare_url(("ITUB4", "BBAS3", "B3SA3", "VALE3")))
    assert response.status_code == 200
    assert response.json()["availability"] == "available"
    assert response.json()["tickers"] == ["ITUB4", "BBAS3", "B3SA3", "VALE3"]


def test_authentication_precedes_database_access():
    def forbidden_db():
        raise AssertionError("unauthenticated request reached the database")

    app.dependency_overrides[get_db] = forbidden_db
    app.dependency_overrides.pop(authenticate, None)
    try:
        with TestClient(app) as client:
            assert client.get(compare_url()).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_comparison_hides_other_owners_assets_and_does_not_fetch(api):
    client, provider = api
    assert client.get(compare_url(("ITUB4", "PETR4"))).status_code == 404
    assert provider.calls == []
    app.dependency_overrides[authenticate] = lambda: Principal(B)
    assert client.get(compare_url(("ITUB4", "PETR4"))).status_code == 404
    assert provider.calls == []


@pytest.mark.parametrize("tickers", [(), ("ITUB4",), ("ITUB4", "BBAS3", "B3SA3", "VALE3", "ITUB4"), ("ITUB4", "ITUB4"), ("itub4", "BBAS3")])
def test_comparison_rejects_invalid_count_duplicates_and_tickers(api, tickers):
    client, provider = api
    assert client.get(compare_url(tickers)).status_code == 422
    assert provider.calls == []


@pytest.mark.parametrize("period,expected_start", [
    ("1M", date(2026, 9, 29)), ("3M", date(2026, 7, 29)),
    ("6M", date(2026, 4, 29)), ("1A", date(2025, 10, 29)), ("MAX", None),
])
def test_comparison_forwards_all_supported_periods(api, period, expected_start):
    client, provider = api
    response = client.get(compare_url(period=period))
    assert response.status_code == 200
    assert response.json()["period"] == period
    assert [call[1] for call in provider.calls] == [expected_start, expected_start]


def test_comparison_rejects_unsupported_period(api):
    client, provider = api
    assert client.get(compare_url(period="2Y")).status_code == 422
    assert provider.calls == []


def test_comparison_requires_compatible_currency_source_and_price_basis(api):
    client, provider = api
    provider.histories["BBAS3"] = history("BBAS3", [(DAY_1, "20")], source="other-source")
    response = client.get(compare_url())
    assert response.status_code == 200
    assert response.json()["availability"] == "unavailable"
    assert response.json()["reason"] == "incompatible_data"
    assert response.json()["points"] == []

    provider.histories["BBAS3"] = history("BBAS3", [(DAY_1, "20")], price_basis="adjusted_close")
    response = client.get(compare_url())
    assert response.json()["availability"] == "unavailable"
    assert response.json()["reason"] == "incompatible_data"
    assert response.json()["points"] == []

    provider.histories["BBAS3"] = history("BBAS3", [(DAY_1, "20")], price_basis="unknown")
    response = client.get(compare_url())
    assert response.json()["availability"] == "unavailable"
    assert response.json()["reason"] == "incompatible_data"

    provider.histories["BBAS3"] = history("BBAS3", [(DAY_1, "20")], currency="USD")
    response = client.get(compare_url())
    assert response.json()["availability"] == "unavailable"
    assert response.json()["reason"] == "invalid_provider_response"


def test_comparison_without_shared_observation_date_does_not_forward_fill(api):
    client, provider = api
    provider.histories["BBAS3"] = history("BBAS3", [(DAY_2, "20")])
    response = client.get(compare_url())
    assert response.status_code == 200
    assert response.json()["availability"] == "empty"
    assert response.json()["reason"] == "no_common_date"
    assert response.json()["points"] == []


def test_comparison_disabled_does_not_call_provider(api):
    client, provider = api
    app.dependency_overrides[individual_equity_price_history_service] = lambda: EquityPriceHistoryService(
        provider, enabled=False, today=lambda: TODAY)
    response = client.get(compare_url())
    assert response.status_code == 200
    assert response.json()["availability"] == "disabled"
    assert response.json()["reason"] == "feature_disabled"
    assert response.json()["points"] == []
    assert provider.calls == []


def test_provider_failure_is_returned_without_any_price_points(api):
    client, provider = api
    provider.error = PriceHistoryUnavailable("provider_unavailable")
    response = client.get(compare_url())
    assert response.status_code == 200
    assert response.json()["availability"] == "unavailable"
    assert response.json()["reason"] == "provider_unavailable"
    assert response.json()["points"] == []
