"""Called only by the opt-in, disposable PostgreSQL integration suite."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
from threading import Barrier
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.auth import authenticate, Principal
from app.main import app
from test_fixed_income import CONTRACT, PATH, A, B


def verify_fixed_income_postgres(engine, client):
    tables = ("fixed_income_investments", "fixed_income_lots", "fixed_income_movements")
    with engine.begin() as connection:
        connection.execute(text("GRANT SELECT, INSERT ON fixed_income_observations TO investment_test_runtime"))
        connection.execute(text("GRANT USAGE ON SEQUENCE fixed_income_observations_id_seq TO investment_test_runtime"))
        connection.execute(text("GRANT SELECT, INSERT ON fixed_income_investment_archives TO investment_test_runtime"))
        connection.execute(text("GRANT USAGE ON SEQUENCE fixed_income_investment_archives_id_seq TO investment_test_runtime"))
        for table in tables:
            flags = connection.execute(text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid = to_regclass(:name)"), {"name": "public." + table}).one()
            assert flags == (True, True)
            for role in ("anon", "authenticated", "service_role", "public"):
                # PUBLIC is checked through ACL expansion, not as a login role.
                leaked = connection.scalar(text("""SELECT count(*) FROM pg_class c,
                    LATERAL aclexplode(coalesce(c.relacl, acldefault(CASE WHEN c.relkind='S' THEN 's'::\"char\" ELSE 'r'::\"char\" END,c.relowner))) acl
                    WHERE c.oid IN (to_regclass(:table),to_regclass(:sequence))
                      AND acl.grantee = CASE WHEN :role='public' THEN 0 ELSE (SELECT oid FROM pg_roles WHERE rolname=:role) END"""),
                    {"table": "public." + table, "sequence": "public." + table + "_id_seq", "role": role})
                assert leaked == 0
            connection.execute(text(f"GRANT SELECT, INSERT ON public.{table} TO investment_test_runtime"))
            connection.execute(text(f"GRANT USAGE ON SEQUENCE public.{table}_id_seq TO investment_test_runtime"))
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "005"

    @contextmanager
    def restricted(owner=None, isolation=None):
        with engine.begin() as connection:
            if isolation:
                connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            connection.execute(text("SET LOCAL ROLE investment_test_runtime"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            if owner:
                connection.execute(text("SELECT set_config('app.user_id', :owner, true), set_config('app.auth_mode', 'supabase', true)"), {"owner": str(owner)})
            yield connection

    ids, lots = {}, {}
    for owner in (A, B):
        app.dependency_overrides[authenticate] = lambda owner=owner: Principal(owner)
        result = client.post(PATH, json=CONTRACT)
        assert result.status_code == 201, result.text
        ids[owner] = result.json()["id"]
        result = client.post(f"{PATH}/{ids[owner]}/applications", json={"date": "2025-01-01", "principal_amount": "100"})
        assert result.status_code == 201, result.text
        lots[owner] = result.json()["lot_id"]

    app.dependency_overrides[authenticate] = lambda: Principal(A)
    assert client.get(f"{PATH}/{ids[B]}").status_code == 404
    with restricted() as connection:
        for table in tables:
            assert list(connection.execute(text(f"SELECT id FROM public.{table}"))) == []
    with restricted(A) as connection:
        for table in tables:
            assert len(list(connection.execute(text(f"SELECT id FROM public.{table}")))) == 1
            assert connection.scalar(text("SELECT has_table_privilege(current_user,:table,'SELECT') AND has_table_privilege(current_user,:table,'INSERT')"), {"table": "public." + table})
            assert connection.scalar(text("SELECT has_sequence_privilege(current_user,:sequence,'USAGE')"), {"sequence": "public." + table + "_id_seq"})
            assert not connection.scalar(text("SELECT has_table_privilege(current_user,:table,'UPDATE')"), {"table": "public." + table})
            assert not connection.scalar(text("SELECT has_table_privilege(current_user,:table,'DELETE')"), {"table": "public." + table})
            assert not connection.scalar(text("SELECT has_table_privilege(current_user,:table,'TRUNCATE')"), {"table": "public." + table})

    # RLS and relationship checks work even without the Python owner filter.
    with pytest.raises(DBAPIError):
        with restricted(A) as connection:
            connection.execute(text("""INSERT INTO fixed_income_lots(investment_id, owner_id, application_date, created_at)
                VALUES (:investment, :owner, '2025-01-01', now())"""), {"investment": ids[B], "owner": str(A)})
    with pytest.raises(DBAPIError):
        with restricted(A) as connection:
            connection.execute(text("""INSERT INTO fixed_income_lots(investment_id, owner_id, application_date, created_at)
                VALUES (:investment, :owner, '2025-01-01', now())"""), {"investment": ids[A], "owner": str(B)})
    # A lot without its application cannot be committed (deferred constraint trigger).
    with pytest.raises(DBAPIError):
        with restricted(A) as connection:
            connection.execute(text("""INSERT INTO fixed_income_lots(investment_id, owner_id, application_date, created_at)
                VALUES (:investment, :owner, '2025-01-01', now())"""), {"investment": ids[A], "owner": str(A)})
    # Even the administrative table owner cannot accidentally mutate this history.
    for table in tables:
        for sql in (f"UPDATE public.{table} SET id=id", f"DELETE FROM public.{table}", f"TRUNCATE public.{table} CASCADE"):
            with pytest.raises(DBAPIError) as error:
                with engine.begin() as connection:
                    connection.execute(text(sql))
            assert error.value.orig.sqlstate == "23514"

    insert = text("""INSERT INTO fixed_income_movements
        (investment_id, lot_id, owner_id, kind, date, principal_amount, cash_received, created_at)
        VALUES (:investment, :lot, :owner, 'REDEMPTION', :date, :principal, :cash, now())""")
    barrier = Barrier(2)
    def redeem():
        try:
            with restricted(A) as connection:
                barrier.wait(timeout=10)
                connection.execute(insert, {"investment": ids[A], "lot": lots[A], "owner": str(A),
                    "date": "2025-01-03", "principal": "70", "cash": "75"})
            return "accepted"
        except DBAPIError as error:
            assert error.orig.sqlstate == "23514"
            return "rejected"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(redeem) for _ in range(2)]
        assert sorted(future.result(timeout=15) for future in futures) == ["accepted", "rejected"]
    assert Decimal(client.get(f"{PATH}/{ids[A]}").json()["principal_balance"]) == 30
    # Backdated writes and non-supported transaction isolation cannot evade the ledger.
    for day, isolation in (("2025-01-02", None), ("2025-01-04", "REPEATABLE READ")):
        with pytest.raises(DBAPIError) as error:
            with restricted(A, isolation) as connection:
                connection.execute(insert, {"investment": ids[A], "lot": lots[A], "owner": str(A),
                    "date": day, "principal": "1", "cash": None})
        assert error.value.orig.sqlstate == "23514"

    # Full redemption retains original events; cash never replaces principal.
    result = client.post(f"{PATH}/{ids[A]}/redemptions", json={"lot_id": lots[A],
        "date": "2025-01-04", "principal_amount": "30", "cash_received": "33.12345678"})
    assert result.status_code == 201, result.text
    detail = client.get(f"{PATH}/{ids[A]}").json()
    assert Decimal(detail["principal_balance"]) == 0 and len(detail["lots"]) == 1
    movements = client.get(f"{PATH}/{ids[A]}/movements").json()
    assert len(movements) == 3 and Decimal(movements[-1]["cash_received"]) == Decimal("33.12345678")
    with pytest.raises(DBAPIError) as error:
        with restricted(A) as connection:
            connection.execute(insert, {"investment": ids[A], "lot": lots[A], "owner": str(A),
                "date": "2025-01-05", "principal": "0.00000001", "cash": None})
    assert error.value.orig.sqlstate == "23514"
    # NUMERIC(20,8) round-trips exactly through PostgreSQL and the API, even near its limit.
    result = client.post(f"{PATH}/{ids[A]}/applications", json={"date": "2025-01-05", "principal_amount": "999999999999.12345678"})
    assert result.status_code == 201, result.text
    assert Decimal(client.get(f"{PATH}/{ids[A]}").json()["principal_balance"]) == Decimal("999999999999.12345678")

    # Phase 2.0.3: the new read-only return snapshot also uses the restricted role/RLS.
    import asyncio
    import httpx
    from app.bcb_rates.provider import SGSProvider
    from app.bcb_rates.service import RateService
    from app.bcb_rates.router import rates_service
    cdi = client.post(PATH, json=CONTRACT | {"remuneration": "CDI", "indexer": "CDI", "contracted_rate": "100", "application_date": "2025-01-02"})
    assert cdi.status_code == 201
    investment = cdi.json()["id"]
    assert client.post(f"{PATH}/{investment}/applications", json={"date": "2025-01-02", "principal_amount": "1000"}).status_code == 201
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=[{"data":"02/01/2025","valor":"1"},{"data":"03/01/2025","valor":"1"}])
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = RateService(SGSProvider(http))
    app.dependency_overrides[rates_service] = lambda: service
    query = "as_of=2025-01-04&convention=daily_cdi_pro_rata_decimal_v1&calendar=anbima_2024_2026_v1&tax_profile=br_resident_individual"
    try:
        app.dependency_overrides[authenticate] = lambda: Principal(B)
        assert client.get(f"{PATH}/{investment}/returns?{query}").status_code == 404
        assert not calls
        app.dependency_overrides[authenticate] = lambda: Principal(A)
        result = client.get(f"{PATH}/{investment}/returns?{query}")
        assert result.status_code == 200, result.text
        assert result.json()["gross_income_estimate"] == "20.10"
        assert result.json()["net_value_estimate"] == "1001.09" and len(calls) == 1
        with restricted(A) as connection:
            assert connection.scalar(text("SELECT count(*) FROM fixed_income_movements WHERE investment_id=:id"), {"id":investment}) == 1
    finally:
        app.dependency_overrides.pop(rates_service, None)
        asyncio.run(http.aclose())
