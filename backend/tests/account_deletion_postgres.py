"""Disposable-PostgreSQL checks for deletion RLS, append-only gates and retry safety."""
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


OWNER = UUID("77777777-7777-4777-8777-777777777777")
OTHER = UUID("88888888-8888-4888-8888-888888888888")
ADMIN = UUID("99999999-9999-4999-8999-999999999999")
OWNER_EMAIL = "delete-owner@example.test"
OTHER_EMAIL = "delete-other@example.test"


def _seed(engine):
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO public.account_members(user_id,email,status)
          VALUES (:owner,:owner_email,'active'),(:other,:other_email,'active')"""),
          {"owner": OWNER, "owner_email": OWNER_EMAIL, "other": OTHER, "other_email": OTHER_EMAIL})
        connection.execute(text("""INSERT INTO public.account_invitations
          (id,email,invited_by,created_at,expires_at,accepted_user_id)
          VALUES ('77777777-7777-4777-8777-000000000001',:owner_email,:admin,now(),now()+interval '7 days',:owner),
                 ('77777777-7777-4777-8777-000000000002','pending-' || :owner_email,:admin,now(),now()+interval '7 days',NULL),
                 ('88888888-8888-4888-8888-000000000001',:other_email,:admin,now(),now()+interval '7 days',:other)"""),
          {"owner_email": OWNER_EMAIL, "other_email": OTHER_EMAIL, "admin": ADMIN, "owner": OWNER, "other": OTHER})
        connection.execute(text("""INSERT INTO public.account_invitation_send_attempts
          (invitation_id,requested_by,attempted_at,outcome,method,http_status)
          VALUES ('77777777-7777-4777-8777-000000000001',:admin,now(),'requested','invite',200)"""),
          {"admin": ADMIN})
        for user_id, ticker in ((OWNER, "ABCD3"), (OTHER, "WXYZ3")):
            connection.execute(text("""INSERT INTO public.operations
              (owner_id,ticker,kind,date,quantity,price,fees,created_at)
              VALUES (:owner,:ticker,'BUY','2026-01-01',1,10,0,now())"""), {"owner": user_id, "ticker": ticker})
            connection.execute(text("""INSERT INTO public.financial_events
              (owner_id,request_id,kind,event_date,cash_amount,source)
              VALUES (:owner,:request,'CONTRIBUTION','2026-01-02',100,'FICTÍCIO — teste PostgreSQL')"""),
              {"owner": user_id, "request": UUID(int=user_id.int % (2**128 - 1) + 1)})
            connection.execute(text("""INSERT INTO public.portfolio_valuation_observations
              (owner_id,request_id,as_of,equities_market_value,equities_source,fixed_income_gross_value,
               fixed_income_net_value,fixed_income_coverage,fixed_income_sources,missing_fixed_income,created_at)
              VALUES (:owner,:request,'2026-01-02',100,'FICTÍCIO — teste PostgreSQL',NULL,NULL,'empty','[]','[]',now())"""),
              {"owner": user_id, "request": UUID(int=user_id.int % (2**128 - 2) + 2)})

        investment_id = connection.scalar(text("""INSERT INTO public.fixed_income_investments
          (owner_id,issuer,product_name,product_type,remuneration,indexer,contracted_rate,application_date,maturity_date,created_at)
          VALUES (:owner,'Banco Fictício','CDB de teste','CDB','FIXED','NONE',10,'2026-01-01','2027-01-01',now()) RETURNING id"""),
          {"owner": OWNER})
        connection.execute(text("""INSERT INTO public.fixed_income_observations
          (investment_id,owner_id,kind,reason,as_of,gross_value,net_value,source,created_at)
          VALUES (:investment,:owner,'OPENING','POSITION','2026-01-01',100,100,'FICTÍCIO — abertura',now())"""),
          {"investment": investment_id, "owner": OWNER})
        lot_id = connection.scalar(text("""INSERT INTO public.fixed_income_lots(investment_id,owner_id,application_date,created_at)
          VALUES (:investment,:owner,'2026-02-01',now()) RETURNING id"""), {"investment": investment_id, "owner": OWNER})
        movement_id = connection.scalar(text("""INSERT INTO public.fixed_income_movements
          (investment_id,lot_id,owner_id,kind,date,principal_amount,created_at)
          VALUES (:investment,:lot,:owner,'APPLICATION','2026-02-01',50,now()) RETURNING id"""),
          {"investment": investment_id, "lot": lot_id, "owner": OWNER})
        connection.execute(text("""INSERT INTO public.fixed_income_application_revisions
          (application_id,owner_id,revision,kind,replacement_date,replacement_amount,reason,request_id,created_at)
          VALUES (:movement,:owner,1,'VOID',NULL,NULL,'FICTÍCIO — revisão de teste',:request,now())"""),
          {"movement": movement_id, "owner": OWNER,
           "request": UUID("77777777-7777-4777-8777-000000000003")})
        connection.execute(text("""INSERT INTO public.fixed_income_observations
          (investment_id,owner_id,kind,reason,as_of,gross_value,net_value,source,created_at)
          VALUES (:investment,:owner,'OBSERVATION','POSITION','2026-10-31',110,105,'FICTÍCIO — posição final',now())"""),
          {"investment": investment_id, "owner": OWNER})
        archived_id = connection.scalar(text("""INSERT INTO public.fixed_income_investments
          (owner_id,issuer,product_name,product_type,remuneration,indexer,contracted_rate,application_date,maturity_date,created_at)
          VALUES (:owner,'Banco Fictício','CDB vazio arquivado','CDB','FIXED','NONE',10,'2026-01-01','2027-01-01',now()) RETURNING id"""),
          {"owner": OWNER})
        connection.execute(text("""INSERT INTO public.fixed_income_investment_archives(investment_id,owner_id,archived_at)
          VALUES (:investment,:owner,now())"""), {"investment": archived_id, "owner": OWNER})
        event_id = connection.scalar(text("""SELECT id FROM public.financial_events WHERE owner_id=:owner"""), {"owner": OWNER})
        connection.execute(text("""INSERT INTO public.financial_event_revisions
          (event_id,owner_id,revision,kind,replacement_kind,replacement_date,replacement_ticker,replacement_cash_amount,
           replacement_gross_amount,replacement_tax_withheld,replacement_source,replacement_description,reason,request_id,created_at)
          VALUES (:event,:owner,1,'VOID',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'FICTÍCIO — revisão de teste',:request,now())"""),
          {"event": event_id, "owner": OWNER,
           "request": UUID("77777777-7777-4777-8777-000000000004")})
        connection.execute(text("""INSERT INTO public.account_fixture_loads(user_id,fixture_id,fixture_sha256,loaded_by,loaded_at)
          VALUES (:owner,'v2-demo-scenario',repeat('a',64),:admin,now())"""), {"owner": OWNER, "admin": ADMIN})


def _runtime_call(runtime_engine, owner, function, **params):
    values = {"user": str(owner), "email": params.get("email", ""), **params}
    function_args = ",".join(f":{key}" for key in params)
    with runtime_engine.begin() as connection:
        connection.execute(text("SELECT set_config('app.user_id',:user,true),set_config('app.user_email',:email,true),set_config('app.auth_mode','supabase',true)"), values)
        return connection.scalar(text(f"SELECT public.{function}({function_args})"), values)


def verify_account_deletion_postgres(engine, runtime_engine):
    _seed(engine)

    # The subject is always tied to the authenticated owner context; a caller cannot
    # pass another user's UUID even through the internal SQL function.
    with pytest.raises(DBAPIError):
        _runtime_call(runtime_engine, OTHER, "purge_dashboard_account_data", user_id=OWNER)
    with pytest.raises(DBAPIError):
        _runtime_call(runtime_engine, OWNER, "begin_dashboard_account_deletion", user_id=OWNER,
                      email="another-person@example.test")
    with pytest.raises(DBAPIError):
        with runtime_engine.begin() as connection:
            connection.execute(text("SET LOCAL ROLE investment_runtime"))
            connection.execute(text("SELECT set_config('app.user_id',:user,true)"), {"user": str(OWNER)})
            connection.execute(text("DELETE FROM public.financial_events WHERE owner_id=:owner"), {"owner": OWNER})

    assert _runtime_call(runtime_engine, OWNER, "begin_dashboard_account_deletion", user_id=OWNER,
                         email=OWNER_EMAIL) == "requested"
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT status FROM public.account_members WHERE user_id=:owner"), {"owner": OWNER}) == "revoked"

    # Inject a failure after earlier DELETE statements run. PostgreSQL must roll back
    # the entire purge phase, retain the resumable job, and preserve append-only triggers.
    with engine.begin() as connection:
        connection.execute(text("""CREATE FUNCTION public.test_abort_account_delete() RETURNS trigger
          LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected disposable failure'; END $$"""))
        connection.execute(text("CREATE TRIGGER test_abort_account_delete BEFORE DELETE ON public.financial_events FOR EACH ROW EXECUTE FUNCTION public.test_abort_account_delete()"))
    with pytest.raises(DBAPIError):
        _runtime_call(runtime_engine, OWNER, "purge_dashboard_account_data", user_id=OWNER)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT state FROM public.account_deletion_jobs WHERE user_id=:owner"), {"owner": OWNER}) == "requested"
        assert connection.scalar(text("SELECT count(*) FROM public.operations WHERE owner_id=:owner"), {"owner": OWNER}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.fixed_income_investments WHERE owner_id=:owner"), {"owner": OWNER}) == 2
        assert connection.scalar(text("SELECT count(*) FROM public.financial_events WHERE owner_id=:owner"), {"owner": OWNER}) == 1
    with engine.begin() as connection:
        connection.execute(text("DROP TRIGGER test_abort_account_delete ON public.financial_events"))
        connection.execute(text("DROP FUNCTION public.test_abort_account_delete()"))

    assert _runtime_call(runtime_engine, OWNER, "purge_dashboard_account_data", user_id=OWNER) == "financial_data_deleted"
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM public.account_members WHERE user_id=:owner"), {"owner": OWNER}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.account_members WHERE user_id=:other"), {"other": OTHER}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.account_invitations WHERE email=:email OR accepted_user_id=:owner OR invited_by=:owner"), {"email": OWNER_EMAIL, "owner": OWNER}) == 0
        assert connection.scalar(text("SELECT count(*) FROM public.account_invitation_send_attempts WHERE invitation_id='77777777-7777-4777-8777-000000000001'")) == 0
        for table in ("operations", "fixed_income_investments", "fixed_income_lots", "fixed_income_movements",
                      "fixed_income_observations", "fixed_income_investment_archives", "fixed_income_application_revisions",
                      "financial_events", "financial_event_revisions", "portfolio_valuation_observations", "account_fixture_loads"):
            assert connection.scalar(text(f"SELECT count(*) FROM public.{table} WHERE owner_id=:owner" if table != "account_fixture_loads" else "SELECT count(*) FROM public.account_fixture_loads WHERE user_id=:owner"), {"owner": OWNER}) == 0, table
        assert connection.scalar(text("SELECT count(*) FROM public.operations WHERE owner_id=:other"), {"other": OTHER}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.financial_events WHERE owner_id=:other"), {"other": OTHER}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.portfolio_valuation_observations WHERE owner_id=:other"), {"other": OTHER}) == 1

    assert _runtime_call(runtime_engine, OWNER, "mark_dashboard_auth_identity_deleted", user_id=OWNER) == "auth_identity_deleted"
    assert _runtime_call(runtime_engine, OWNER, "finish_dashboard_account_deletion", user_id=OWNER) is True
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM public.account_members WHERE user_id=:owner"), {"owner": OWNER}) == 0
        assert connection.scalar(text("SELECT count(*) FROM public.account_members WHERE user_id=:other"), {"other": OTHER}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.account_deletion_jobs WHERE user_id=:owner"), {"owner": OWNER}) == 0
        assert connection.scalar(text("SELECT count(*) FROM public.account_deletion_audit WHERE event_code='completed'")) == 1
        assert connection.scalar(text("SELECT has_table_privilege('investment_deletion_executor','public.operations','DELETE')")) is True
        assert connection.scalar(text("SELECT has_table_privilege('investment_runtime','public.financial_events','DELETE')")) is False
        assert connection.scalar(text("SELECT has_table_privilege('investment_runtime','public.account_members','DELETE')")) is False
        assert connection.scalar(text("SELECT has_function_privilege('investment_runtime','public.purge_dashboard_account_data(uuid)','EXECUTE')")) is True
        executor = connection.execute(text("SELECT rolcanlogin,rolsuper,rolbypassrls,rolcreaterole FROM pg_roles WHERE rolname='investment_deletion_executor'")).one()
        assert executor == (False, False, False, False)
        assert connection.scalar(text("SELECT count(*) FROM pg_auth_members WHERE roleid='investment_deletion_executor'::regrole OR member='investment_deletion_executor'::regrole")) == 0
        assert connection.scalar(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.account_deletion_jobs'::regclass")) is True
        assert connection.scalar(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.account_deletion_audit'::regclass")) is True
