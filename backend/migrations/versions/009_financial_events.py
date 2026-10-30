"""Owner-isolated manual cash/income events and append-only corrections."""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"


EVENT_PAYLOAD = """((kind IN ('CONTRIBUTION','WITHDRAWAL') AND ticker IS NULL AND cash_amount IS NOT NULL AND cash_amount > 0 AND gross_amount IS NULL AND tax_withheld IS NULL AND description IS NULL)
 OR (kind IN ('DIVIDEND','JCP') AND ticker IS NOT NULL AND cash_amount IS NOT NULL AND cash_amount > 0 AND (gross_amount IS NULL OR gross_amount > 0) AND (tax_withheld IS NULL OR tax_withheld >= 0) AND description IS NULL AND (gross_amount IS NULL OR tax_withheld IS NULL OR gross_amount-tax_withheld=cash_amount))
 OR (kind='CORPORATE_ACTION' AND ticker IS NOT NULL AND cash_amount IS NULL AND gross_amount IS NULL AND tax_withheld IS NULL AND description IS NOT NULL AND length(trim(description)) > 0))"""

REPLACEMENT_PAYLOAD = """((replacement_kind IN ('CONTRIBUTION','WITHDRAWAL') AND replacement_ticker IS NULL AND replacement_cash_amount IS NOT NULL AND replacement_cash_amount > 0 AND replacement_gross_amount IS NULL AND replacement_tax_withheld IS NULL AND replacement_description IS NULL)
 OR (replacement_kind IN ('DIVIDEND','JCP') AND replacement_ticker IS NOT NULL AND replacement_cash_amount IS NOT NULL AND replacement_cash_amount > 0 AND (replacement_gross_amount IS NULL OR replacement_gross_amount > 0) AND (replacement_tax_withheld IS NULL OR replacement_tax_withheld >= 0) AND replacement_description IS NULL AND (replacement_gross_amount IS NULL OR replacement_tax_withheld IS NULL OR replacement_gross_amount-replacement_tax_withheld=replacement_cash_amount))
 OR (replacement_kind='CORPORATE_ACTION' AND replacement_ticker IS NOT NULL AND replacement_cash_amount IS NULL AND replacement_gross_amount IS NULL AND replacement_tax_withheld IS NULL AND replacement_description IS NOT NULL AND length(trim(replacement_description)) > 0))"""


def upgrade():
    op.create_table(
        "financial_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=True),
        sa.Column("cash_amount", sa.Numeric(20, 8), nullable=True),
        sa.Column("gross_amount", sa.Numeric(20, 8), nullable=True),
        sa.Column("tax_withheld", sa.Numeric(20, 8), nullable=True),
        sa.Column("source", sa.String(240), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("request_id", name="financial_event_request_unique"),
        sa.CheckConstraint("kind IN ('CONTRIBUTION','WITHDRAWAL','DIVIDEND','JCP','CORPORATE_ACTION')", name="financial_event_kind"),
        sa.CheckConstraint("length(trim(source)) BETWEEN 1 AND 240", name="financial_event_source"),
        sa.CheckConstraint(EVENT_PAYLOAD, name="financial_event_payload"),
    )
    op.create_index("ix_financial_events_owner_id", "financial_events", ["owner_id"])
    op.create_index("ix_financial_events_owner_date_id", "financial_events", ["owner_id", "event_date", "id"])

    op.create_table(
        "financial_event_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("financial_events.id"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("replacement_kind", sa.String(24), nullable=True),
        sa.Column("replacement_date", sa.Date(), nullable=True),
        sa.Column("replacement_ticker", sa.String(20), nullable=True),
        sa.Column("replacement_cash_amount", sa.Numeric(20, 8), nullable=True),
        sa.Column("replacement_gross_amount", sa.Numeric(20, 8), nullable=True),
        sa.Column("replacement_tax_withheld", sa.Numeric(20, 8), nullable=True),
        sa.Column("replacement_source", sa.String(240), nullable=True),
        sa.Column("replacement_description", sa.String(1000), nullable=True),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("event_id", "revision", name="financial_event_revision_number"),
        sa.UniqueConstraint("request_id", name="financial_event_revision_request_unique"),
        sa.CheckConstraint("kind IN ('REPLACE','VOID')", name="financial_event_revision_kind"),
        sa.CheckConstraint("revision > 0 AND length(trim(reason)) BETWEEN 1 AND 1000", name="financial_event_revision_metadata"),
        sa.CheckConstraint("(kind='VOID' AND replacement_kind IS NULL AND replacement_date IS NULL AND replacement_ticker IS NULL AND replacement_cash_amount IS NULL AND replacement_gross_amount IS NULL AND replacement_tax_withheld IS NULL AND replacement_source IS NULL AND replacement_description IS NULL) OR (kind='REPLACE' AND replacement_kind IS NOT NULL AND replacement_date IS NOT NULL AND replacement_source IS NOT NULL AND length(trim(replacement_source)) BETWEEN 1 AND 240 AND " + REPLACEMENT_PAYLOAD + ")", name="financial_event_revision_payload"),
    )
    op.create_index("ix_financial_event_revisions_event_id", "financial_event_revisions", ["event_id"])
    op.create_index("ix_financial_event_revisions_owner_id", "financial_event_revisions", ["owner_id"])

    rule = "(owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid OR (owner_id IS NULL AND current_setting('app.auth_mode',true)='local'))"
    for table in ("financial_events", "financial_event_revisions"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY api_owner ON public.{table} FOR ALL USING ({rule}) WITH CHECK ({rule})")
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
        op.execute(f"REVOKE ALL ON SEQUENCE public.{table}_id_seq FROM PUBLIC")
        for role in ("anon", "authenticated", "service_role"):
            op.execute(f"""DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
              REVOKE ALL ON TABLE public.{table} FROM {role};
              REVOKE ALL ON SEQUENCE public.{table}_id_seq FROM {role}; END IF; END; $$""")

    op.execute("""CREATE FUNCTION public.financial_event_reject_mutation() RETURNS trigger
      LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
      BEGIN RAISE EXCEPTION 'Financial events and revisions are append-only' USING ERRCODE='23514'; END; $$""")
    op.execute("""CREATE FUNCTION public.financial_event_revision_before() RETURNS trigger
      LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
      DECLARE original public.financial_events%ROWTYPE; current_revision integer; current_kind text;
      BEGIN
        IF current_setting('transaction_isolation') <> 'read committed' THEN
          RAISE EXCEPTION 'READ COMMITTED required' USING ERRCODE='23514';
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(NEW.event_id::text, 0));
        SELECT * INTO original FROM public.financial_events WHERE id=NEW.event_id;
        IF NOT FOUND OR original.owner_id IS DISTINCT FROM NEW.owner_id THEN
          RAISE EXCEPTION 'Invalid financial event or owner' USING ERRCODE='23514';
        END IF;
        SELECT coalesce(max(revision),0) INTO current_revision
          FROM public.financial_event_revisions WHERE event_id=NEW.event_id AND owner_id IS NOT DISTINCT FROM NEW.owner_id;
        SELECT kind INTO current_kind FROM public.financial_event_revisions
          WHERE event_id=NEW.event_id AND owner_id IS NOT DISTINCT FROM NEW.owner_id ORDER BY revision DESC LIMIT 1;
        IF current_kind='VOID' OR NEW.revision<>current_revision+1 THEN
          RAISE EXCEPTION 'Stale or terminal financial event revision' USING ERRCODE='23514';
        END IF;
        NEW.created_at := clock_timestamp();
        RETURN NEW;
      END; $$""")
    for table in ("financial_events", "financial_event_revisions"):
        op.execute(f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.financial_event_reject_mutation()")
        op.execute(f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} FOR EACH STATEMENT EXECUTE FUNCTION public.financial_event_reject_mutation()")
    op.execute("CREATE TRIGGER financial_event_revision_guard BEFORE INSERT ON public.financial_event_revisions FOR EACH ROW EXECUTE FUNCTION public.financial_event_revision_before()")
    op.execute("""DO $$ DECLARE r record; BEGIN
      SELECT * INTO r FROM pg_roles WHERE rolname='investment_runtime';
      IF NOT FOUND OR NOT r.rolcanlogin OR r.rolsuper OR r.rolbypassrls OR r.rolinherit
         OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication
         OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid) THEN
        RAISE EXCEPTION 'investment_runtime is missing or has unsafe role attributes/memberships';
      END IF;
      GRANT USAGE ON SCHEMA public TO investment_runtime;
      REVOKE ALL ON TABLE public.financial_events, public.financial_event_revisions FROM investment_runtime;
      REVOKE ALL ON SEQUENCE public.financial_events_id_seq, public.financial_event_revisions_id_seq FROM investment_runtime;
      GRANT SELECT, INSERT ON TABLE public.financial_events, public.financial_event_revisions TO investment_runtime;
      GRANT USAGE ON SEQUENCE public.financial_events_id_seq, public.financial_event_revisions_id_seq TO investment_runtime;
    END; $$""")
    op.execute("""DO $$ BEGIN
      IF NOT (SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.financial_events'::regclass)
         OR NOT (SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.financial_event_revisions'::regclass) THEN
        RAISE EXCEPTION 'Financial event RLS/FORCE RLS must remain enabled';
      END IF;
      IF has_table_privilege('investment_runtime','public.financial_events','UPDATE')
         OR has_table_privilege('investment_runtime','public.financial_events','DELETE')
         OR has_table_privilege('investment_runtime','public.financial_events','TRUNCATE')
         OR has_table_privilege('investment_runtime','public.financial_event_revisions','UPDATE')
         OR has_table_privilege('investment_runtime','public.financial_event_revisions','DELETE')
         OR has_table_privilege('investment_runtime','public.financial_event_revisions','TRUNCATE') THEN
        RAISE EXCEPTION 'Financial event runtime has forbidden mutation privileges';
      END IF;
    END; $$""")
    op.execute("REVOKE ALL ON FUNCTION public.financial_event_reject_mutation() FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION public.financial_event_revision_before() FROM PUBLIC")


def downgrade():
    raise RuntimeError("Append-only financial events are forward-only; use a corrective migration")
