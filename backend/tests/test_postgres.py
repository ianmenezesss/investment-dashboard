"""Opt-in: exige banco PostgreSQL dedicado, vazio e descartável."""
import os
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
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "012"
    # Supabase migrations commonly run as a privileged CREATEROLE role rather
    # than a PostgreSQL superuser. Reproduce the function-owner transfer rules
    # and verify temporary SET membership is removed immediately afterward.
    with engine.begin() as connection:
        connection.execute(text("CREATE ROLE investment_migration_probe NOLOGIN CREATEROLE NOBYPASSRLS"))
        connection.execute(text("GRANT CREATE, USAGE ON SCHEMA public TO investment_migration_probe WITH GRANT OPTION"))
        connection.execute(text("SET LOCAL ROLE investment_migration_probe"))
        connection.execute(text("CREATE ROLE investment_owner_probe NOLOGIN NOBYPASSRLS"))
        connection.execute(text("GRANT CREATE ON SCHEMA public TO investment_owner_probe"))
        connection.execute(text("CREATE FUNCTION public.investment_owner_probe() RETURNS integer LANGUAGE sql AS 'SELECT 1'"))
        connection.execute(text("GRANT investment_owner_probe TO CURRENT_USER WITH SET TRUE, INHERIT FALSE"))
        connection.execute(text("ALTER FUNCTION public.investment_owner_probe() OWNER TO investment_owner_probe"))
        connection.execute(text("REVOKE investment_owner_probe FROM CURRENT_USER"))
        connection.execute(text("REVOKE CREATE ON SCHEMA public FROM investment_owner_probe"))
        connection.execute(text("RESET ROLE"))
        assert connection.scalar(text("SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid='public.investment_owner_probe()'::regprocedure")) == "investment_owner_probe"
        assert connection.scalar(text("""SELECT count(*) FROM pg_auth_members
          WHERE roleid='investment_owner_probe'::regrole
            AND NOT (member='investment_migration_probe'::regrole AND admin_option
                     AND NOT inherit_option AND NOT set_option)""")) == 0
        assert connection.scalar(text("SELECT count(*) FROM pg_auth_members WHERE member='investment_owner_probe'::regrole")) == 0
        assert connection.scalar(text("SELECT count(*) FROM pg_auth_members WHERE roleid='investment_owner_probe'::regrole AND member='investment_migration_probe'::regrole AND set_option")) == 0
        connection.execute(text("DROP FUNCTION public.investment_owner_probe()"))
        connection.execute(text("REVOKE CREATE, USAGE ON SCHEMA public FROM investment_migration_probe"))
        connection.execute(text("DROP ROLE investment_owner_probe, investment_migration_probe"))
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO account_members(user_id,email,status) VALUES (:a,'a@example.test','active'),(:b,'b@example.test','active')"), {"a": UUID("11111111-1111-4111-8111-111111111111"), "b": UUID("22222222-2222-4222-8222-222222222222")})
        connection.execute(text("INSERT INTO account_invitations(id,email,invited_by,created_at,expires_at) VALUES (:id,'invite@example.test',:admin,now(),now()+interval '7 days')"), {"id": UUID("33333333-3333-4333-8333-333333333333"), "admin": UUID("11111111-1111-4111-8111-111111111111")})
    # The privileged acceptance function must bind both identity and email to the
    # trusted request context; a revoked member may return only via a new invite.
    invitee = UUID("44444444-4444-4444-8444-444444444444")
    admin = UUID("11111111-1111-4111-8111-111111111111")
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE investment_runtime"))
        connection.execute(text("SELECT set_config('app.admin_id',:admin,true)"), {"admin": str(admin)})
        connection.execute(text("INSERT INTO account_invitations(id,email,invited_by,created_at,expires_at) VALUES (:id,'invitee@example.test',:admin,now(),now()+interval '7 days')"), {"id": UUID("55555555-5555-4555-8555-555555555555"), "admin": admin})
        connection.execute(text("SELECT set_config('app.user_id',:other,true),set_config('app.user_email','invitee@example.test',true)"), {"other": str(UUID("22222222-2222-4222-8222-222222222222"))})
        assert connection.scalar(text("SELECT public.accept_dashboard_invitation(:user_id,'invitee@example.test')"), {"user_id": invitee}) is False
        connection.execute(text("SELECT set_config('app.user_id',:user_id,true),set_config('app.user_email','different@example.test',true)"), {"user_id": str(invitee)})
        assert connection.scalar(text("SELECT public.accept_dashboard_invitation(:user_id,'invitee@example.test')"), {"user_id": invitee}) is False
        connection.execute(text("SELECT set_config('app.user_email','invitee@example.test',true)"))
        assert connection.scalar(text("SELECT public.accept_dashboard_invitation(:user_id,'invitee@example.test')"), {"user_id": invitee}) is True
        assert connection.scalar(text("SELECT public.revoke_dashboard_account(:user_id,:admin_id)"), {"user_id": invitee, "admin_id": admin}) is True
        connection.execute(text("INSERT INTO account_invitations(id,email,invited_by,created_at,expires_at) VALUES (:id,'invitee@example.test',:admin,now(),now()+interval '7 days')"), {"id": UUID("66666666-6666-4666-8666-666666666666"), "admin": admin})
        assert connection.scalar(text("SELECT public.accept_dashboard_invitation(:user_id,'invitee@example.test')"), {"user_id": invitee}) is True
        assert connection.scalar(text("SELECT status FROM account_members WHERE user_id=:user_id"), {"user_id": invitee}) == "active"
        connection.execute(text("SELECT set_config('app.user_id',:user_id,true)"), {"user_id": str(admin)})
        assert all(connection.scalar(text("SELECT public.consume_dashboard_assistant_quota(:user_id)"), {"user_id": admin}) is True for _ in range(5))
        assert connection.scalar(text("SELECT public.consume_dashboard_assistant_quota(:user_id)"), {"user_id": admin}) is False
        assert connection.scalar(text("SELECT public.consume_dashboard_assistant_quota(:user_id)"), {"user_id": UUID("22222222-2222-4222-8222-222222222222")}) is False
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
                connection.execute(text("GRANT SELECT ON portfolio_valuation_observations TO investment_test_runtime"))
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

            observation = client.post("/api/dashboard/wealth-observations",
                headers={"Idempotency-Key": "ffffffff-ffff-4fff-8fff-ffffffffffff"},
                json={"as_of": "2026-01-07", "equities_market_value": "250.00",
                      "equities_source": "Extrato fictício da corretora"})
            assert observation.status_code == 201, observation.text
            # Active synthetic CDBs have no observation on this date, so a total
            # would be misleading; the missing coverage must remain explicit.
            assert observation.json()["fixed_income_coverage"] == "unavailable"
            assert observation.json()["missing_fixed_income"]
            assert observation.json()["consolidated_net_value"] is None
            assert observation.json()["consolidated_coverage"] == "partial"
            app.dependency_overrides[authenticate] = lambda: Principal(b)
            assert client.get("/api/dashboard/wealth-observations").json() == []
            app.dependency_overrides[authenticate] = lambda: Principal(a)
            assert len(client.get("/api/dashboard/wealth-observations").json()) == 1

            with runtime_engine.begin() as connection:
                assert not connection.scalar(text("SELECT has_table_privilege(current_user,'public.financial_events','UPDATE')"))
                assert not connection.scalar(text("SELECT has_table_privilege(current_user,'public.financial_events','DELETE')"))
                assert not connection.scalar(text("SELECT has_table_privilege(current_user,'public.financial_event_revisions','UPDATE')"))
                assert not connection.scalar(text("SELECT has_table_privilege(current_user,'public.financial_event_revisions','DELETE')"))
                assert connection.scalar(text("SELECT has_table_privilege(current_user,'public.portfolio_valuation_observations','SELECT')"))
                assert connection.scalar(text("SELECT has_table_privilege(current_user,'public.portfolio_valuation_observations','INSERT')"))
                assert not connection.scalar(text("SELECT has_table_privilege(current_user,'public.portfolio_valuation_observations','UPDATE')"))
                assert not connection.scalar(text("SELECT has_table_privilege(current_user,'public.portfolio_valuation_observations','DELETE')"))
                assert not connection.scalar(text("SELECT has_table_privilege(current_user,'public.portfolio_valuation_observations','TRUNCATE')"))
                assert connection.scalar(text("SELECT has_sequence_privilege(current_user,'public.portfolio_valuation_observations_id_seq','USAGE')"))
                connection.execute(text("SELECT set_config('app.user_id', '', true), set_config('app.auth_mode', 'supabase', true)"))
                assert connection.scalar(text("SELECT count(*) FROM public.financial_events")) == 0
                assert connection.scalar(text("SELECT count(*) FROM public.portfolio_valuation_observations")) == 0
                connection.execute(text("SELECT set_config('app.user_id', :owner, true)"), {"owner": str(a)})
                assert connection.scalar(text("SELECT count(*) FROM public.portfolio_valuation_observations")) == 1
            with engine.begin() as connection:
                connection.execute(text("GRANT SELECT ON public.financial_events, public.financial_event_revisions TO investment_test_runtime"))
            from account_deletion_postgres import verify_account_deletion_postgres
            verify_account_deletion_postgres(engine, runtime_engine)
            # Reproduce the existing runtime privileges required by the private API:
            # single-operation deletion remains owner-scoped; ledgers stay append-only.
            with engine.begin() as connection:
                for table in ("operations", "fixed_income_investments", "fixed_income_lots",
                              "fixed_income_movements", "fixed_income_observations",
                              "fixed_income_investment_archives", "fixed_income_application_revisions",
                              "financial_events", "financial_event_revisions",
                              "portfolio_valuation_observations"):
                    connection.execute(text(f"GRANT SELECT, INSERT ON public.{table} TO investment_runtime"))
                connection.execute(text("GRANT DELETE ON public.operations TO investment_runtime"))
                for sequence in ("operations_id_seq", "fixed_income_investments_id_seq", "fixed_income_lots_id_seq",
                                 "fixed_income_movements_id_seq", "fixed_income_observations_id_seq",
                                 "fixed_income_investment_archives_id_seq", "fixed_income_application_revisions_id_seq",
                                 "financial_events_id_seq", "financial_event_revisions_id_seq",
                                 "portfolio_valuation_observations_id_seq"):
                    connection.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE public.{sequence} TO investment_runtime"))
            from demo_fixture_postgres import verify_demo_fixture_postgres
            verify_demo_fixture_postgres(engine, runtime_engine)
            runtime_engine.dispose()
    finally:
        app.dependency_overrides.clear()
        # Banco exclusivamente de teste; não apagar tabelas ou reverter ownership.
        engine.dispose()
