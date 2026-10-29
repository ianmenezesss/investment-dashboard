"""OPTIONS preflight for private CDB revision routes; no database or token access."""
import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.main import app

ORIGIN = "https://investment-dashboard-pvd.vercel.app"


@pytest.mark.parametrize("path", [
    "/api/fixed-income/investments/1/applications/2/revisions/preview",
    "/api/fixed-income/investments/1/applications/2/revisions",
])
def test_revision_preflight_accepts_private_frontend_headers_without_auth(path):
    cors = next(item for item in app.user_middleware if item.cls is CORSMiddleware)
    previous = cors.kwargs["allow_origins"]
    cors.kwargs["allow_origins"] = [ORIGIN]
    app.middleware_stack = None
    try:
        with TestClient(app) as client:
            response = client.options(path, headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
            })
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == ORIGIN
        assert "POST" in response.headers["access-control-allow-methods"]
        allowed = response.headers["access-control-allow-headers"].lower()
        assert all(header in allowed for header in ("authorization", "content-type", "idempotency-key"))
    finally:
        cors.kwargs["allow_origins"] = previous
        app.middleware_stack = None
