"""Invite-only accounts with owner-only financial access."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from app.database import settings

revision = "011"
down_revision = "010"


def upgrade():
    op.create_table(
        "account_members",
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("assistant_minute_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assistant_minute_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assistant_usage_date", sa.Date(), nullable=True),
        sa.Column("assistant_daily_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("status IN ('active','revoked')", name="account_member_status"),
    )
    op.create_table(
        "account_invitations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("invited_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("email = lower(trim(email)) AND length(email) BETWEEN 3 AND 320", name="account_invite_email"),
        sa.CheckConstraint("expires_at > created_at", name="account_invite_expiry"),
    )
    op.create_index("ix_account_invites_creator", "account_invitations", ["invited_by", "created_at"])
    op.create_index("uq_account_invite_pending_email", "account_invitations", ["email"], unique=True,
                    postgresql_where=sa.text("accepted_user_id IS NULL AND revoked_at IS NULL"))
    for table in ("account_members", "account_invitations"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC, anon, authenticated, service_role")
    op.execute("CREATE POLICY member_self_read ON public.account_members FOR SELECT USING (user_id = NULLIF(current_setting('app.user_id',true),'')::uuid)")
    op.execute("CREATE POLICY member_self_activate ON public.account_members FOR INSERT WITH CHECK (user_id = NULLIF(current_setting('app.user_id',true),'')::uuid)")
    op.execute("CREATE POLICY member_self_quota ON public.account_members FOR UPDATE USING (user_id = NULLIF(current_setting('app.user_id',true),'')::uuid) WITH CHECK (user_id = NULLIF(current_setting('app.user_id',true),'')::uuid)")
    op.execute("CREATE POLICY member_admin_revoke ON public.account_members FOR UPDATE USING (NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL) WITH CHECK (NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL)")
    op.execute("CREATE POLICY invite_admin_read ON public.account_invitations FOR SELECT USING (NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL)")
    op.execute("CREATE POLICY invite_email_read ON public.account_invitations FOR SELECT USING (email = lower(NULLIF(current_setting('app.user_email',true),'')))")
    op.execute("CREATE POLICY invite_admin_insert ON public.account_invitations FOR INSERT WITH CHECK (invited_by = NULLIF(current_setting('app.admin_id',true),'')::uuid)")
    op.execute("CREATE POLICY invite_admin_revoke ON public.account_invitations FOR UPDATE USING (NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL) WITH CHECK (NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL)")
    op.execute("CREATE POLICY invite_email_accept ON public.account_invitations FOR UPDATE USING (email = lower(NULLIF(current_setting('app.user_email',true),'')) AND accepted_user_id IS NULL AND revoked_at IS NULL) WITH CHECK (email = lower(NULLIF(current_setting('app.user_email',true),'')))")
    op.execute("GRANT SELECT ON public.account_members TO investment_runtime")
    op.execute("GRANT SELECT, INSERT ON public.account_invitations TO investment_runtime")
    op.execute("GRANT UPDATE (revoked_at) ON public.account_invitations TO investment_runtime")
    op.execute("""CREATE FUNCTION public.accept_dashboard_invitation(p_user_id uuid, p_email text)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
      DECLARE existing_status text; claimed_id uuid;
      BEGIN
        IF NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM p_user_id
          OR lower(NULLIF(current_setting('app.user_email',true),'')) IS DISTINCT FROM lower(trim(p_email)) THEN
          RETURN false;
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('dashboard-account-activation:' || p_user_id::text, 0));
        SELECT status INTO existing_status FROM public.account_members WHERE user_id=p_user_id;
        IF existing_status='active' THEN RETURN true; END IF;
        SELECT id INTO claimed_id FROM public.account_invitations
          WHERE email=lower(trim(p_email)) AND accepted_user_id IS NULL AND revoked_at IS NULL
            AND expires_at > now() FOR UPDATE;
        IF claimed_id IS NULL THEN RETURN false; END IF;
        UPDATE public.account_invitations SET accepted_user_id=p_user_id WHERE id=claimed_id;
        INSERT INTO public.account_members(user_id,email,status) VALUES (p_user_id,lower(trim(p_email)),'active')
          ON CONFLICT (user_id) DO UPDATE SET email=EXCLUDED.email, status='active';
        RETURN true;
      END $$""")
    op.execute("""CREATE FUNCTION public.revoke_dashboard_account(p_user_id uuid, p_admin_id uuid)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
      DECLARE invite_id uuid;
      BEGIN
        IF NULLIF(current_setting('app.admin_id',true),'')::uuid IS DISTINCT FROM p_admin_id THEN RETURN false; END IF;
        SELECT id INTO invite_id FROM public.account_invitations
          WHERE accepted_user_id=p_user_id AND revoked_at IS NULL FOR UPDATE;
        IF invite_id IS NULL THEN RETURN false; END IF;
        UPDATE public.account_invitations SET revoked_at=now() WHERE id=invite_id;
        UPDATE public.account_members SET status='revoked' WHERE user_id=p_user_id;
        RETURN true;
      END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.accept_dashboard_invitation(uuid,text) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION public.revoke_dashboard_account(uuid,uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.accept_dashboard_invitation(uuid,text) TO investment_runtime")
    op.execute("GRANT EXECUTE ON FUNCTION public.revoke_dashboard_account(uuid,uuid) TO investment_runtime")
    op.execute("""CREATE FUNCTION public.consume_dashboard_assistant_quota(p_user_id uuid)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
      DECLARE member_row public.account_members%ROWTYPE; today_utc date := (now() AT TIME ZONE 'UTC')::date;
      BEGIN
        IF NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM p_user_id THEN RETURN false; END IF;
        SELECT * INTO member_row FROM public.account_members WHERE user_id=p_user_id AND status='active' FOR UPDATE;
        IF NOT FOUND THEN RETURN false; END IF;
        IF member_row.assistant_usage_date IS DISTINCT FROM today_utc THEN
          member_row.assistant_usage_date := today_utc; member_row.assistant_daily_count := 0;
        END IF;
        IF member_row.assistant_minute_started_at IS NULL OR now()-member_row.assistant_minute_started_at >= interval '1 minute' THEN
          member_row.assistant_minute_started_at := now(); member_row.assistant_minute_count := 0;
        END IF;
        IF member_row.assistant_minute_count >= 5 OR member_row.assistant_daily_count >= 50 THEN RETURN false; END IF;
        UPDATE public.account_members SET assistant_usage_date=member_row.assistant_usage_date,
          assistant_daily_count=member_row.assistant_daily_count+1,
          assistant_minute_started_at=member_row.assistant_minute_started_at,
          assistant_minute_count=member_row.assistant_minute_count+1 WHERE user_id=p_user_id;
        RETURN true;
      END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.consume_dashboard_assistant_quota(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.consume_dashboard_assistant_quota(uuid) TO investment_runtime")
    op.execute("REVOKE ALL ON FUNCTION public.accept_dashboard_invitation(uuid,text) FROM anon, authenticated, service_role")
    op.execute("REVOKE ALL ON FUNCTION public.revoke_dashboard_account(uuid,uuid) FROM anon, authenticated, service_role")
    op.execute("REVOKE ALL ON FUNCTION public.consume_dashboard_assistant_quota(uuid) FROM anon, authenticated, service_role")
    # Keep already-authorized UUID accounts able to access their existing owner-scoped data.
    for user_id in set(settings.allowed_user_ids + settings.invitation_admin_ids):
        op.execute(f"INSERT INTO public.account_members(user_id,email,status) VALUES ('{user_id}'::uuid,NULL,'active') ON CONFLICT (user_id) DO NOTHING")


def downgrade():
    raise RuntimeError("Forward-only invited accounts; preserve account/access history and use a corrective migration")
