"""Store dated, owner-scoped observations used by prospective wealth history."""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"


def upgrade():
    op.create_table(
        "portfolio_valuation_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("equities_market_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("equities_source", sa.String(240), nullable=False),
        sa.Column("fixed_income_gross_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("fixed_income_net_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("fixed_income_coverage", sa.String(16), nullable=False),
        sa.Column("fixed_income_sources", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("missing_fixed_income", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("request_id", name="pvo_request_unique"),
        sa.CheckConstraint("length(trim(equities_source)) BETWEEN 1 AND 240", name="pvo_equities_source"),
        sa.CheckConstraint("equities_market_value >= 0 AND equities_market_value <= 999999999999.99", name="pvo_equities_value"),
        sa.CheckConstraint("(fixed_income_gross_value IS NULL AND fixed_income_net_value IS NULL) OR (fixed_income_gross_value IS NOT NULL AND fixed_income_net_value IS NOT NULL AND fixed_income_net_value >= 0 AND fixed_income_net_value <= fixed_income_gross_value AND fixed_income_gross_value <= 999999999999.99)", name="pvo_fixed_income_values"),
        sa.CheckConstraint("fixed_income_coverage IN ('complete','partial','unavailable','empty')", name="pvo_fixed_income_coverage"),
    )
    op.create_index("ix_portfolio_valuation_observations_owner_id", "portfolio_valuation_observations", ["owner_id"])
    op.create_index("ix_pvo_owner_date_id", "portfolio_valuation_observations", ["owner_id", "as_of", "id"])

    rule = "(owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid OR (owner_id IS NULL AND current_setting('app.auth_mode',true)='local'))"
    op.execute("ALTER TABLE public.portfolio_valuation_observations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.portfolio_valuation_observations FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY api_owner ON public.portfolio_valuation_observations FOR ALL USING ({rule}) WITH CHECK ({rule})")
    op.execute("CREATE TRIGGER portfolio_valuation_observations_append_only BEFORE UPDATE OR DELETE ON public.portfolio_valuation_observations FOR EACH ROW EXECUTE FUNCTION public.financial_event_reject_mutation()")
    op.execute("CREATE TRIGGER portfolio_valuation_observations_no_truncate BEFORE TRUNCATE ON public.portfolio_valuation_observations FOR EACH STATEMENT EXECUTE FUNCTION public.financial_event_reject_mutation()")
    op.execute("REVOKE ALL ON TABLE public.portfolio_valuation_observations FROM PUBLIC")
    op.execute("REVOKE ALL ON SEQUENCE public.portfolio_valuation_observations_id_seq FROM PUBLIC")
    for role in ("anon", "authenticated", "service_role"):
        op.execute(f"""DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
          REVOKE ALL ON TABLE public.portfolio_valuation_observations FROM {role};
          REVOKE ALL ON SEQUENCE public.portfolio_valuation_observations_id_seq FROM {role}; END IF; END; $$""")
    op.execute("""DO $$ DECLARE r record; BEGIN
      SELECT * INTO r FROM pg_roles WHERE rolname='investment_runtime';
      IF NOT FOUND OR NOT r.rolcanlogin OR r.rolsuper OR r.rolbypassrls OR r.rolinherit
         OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication
         OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid) THEN
        RAISE EXCEPTION 'investment_runtime is missing or has unsafe role attributes/memberships';
      END IF;
      GRANT USAGE ON SCHEMA public TO investment_runtime;
      REVOKE ALL ON TABLE public.portfolio_valuation_observations FROM investment_runtime;
      REVOKE ALL ON SEQUENCE public.portfolio_valuation_observations_id_seq FROM investment_runtime;
      GRANT SELECT, INSERT ON TABLE public.portfolio_valuation_observations TO investment_runtime;
      GRANT USAGE ON SEQUENCE public.portfolio_valuation_observations_id_seq TO investment_runtime;
    END; $$""")
    op.execute("""DO $$ BEGIN
      IF NOT (SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.portfolio_valuation_observations'::regclass)
         OR has_table_privilege('investment_runtime','public.portfolio_valuation_observations','UPDATE')
         OR has_table_privilege('investment_runtime','public.portfolio_valuation_observations','DELETE')
         OR has_table_privilege('investment_runtime','public.portfolio_valuation_observations','TRUNCATE') THEN
        RAISE EXCEPTION 'Portfolio observation access policy is unsafe';
      END IF;
    END; $$""")
    op.execute("REVOKE ALL ON FUNCTION public.financial_event_reject_mutation() FROM PUBLIC")


def downgrade():
    raise RuntimeError("Forward-only portfolio observations; preserve history and use a corrective migration")
