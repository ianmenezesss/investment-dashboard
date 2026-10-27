"""Opt-in: exige banco PostgreSQL dedicado, vazio e descartável."""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from app.database import get_db, settings
from app.main import app
from app.auth import Principal, authenticate
from uuid import UUID
from decimal import Decimal


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL de testes não configurado")
def test_migrations_persistence_and_chronological_validation(monkeypatch):
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    if inspect(engine).get_table_names():
        pytest.fail("Use um banco de testes vazio; nenhuma tabela existente será alterada.")
    from app import database
    monkeypatch.setattr(database, "engine", engine)
    command.upgrade(Config("alembic.ini"), "head")

    def db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = db
    headers = {"Authorization": f"Bearer {settings.api_token.get_secret_value()}"}
    try:
        with TestClient(app) as client:
            buy = {"ticker": "ITUB4", "kind": "BUY", "date": "2026-01-01", "quantity": "10", "price": "20", "fees": "2"}
            created = client.post("/api/operations", headers=headers, json=buy)
            assert created.status_code == 201
            purchase_id = created.json()["id"]
            assert client.get("/api/operations", headers=headers).json()[0]["price"] == "20.00000000"
            sale = client.post("/api/operations", headers=headers, json=dict(buy, kind="SELL", quantity="5", price="30", fees="0", date="2026-01-02"))
            assert sale.status_code == 201
            assert Decimal(client.get("/api/dashboard", headers=headers).json()["realized_profit"]) == Decimal("49")
            assert client.delete(f"/api/operations/{purchase_id}", headers=headers).status_code == 422
            assert client.delete(f"/api/operations/{sale.json()['id']}", headers=headers).status_code == 204
            assert client.delete(f"/api/operations/{purchase_id}", headers=headers).status_code == 204
            # Exercitar o mesmo isolamento sob um papel sem bypass RLS.
            with engine.begin() as connection:
                connection.execute(text("CREATE ROLE investment_test_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS"))
                connection.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON operations TO investment_test_runtime"))
                connection.execute(text("GRANT USAGE, SELECT ON SEQUENCE operations_id_seq TO investment_test_runtime"))

            def restricted_db():
                with Session(engine) as session:
                    session.execute(text("SET LOCAL ROLE investment_test_runtime"))
                    yield session

            app.dependency_overrides[get_db] = restricted_db
            monkeypatch.setattr(settings, "auth_mode", "supabase")
            a = UUID("11111111-1111-4111-8111-111111111111")
            b = UUID("22222222-2222-4222-8222-222222222222")
            ids = {}
            for owner in [a, b]:
                app.dependency_overrides[authenticate] = lambda owner=owner: Principal(owner)
                created = client.post("/api/operations", json=dict(buy, owner_id=str(b)))
                assert created.status_code == 201
                ids[owner] = created.json()["id"]
            app.dependency_overrides[authenticate] = lambda: Principal(a)
            assert [row["id"] for row in client.get("/api/operations").json()] == [ids[a]]
            assert client.delete(f"/api/operations/{ids[b]}").status_code == 404
            with engine.begin() as connection:
                connection.execute(text("SET LOCAL ROLE investment_test_runtime"))
                # Sem contexto de identidade, nenhuma linha pode ser lida.
                assert list(connection.execute(text("SELECT id FROM operations"))) == []
                connection.execute(text("SELECT set_config('app.user_id', :owner, true), set_config('app.auth_mode', 'supabase', true)"), {"owner": str(a)})
                assert [row[0] for row in connection.execute(text("SELECT id FROM operations"))] == [ids[a]]
    finally:
        app.dependency_overrides.clear()
        # Banco exclusivamente de teste; não apagar tabelas ou reverter ownership.
        engine.dispose()
