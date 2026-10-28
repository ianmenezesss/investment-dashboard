import asyncio
from uuid import UUID
import httpx
import pytest
from fastapi.testclient import TestClient
from app.auth import authenticate, Principal
from app.database import get_db, settings
from app.main import app
from app.bcb_rates.router import rates_service
from app.bcb_rates.provider import SGSProvider
from app.bcb_rates.service import RateService

URL = "/api/fixed-income/rates/12?start_date=2025-01-01&end_date=2025-01-05"


def test_requires_auth_before_provider_and_does_not_access_database():
    def forbidden():
        raise AssertionError("Unauthenticated provider/DB access")
    app.dependency_overrides[rates_service] = forbidden
    app.dependency_overrides[get_db] = forbidden
    try:
        with TestClient(app) as client:
            assert client.get(URL).status_code == 401
            assert client.get(URL, headers={"Authorization": "Bearer invalid"}).status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("status", [200, 429, 500])
def test_authenticated_contract_cache_shared_only_for_public_rates_and_safe_errors(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=[{"data": "02/01/2025", "valor": "0.012345678901"}], headers={"retry-after": "60"})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = RateService(SGSProvider(http))
    app.dependency_overrides[rates_service] = lambda: service
    app.dependency_overrides[authenticate] = lambda: Principal(UUID("11111111-1111-4111-8111-111111111111"))
    def no_db():
        raise AssertionError("Public rates must not read financial data")
    app.dependency_overrides[get_db] = no_db
    try:
        with TestClient(app) as client:
            result = client.get(URL)
            assert result.headers["cache-control"] == "no-store"
            assert result.status_code == (200 if status == 200 else 429 if status == 429 else 502)
            if status == 200:
                data = result.json()
                assert data["unit"] == "% ao dia" and data["series_code"] == 12
                assert data["observations"] == [{"date": "2025-01-02", "value": "0.012345678901", "series_code": 12, "unit": "% ao dia"}]
                assert not data["from_cache"] and data["source"] == "BCB/SGS"
                app.dependency_overrides[authenticate] = lambda: Principal(UUID("22222222-2222-4222-8222-222222222222"))
                assert client.get(URL).json()["from_cache"]
            else:
                assert set(result.json()["detail"]) == {"code"} and result.headers["retry-after"]
                assert client.get(URL).status_code == result.status_code
            assert len(calls) == 1
            for bad in ("/api/fixed-income/rates/432?start_date=2025-01-01&end_date=2025-01-02",
                "/api/fixed-income/rates/12?start_date=2025-01-05&end_date=2025-01-01",
                "/api/fixed-income/rates/12?start_date=2099-01-01&end_date=2099-01-02",
                "/api/fixed-income/rates/12?start_date=2024-01-01&end_date=2025-01-01"):
                assert client.get(bad).status_code == 422
            assert len(calls) == 1
    finally:
        app.dependency_overrides.clear()
        asyncio.run(http.aclose())


def test_authenticated_local_alternative_with_missing_service_returns_stable_error():
    with TestClient(app) as client:
        app.state.bcb_rates_service = None
        result = client.get(URL, headers={"Authorization": f"Bearer {settings.api_token.get_secret_value()}"})
        assert result.status_code == 503 and result.json()["detail"]["code"] == "rates_service_unavailable"
