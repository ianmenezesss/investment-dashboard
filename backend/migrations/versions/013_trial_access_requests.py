"""Admin-reviewed trial access requests and seven-day memberships."""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"


def upgrade():
    op.add_column("account_members", sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("account_invitations", sa.Column("access_duration_days", sa.SmallInteger(), nullable=True))
    op.create_check_constraint("account_invite_access_duration", "account_invitations",
                               "access_duration_days IS NULL OR access_duration_days = 7")
    op.create_table(
        "account_access_requests",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("invitation_id", sa.Uuid(), nullable=True),
        sa.Column("processing_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("email = lower(trim(email)) AND length(email) BETWEEN 3 AND 320", name="account_access_request_email"),
        sa.CheckConstraint("ip_hash ~ '^[0-9a-f]{64}$'", name="account_access_request_ip_hash"),
        sa.CheckConstraint("status IN ('pending','approving','approved','rejected')", name="account_access_request_status"),
    )
    op.create_index("ix_account_access_requests_admin", "account_access_requests", ["status", "requested_at"])
    op.create_index("uq_account_access_request_email_open", "account_access_requests", ["email"], unique=True,
                    postgresql_where=sa.text("status IN ('pending','approving','approved')"))
    op.create_table(
        "account_access_request_limits",
        sa.Column("scope_key", sa.String(72), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("scope_key = 'global' OR scope_key ~ '^ip:[0-9a-f]{64}$'", name="account_access_request_limit_scope"),
        sa.CheckConstraint("attempts >= 0", name="account_access_request_limit_attempts"),
    )
    op.execute("ALTER TABLE public.account_access_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.account_access_requests FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.account_access_request_limits ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.account_access_request_limits FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON public.account_access_requests FROM PUBLIC, anon, authenticated, service_role")
    op.execute("REVOKE ALL ON public.account_access_request_limits FROM PUBLIC, anon, authenticated, service_role")
    op.execute("CREATE POLICY access_request_read_admin ON public.account_access_requests FOR SELECT USING (current_user='investment_runtime' AND NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL)")
    op.execute("CREATE POLICY access_request_insert_endpoint ON public.account_access_requests FOR INSERT WITH CHECK (current_user='investment_runtime' AND current_setting('app.access_request_submit',true)='true')")
    op.execute("CREATE POLICY access_request_update_admin ON public.account_access_requests FOR UPDATE USING (current_user='investment_runtime' AND NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL) WITH CHECK (current_user='investment_runtime' AND NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL)")
    op.execute("GRANT SELECT, INSERT, UPDATE ON public.account_access_requests TO investment_runtime")
    op.execute("CREATE POLICY access_request_limit_read_endpoint ON public.account_access_request_limits FOR SELECT USING (current_user='investment_runtime' AND current_setting('app.access_request_submit',true)='true')")
    op.execute("CREATE POLICY access_request_limit_insert_endpoint ON public.account_access_request_limits FOR INSERT WITH CHECK (current_user='investment_runtime' AND current_setting('app.access_request_submit',true)='true')")
    op.execute("CREATE POLICY access_request_limit_update_endpoint ON public.account_access_request_limits FOR UPDATE USING (current_user='investment_runtime' AND current_setting('app.access_request_submit',true)='true') WITH CHECK (current_user='investment_runtime' AND current_setting('app.access_request_submit',true)='true')")
    op.execute("GRANT SELECT, INSERT, UPDATE ON public.account_access_request_limits TO investment_runtime")
    op.execute("""CREATE OR REPLACE FUNCTION public.submit_dashboard_trial_access_request(p_email text, p_ip_hash text)
      RETURNS boolean LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
      DECLARE global_attempts bigint; ip_attempts bigint; v_now timestamptz := clock_timestamp();
      BEGIN
        IF current_user <> 'investment_runtime'
          OR current_setting('app.access_request_submit',true) IS DISTINCT FROM 'true'
          OR p_email IS NULL OR p_email IS DISTINCT FROM lower(trim(p_email))
          OR length(p_email) NOT BETWEEN 3 AND 320
          OR p_email !~ '^[^[:space:]@<>]+@[^[:space:]@<>]+\\.[^[:space:]@<>]+$'
          OR p_ip_hash IS NULL
          OR p_ip_hash !~ '^[0-9a-f]{64}$' THEN
          RAISE EXCEPTION 'Invalid public access request context' USING ERRCODE='42501';
        END IF;
        -- Counters include duplicate and rejected submissions, across all instances.
        PERFORM pg_advisory_xact_lock(hashtextextended('trial-access-global',0));
        INSERT INTO public.account_access_request_limits(scope_key,window_started_at,attempts)
          VALUES('global',v_now,1)
          ON CONFLICT(scope_key) DO UPDATE SET
            attempts=CASE WHEN account_access_request_limits.window_started_at <= v_now-interval '24 hours' THEN 1 ELSE account_access_request_limits.attempts+1 END,
            window_started_at=CASE WHEN account_access_request_limits.window_started_at <= v_now-interval '24 hours' THEN v_now ELSE account_access_request_limits.window_started_at END
          RETURNING attempts INTO global_attempts;
        IF global_attempts > 100 THEN RETURN false; END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('trial-access-ip:' || p_ip_hash,0));
        INSERT INTO public.account_access_request_limits(scope_key,window_started_at,attempts)
          VALUES('ip:' || p_ip_hash,v_now,1)
          ON CONFLICT(scope_key) DO UPDATE SET
            attempts=CASE WHEN account_access_request_limits.window_started_at <= v_now-interval '24 hours' THEN 1 ELSE account_access_request_limits.attempts+1 END,
            window_started_at=CASE WHEN account_access_request_limits.window_started_at <= v_now-interval '24 hours' THEN v_now ELSE account_access_request_limits.window_started_at END
          RETURNING attempts INTO ip_attempts;
        IF ip_attempts > 3 THEN RETURN false; END IF;
        BEGIN
          INSERT INTO public.account_access_requests(id,email,ip_hash,status)
            VALUES(gen_random_uuid(),p_email,p_ip_hash,'pending');
        EXCEPTION WHEN unique_violation THEN
          RETURN false;
        END;
        RETURN true;
      END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.submit_dashboard_trial_access_request(text,text) FROM PUBLIC, anon, authenticated, service_role")
    op.execute("GRANT EXECUTE ON FUNCTION public.submit_dashboard_trial_access_request(text,text) TO investment_runtime")
    op.execute("""CREATE OR REPLACE FUNCTION public.accept_dashboard_invitation(p_user_id uuid, p_email text)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
      DECLARE existing_status text; claimed_id uuid; duration_days smallint;
      BEGIN
        IF NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM p_user_id
          OR lower(NULLIF(current_setting('app.user_email',true),'')) IS DISTINCT FROM lower(trim(p_email)) THEN
          RETURN false;
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('dashboard-account-activation:' || p_user_id::text, 0));
        SELECT status INTO existing_status FROM public.account_members WHERE user_id=p_user_id;
        IF existing_status='active' THEN RETURN true; END IF;
        SELECT id,access_duration_days INTO claimed_id,duration_days FROM public.account_invitations
          WHERE email=lower(trim(p_email)) AND accepted_user_id IS NULL AND revoked_at IS NULL
            AND expires_at > now() FOR UPDATE;
        IF claimed_id IS NULL THEN RETURN false; END IF;
        UPDATE public.account_invitations SET accepted_user_id=p_user_id WHERE id=claimed_id;
        INSERT INTO public.account_members(user_id,email,status,access_expires_at)
          VALUES(p_user_id,lower(trim(p_email)),'active',
            CASE WHEN duration_days=7 THEN clock_timestamp()+interval '168 hours' ELSE NULL END)
          ON CONFLICT (user_id) DO UPDATE SET email=EXCLUDED.email,status='active',access_expires_at=EXCLUDED.access_expires_at;
        RETURN true;
      END $$""")
    op.execute("""DO $$ BEGIN
      IF NOT (SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.account_access_requests'::regclass)
        OR NOT (SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.account_access_request_limits'::regclass)
        OR has_table_privilege('investment_runtime','public.account_access_requests','DELETE')
        OR has_table_privilege('investment_runtime','public.account_access_requests','TRUNCATE')
        OR has_table_privilege('investment_runtime','public.account_access_request_limits','DELETE')
        OR has_table_privilege('investment_runtime','public.account_access_request_limits','TRUNCATE')
        OR has_table_privilege('anon','public.account_access_requests','SELECT')
        OR has_table_privilege('authenticated','public.account_access_requests','SELECT')
        OR has_table_privilege('service_role','public.account_access_requests','SELECT')
        OR has_table_privilege('anon','public.account_access_request_limits','SELECT')
        OR has_table_privilege('authenticated','public.account_access_request_limits','SELECT')
        OR has_table_privilege('service_role','public.account_access_request_limits','SELECT') THEN
        RAISE EXCEPTION 'Access request table permissions or RLS are unsafe';
      END IF;
    END $$""")


def downgrade():
    raise RuntimeError("Forward-only trial access lifecycle; preserve access decisions and invitation provenance")
