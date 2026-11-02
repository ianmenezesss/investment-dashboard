"""Safe self-service deletion and explicit fictional fixture load provenance."""
from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"

APPEND_ONLY_TABLES = (
    "fixed_income_investments",
    "fixed_income_lots",
    "fixed_income_movements",
    "fixed_income_observations",
    "fixed_income_investment_archives",
    "fixed_income_application_revisions",
    "financial_events",
    "financial_event_revisions",
    "portfolio_valuation_observations",
)


def upgrade():
    op.execute("""DO $$ DECLARE role_id oid; BEGIN
      SELECT oid INTO role_id FROM pg_roles WHERE rolname='investment_deletion_executor';
      IF role_id IS NULL THEN
        CREATE ROLE investment_deletion_executor NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
          NOINHERIT NOREPLICATION NOBYPASSRLS;
      ELSE
        IF EXISTS (SELECT 1 FROM pg_roles WHERE oid=role_id AND
          (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit OR rolreplication OR rolbypassrls))
          OR EXISTS (SELECT 1 FROM pg_auth_members WHERE roleid=role_id OR member=role_id) THEN
          RAISE EXCEPTION 'investment_deletion_executor exists with unsafe attributes or memberships';
        END IF;
      END IF;
    END $$""")

    op.create_table(
        "account_deletion_jobs",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("operation_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("state IN ('requested','financial_data_deleted','auth_identity_deleted')", name="account_deletion_state"),
        sa.CheckConstraint("email = lower(trim(email)) AND length(email) BETWEEN 3 AND 320", name="account_deletion_email"),
    )
    op.create_table(
        "account_deletion_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("event_code", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("event_code IN ('requested','financial_data_deleted','auth_identity_deleted','completed')", name="account_deletion_audit_event"),
    )
    op.create_index("ix_account_deletion_audit_operation", "account_deletion_audit", ["operation_id", "id"])
    op.create_table(
        "account_fixture_loads",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("fixture_id", sa.String(80), nullable=False),
        sa.Column("fixture_sha256", sa.String(64), nullable=False),
        sa.Column("loaded_by", sa.Uuid(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("length(fixture_sha256)=64", name="account_fixture_sha256"),
        sa.CheckConstraint("fixture_id='v2-demo-scenario'", name="account_fixture_id"),
    )

    for table in ("account_deletion_jobs", "account_deletion_audit", "account_fixture_loads"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC, anon, authenticated, service_role")
    op.execute("CREATE POLICY deletion_job_executor ON public.account_deletion_jobs FOR ALL USING (current_user='investment_deletion_executor' AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid) WITH CHECK (current_user='investment_deletion_executor' AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid)")
    op.execute("CREATE POLICY deletion_audit_executor ON public.account_deletion_audit FOR ALL USING (current_user='investment_deletion_executor') WITH CHECK (current_user='investment_deletion_executor')")
    op.execute("CREATE POLICY fixture_owner ON public.account_fixture_loads FOR ALL USING (user_id=NULLIF(current_setting('app.user_id',true),'')::uuid) WITH CHECK (user_id=NULLIF(current_setting('app.user_id',true),'')::uuid)")
    op.execute("CREATE POLICY fixture_delete_executor ON public.account_fixture_loads FOR DELETE USING (current_user='investment_deletion_executor' AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid)")

    # The executor can delete only through SECURITY DEFINER functions owned by this
    # NOLOGIN role. Runtime never receives membership, DELETE grants, or TRUNCATE.
    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO investment_deletion_executor")
    op.execute("GRANT SELECT, DELETE ON TABLE public.operations, public.fixed_income_investments, public.fixed_income_lots, public.fixed_income_movements, public.fixed_income_observations, public.fixed_income_investment_archives, public.fixed_income_application_revisions, public.financial_events, public.financial_event_revisions, public.portfolio_valuation_observations TO investment_deletion_executor")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.account_members, public.account_invitations, public.account_deletion_jobs, public.account_deletion_audit, public.account_fixture_loads TO investment_deletion_executor")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE public.account_deletion_audit_id_seq TO investment_deletion_executor")
    op.execute("GRANT SELECT, INSERT ON TABLE public.account_fixture_loads TO investment_runtime")

    op.execute("""CREATE OR REPLACE FUNCTION public.fi_reject_mutation() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
      BEGIN
        IF TG_OP='DELETE' AND current_user='investment_deletion_executor' THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'Fixed-income ledger is append-only' USING ERRCODE='23514';
      END; $$""")
    op.execute("""CREATE OR REPLACE FUNCTION public.financial_event_reject_mutation() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
      BEGIN
        IF TG_OP='DELETE' AND current_user='investment_deletion_executor' THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'Financial events and revisions are append-only' USING ERRCODE='23514';
      END; $$""")

    op.execute("CREATE POLICY member_delete_executor ON public.account_members FOR DELETE USING (current_user='investment_deletion_executor' AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid)")
    op.execute("CREATE POLICY invitation_delete_executor ON public.account_invitations FOR DELETE USING (current_user='investment_deletion_executor' AND (accepted_user_id=NULLIF(current_setting('app.user_id',true),'')::uuid OR invited_by=NULLIF(current_setting('app.user_id',true),'')::uuid OR email=lower(NULLIF(current_setting('app.user_email',true),''))))")

    op.execute("""CREATE FUNCTION public.dashboard_account_deletion_state(p_user_id uuid)
      RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=on AS $$
      DECLARE result text;
      BEGIN
        IF NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM p_user_id THEN
          RAISE EXCEPTION 'Account identity mismatch' USING ERRCODE='42501';
        END IF;
        SELECT state INTO result FROM public.account_deletion_jobs WHERE user_id=p_user_id;
        RETURN result;
      END $$""")
    op.execute("""CREATE FUNCTION public.begin_dashboard_account_deletion(p_user_id uuid, p_email text)
      RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=on AS $$
      DECLARE existing_state text; member_email text; member_status text; op_id uuid;
      BEGIN
        IF NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM p_user_id
          OR lower(trim(NULLIF(current_setting('app.user_email',true),''))) IS DISTINCT FROM lower(trim(p_email)) THEN
          RAISE EXCEPTION 'Account identity mismatch' USING ERRCODE='42501';
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('dashboard-delete:' || p_user_id::text,0));
        SELECT state INTO existing_state FROM public.account_deletion_jobs WHERE user_id=p_user_id FOR UPDATE;
        IF existing_state IS NOT NULL THEN RETURN existing_state; END IF;
        SELECT email,status INTO member_email,member_status FROM public.account_members WHERE user_id=p_user_id FOR UPDATE;
        IF member_status IS DISTINCT FROM 'active' OR lower(trim(coalesce(member_email,''))) IS DISTINCT FROM lower(trim(p_email)) THEN
          RAISE EXCEPTION 'Active account required for deletion request' USING ERRCODE='42501';
        END IF;
        op_id := gen_random_uuid();
        INSERT INTO public.account_deletion_jobs(user_id,operation_id,email,state)
          VALUES(p_user_id,op_id,lower(trim(p_email)),'requested');
        UPDATE public.account_members SET status='revoked' WHERE user_id=p_user_id;
        INSERT INTO public.account_deletion_audit(operation_id,event_code) VALUES(op_id,'requested');
        RETURN 'requested';
      END $$""")
    op.execute("""CREATE FUNCTION public.purge_dashboard_account_data(p_user_id uuid)
      RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=on AS $$
      DECLARE job public.account_deletion_jobs%ROWTYPE;
      BEGIN
        IF NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM p_user_id THEN
          RAISE EXCEPTION 'Account identity mismatch' USING ERRCODE='42501';
        END IF;
        SELECT * INTO job FROM public.account_deletion_jobs WHERE user_id=p_user_id FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'Deletion request not found' USING ERRCODE='P0002'; END IF;
        IF job.state IN ('financial_data_deleted','auth_identity_deleted') THEN RETURN job.state; END IF;
        PERFORM set_config('app.user_email',job.email,true);

        DELETE FROM public.financial_event_revisions WHERE owner_id=p_user_id;
        DELETE FROM public.financial_events WHERE owner_id=p_user_id;
        DELETE FROM public.portfolio_valuation_observations WHERE owner_id=p_user_id;
        DELETE FROM public.fixed_income_application_revisions WHERE owner_id=p_user_id;
        DELETE FROM public.fixed_income_observations WHERE owner_id=p_user_id;
        DELETE FROM public.fixed_income_investment_archives WHERE owner_id=p_user_id;
        DELETE FROM public.fixed_income_movements WHERE owner_id=p_user_id;
        DELETE FROM public.fixed_income_lots WHERE owner_id=p_user_id;
        DELETE FROM public.fixed_income_investments WHERE owner_id=p_user_id;
        DELETE FROM public.operations WHERE owner_id=p_user_id;
        DELETE FROM public.account_invitations WHERE accepted_user_id=p_user_id OR invited_by=p_user_id OR email=job.email;
        DELETE FROM public.account_fixture_loads WHERE user_id=p_user_id;

        UPDATE public.account_deletion_jobs SET state='financial_data_deleted',updated_at=clock_timestamp() WHERE user_id=p_user_id;
        INSERT INTO public.account_deletion_audit(operation_id,event_code) VALUES(job.operation_id,'financial_data_deleted');
        RETURN 'financial_data_deleted';
      END $$""")
    op.execute("""CREATE FUNCTION public.mark_dashboard_auth_identity_deleted(p_user_id uuid)
      RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=on AS $$
      DECLARE job public.account_deletion_jobs%ROWTYPE;
      BEGIN
        IF NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM p_user_id THEN
          RAISE EXCEPTION 'Account identity mismatch' USING ERRCODE='42501';
        END IF;
        SELECT * INTO job FROM public.account_deletion_jobs WHERE user_id=p_user_id FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'Deletion request not found' USING ERRCODE='P0002'; END IF;
        IF job.state='financial_data_deleted' THEN
          UPDATE public.account_deletion_jobs SET state='auth_identity_deleted',updated_at=clock_timestamp() WHERE user_id=p_user_id;
          INSERT INTO public.account_deletion_audit(operation_id,event_code) VALUES(job.operation_id,'auth_identity_deleted');
          RETURN 'auth_identity_deleted';
        END IF;
        RETURN job.state;
      END $$""")
    op.execute("""CREATE FUNCTION public.finish_dashboard_account_deletion(p_user_id uuid)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public SET row_security=on AS $$
      DECLARE job public.account_deletion_jobs%ROWTYPE;
      BEGIN
        IF NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM p_user_id THEN
          RAISE EXCEPTION 'Account identity mismatch' USING ERRCODE='42501';
        END IF;
        SELECT * INTO job FROM public.account_deletion_jobs WHERE user_id=p_user_id FOR UPDATE;
        IF NOT FOUND OR job.state<>'auth_identity_deleted' THEN RETURN false; END IF;
        PERFORM set_config('app.user_email',job.email,true);
        DELETE FROM public.account_invitations WHERE accepted_user_id=p_user_id OR invited_by=p_user_id OR email=job.email;
        DELETE FROM public.account_members WHERE user_id=p_user_id;
        DELETE FROM public.account_deletion_jobs WHERE user_id=p_user_id;
        INSERT INTO public.account_deletion_audit(operation_id,event_code) VALUES(job.operation_id,'completed');
        RETURN true;
      END $$""")

    for signature in (
        "dashboard_account_deletion_state(uuid)",
        "begin_dashboard_account_deletion(uuid,text)",
        "purge_dashboard_account_data(uuid)",
        "mark_dashboard_auth_identity_deleted(uuid)",
        "finish_dashboard_account_deletion(uuid)",
    ):
        op.execute(f"ALTER FUNCTION public.{signature} OWNER TO investment_deletion_executor")
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC, anon, authenticated, service_role")
        op.execute(f"GRANT EXECUTE ON FUNCTION public.{signature} TO investment_runtime")
    op.execute("REVOKE CREATE ON SCHEMA public FROM investment_deletion_executor")

    for table in APPEND_ONLY_TABLES:
        op.execute(f"REVOKE DELETE, TRUNCATE ON TABLE public.{table} FROM investment_runtime")
    op.execute("""DO $$ BEGIN
      IF has_table_privilege('investment_runtime','public.fixed_income_investments','DELETE')
        OR has_table_privilege('investment_runtime','public.financial_events','DELETE')
        OR has_table_privilege('investment_runtime','public.account_deletion_jobs','SELECT')
        OR has_table_privilege('investment_runtime','public.account_deletion_audit','SELECT')
        OR has_table_privilege('investment_runtime','public.account_members','DELETE')
        OR has_table_privilege('investment_runtime','public.account_invitations','DELETE') THEN
        RAISE EXCEPTION 'Runtime account-deletion privileges are broader than intended';
      END IF;
      IF NOT (SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.account_deletion_jobs'::regclass)
        OR NOT (SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.account_deletion_audit'::regclass)
        OR NOT (SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.account_fixture_loads'::regclass)
        OR (SELECT rolsuper OR rolcanlogin OR rolbypassrls OR rolcreaterole OR rolcreatedb FROM pg_roles WHERE rolname='investment_deletion_executor')
        OR EXISTS (SELECT 1 FROM pg_auth_members WHERE roleid='investment_deletion_executor'::regrole OR member='investment_deletion_executor'::regrole) THEN
        RAISE EXCEPTION 'Account-deletion executor or RLS configuration is unsafe';
      END IF;
      IF has_schema_privilege('investment_deletion_executor','public','CREATE') THEN
        RAISE EXCEPTION 'Account-deletion executor must not retain CREATE on public';
      END IF;
    END $$""")


def downgrade():
    raise RuntimeError("Forward-only deletion and fixture controls; preserve audit history and use a corrective migration")
