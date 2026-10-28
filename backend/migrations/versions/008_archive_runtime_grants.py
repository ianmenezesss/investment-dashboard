"""Grant the restricted runtime only the privileges required to archive empty contracts."""
from alembic import op

revision = "008"
down_revision = "007"


def upgrade():
    op.execute("""DO $$ DECLARE r record; BEGIN
      SELECT * INTO r FROM pg_roles WHERE rolname='investment_runtime';
      IF NOT FOUND OR NOT r.rolcanlogin OR r.rolsuper OR r.rolbypassrls OR r.rolinherit
         OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication
         OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid) THEN
        RAISE EXCEPTION 'investment_runtime is missing or has unsafe role attributes/memberships';
      END IF;
      REVOKE ALL ON TABLE public.fixed_income_investment_archives FROM investment_runtime;
      REVOKE ALL ON SEQUENCE public.fixed_income_investment_archives_id_seq FROM investment_runtime;
      GRANT USAGE ON SCHEMA public TO investment_runtime;
      GRANT SELECT, INSERT ON TABLE public.fixed_income_investment_archives TO investment_runtime;
      GRANT USAGE ON SEQUENCE public.fixed_income_investment_archives_id_seq TO investment_runtime;
    END; $$""")
    op.execute("""DO $$ BEGIN
      IF NOT (SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.fixed_income_investment_archives'::regclass) THEN
        RAISE EXCEPTION 'Archive RLS/FORCE RLS must remain enabled';
      END IF;
      IF has_table_privilege('investment_runtime','public.fixed_income_investment_archives','UPDATE')
         OR has_table_privilege('investment_runtime','public.fixed_income_investment_archives','DELETE')
         OR has_table_privilege('investment_runtime','public.fixed_income_investment_archives','TRUNCATE') THEN
        RAISE EXCEPTION 'Archive runtime has forbidden mutation privileges';
      END IF;
    END; $$""")


def downgrade():
    raise RuntimeError("Forward-only grant migration; review runtime access before corrective migration")
