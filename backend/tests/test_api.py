import os
import tomllib
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("API_TOKEN", "test-only-token")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db, settings
from app.main import app


def test_backend_package_and_api_versions_match_v3():
    package = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    assert package["project"]["version"] == app.version == "3.0.0"


def test_protected_empty_dashboard_and_export():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = db
    try:
        with TestClient(app) as client:
            assert client.get("/health").json() == {"status": "ok"}
            assert client.get("/api/dashboard").status_code in (401, 403)
            assert client.get("/api/dashboard", headers={"Authorization": "Bearer wrong"}).status_code == 401
            headers = {"Authorization": f"Bearer {settings.api_token.get_secret_value()}"}
            result = client.get("/api/dashboard", headers=headers)
            assert result.status_code == 200
            assert result.json()["acquisition_cost"] == "0"
            assert result.json()["market_value"] is None
            exported = client.get("/api/export", headers=headers).json()
            assert exported["schema_version"] == 3 and exported["account"] is None and exported["operations"] == []
            assert all(exported[key] == [] for key in ("fixed_income_investments", "fixed_income_lots", "fixed_income_movements", "fixed_income_observations", "fixed_income_archives", "fixed_income_revisions", "financial_events", "financial_event_revisions", "wealth_observations"))
            invalid = client.post("/api/operations", headers=headers, json={"ticker": "ITUB4", "kind": "BUY", "date": "2026-01-01", "quantity": "-1", "price": "10"})
            assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
