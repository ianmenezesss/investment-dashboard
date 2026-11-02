"""Audit invite delivery attempts and permit safe member revocation."""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"


def upgrade():
    op.create_table(
        "account_invitation_send_attempts",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        # A user's authorized privacy deletion also removes invitations; its
        # operational send history follows that deletion without blocking it.
        sa.Column("invitation_id", sa.Uuid(), sa.ForeignKey("account_invitations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column("provider_code", sa.String(40), nullable=True),
        sa.CheckConstraint("outcome IN ('started','requested','failed','uncertain')", name="invitation_send_outcome"),
        sa.CheckConstraint("method IN ('invite','recovery')", name="invitation_send_method"),
        sa.CheckConstraint("http_status IS NULL OR http_status BETWEEN 100 AND 599", name="invitation_send_http_status"),
    )
    op.create_index("ix_invitation_send_attempts_invitation", "account_invitation_send_attempts",
                    ["invitation_id", "attempted_at", "id"])
    op.create_index("ix_invitation_send_attempts_admin", "account_invitation_send_attempts",
                    ["requested_by", "attempted_at"])
    op.create_index("ix_invitation_send_attempts_time", "account_invitation_send_attempts", ["attempted_at"])
    op.execute("ALTER TABLE public.account_invitation_send_attempts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.account_invitation_send_attempts FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY invitation_send_admin ON public.account_invitation_send_attempts TO investment_runtime USING (NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL) WITH CHECK (NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL)")
    op.execute("REVOKE ALL ON public.account_invitation_send_attempts FROM PUBLIC, anon, authenticated, service_role")
    op.execute("REVOKE ALL ON SEQUENCE public.account_invitation_send_attempts_id_seq FROM PUBLIC, anon, authenticated, service_role")
    op.execute("GRANT SELECT, INSERT ON public.account_invitation_send_attempts TO investment_runtime")
    op.execute("GRANT UPDATE (outcome,method,http_status,provider_code) ON public.account_invitation_send_attempts TO investment_runtime")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE public.account_invitation_send_attempts_id_seq TO investment_runtime")

    # Revoke a membership by its state, not by the existence of an accepted invite.
    # This also handles legacy memberships created before invitations existed.
    op.execute("""CREATE OR REPLACE FUNCTION public.revoke_dashboard_account(p_user_id uuid, p_admin_id uuid)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
      DECLARE v_status text;
      BEGIN
        IF p_user_id = p_admin_id
          OR NULLIF(current_setting('app.admin_id',true),'')::uuid IS DISTINCT FROM p_admin_id THEN
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
    op.execute("REVOKE ALL ON FUNCTION public.revoke_dashboard_account(uuid,uuid) FROM PUBLIC, anon, authenticated, service_role")
    op.execute("GRANT EXECUTE ON FUNCTION public.revoke_dashboard_account(uuid,uuid) TO investment_runtime")


def downgrade():
    raise RuntimeError("Forward-only admin audit migration; use a corrective migration")
