"""Separate access administration from the untrusted runtime SQL identity.

An application GUC is request context, never evidence that its caller is an
administrator. Administrative operations now require a distinct database login
which belongs to investment_access_admin. No login or password is provisioned by
this migration, and the normal runtime must never be a member of that role.
"""
from alembic import op
import sqlalchemy as sa

from app.database import settings

revision = "017"
down_revision = "016"


def upgrade():
    op.execute("""DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='investment_access_admin') THEN
        CREATE ROLE investment_access_admin NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
          NOINHERIT NOREPLICATION NOBYPASSRLS;
      ELSIF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='investment_access_admin' AND
          (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit OR rolreplication OR rolbypassrls)) THEN
        RAISE EXCEPTION 'investment_access_admin has unsafe attributes';
      END IF;
      IF pg_has_role('investment_runtime','investment_access_admin','MEMBER') THEN
        RAISE EXCEPTION 'The runtime must not belong to the administration role';
      END IF;
    END $$""")
    op.execute("GRANT USAGE ON SCHEMA public TO investment_access_admin")

    # These records are configured only through the migration/owner connection.
    # A runtime session cannot invent an administrator by setting app.admin_id.
    op.create_table(
        "account_access_administrators",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
    )
    op.execute("REVOKE ALL ON public.account_access_administrators FROM PUBLIC, anon, authenticated, service_role, investment_runtime, investment_access_admin")
    for user_id in set(settings.invitation_admin_ids):
        op.get_bind().execute(sa.text("INSERT INTO public.account_access_administrators(user_id) VALUES (:user_id)"),
                             {"user_id": user_id})
    op.execute("ALTER TABLE public.account_access_administrators ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.account_access_administrators FORCE ROW LEVEL SECURITY")
    owner = op.get_bind().dialect.identifier_preparer.quote(op.get_bind().scalar(sa.text("SELECT current_user")))
    op.execute(f"CREATE POLICY access_administrator_owner_maintenance ON public.account_access_administrators FOR ALL TO {owner} USING (true) WITH CHECK (true)")
    op.execute("GRANT SELECT ON public.account_access_administrators TO investment_deletion_executor")
    op.execute("CREATE POLICY access_administrator_executor_read ON public.account_access_administrators FOR SELECT TO investment_deletion_executor USING (true)")

    op.create_table(
        "account_access_audit",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("event_code", sa.String(48), nullable=False),
        sa.Column("subject_user_id", sa.Uuid(), nullable=True),
        sa.Column("invitation_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("event_code ~ '^[a-z][a-z0-9_]{1,47}$'", name="account_access_audit_event"),
    )
    op.create_index("ix_account_access_audit_time", "account_access_audit", ["occurred_at", "id"])
    op.create_index("ix_account_access_audit_subject", "account_access_audit", ["subject_user_id", "id"])
    op.execute("ALTER TABLE public.account_access_audit ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.account_access_audit FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON public.account_access_audit FROM PUBLIC, anon, authenticated, service_role, investment_runtime")
    op.execute("REVOKE ALL ON SEQUENCE public.account_access_audit_id_seq FROM PUBLIC, anon, authenticated, service_role, investment_runtime")
    op.execute("GRANT SELECT, INSERT ON public.account_access_audit TO investment_access_admin")
    op.execute("GRANT INSERT ON public.account_access_audit TO investment_deletion_executor")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE public.account_access_audit_id_seq TO investment_access_admin, investment_deletion_executor")

    # Existing functions are owned by the restricted executor. Temporarily grant
    # only the migration session SET capability and schema CREATE while replacing
    # them, then remove both capabilities in this same Alembic transaction.
    op.execute("""DO $$ BEGIN
      IF current_setting('server_version_num')::integer >= 160000 THEN
        GRANT investment_deletion_executor TO CURRENT_USER WITH SET TRUE, INHERIT FALSE;
      ELSE
        GRANT investment_deletion_executor TO CURRENT_USER;
      END IF;
    END $$""")
    op.execute("GRANT CREATE ON SCHEMA public TO investment_deletion_executor")
    op.execute("SET LOCAL ROLE investment_deletion_executor")
    op.execute("""CREATE OR REPLACE FUNCTION public.dashboard_admin_authorized()
      RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        SELECT pg_has_role(session_user,'investment_access_admin','MEMBER')
          AND EXISTS (SELECT 1 FROM public.account_access_administrators
            WHERE user_id::text=NULLIF(current_setting('app.admin_id',true),''))
      $$""")
    op.execute("REVOKE ALL ON FUNCTION public.dashboard_admin_authorized() FROM PUBLIC, anon, authenticated, service_role, investment_runtime")
    op.execute("GRANT EXECUTE ON FUNCTION public.dashboard_admin_authorized() TO investment_access_admin, investment_deletion_executor")

    op.execute("""CREATE OR REPLACE FUNCTION public.revoke_dashboard_account(p_user_id uuid, p_admin_id uuid)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
      DECLARE v_status text;
      BEGIN
        IF NOT public.dashboard_admin_authorized()
          OR NULLIF(current_setting('app.admin_id',true),'')::uuid IS DISTINCT FROM p_admin_id
          OR p_user_id IS NULL OR p_admin_id IS NULL
          OR EXISTS (SELECT 1 FROM public.account_access_administrators WHERE user_id=p_user_id)
        THEN RETURN false; END IF;
        -- Activation, revocation and reactivation serialize on the same member.
        PERFORM pg_advisory_xact_lock(hashtextextended('dashboard-account-activation:' || p_user_id::text,0));
        SELECT status INTO v_status FROM public.account_members WHERE user_id=p_user_id FOR UPDATE;
        IF NOT FOUND THEN RETURN false; END IF;
        IF v_status='revoked' THEN RETURN true; END IF;
        UPDATE public.account_invitations SET revoked_at=clock_timestamp(),
          claim_user_id=NULL,claim_token_hash=NULL,claim_expires_at=NULL
          WHERE (accepted_user_id=p_user_id OR target_user_id=p_user_id)
            AND revoked_at IS NULL;
        UPDATE public.account_members SET status='revoked' WHERE user_id=p_user_id;
        INSERT INTO public.account_access_audit(actor_id,event_code,subject_user_id)
          VALUES(p_admin_id,'membership_revoked',p_user_id);
        RETURN true;
      END $$""")
    op.execute("""CREATE OR REPLACE FUNCTION public.reserve_dashboard_reactivation(
        p_user_id uuid,p_admin_id uuid,p_invitation_id uuid,p_email text)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
      DECLARE v_status text; v_expiry timestamptz; v_now timestamptz;
      BEGIN
        IF NOT public.dashboard_admin_authorized()
          OR NULLIF(current_setting('app.admin_id',true),'')::uuid IS DISTINCT FROM p_admin_id
          OR p_user_id IS NULL OR p_admin_id IS NULL OR p_invitation_id IS NULL
          OR EXISTS (SELECT 1 FROM public.account_access_administrators WHERE user_id=p_user_id)
          OR p_email IS NULL OR p_email IS DISTINCT FROM lower(trim(p_email))
          OR length(p_email) NOT BETWEEN 3 AND 320 THEN RETURN false; END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('dashboard-invitations:' || p_admin_id::text,0));
        PERFORM pg_advisory_xact_lock(hashtextextended('dashboard-account-activation:' || p_user_id::text,0));
        v_now := clock_timestamp();
        SELECT status,access_expires_at INTO v_status,v_expiry
          FROM public.account_members WHERE user_id=p_user_id FOR UPDATE;
        IF NOT FOUND OR NOT (v_status='revoked' OR (v_expiry IS NOT NULL AND v_expiry<=v_now)) THEN
          RETURN false;
        END IF;
        IF EXISTS (SELECT 1 FROM public.account_invitations WHERE target_user_id=p_user_id
          AND accepted_user_id IS NULL AND revoked_at IS NULL AND expires_at>v_now) THEN RETURN false; END IF;
        IF (SELECT count(*) FROM public.account_invitations
              WHERE invited_by=p_admin_id AND created_at>=v_now-interval '1 day')>=500
          OR (SELECT count(*) FROM public.account_invitations WHERE invited_by=p_admin_id
              AND revoked_at IS NULL AND accepted_user_id IS NULL AND expires_at>v_now)>=500 THEN
          RETURN false;
        END IF;
        UPDATE public.account_invitations SET revoked_at=v_now,
          claim_user_id=NULL,claim_token_hash=NULL,claim_expires_at=NULL
          WHERE email=p_email AND accepted_user_id IS NULL AND revoked_at IS NULL AND expires_at<=v_now;
        INSERT INTO public.account_invitations
          (id,email,invited_by,created_at,expires_at,access_duration_days,target_user_id)
          VALUES(p_invitation_id,p_email,p_admin_id,v_now,v_now+interval '7 days',7,p_user_id);
        INSERT INTO public.account_access_audit(actor_id,event_code,subject_user_id,invitation_id)
          VALUES(p_admin_id,'reactivation_prepared',p_user_id,p_invitation_id);
        RETURN true;
      END $$""")
    for signature in ("revoke_dashboard_account(uuid,uuid)", "reserve_dashboard_reactivation(uuid,uuid,uuid,text)"):
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC, anon, authenticated, service_role, investment_runtime")
        op.execute(f"GRANT EXECUTE ON FUNCTION public.{signature} TO investment_access_admin")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM investment_deletion_executor")
    op.execute("REVOKE investment_deletion_executor FROM CURRENT_USER")

    # Replace every old admin policy. The self-service runtime policies remain
    # owner scoped, including invitation claims and financial data isolation.
    policies = (
        ("account_members", "member_admin_read", "SELECT", "true", None),
        ("account_invitations", "invite_admin_read", "SELECT", "true", None),
        ("account_invitations", "invite_admin_insert", "INSERT", None,
         "invited_by=NULLIF(current_setting('app.admin_id',true),'')::uuid"),
        ("account_invitations", "invite_admin_revoke", "UPDATE", "true", "true"),
        ("account_access_requests", "access_request_read_admin", "SELECT", "true", None),
        ("account_access_requests", "access_request_update_admin", "UPDATE", "true", "true"),
        ("account_invitation_send_attempts", "invitation_send_admin", "ALL", "true", "true"),
    )
    for table, name, action, using, check in policies:
        op.execute(f"DROP POLICY {name} ON public.{table}")
        sql = f"CREATE POLICY {name} ON public.{table} FOR {action} TO investment_access_admin"
        if using:
            sql += f" USING (public.dashboard_admin_authorized() AND ({using}))"
        if check:
            sql += f" WITH CHECK (public.dashboard_admin_authorized() AND ({check}))"
        op.execute(sql)
    op.execute("DROP POLICY member_admin_revoke ON public.account_members")
    op.execute("DROP POLICY member_admin_executor_update ON public.account_members")
    op.execute("CREATE POLICY member_admin_executor_read ON public.account_members FOR SELECT TO investment_deletion_executor USING (public.dashboard_admin_authorized())")
    op.execute("CREATE POLICY member_admin_executor_update ON public.account_members FOR UPDATE TO investment_deletion_executor USING (public.dashboard_admin_authorized()) WITH CHECK (public.dashboard_admin_authorized())")
    op.execute("CREATE POLICY invitation_admin_executor ON public.account_invitations FOR ALL TO investment_deletion_executor USING (public.dashboard_admin_authorized()) WITH CHECK (public.dashboard_admin_authorized())")
    op.execute("CREATE POLICY access_audit_admin_read ON public.account_access_audit FOR SELECT TO investment_access_admin USING (public.dashboard_admin_authorized())")
    op.execute("CREATE POLICY access_audit_admin_insert ON public.account_access_audit FOR INSERT TO investment_access_admin, investment_deletion_executor WITH CHECK (public.dashboard_admin_authorized() AND actor_id=NULLIF(current_setting('app.admin_id',true),'')::uuid)")
    op.execute("GRANT SELECT ON public.account_members TO investment_access_admin")
    op.execute("GRANT SELECT, INSERT ON public.account_invitations TO investment_access_admin")
    op.execute("GRANT UPDATE (revoked_at) ON public.account_invitations TO investment_access_admin")
    op.execute("GRANT SELECT, UPDATE ON public.account_access_requests TO investment_access_admin")
    op.execute("GRANT SELECT, INSERT ON public.account_invitation_send_attempts TO investment_access_admin")
    op.execute("GRANT UPDATE (outcome,method,http_status,provider_code) ON public.account_invitation_send_attempts TO investment_access_admin")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE public.account_invitation_send_attempts_id_seq TO investment_access_admin")
    op.execute("REVOKE INSERT ON public.account_invitations FROM investment_runtime")
    op.execute("REVOKE UPDATE (revoked_at) ON public.account_invitations FROM investment_runtime")
    op.execute("REVOKE ALL ON public.account_invitation_send_attempts FROM investment_runtime")
    op.execute("REVOKE ALL ON SEQUENCE public.account_invitation_send_attempts_id_seq FROM investment_runtime")
    op.execute("REVOKE UPDATE ON public.account_access_requests FROM investment_runtime")

    # The old saga could strand authorized approvals after a mail timeout. The
    # authorization and exact invitation already committed are retained; delivery
    # remains unknown until the recorded attempt or a controlled resend resolves it.
    # FORCE RLS also applies to a non-superuser DDL owner. These policies give
    # only this authorized migration login access for the bounded backfill and
    # disappear in the same transaction, without ever disabling RLS.
    op.execute(f"CREATE POLICY access_reconcile_migration ON public.account_access_requests FOR ALL TO {owner} USING (true) WITH CHECK (true)")
    op.execute(f"CREATE POLICY invitation_reconcile_migration ON public.account_invitations FOR SELECT TO {owner} USING (true)")
    op.execute("""UPDATE public.account_access_requests r SET status='approved',
      reviewed_by=COALESCE(r.reviewed_by,i.invited_by),
      reviewed_at=COALESCE(r.reviewed_at,r.processing_at,i.created_at),processing_at=NULL
      FROM public.account_invitations i WHERE r.status='approving' AND r.invitation_id=i.id""")
    op.execute("""UPDATE public.account_access_requests SET status='pending',processing_at=NULL,invitation_id=NULL
      WHERE status='approving'""")
    op.execute("DROP POLICY access_reconcile_migration ON public.account_access_requests")
    op.execute("DROP POLICY invitation_reconcile_migration ON public.account_invitations")

    op.execute("""DO $$ BEGIN
      IF pg_has_role('investment_runtime','investment_access_admin','MEMBER')
        OR has_table_privilege('investment_access_admin','public.operations','SELECT')
        OR has_table_privilege('investment_access_admin','public.account_members','UPDATE')
        OR has_schema_privilege('investment_access_admin','public','CREATE')
        OR has_schema_privilege('investment_deletion_executor','public','CREATE')
        OR has_function_privilege('investment_runtime','public.revoke_dashboard_account(uuid,uuid)','EXECUTE')
        OR has_function_privilege('investment_runtime','public.reserve_dashboard_reactivation(uuid,uuid,uuid,text)','EXECUTE') THEN
        RAISE EXCEPTION 'Unsafe access administration privileges';
      END IF;
    END $$""")


def downgrade():
    raise RuntimeError("Forward-only access security boundary; use a reviewed corrective migration")
