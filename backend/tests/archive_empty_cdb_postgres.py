"""Opt-in coverage for contract archival on the disposable PostgreSQL runner."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.auth import authenticate, Principal
from app.main import app
from test_fixed_income import A, B, CONTRACT, PATH


def verify_archive_postgres(engine, client):
    with engine.begin() as connection:
        flags = connection.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=to_regclass('public.fixed_income_investment_archives')")).one()
        assert flags == (True, True)
        connection.execute(text("SET LOCAL ROLE investment_test_runtime"))
        assert connection.scalar(text("SELECT has_table_privilege(current_user,'fixed_income_investment_archives','SELECT') AND has_table_privilege(current_user,'fixed_income_investment_archives','INSERT')"))
        for privilege in ('UPDATE', 'DELETE', 'TRUNCATE'):
            assert not connection.scalar(text("SELECT has_table_privilege(current_user,'fixed_income_investment_archives',:privilege)"), {'privilege': privilege})
        assert connection.scalar(text("SELECT has_sequence_privilege(current_user,'fixed_income_investment_archives_id_seq','USAGE')"))

    app.dependency_overrides[authenticate] = lambda: Principal(A)
    active_before = {row['id'] for row in client.get(PATH).json()}
    created = client.post(PATH, json=CONTRACT)
    assert created.status_code == 201, created.text
    empty_id = created.json()['id']
    original_name = created.json()['product_name']
    app.dependency_overrides[authenticate] = lambda: Principal(B)
    assert client.delete(f"{PATH}/{empty_id}/archive").status_code == 404
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE investment_test_runtime"))
        assert connection.scalar(text("SELECT count(*) FROM fixed_income_investment_archives")) == 0

    app.dependency_overrides[authenticate] = lambda: Principal(A)
    assert client.delete(f"{PATH}/{empty_id}/archive").status_code == 204
    assert {row['id'] for row in client.get(PATH).json()} == active_before
    assert client.get(f"{PATH}/{empty_id}").status_code == 404
    with engine.begin() as connection:
        assert connection.execute(text("SELECT id,product_name FROM fixed_income_investments WHERE id=:id"), {'id': empty_id}).one() == (empty_id, original_name)
        assert connection.scalar(text("SELECT count(*) FROM fixed_income_investment_archives WHERE investment_id=:id AND owner_id=:owner"), {'id': empty_id, 'owner': str(A)}) == 1
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE investment_test_runtime"))
        assert connection.scalar(text("SELECT count(*) FROM fixed_income_investment_archives")) == 0
        connection.execute(text("SELECT set_config('app.user_id',:owner,true),set_config('app.auth_mode','supabase',true)"), {'owner': str(B)})
        assert connection.scalar(text("SELECT count(*) FROM fixed_income_investment_archives")) == 0
        connection.execute(text("SELECT set_config('app.user_id',:owner,true)"), {'owner': str(A)})
        assert connection.scalar(text("SELECT count(*) FROM fixed_income_investment_archives WHERE investment_id=:id"), {'id': empty_id}) == 1

    # Direct runtime inserts cannot attach new history to the archived contract.
    statements = (
        ("INSERT INTO fixed_income_lots(investment_id,owner_id,application_date,created_at) VALUES (:id,:owner,'2025-01-01',now())", {'id': empty_id, 'owner': str(A)}),
        ("INSERT INTO fixed_income_observations(investment_id,owner_id,kind,reason,as_of,gross_value,net_value,source,created_at) VALUES (:id,:owner,'OPENING','POSITION','2025-01-01',1,1,'Fictício',now())", {'id': empty_id, 'owner': str(A)}),
    )
    for statement, params in statements:
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(text("SET LOCAL ROLE investment_test_runtime"))
                connection.execute(text("SELECT set_config('app.user_id',:owner,true),set_config('app.auth_mode','supabase',true)"), {'owner': str(A)})
                connection.execute(text(statement), params)
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            connection.execute(text("SET LOCAL ROLE investment_test_runtime"))
            connection.execute(text("SELECT set_config('app.user_id',:owner,true),set_config('app.auth_mode','supabase',true)"), {'owner': str(A)})
            connection.execute(text("INSERT INTO fixed_income_lots(investment_id,owner_id,application_date,created_at) VALUES (:id,:owner,'2025-01-01',now())"), {'id': empty_id, 'owner': str(A)})

    # Lots and manual position observations each disqualify an otherwise empty contract.
    populated = client.post(PATH, json=CONTRACT | {'product_name': 'CDB com lote fictício'})
    assert populated.status_code == 201
    populated_id = populated.json()['id']
    applied = client.post(f"{PATH}/{populated_id}/applications", json={'date': '2025-01-01', 'principal_amount': '100'})
    assert applied.status_code == 201, applied.text
    assert client.delete(f"{PATH}/{populated_id}/archive").status_code == 409

    from test_opening_balances import POSITION, contract
    observed_id = contract(client)
    assert client.post(f"{PATH}/{observed_id}/opening-balance", json=POSITION).status_code == 201
    assert client.delete(f"{PATH}/{observed_id}/archive").status_code == 409

    # Under the shared advisory lock, an application and archive cannot both win.
    raced = client.post(PATH, json=CONTRACT | {'product_name': 'CDB concorrente fictício'})
    assert raced.status_code == 201
    raced_id = raced.json()['id']
    barrier = Barrier(2)
    def archive():
        barrier.wait(timeout=10)
        return client.delete(f"{PATH}/{raced_id}/archive").status_code
    def application():
        barrier.wait(timeout=10)
        return client.post(f"{PATH}/{raced_id}/applications", json={'date': '2025-01-01', 'principal_amount': '25'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        archive_future = pool.submit(archive)
        application_future = pool.submit(application)
        statuses = (archive_future.result(timeout=20), application_future.result(timeout=20))
    assert statuses in ((204, 404), (409, 201)), statuses
    with engine.begin() as connection:
        is_archived = connection.scalar(text("SELECT EXISTS(SELECT 1 FROM fixed_income_investment_archives WHERE investment_id=:id)"), {'id': raced_id})
        lots = connection.scalar(text("SELECT count(*) FROM fixed_income_lots WHERE investment_id=:id"), {'id': raced_id})
        assert (is_archived and lots == 0) or (not is_archived and lots == 1)

    # Tombstones reject broad mutation even for the migration/table owner.
    for statement in (
        "UPDATE public.fixed_income_investment_archives SET id=id",
        "DELETE FROM public.fixed_income_investment_archives",
        "TRUNCATE public.fixed_income_investment_archives CASCADE",
    ):
        with pytest.raises(DBAPIError) as error:
            with engine.begin() as connection:
                connection.execute(text(statement))
        assert error.value.orig.sqlstate == '23514'
