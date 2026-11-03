"""Assertions for migration 018, called only against the disposable test database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from sqlalchemy import text


def verify_assistant_request_quotas(engine):
    user_id, other_user_id = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO public.account_members(user_id,email,status)
            VALUES (:id,'assistant-quota@example.test','active'),(:other,'assistant-other@example.test','active')"""),
            {"id": user_id, "other": other_user_id})
    reserve_sql = text("SELECT public.reserve_dashboard_assistant_request(:id,:request,2,3,:cooldown)")
    def reserve(connection, request_id, cooldown=0):
        return connection.scalar(reserve_sql, {"id": user_id, "request": request_id, "cooldown": cooldown})
    def release(connection, request_id):
        return connection.scalar(text("SELECT public.release_dashboard_assistant_request(:id,:request)"),
            {"id": user_id, "request": request_id})
    def runtime(connection):
        connection.execute(text("SET LOCAL ROLE investment_runtime"))
        connection.execute(text("SELECT set_config('app.user_id',:id,true)"), {"id": str(user_id)})

    # The row lock serializes two API instances; only one acquires a lease.
    barrier = Barrier(2)
    def compete(request_id):
        with engine.begin() as connection:
            runtime(connection)
            barrier.wait(timeout=10)
            return request_id, reserve(connection, request_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(compete, (uuid4(), uuid4())))
    assert sorted(state for _, state in outcomes) == ["allowed", "busy"]
    winner = next(request_id for request_id, state in outcomes if state == "allowed")
    with engine.begin() as connection:
        runtime(connection)
        assert release(connection, uuid4()) is False
        assert reserve(connection, uuid4()) == "busy"
        assert release(connection, winner) is True
        assert reserve(connection, uuid4(), cooldown=60) == "cooldown"
        second = uuid4()
        assert reserve(connection, second) == "allowed"
        assert release(connection, second) is True
        assert reserve(connection, uuid4()) == "minute"
        connection.execute(text("SELECT set_config('app.user_id',:id,true)"), {"id": str(other_user_id)})
        assert reserve(connection, uuid4()) == "inactive"
    with engine.begin() as connection:
        connection.execute(text("UPDATE public.account_members SET assistant_minute_started_at=now()-interval '2 minutes' WHERE user_id=:id"), {"id": user_id})
    with engine.begin() as connection:
        runtime(connection)
        third = uuid4()
        assert reserve(connection, third) == "allowed"
        assert release(connection, third) is True
        assert reserve(connection, uuid4()) == "daily"
    with engine.begin() as connection:
        connection.execute(text("UPDATE public.account_members SET assistant_usage_date=CURRENT_DATE-1,assistant_minute_started_at=now()-interval '2 minutes',assistant_in_flight_until=now()-interval '1 minute' WHERE user_id=:id"), {"id": user_id})
    with engine.begin() as connection:
        runtime(connection)
        assert reserve(connection, uuid4()) == "allowed"
    with engine.begin() as connection:
        connection.execute(text("UPDATE public.account_members SET access_expires_at=now()-interval '1 second' WHERE user_id=:id"), {"id": user_id})
    with engine.begin() as connection:
        runtime(connection)
        assert reserve(connection, uuid4()) == "inactive"
        assert connection.scalar(text("SELECT has_table_privilege('investment_runtime','public.account_members','UPDATE')")) is False
        for signature in (
            "reserve_dashboard_assistant_request(uuid,uuid,integer,integer,integer)",
            "release_dashboard_assistant_request(uuid,uuid)",
        ):
            assert connection.scalar(text("SELECT has_function_privilege('investment_runtime',:signature,'EXECUTE')"), {"signature": f"public.{signature}"}) is True
            assert connection.scalar(text("SELECT has_function_privilege('anon',:signature,'EXECUTE')"), {"signature": f"public.{signature}"}) is False
