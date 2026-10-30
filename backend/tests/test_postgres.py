"""Opt-in: exige banco PostgreSQL dedicado, vazio e descartável."""
import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from app.database import get_db, settings
from app.main import app
from app.auth import Principal, authenticate
from uuid import UUID
from decimal import Decimal
from datetime import date


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL de testes não configurado")
def test_migrations_persistence_and_chronological_validation(monkeypatch):
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    if inspect(engine).get_table_names():
        pytest.fail("Use um banco de testes vazio; nenhuma tabela existente será alterada.")
    from app import database
    monkeypatch.setattr(database, "engine", engine)
    command.upgrade(Config("alembic.ini"), "002")
    # Emulate Supabase default grants on NEW objects, so 003 must revoke them.
    with engine.begin() as connection:
        connection.execute(text("CREATE ROLE investment_runtime LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION"))
        for role in ("anon", "authenticated", "service_role"):
            connection.execute(text(f"CREATE ROLE {role} NOLOGIN"))
        connection.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role"))
        connection.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated, service_role"))
    # Migration 003 must preserve a pre-existing stock operation verbatim.
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO operations(ticker,kind,date,quantity,price,fees,created_at,owner_id)
            VALUES ('BBAS3','BUY','2025-01-01',1,20,0,now(),'33333333-3333-4333-8333-333333333333')"""))
    command.upgrade(Config("alembic.ini"), "003")
    # A fictional contract/ledger already exists before 004. Compare every original field.
    with engine.begin() as connection:
        investment = connection.scalar(text("""INSERT INTO fixed_income_investments
          (owner_id,issuer,product_name,product_type,remuneration,indexer,contracted_rate,application_date,maturity_date,created_at)
          VALUES ('33333333-3333-4333-8333-333333333333','Banco Exemplo','CDB Pré-migração Exemplo',
          'CDB','CDI','CDI',100,'2025-01-01','2027-01-01',now()) RETURNING id"""))
        lot = connection.scalar(text("""INSERT INTO fixed_income_lots(investment_id,owner_id,application_date,created_at)
          VALUES (:id,'33333333-3333-4333-8333-333333333333','2025-01-01',now()) RETURNING id"""), {'id':investment})
        connection.execute(text("""INSERT INTO fixed_income_movements
          (investment_id,lot_id,owner_id,kind,date,principal_amount,created_at)
          VALUES (:id,:lot,'33333333-3333-4333-8333-333333333333','APPLICATION','2025-01-01',100,now())"""),{'id':investment,'lot':lot})
    with engine.connect() as connection:
        original = {table: list(connection.execute(text(f'SELECT * FROM {table} ORDER BY id'))) for table in
          ('fixed_income_investments','fixed_income_lots','fixed_income_movements')}
    command.upgrade(Config("alembic.ini"), "head")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "009"
    with engine.connect() as connection:
        for table, rows in original.items():
            assert list(connection.execute(text(f'SELECT * FROM {table} ORDER BY id'))) == rows
        assert connection.scalar(text('SELECT count(*) FROM fixed_income_observations')) == 0
        assert connection.execute(text("SELECT ticker,quantity,price FROM operations")).one() == ("BBAS3", Decimal(1), Decimal(20))

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
                connection.execute(text("ALTER ROLE investment_runtime PASSWORD 'fictional-test-only-password'"))
                connection.execute(text("GRANT SELECT ON operations TO investment_runtime"))

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
                ticker = "ITUB4" if owner == a else "PETR4"
                created = client.post("/api/operations", json=dict(buy, ticker=ticker, owner_id=str(b)))
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
            from fixed_income_postgres import verify_fixed_income_postgres
            verify_fixed_income_postgres(engine, client)
            from opening_balance_postgres import verify_opening_postgres
            verify_opening_postgres(engine, client)
            from archive_empty_cdb_postgres import verify_archive_postgres
            verify_archive_postgres(engine, client)
            from application_revisions_postgres import verify_revisions_postgres
            verify_revisions_postgres(engine, client)

            # Use a real restricted login so rollback clears only the transaction-local
            # owner context, as it does for the production runtime role.
            from app.equity_history import equity_history_service
            from app.market_data.equity_history import DailyPrice, TickerHistory

            class FakeHistoryService:
                async def get(self, tickers, *, price_start, event_start, end):
                    return {ticker: TickerHistory((DailyPrice(date(2026, 1, 1), Decimal("25")),))
                            for ticker in tickers}

            assert app.state.equity_history_service.enabled is False
            disabled_history = client.get("/api/dashboard/equity-history?period=Tudo")
            assert disabled_history.status_code == 200
            assert disabled_history.json()["coverage"] == "unavailable"
            assert disabled_history.json()["provider_errors"] == {"ITUB4": "disabled"}

            runtime_engine = create_engine(engine.url.set(
                username="investment_runtime", password="fictional-test-only-password"))

            def runtime_db():
                with Session(runtime_engine) as session:
                    yield session

            app.dependency_overrides[get_db] = runtime_db
            app.dependency_overrides[equity_history_service] = lambda: FakeHistoryService()
            app.dependency_overrides[authenticate] = lambda: Principal(a)
            history_a = client.get("/api/dashboard/equity-history?period=Tudo")
            assert history_a.status_code == 200
            assert {holding["ticker"] for point in history_a.json()["points"]
                    for holding in point["holdings"]} == {"ITUB4"}
            app.dependency_overrides[authenticate] = lambda: Principal(b)
            history_b = client.get("/api/dashboard/equity-history?period=Tudo")
            assert history_b.status_code == 200
            assert {holding["ticker"] for point in history_b.json()["points"]
                    for holding in point["holdings"]} == {"PETR4"}

            # New private cash/income events retain owner isolation and append-only writes.
            app.dependency_overrides[authenticate] = lambda: Principal(a)
            event_a = client.post("/api/financial-events", headers={"Idempotency-Key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}, json={
                "kind": "CONTRIBUTION", "event_date": "2026-01-03", "cash_amount": "125.25000001", "source": "Fixture PostgreSQL",
            })
            assert event_a.status_code == 201, event_a.text
            app.dependency_overrides[authenticate] = lambda: Principal(b)
            event_b = client.post("/api/financial-events", headers={"Idempotency-Key": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}, json={
                "kind": "DIVIDEND", "event_date": "2026-01-04", "ticker": "PETR4", "cash_amount": "8.75", "source": "Fixture PostgreSQL",
            })
            assert event_b.status_code == 201, event_b.text
            app.dependency_overrides[authenticate] = lambda: Principal(a)
            replace_a = client.post(f"/api/financial-events/{event_a.json()['id']}/revisions", headers={"Idempotency-Key": "cccccccc-cccc-4ccc-8ccc-cccccccccccc"}, json={
                "kind": "REPLACE", "expected_revision": 0, "reason": "Valor conferido na fixture",
                "replacement": {"kind": "CONTRIBUTION", "event_date": "2026-01-05", "cash_amount": "130.00000003", "source": "Fixture PostgreSQL revisada"},
            })
            assert replace_a.status_code == 201, replace_a.text
            assert Decimal(client.get("/api/dashboard/financial-events/summary").json()["contributions"]) == Decimal("130.00000003")
            app.dependency_overrides[authenticate] = lambda: Principal(b)
            void_b = client.post(f"/api/financial-events/{event_b.json()['id']}/revisions", headers={"Idempotency-Key": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"}, json={
                "kind": "VOID", "expected_revision": 0, "reason": "Fixture de duplicidade",
            })
            assert void_b.status_code == 201, void_b.text
            assert client.get("/api/financial-events").json() == []
            assert client.get(f"/api/financial-events/{event_a.json()['id']}/revisions").status_code == 404
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(text("""INSERT INTO financial_events
                      (owner_id,request_id,kind,event_date,cash_amount,source)
                      VALUES ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
                        'dddddddd-dddd-4ddd-8ddd-dddddddddddd','CONTRIBUTION','2026-01-06',NULL,'Invalid fixture')"""))
            app.dependency_overrides[authenticate] = lambda: Principal(a)
            assert [row["id"] for row in client.get("/api/financial-events").json()] == [event_a.json()["id"]]
            assert Decimal(client.get("/api/dashboard/financial-events/summary").json()["contributions"]) == Decimal("130.00000003")

            # CSV batch uses the same owner/RLS boundary and is atomic/idempotent.
            batch_key = "ffffffff-ffff-4fff-8fff-ffffffffffff"
            batch_rows = {"rows": [
                {"row_number": 2, "event": {"kind": "CONTRIBUTION", "event_date": "2026-01-07", "cash_amount": "42.125", "source": "CSV PostgreSQL fixture"}},
                {"row_number": 3, "event": {"kind": "CONTRIBUTION", "event_date": "2026-01-07", "cash_amount": "42.125", "source": "CSV PostgreSQL fixture"}},
            ]}
            batch_a = client.post("/api/financial-events/import", headers={"Idempotency-Key": batch_key}, json=batch_rows)
            assert batch_a.status_code == 201, batch_a.text
            assert (batch_a.json()["imported_count"], batch_a.json()["duplicate_count"]) == (1, 1)
            replay_a = client.post("/api/financial-events/import", headers={"Idempotency-Key": batch_key}, json=batch_rows)
            assert replay_a.status_code == 200
            assert (replay_a.json()["imported_count"], replay_a.json()["duplicate_count"]) == (0, 2)
            assert Decimal(client.get("/api/dashboard/financial-events/summary").json()["contributions"]) == Decimal("172.12500003")

            concurrent_body = {"rows": [{"row_number": 2, "event": {
                "kind": "CONTRIBUTION", "event_date": "2026-01-08", "cash_amount": "19.50", "source": "Concurrent CSV fixture",
            }}]}
            def concurrent_import(key):
                return client.post("/api/financial-events/import", headers={"Idempotency-Key": key}, json=concurrent_body)
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(concurrent_import, (
                    "13131313-1313-4313-8313-131313131313", "14141414-1414-4414-8414-141414141414",
                )))
            assert all(result.status_code in (200, 201) for result in responses)
            assert sorted(result.json()["imported_count"] for result in responses) == [0, 1]
            assert len(client.get("/api/financial-events").json()) == 3

            # A matching financial fact in another owner remains independent.
            app.dependency_overrides[authenticate] = lambda: Principal(b)
            batch_b = client.post("/api/financial-events/import", headers={"Idempotency-Key": "12121212-1212-4212-8212-121212121212"}, json={
                "rows": [{"row_number": 2, "event": {"kind": "CONTRIBUTION", "event_date": "2026-01-07", "cash_amount": "42.125", "source": "CSV PostgreSQL fixture"}}],
            })
            assert batch_b.status_code == 201, batch_b.text
            assert batch_b.json()["imported_count"] == 1
            app.dependency_overrides[authenticate] = lambda: Principal(a)
            assert len(client.get("/api/financial-events").json()) == 3
            with runtime_engine.begin() as connection:
                assert not connection.scalar(text("SELECT has_table_privilege(current_user,'public.financial_events','UPDATE')"))
                assert not connection.scalar(text("SELECT has_table_privilege(current_user,'public.financial_events','DELETE')"))
                assert not connection.scalar(text("SELECT has_table_privilege(current_user,'public.financial_event_revisions','UPDATE')"))
                assert not connection.scalar(text("SELECT has_table_privilege(current_user,'public.financial_event_revisions','DELETE')"))
                connection.execute(text("SELECT set_config('app.user_id', '', true), set_config('app.auth_mode', 'supabase', true)"))
                assert connection.scalar(text("SELECT count(*) FROM public.financial_events")) == 0
            with engine.begin() as connection:
                connection.execute(text("GRANT SELECT ON public.financial_events, public.financial_event_revisions TO investment_test_runtime"))
            runtime_engine.dispose()
    finally:
        app.dependency_overrides.clear()
        # Banco exclusivamente de teste; não apagar tabelas ou reverter ownership.
        engine.dispose()
