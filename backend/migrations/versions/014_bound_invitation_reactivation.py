"""Bind acceptance to one invitation and record the latest access activation."""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"


def upgrade():
    op.add_column("account_members", sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("account_invitations", sa.Column("target_user_id", sa.Uuid(), nullable=True))
    op.add_column("account_invitations", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("account_invitations", sa.Column("claim_user_id", sa.Uuid(), nullable=True))
    op.add_column("account_invitations", sa.Column("claim_token_hash", sa.String(64), nullable=True))
    op.add_column("account_invitations", sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("account_invitation_claim_hash", "account_invitations",
        "claim_token_hash IS NULL OR claim_token_hash ~ '^[0-9a-f]{64}$'")
    op.create_check_constraint("account_invitation_claim_consistency", "account_invitations",
        "(claim_user_id IS NULL AND claim_token_hash IS NULL AND claim_expires_at IS NULL) OR (claim_user_id IS NOT NULL AND claim_token_hash IS NOT NULL AND claim_expires_at IS NOT NULL)")
    op.execute("GRANT UPDATE (claim_user_id,claim_token_hash,claim_expires_at) ON public.account_invitations TO investment_runtime")

    # Admin membership details are read only after the server checked its allowlist and set this transaction context.
    op.execute("CREATE POLICY member_admin_read ON public.account_members FOR SELECT USING (NULLIF(current_setting('app.admin_id',true),'') IS NOT NULL)")
    op.execute("""CREATE OR REPLACE FUNCTION public.accept_dashboard_invitation(p_user_id uuid, p_email text)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
      DECLARE v_invitation_id uuid; v_target_user_id uuid; v_duration_days smallint; v_claim_user_id uuid;
        v_claim_token_hash text; v_claim_expires_at timestamptz;
        v_member_status text; v_member_expiry timestamptz; v_now timestamptz;
      BEGIN
        IF NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM p_user_id
          OR lower(NULLIF(current_setting('app.user_email',true),'')) IS DISTINCT FROM lower(trim(p_email))
          OR NULLIF(current_setting('app.invitation_id',true),'') IS NULL
          OR NULLIF(current_setting('app.claim_user_id',true),'')::uuid IS DISTINCT FROM p_user_id
          OR NULLIF(current_setting('app.claim_token_hash',true),'') IS NULL THEN
          RETURN false;
        END IF;
        v_invitation_id := current_setting('app.invitation_id',true)::uuid;
        PERFORM pg_advisory_xact_lock(hashtextextended('dashboard-account-activation:' || p_user_id::text, 0));
        v_now := clock_timestamp();
        SELECT target_user_id,access_duration_days,claim_user_id,claim_token_hash,claim_expires_at
          INTO v_target_user_id,v_duration_days,v_claim_user_id,v_claim_token_hash,v_claim_expires_at
          FROM public.account_invitations WHERE id=v_invitation_id AND email=lower(trim(p_email))
            AND accepted_user_id IS NULL AND revoked_at IS NULL AND expires_at > v_now
            AND claim_user_id=p_user_id AND claim_token_hash=current_setting('app.claim_token_hash',true)
            AND claim_expires_at > v_now FOR UPDATE;
        IF NOT FOUND OR v_claim_user_id IS DISTINCT FROM p_user_id OR v_claim_token_hash IS DISTINCT FROM current_setting('app.claim_token_hash',true)
          OR v_claim_expires_at <= v_now THEN RETURN false; END IF;
        SELECT status,access_expires_at INTO v_member_status,v_member_expiry
          FROM public.account_members WHERE user_id=p_user_id FOR UPDATE;
        IF FOUND THEN
          IF NOT (v_member_status='revoked' OR (v_member_expiry IS NOT NULL AND v_member_expiry <= v_now))
            OR v_target_user_id IS DISTINCT FROM p_user_id THEN RETURN false; END IF;
        ELSIF v_target_user_id IS NOT NULL THEN
          RETURN false;
        END IF;
        UPDATE public.account_invitations SET accepted_user_id=p_user_id,accepted_at=v_now,
          claim_user_id=NULL,claim_token_hash=NULL,claim_expires_at=NULL WHERE id=v_invitation_id;
        INSERT INTO public.account_members(user_id,email,status,access_expires_at,activated_at)
          VALUES(p_user_id,lower(trim(p_email)),'active',
            CASE WHEN v_duration_days=7 THEN v_now+interval '168 hours' ELSE NULL END,v_now)
          ON CONFLICT (user_id) DO UPDATE SET email=EXCLUDED.email,status='active',
            access_expires_at=EXCLUDED.access_expires_at,activated_at=EXCLUDED.activated_at;
        RETURN true;
      END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.accept_dashboard_invitation(uuid,text) FROM PUBLIC, anon, authenticated, service_role")
    op.execute("GRANT EXECUTE ON FUNCTION public.accept_dashboard_invitation(uuid,text) TO investment_runtime")


def downgrade():
    raise RuntimeError("Forward-only invitation and account-access audit; use a corrective migration")
