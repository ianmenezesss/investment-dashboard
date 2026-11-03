"""Real separate SQL logins exercise the rebuilt access trust boundary."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from pydantic import SecretStr

from app.database import settings


def upgrade_access_as_non_superuser(engine):
    """Exercise the new migrations under a real owning DDL login and FORCE RLS."""
    role = "investment_access_migration_ddl"
    password = uuid4().hex + uuid4().hex
    existing = ("account_members", "account_invitations", "account_access_requests",
                "account_invitation_send_attempts", "alembic_version")
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        original_owners = {table: connection.scalar(text(
            "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid=CAST(:table AS regclass)"),
            {"table": f"public.{table}"}) for table in existing}
        connection.execute(text(f"CREATE ROLE {role} LOGIN CREATEROLE NOINHERIT NOSUPERUSER NOCREATEDB NOBYPASSRLS PASSWORD '{password}'"))
        connection.execute(text(f"GRANT USAGE, CREATE ON SCHEMA public TO {role} WITH GRANT OPTION"))
        connection.execute(text(f"GRANT investment_deletion_executor TO {role} WITH ADMIN TRUE, INHERIT FALSE, SET FALSE"))
        for table in existing:
            connection.execute(text(f"ALTER TABLE public.{table} OWNER TO {role}"))
    previous = settings.migration_database_url
    migration_url = engine.url.set(username=role, password=password).render_as_string(hide_password=False)
    probe = create_engine(migration_url, hide_parameters=True)
    try:
        with probe.connect() as connection:
            assert connection.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=session_user")) is False
        settings.migration_database_url = SecretStr(migration_url)
        command.upgrade(Config("alembic.ini"), "head")
        with probe.begin() as connection:
            # Future administrator maintenance must also work with FORCE RLS.
            row_id = uuid4()
            connection.execute(text("INSERT INTO account_access_administrators(user_id) VALUES(:id)"), {"id": row_id})
            assert connection.scalar(text("SELECT count(*) FROM account_access_administrators WHERE user_id=:id"), {"id": row_id}) == 1
            connection.execute(text("DELETE FROM account_access_administrators WHERE user_id=:id"), {"id": row_id})
    finally:
        settings.migration_database_url = previous
        probe.dispose()
        with engine.begin() as connection:
            for table, owner in original_owners.items():
                connection.execute(text(f"ALTER TABLE public.{table} OWNER TO {quote(owner)}"))
            for table in ("account_access_administrators", "account_access_audit"):
                if connection.scalar(text("SELECT to_regclass(:table)"), {"table": "public." + table}):
                    connection.execute(text(f"ALTER TABLE public.{table} OWNER TO {quote(original_owners['account_members'])}"))
            if connection.scalar(text("SELECT to_regclass('public.account_access_administrators')")):
                connection.execute(text(f"ALTER POLICY access_administrator_owner_maintenance ON public.account_access_administrators TO {quote(original_owners['account_members'])}"))
            connection.execute(text(f"REVOKE USAGE, CREATE ON SCHEMA public FROM {role} CASCADE"))
            connection.execute(text(f"REVOKE investment_deletion_executor FROM {role} CASCADE"))
            if connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='investment_access_admin')")):
                connection.execute(text(f"REVOKE investment_access_admin FROM {role} CASCADE"))
            connection.execute(text(f"DROP ROLE {role}"))


def verify_rebuilt_access_postgres(engine, runtime_engine, monkeypatch):
    admin = UUID("17171717-1717-4717-8717-171717171717")
    protected_admin = UUID("17171717-1717-4717-8717-171717171718")
    legacy = UUID("17171717-1717-4717-8717-171717171719")
    trial_user = UUID("17171717-1717-4717-8717-171717171720")
    saga_invite, saga_request, empty_request = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO public.account_members(user_id,email,status)
          VALUES (:admin,'new-admin@example.test','active'),(:protected,'protected-admin@example.test','active'),
                 (:legacy,'legacy-boundary@example.test','active'),(:trial,'trial-boundary@example.test','revoked')"""),
          {"admin": admin, "protected": protected_admin, "legacy": legacy, "trial": trial_user})
        connection.execute(text("""INSERT INTO public.account_invitations(id,email,invited_by,created_at,expires_at,access_duration_days)
          VALUES(:id,'recovered-saga@example.test',:admin,now(),now()+interval '7 days',7)"""),
          {"id": saga_invite, "admin": admin})
        connection.execute(text("""INSERT INTO public.account_access_requests(id,email,ip_hash,status,invitation_id,processing_at)
          VALUES(:linked,'recovered-saga@example.test',:ip,'approving',:invite,now()),
                (:empty,'empty-saga@example.test',:ip,'approving',NULL,now())"""),
          {"linked": saga_request, "empty": empty_request, "ip": "7"*64, "invite": saga_invite})
    monkeypatch.setattr(settings, "invitation_admin_ids", [admin, protected_admin])
    upgrade_access_as_non_superuser(engine)
    from assistant_quota_postgres import verify_assistant_request_quotas
    verify_assistant_request_quotas(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "018"
        assert connection.execute(text("SELECT status,invitation_id,reviewed_by,processing_at FROM account_access_requests WHERE id=:id"),
                                  {"id": saga_request}).one() == ("approved", saga_invite, admin, None)
        assert connection.execute(text("SELECT status,invitation_id,processing_at FROM account_access_requests WHERE id=:id"),
                                  {"id": empty_request}).one() == ("pending", None, None)

    # A UUID and arbitrary custom GUCs no longer grant administrative power.
    with runtime_engine.begin() as connection:
        connection.execute(text("SELECT set_config('app.admin_id',:admin,true)"), {"admin": str(admin)})
        assert connection.scalar(text("SELECT count(*) FROM public.account_access_requests")) == 0
        assert connection.scalar(text("SELECT count(*) FROM public.account_members")) == 0
        assert connection.scalar(text("SELECT count(*) FROM public.account_invitations")) == 0
        assert not connection.scalar(text("SELECT pg_has_role(current_user,'investment_access_admin','MEMBER')"))
    for statement in (
        "SELECT public.revoke_dashboard_account(:user_id,:admin)",
        "SELECT public.reserve_dashboard_reactivation(:user_id,:admin,:invite,'trial-boundary@example.test')",
        "SELECT * FROM public.account_access_administrators",
        "SELECT * FROM public.account_access_audit",
        "SELECT * FROM public.account_invitation_send_attempts",
        "SET LOCAL ROLE investment_access_admin",
        "SET LOCAL ROLE investment_deletion_executor",
        "INSERT INTO public.account_invitations(id,email,invited_by,created_at,expires_at) VALUES(:invite,'spoofed@example.test',:admin,now(),now()+interval '7 days')",
        "UPDATE public.account_members SET status='revoked' WHERE user_id=:user_id",
    ):
        with pytest.raises(DBAPIError):
            with runtime_engine.begin() as connection:
                connection.execute(text("SELECT set_config('app.admin_id',:admin,true)"), {"admin": str(admin)})
                connection.execute(text(statement), {"admin": admin, "user_id": trial_user, "invite": uuid4()})

    login = "investment_access_operator"
    password = "fictional-access-boundary-test-password"
    with engine.begin() as connection:
        connection.execute(text(f"CREATE ROLE {login} LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION PASSWORD '{password}'"))
        connection.execute(text(f"GRANT investment_access_admin TO {login} WITH INHERIT TRUE, SET TRUE"))
    admin_engine = create_engine(engine.url.set(username=login, password=password), hide_parameters=True)
    try:
        with admin_engine.begin() as connection:
            assert connection.scalar(text("SELECT session_user")) == login
            assert connection.scalar(text("SELECT public.dashboard_admin_authorized()")) is False
            connection.execute(text("SELECT set_config('app.admin_id',:admin,true)"), {"admin": str(legacy)})
            assert connection.scalar(text("SELECT public.dashboard_admin_authorized()")) is False
            connection.execute(text("SELECT set_config('app.admin_id',:admin,true)"), {"admin": str(admin)})
            assert connection.scalar(text("SELECT public.dashboard_admin_authorized()")) is True
            assert connection.scalar(text("SELECT count(*) FROM account_access_requests WHERE id=:id"), {"id": saga_request}) == 1
            assert connection.scalar(text("SELECT public.revoke_dashboard_account(:user_id,:admin)"), {"user_id": protected_admin, "admin": admin}) is False
            assert connection.scalar(text("SELECT public.revoke_dashboard_account(:user_id,:admin)"), {"user_id": admin, "admin": admin}) is False
            assert connection.scalar(text("SELECT public.revoke_dashboard_account(:user_id,:admin)"), {"user_id": legacy, "admin": admin}) is True
            assert connection.scalar(text("SELECT public.revoke_dashboard_account(:user_id,:admin)"), {"user_id": legacy, "admin": admin}) is True
            assert connection.scalar(text("SELECT count(*) FROM account_access_audit WHERE subject_user_id=:id AND event_code='membership_revoked'"), {"id": legacy}) == 1
        for statement in ("SELECT * FROM public.operations", "SELECT * FROM public.financial_events",
                          "SET LOCAL ROLE investment_runtime", "SET LOCAL ROLE investment_deletion_executor",
                          "UPDATE account_members SET status='active' WHERE user_id=:user_id",
                          "DELETE FROM account_access_audit"):
            with pytest.raises(DBAPIError):
                with admin_engine.begin() as connection:
                    connection.execute(text("SELECT set_config('app.admin_id',:admin,true)"), {"admin": str(admin)})
                    connection.execute(text(statement), {"user_id": legacy})
        barrier = Barrier(2)
        def reserve(invitation_id):
            with admin_engine.begin() as connection:
                connection.execute(text("SELECT set_config('app.admin_id',:admin,true)"), {"admin": str(admin)})
                barrier.wait(timeout=10)
                return connection.scalar(text("SELECT public.reserve_dashboard_reactivation(:user_id,:admin,:invite,'trial-boundary@example.test')"),
                                         {"user_id": trial_user, "admin": admin, "invite": invitation_id})
        candidates = [uuid4(), uuid4()]
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(reserve, candidates))
        assert sorted(outcomes) == [False, True]
        invitation_id = candidates[outcomes.index(True)]
        with engine.begin() as connection:
            connection.execute(text("UPDATE account_invitations SET claim_user_id=:user_id,claim_token_hash=:hash,claim_expires_at=now()+interval '10 minutes' WHERE id=:id"),
                               {"user_id": trial_user, "hash": "8"*64, "id": invitation_id})
        with runtime_engine.begin() as connection:
            connection.execute(text("""SELECT set_config('app.user_id',:user_id,true),
              set_config('app.user_email','trial-boundary@example.test',true),
              set_config('app.invitation_id',:invite,true),set_config('app.claim_user_id',:user_id,true),
              set_config('app.claim_token_hash',:hash,true)"""),
              {"user_id": str(trial_user), "invite": str(invitation_id), "hash": "8"*64})
            assert connection.scalar(text("SELECT public.accept_dashboard_invitation(:user_id,'trial-boundary@example.test')"), {"user_id": trial_user}) is True
            assert connection.scalar(text("SELECT access_expires_at-activated_at=interval '168 hours' FROM account_members WHERE user_id=:user_id"), {"user_id": trial_user}) is True
            assert connection.scalar(text("SELECT public.accept_dashboard_invitation(:user_id,'trial-boundary@example.test')"), {"user_id": trial_user}) is False
            # Distributed assistant leases and configurable limits use the real
            # restricted runtime identity without broad member UPDATE grants.
            request_id = uuid4()
            assert connection.scalar(text("SELECT public.reserve_dashboard_assistant_request(:user_id,:request,30,500,0)"), {"user_id": trial_user, "request": request_id}) == "allowed"
            assert connection.scalar(text("SELECT public.reserve_dashboard_assistant_request(:user_id,:request,30,500,0)"), {"user_id": trial_user, "request": uuid4()}) == "busy"
            assert connection.scalar(text("SELECT public.release_dashboard_assistant_request(:user_id,:request)"), {"user_id": trial_user, "request": request_id}) is True
        with admin_engine.begin() as connection:
            connection.execute(text("SELECT set_config('app.admin_id',:admin,true)"), {"admin": str(admin)})
            assert connection.scalar(text("SELECT public.revoke_dashboard_account(:user_id,:admin)"), {"user_id": trial_user, "admin": admin}) is True
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT status FROM account_members WHERE user_id=:id"), {"id": trial_user}) == "revoked"
            assert connection.scalar(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.account_access_audit'::regclass"))
            assert not connection.scalar(text("SELECT has_schema_privilege('investment_deletion_executor','public','CREATE')"))
            assert not connection.scalar(text("SELECT has_table_privilege('investment_access_admin','public.account_members','UPDATE')"))
    finally:
        admin_engine.dispose()
        # Keep the configured synthetic role so pg_dump/restore can compare its
        # object privileges; the disposable server is removed by the test runner.
