import asyncio
from datetime import date, datetime, timezone
import httpx
import pytest
from fastapi import HTTPException
from app.auth import Principal, authenticate
from app.database import get_db
from app.main import app
from app.bcb_rates.router import rates_service
from app.bcb_rates.provider import SGSProvider
from app.bcb_rates.service import RateService
from app.bcb_rates.schemas import RateHistory, RateError
from app.fixed_income.returns_router import collect_cdi
from test_fixed_income import client, create, apply, redeem, A, B, PATH

QUERY = "as_of=2025-01-04&convention=daily_cdi_pro_rata_decimal_v1&calendar=anbima_2024_2026_v1&tax_profile=br_resident_individual"


def contract(client):
    return create(client, remuneration="CDI", indexer="CDI", contracted_rate="100", application_date="2025-01-02")


def test_private_snapshot_is_owner_scoped_and_releases_transaction_before_http(client):
    investment = contract(client)
    first = apply(client, investment, "1000", "2025-01-02")
    assert redeem(client, investment, first["lot_id"], "400", "2025-01-03", cash_received="420").status_code == 201
    app.dependency_overrides[authenticate] = lambda: Principal(B)
    other = contract(client)
    apply(client, other, "200", "2025-01-02")
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    calls, sessions = [], []
    original = app.dependency_overrides[get_db]
    def tracked_db():
        for session in original():
            sessions.append(session)
            yield session
    def handler(request):
        assert not sessions[-1].in_transaction()
        assert request.url.params["dataInicial"] == "02/01/2025"
        assert request.url.params["dataFinal"] == "03/01/2025"
        calls.append(request)
        return httpx.Response(200, json=[{"data":"02/01/2025","valor":"1"},{"data":"03/01/2025","valor":"1"}])
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_db] = tracked_db
    app.dependency_overrides[rates_service] = lambda: RateService(SGSProvider(http))
    try:
        before = client.get(f"{PATH}/{investment}/movements").json()
        response = client.get(f"{PATH}/{investment}/returns?{QUERY}&owner_id={B}")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["principal_balance"] == "600.00000000"
        assert result["gross_income_estimate"] == "12.06" and result["status"] == "estimated"
        assert result["lots"][0]["realized_tax_status"] == "insufficient_information"
        assert len(result["rates_references"]) == 1
        assert response.headers["cache-control"] == "no-store"
        assert client.get(f"{PATH}/{investment}/movements").json() == before
        assert client.get(f"{PATH}/{other}/returns?{QUERY}").status_code == 404
        assert len(calls) == 1
        app.dependency_overrides[authenticate] = lambda: Principal(B)
        assert client.get(f"{PATH}/{investment}/returns?{QUERY}").status_code == 404
    finally:
        asyncio.run(http.aclose())


def test_missing_convention_and_bad_dates_do_not_call_sgs(client):
    investment = contract(client)
    apply(client, investment, "1000", "2025-01-02")
    class Forbidden:
        async def get(self, *_):
            raise AssertionError("Unexpected SGS call")
    app.dependency_overrides[rates_service] = Forbidden
    result = client.get(f"{PATH}/{investment}/returns?as_of=2025-01-04").json()
    assert result["lots"][0]["status"] == "convention_required" and result["gross_value_estimate"] is None
    for invalid in ("2025-01-01", "2099-01-01", "invalid"):
        assert client.get(f"{PATH}/{investment}/returns?as_of={invalid}").status_code == 422


def test_upstream_failure_keeps_principal_with_explicit_unavailable_estimate(client):
    investment = contract(client)
    apply(client, investment, "1000", "2025-01-02")
    class Unavailable:
        async def get(self, *_):
            raise RateError("upstream_network_error")
    app.dependency_overrides[rates_service] = Unavailable
    result = client.get(f"{PATH}/{investment}/returns?{QUERY}").json()
    assert result["rates_error"] == "upstream_network_error"
    assert result["gross_income_estimate"] is None and result["net_value_estimate"] is None
    assert result["lots"][0]["status"] == "rates_unavailable"
    assert result["principal_balance"] == "1000.00000000"


def test_auth_and_authorization_before_ledger_or_sgs(client):
    def forbidden():
        raise AssertionError("Unauthorized IO")
    app.dependency_overrides[get_db] = forbidden
    app.dependency_overrides[rates_service] = forbidden
    app.dependency_overrides.pop(authenticate)
    assert client.get(f"{PATH}/1/returns?{QUERY}").status_code == 401
    assert client.get(f"{PATH}/1/returns?{QUERY}", headers={"Authorization":"Bearer invalid"}).status_code == 401
    def disallowed():
        raise HTTPException(403, "Conta não autorizada")
    app.dependency_overrides[authenticate] = disallowed
    assert client.get(f"{PATH}/1/returns?{QUERY}").status_code == 403


def test_bounded_windows_reuse_sgs_contract_without_overlap():
    async def run():
        periods = []
        class Service:
            async def get(self, code, period):
                assert code == 12
                periods.append(period)
                now = datetime.now(timezone.utc)
                return RateHistory(series_code=12, name="CDI", **period.model_dump(), status="empty", observations=(),
                    duplicates_removed=0, last_observation_date=None, fetched_at=now, expires_at=now)
        points, refs, error = await collect_cdi(Service(), date(2024, 1, 2), date(2026, 1, 2))
        assert error is None and not points and len(refs) == 2
        assert periods[0].start_date == date(2024, 1, 2) and periods[0].end_date == date(2025, 1, 1)
        assert periods[1].start_date == date(2025, 1, 2) and periods[1].end_date == date(2026, 1, 1)
    asyncio.run(run())
