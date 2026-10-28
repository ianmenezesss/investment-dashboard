"""Only invoked inside the disposable PostgreSQL test runner; fictional records."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from decimal import Decimal
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.main import app
from app.auth import authenticate, Principal
from test_fixed_income import PATH, A, B
from test_opening_balances import POSITION, contract


def verify_opening_postgres(engine, client):
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    investment = contract(client)
    barrier = Barrier(2)
    def post():
        barrier.wait(timeout=10)
        return client.post(f"{PATH}/{investment}/opening-balance", json=POSITION).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(post),pool.submit(post)]
        assert sorted(f.result(timeout=15) for f in futures)==[201,409]
    data=client.get(f"{PATH}/{investment}").json()
    assert data['latest_observation']['confirmed_principal'] is None
    assert data['lots']==[] and client.get(f"{PATH}/{investment}/movements").json()==[]
    result=client.post(f"{PATH}/{investment}/applications",json={'date':'2026-10-16','principal_amount':'100'})
    assert result.status_code==201,result.text
    observation=client.post(f"{PATH}/{investment}/observations",json=POSITION|{'as_of':'2026-10-17','reason':'AFTER_CONSOLIDATED_REDEMPTION','cash_received':'300','gross_value':'4800','net_value':'4750'})
    assert observation.status_code==201,observation.text
    assert len(client.get(f"{PATH}/{investment}/observations").json())==2
    assert len(client.get(f"{PATH}/{investment}/movements").json())==1
    app.dependency_overrides[authenticate] = lambda: Principal(B)
    assert client.get(f"{PATH}/{investment}/observations").status_code==404
    assert client.post(f"{PATH}/{investment}/observations",json=POSITION).status_code==404
    with engine.begin() as c:
        c.execute(text('SET LOCAL ROLE investment_test_runtime'))
        assert c.scalar(text('SELECT count(*) FROM fixed_income_observations'))==0
        c.execute(text("SELECT set_config('app.user_id',:owner,true),set_config('app.auth_mode','supabase',true)"),{'owner':str(B)})
        assert c.scalar(text('SELECT count(*) FROM fixed_income_observations'))==0
        c.execute(text("SELECT set_config('app.user_id',:owner,true)"),{'owner':str(A)})
        assert c.scalar(text('SELECT count(*) FROM fixed_income_observations'))==2
        assert c.scalar(text("SELECT has_table_privilege(current_user,'fixed_income_observations','SELECT') AND has_table_privilege(current_user,'fixed_income_observations','INSERT')"))
        for privilege in ('UPDATE','DELETE','TRUNCATE'):
            assert not c.scalar(text("SELECT has_table_privilege(current_user,'fixed_income_observations',:p)"),{'p':privilege})
        assert c.scalar(text("SELECT has_sequence_privilege(current_user,'fixed_income_observations_id_seq','USAGE')"))
    for sql in ('UPDATE fixed_income_observations SET id=id','DELETE FROM fixed_income_observations','TRUNCATE fixed_income_observations'):
        with pytest.raises(DBAPIError) as error:
            with engine.begin() as c:c.execute(text(sql))
        assert error.value.orig.sqlstate=='23514'
    # SQL writers cannot bypass date/owner/amount invariants by skipping FastAPI.
    insert = text("""INSERT INTO fixed_income_observations(investment_id,owner_id,kind,reason,as_of,gross_value,net_value,taxes_combined,source,created_at)
      VALUES(:id,:owner,'OBSERVATION','POSITION',:day,:gross,:net,:tax,'Fonte fictícia',now())""")
    for day,gross,net,tax in [('2026-10-14','5000','4950','50'),('2026-10-17','5000','4950','40'),('2026-10-17','NaN','4950','50')]:
        with pytest.raises(DBAPIError) as error:
            with engine.begin() as c:
                c.execute(text('SET LOCAL ROLE investment_test_runtime'))
                c.execute(text("SELECT set_config('app.user_id',:owner,true),set_config('app.auth_mode','supabase',true)"),{'owner':str(A)})
                c.execute(insert,{'id':investment,'owner':str(A),'day':day,'gross':gross,'net':net,'tax':tax})
        assert error.value.orig.sqlstate=='23514'
    with engine.connect() as c:
        assert c.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='fixed_income_observations'::regclass")).one()==(True,True)
        for role in ('anon','authenticated','service_role'):
            assert not c.scalar(text("SELECT has_table_privilege(:r,'fixed_income_observations','SELECT') OR has_table_privilege(:r,'fixed_income_observations','INSERT')"),{'r':role})
        assert c.scalar(text("SELECT confirmed_principal FROM fixed_income_observations WHERE kind='OPENING' AND investment_id=:id"),{'id':investment}) is None
        assert c.scalar(text("SELECT gross_value-net_value FROM fixed_income_observations WHERE kind='OPENING' AND investment_id=:id"),{'id':investment})==Decimal('50')
    app.dependency_overrides[authenticate] = lambda: Principal(A)
