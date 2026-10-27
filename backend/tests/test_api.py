import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("API_TOKEN", "test-only-token")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db, settings
from app.main import app


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
            assert client.get("/api/export", headers=headers).json() == {"schema_version": 1, "operations": []}
            invalid = client.post("/api/operations", headers=headers, json={"ticker": "ITUB4", "kind": "BUY", "date": "2026-01-01", "quantity": "-1", "price": "10"})
            assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
