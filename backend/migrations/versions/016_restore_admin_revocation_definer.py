"""Restore the restricted SECURITY DEFINER boundary for admin revocation."""
from alembic import op

revision = "016"
down_revision = "015"


def upgrade():
    # The deletion executor is already a NOLOGIN/NOBYPASSRLS role with narrowly
    # scoped account table grants. Reuse it for these two administrative writes.
    # FORCE RLS stays enabled; existing admin policies require the backend-set
    # app.admin_id context and the functions independently match it to p_admin_id.
    op.execute("CREATE POLICY member_admin_executor_update ON public.account_members FOR UPDATE TO investment_deletion_executor USING (NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL) WITH CHECK (NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL)")

    # CREATE OR REPLACE in 015 omitted SECURITY DEFINER, which reset the
    # function to SECURITY INVOKER. Keep runtime table grants unchanged.
    op.execute("""CREATE OR REPLACE FUNCTION public.revoke_dashboard_account(p_user_id uuid, p_admin_id uuid)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
      DECLARE v_status text;
      BEGIN
        IF current_user <> 'investment_deletion_executor'
          OR (session_user <> 'investment_runtime' AND current_setting('role',true) <> 'investment_runtime')
          OR NULLIF(current_setting('app.admin_id',true),'')::uuid IS DISTINCT FROM p_admin_id
          OR p_user_id IS NULL OR p_admin_id IS NULL OR p_user_id = p_admin_id
        THEN
          RETURN false;
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('dashboard-account-revocation:' || p_user_id::text, 0));
        SELECT status INTO v_status FROM public.account_members WHERE user_id=p_user_id FOR UPDATE;
        IF NOT FOUND OR v_status <> 'active' THEN RETURN false; END IF;
        UPDATE public.account_invitations SET revoked_at=clock_timestamp()
          WHERE (accepted_user_id=p_user_id OR target_user_id=p_user_id)
            AND revoked_at IS NULL AND (accepted_user_id IS NOT NULL OR expires_at > clock_timestamp());
        UPDATE public.account_members SET status='revoked' WHERE user_id=p_user_id AND status='active';
        RETURN FOUND;
      END $$""")

    # Reserve the seven-day reactivation invitation and revoke expired pending
    # invitations atomically. The backend still verifies the administrator
    # allowlist and the target's confirmed Auth identity before calling this.
    op.execute("""CREATE OR REPLACE FUNCTION public.reserve_dashboard_reactivation(
        p_user_id uuid, p_admin_id uuid, p_invitation_id uuid, p_email text)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
      DECLARE v_status text; v_expiry timestamptz; v_now timestamptz;
      BEGIN
        IF current_user <> 'investment_deletion_executor'
          OR (session_user <> 'investment_runtime' AND current_setting('role',true) <> 'investment_runtime')
          OR NULLIF(current_setting('app.admin_id',true),'')::uuid IS DISTINCT FROM p_admin_id
          OR p_user_id IS NULL OR p_admin_id IS NULL OR p_invitation_id IS NULL
          OR p_user_id = p_admin_id OR p_email IS NULL
          OR p_email IS DISTINCT FROM lower(trim(p_email))
          OR length(p_email) NOT BETWEEN 3 AND 320 THEN
          RETURN false;
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('dashboard-invitations:' || p_admin_id::text, 0));
        PERFORM pg_advisory_xact_lock(hashtextextended('dashboard-reactivation:' || p_user_id::text, 0));
        v_now := clock_timestamp();
        SELECT status,access_expires_at INTO v_status,v_expiry
          FROM public.account_members WHERE user_id=p_user_id FOR UPDATE;
        IF NOT FOUND OR NOT (v_status='revoked' OR (v_expiry IS NOT NULL AND v_expiry <= v_now)) THEN
          RETURN false;
        END IF;
        IF EXISTS (SELECT 1 FROM public.account_invitations
          WHERE target_user_id=p_user_id AND accepted_user_id IS NULL
            AND revoked_at IS NULL AND expires_at > v_now) THEN RETURN false; END IF;
        IF (SELECT count(*) FROM public.account_invitations
              WHERE invited_by=p_admin_id AND created_at >= v_now-interval '1 day') >= 10
          OR (SELECT count(*) FROM public.account_invitations
              WHERE invited_by=p_admin_id AND revoked_at IS NULL
                AND accepted_user_id IS NULL AND expires_at > v_now) >= 10 THEN
          RETURN false;
        END IF;
        UPDATE public.account_invitations SET revoked_at=v_now
          WHERE email=p_email AND accepted_user_id IS NULL
            AND revoked_at IS NULL AND expires_at <= v_now;
        INSERT INTO public.account_invitations
          (id,email,invited_by,created_at,expires_at,access_duration_days,target_user_id)
          VALUES (p_invitation_id,p_email,p_admin_id,v_now,v_now+interval '7 days',7,p_user_id);
        RETURN true;
      END $$""")

    # Set the ACL while the migration role still owns both functions. After
    # ALTER OWNER, this role no longer has authority to REVOKE/GRANT EXECUTE.
    for signature in (
        "revoke_dashboard_account(uuid,uuid)",
        "reserve_dashboard_reactivation(uuid,uuid,uuid,text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC, anon, authenticated, service_role")
        op.execute(f"GRANT EXECUTE ON FUNCTION public.{signature} TO investment_runtime")

    # ALTER FUNCTION ... OWNER TO requires the new owner to have CREATE on the
    # containing schema, in addition to the migration role being able to SET
    # ROLE to that owner. Grant CREATE only for this transaction, as migration
    # 012 does, and remove it immediately after both ownership changes.
    op.execute("""DO $$ BEGIN
      IF current_setting('server_version_num')::integer >= 160000 THEN
        GRANT investment_deletion_executor TO CURRENT_USER WITH SET TRUE, INHERIT FALSE;
      ELSE
        GRANT investment_deletion_executor TO CURRENT_USER;
      END IF;
    END $$""")
    op.execute("GRANT CREATE ON SCHEMA public TO investment_deletion_executor")
    for signature in (
        "revoke_dashboard_account(uuid,uuid)",
        "reserve_dashboard_reactivation(uuid,uuid,uuid,text)",
    ):
        op.execute(f"ALTER FUNCTION public.{signature} OWNER TO investment_deletion_executor")
    op.execute("REVOKE CREATE ON SCHEMA public FROM investment_deletion_executor")
    # On PostgreSQL 16+, revoking the temporary membership can leave the
    # bootstrap ADMIN-only membership for the CREATEROLE role that created the
    # executor. Permit only that non-inheriting, non-SET administrative edge;
    # no runtime role may belong to the executor.
    op.execute("REVOKE investment_deletion_executor FROM CURRENT_USER")

    op.execute("""DO $$ BEGIN
      IF (SELECT prosecdef FROM pg_proc WHERE oid='public.revoke_dashboard_account(uuid,uuid)'::regprocedure) IS NOT TRUE
        OR (SELECT prosecdef FROM pg_proc WHERE oid='public.reserve_dashboard_reactivation(uuid,uuid,uuid,text)'::regprocedure) IS NOT TRUE
        OR (SELECT proconfig FROM pg_proc WHERE oid='public.revoke_dashboard_account(uuid,uuid)'::regprocedure)
             IS DISTINCT FROM ARRAY['search_path=pg_catalog, public']::text[]
        OR (SELECT proconfig FROM pg_proc WHERE oid='public.reserve_dashboard_reactivation(uuid,uuid,uuid,text)'::regprocedure)
             IS DISTINCT FROM ARRAY['search_path=pg_catalog, public']::text[]
        OR (SELECT proowner FROM pg_proc WHERE oid='public.revoke_dashboard_account(uuid,uuid)'::regprocedure)
             IS DISTINCT FROM 'investment_deletion_executor'::regrole
        OR (SELECT proowner FROM pg_proc WHERE oid='public.reserve_dashboard_reactivation(uuid,uuid,uuid,text)'::regprocedure)
             IS DISTINCT FROM 'investment_deletion_executor'::regrole
        OR NOT has_function_privilege('investment_runtime','public.revoke_dashboard_account(uuid,uuid)','EXECUTE')
        OR NOT has_function_privilege('investment_runtime','public.reserve_dashboard_reactivation(uuid,uuid,uuid,text)','EXECUTE')
        OR has_function_privilege('anon','public.revoke_dashboard_account(uuid,uuid)','EXECUTE')
        OR has_function_privilege('authenticated','public.revoke_dashboard_account(uuid,uuid)','EXECUTE')
        OR has_function_privilege('service_role','public.revoke_dashboard_account(uuid,uuid)','EXECUTE')
        OR has_function_privilege('anon','public.reserve_dashboard_reactivation(uuid,uuid,uuid,text)','EXECUTE')
        OR has_function_privilege('authenticated','public.reserve_dashboard_reactivation(uuid,uuid,uuid,text)','EXECUTE')
        OR has_function_privilege('service_role','public.reserve_dashboard_reactivation(uuid,uuid,uuid,text)','EXECUTE')
        OR has_table_privilege('investment_runtime','public.account_members','UPDATE')
        OR has_table_privilege('investment_runtime','public.account_members','DELETE')
        OR has_schema_privilege('investment_deletion_executor','public','CREATE')
        OR (SELECT NOT relrowsecurity OR NOT relforcerowsecurity FROM pg_class WHERE oid='public.account_members'::regclass)
        OR (SELECT rolsuper OR rolcanlogin OR rolbypassrls OR rolcreaterole OR rolcreatedb
            FROM pg_roles WHERE rolname='investment_deletion_executor') THEN
        RAISE EXCEPTION 'Administrative membership executor configuration is unsafe';
      END IF;
      IF current_setting('server_version_num')::integer >= 160000 AND EXISTS (
        SELECT 1 FROM pg_auth_members m
        WHERE m.roleid='investment_deletion_executor'::regrole
          AND NOT (m.member=(SELECT oid FROM pg_roles WHERE rolname=current_user)
            AND m.admin_option AND NOT m.inherit_option AND NOT m.set_option)
      ) THEN
        RAISE EXCEPTION 'Administrative executor retained an unintended role membership';
      END IF;
      IF (current_setting('server_version_num')::integer < 160000 AND EXISTS (
          SELECT 1 FROM pg_auth_members m
          WHERE m.roleid='investment_deletion_executor'::regrole
            AND m.member<>(SELECT oid FROM pg_roles WHERE rolname=current_user)
        )) OR EXISTS (
          SELECT 1 FROM pg_auth_members WHERE member='investment_deletion_executor'::regrole
        ) THEN
        RAISE EXCEPTION 'Administrative executor retained an unintended role membership';
      END IF;
    END $$""")


def downgrade():
    raise RuntimeError("Forward-only security correction; use a reviewed corrective migration")
