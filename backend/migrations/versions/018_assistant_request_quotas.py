"""Configurable assistant quotas with a short, distributed per-user lease."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "018"
down_revision = "017"


def upgrade():
    op.add_column("account_members", sa.Column("assistant_last_started_at", sa.DateTime(timezone=True)))
    op.add_column("account_members", sa.Column("assistant_in_flight_until", sa.DateTime(timezone=True)))
    op.add_column("account_members", sa.Column("assistant_request_id", UUID(as_uuid=True)))
    op.execute("""CREATE FUNCTION public.reserve_dashboard_assistant_request(
        p_user_id uuid, p_request_id uuid, p_per_minute integer, p_per_day integer, p_cooldown integer)
      RETURNS text LANGUAGE plpgsql SECURITY DEFINER
      SET search_path = pg_catalog, public SET row_security = on AS $$
      DECLARE member_row public.account_members%ROWTYPE; v_now timestamptz; today_utc date;
      BEGIN
        IF NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM p_user_id
          OR p_user_id IS NULL OR p_request_id IS NULL
          OR p_per_minute IS NULL OR p_per_minute NOT BETWEEN 1 AND 60
          OR p_per_day IS NULL OR p_per_day NOT BETWEEN 1 AND 10000
          OR p_cooldown IS NULL OR p_cooldown NOT BETWEEN 0 AND 60 THEN
          RETURN 'inactive';
        END IF;
        SELECT * INTO member_row FROM public.account_members WHERE user_id=p_user_id FOR UPDATE;
        v_now := clock_timestamp();
        today_utc := (v_now AT TIME ZONE 'UTC')::date;
        IF NOT FOUND OR member_row.status <> 'active'
          OR (member_row.access_expires_at IS NOT NULL AND member_row.access_expires_at <= v_now) THEN
          RETURN 'inactive';
        END IF;
        IF member_row.assistant_in_flight_until > v_now THEN RETURN 'busy'; END IF;
        IF member_row.assistant_last_started_at > v_now-make_interval(secs => p_cooldown) THEN RETURN 'cooldown'; END IF;
        IF member_row.assistant_usage_date IS DISTINCT FROM today_utc THEN
          member_row.assistant_usage_date := today_utc; member_row.assistant_daily_count := 0;
        END IF;
        IF member_row.assistant_minute_started_at IS NULL
          OR v_now-member_row.assistant_minute_started_at >= interval '1 minute' THEN
          member_row.assistant_minute_started_at := v_now; member_row.assistant_minute_count := 0;
        END IF;
        IF member_row.assistant_daily_count >= p_per_day THEN RETURN 'daily'; END IF;
        IF member_row.assistant_minute_count >= p_per_minute THEN RETURN 'minute'; END IF;
        UPDATE public.account_members SET assistant_usage_date=member_row.assistant_usage_date,
          assistant_daily_count=member_row.assistant_daily_count+1,
          assistant_minute_started_at=member_row.assistant_minute_started_at,
          assistant_minute_count=member_row.assistant_minute_count+1,
          assistant_last_started_at=v_now, assistant_request_id=p_request_id,
          assistant_in_flight_until=v_now+interval '30 seconds' WHERE user_id=p_user_id;
        RETURN 'allowed';
      END $$""")
    op.execute("""CREATE FUNCTION public.release_dashboard_assistant_request(p_user_id uuid,p_request_id uuid)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
      SET search_path = pg_catalog, public SET row_security = on AS $$
      BEGIN
        IF NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM p_user_id
          OR p_user_id IS NULL OR p_request_id IS NULL THEN RETURN false; END IF;
        UPDATE public.account_members SET assistant_request_id=NULL,assistant_in_flight_until=NULL
          WHERE user_id=p_user_id AND assistant_request_id=p_request_id;
        RETURN FOUND;
      END $$""")
    signatures = (
        "reserve_dashboard_assistant_request(uuid,uuid,integer,integer,integer)",
        "release_dashboard_assistant_request(uuid,uuid)",
    )
    for signature in signatures:
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC, anon, authenticated, service_role")
        op.execute(f"GRANT EXECUTE ON FUNCTION public.{signature} TO investment_runtime")
    op.execute("""DO $$ BEGIN
      IF current_setting('server_version_num')::integer >= 160000 THEN
        GRANT investment_deletion_executor TO CURRENT_USER WITH SET TRUE, INHERIT FALSE;
      ELSE
        GRANT investment_deletion_executor TO CURRENT_USER;
      END IF;
    END $$""")
    op.execute("GRANT CREATE ON SCHEMA public TO investment_deletion_executor")
    for signature in signatures:
        op.execute(f"ALTER FUNCTION public.{signature} OWNER TO investment_deletion_executor")
    op.execute("REVOKE CREATE ON SCHEMA public FROM investment_deletion_executor")
    op.execute("REVOKE investment_deletion_executor FROM CURRENT_USER")


def downgrade():
    raise RuntimeError("Forward-only assistant quotas; preserve usage and apply a corrective migration")
