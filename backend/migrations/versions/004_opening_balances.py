"""Manual observed positions, append-only; no financial history is synthesized."""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"


def upgrade():
    op.create_table("fixed_income_observations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("investment_id", sa.Integer, sa.ForeignKey("fixed_income_investments.id"), nullable=False),
        sa.Column("owner_id", sa.Uuid, nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("as_of", sa.Date, nullable=False),
        sa.Column("gross_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("net_value", sa.Numeric(14, 2), nullable=False),
        *[sa.Column(field, sa.Numeric(14, 2), nullable=True) for field in ("ir_estimate", "iof_estimate", "taxes_combined", "reported_gain", "confirmed_principal", "cash_received")],
        sa.Column("source", sa.String(160), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('OPENING','OBSERVATION')", name="fi_observation_kind"),
        sa.CheckConstraint("reason IN ('POSITION','AFTER_CONSOLIDATED_REDEMPTION')", name="fi_observation_reason"),
        sa.CheckConstraint("net_value <= gross_value", name="fi_observation_net"),
        sa.CheckConstraint("taxes_combined IS NULL OR (ir_estimate IS NULL AND iof_estimate IS NULL)", name="fi_observation_tax_mode"),
        sa.CheckConstraint("taxes_combined IS NULL OR gross_value-net_value=taxes_combined", name="fi_observation_tax_total"),
        sa.CheckConstraint("ir_estimate IS NULL OR iof_estimate IS NULL OR gross_value-net_value=ir_estimate+iof_estimate", name="fi_observation_tax_parts"),
        sa.CheckConstraint("coalesce(ir_estimate,0)+coalesce(iof_estimate,0)<=gross_value-net_value", name="fi_observation_tax_known"),
        sa.CheckConstraint("(kind <> 'OPENING' OR reason='POSITION') AND (cash_received IS NULL OR (kind='OBSERVATION' AND reason='AFTER_CONSOLIDATED_REDEMPTION'))", name="fi_observation_cash"),
        sa.CheckConstraint("length(trim(source))>0", name="fi_observation_source"),
        *[sa.CheckConstraint(f"{field} IS NULL OR ({field}>=0 AND {field}<=999999999999.99)", name=f"fi_obs_{field}_valid") for field in ("gross_value", "net_value", "ir_estimate", "iof_estimate", "taxes_combined", "confirmed_principal", "cash_received")],
        sa.CheckConstraint("reported_gain IS NULL OR (reported_gain>=-999999999999.99 AND reported_gain<=999999999999.99)", name="fi_observation_gain"))
    op.create_index("ix_fixed_income_observations_owner_id", "fixed_income_observations", ["owner_id"])
    op.create_index("ix_fi_observation_chronology", "fixed_income_observations", ["investment_id", "as_of", "id"])
    op.create_index("fi_one_opening_per_investment", "fixed_income_observations", ["investment_id"], unique=True, postgresql_where=sa.text("kind='OPENING'"))
    op.execute("ALTER TABLE public.fixed_income_observations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.fixed_income_observations FORCE ROW LEVEL SECURITY")
    rule = "(owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid OR (owner_id IS NULL AND current_setting('app.auth_mode',true)='local'))"
    op.execute(f"CREATE POLICY api_owner ON public.fixed_income_observations FOR ALL USING ({rule}) WITH CHECK ({rule})")
    op.execute("""CREATE FUNCTION public.fi_validate_observation() RETURNS trigger LANGUAGE plpgsql
    SET search_path=pg_catalog,public AS $$
    DECLARE contract public.fixed_income_investments%ROWTYPE; last_day date;
    BEGIN
      IF current_setting('transaction_isolation') <> 'read committed' THEN RAISE EXCEPTION 'READ COMMITTED required' USING ERRCODE='23514'; END IF;
      PERFORM pg_advisory_xact_lock(20001,NEW.investment_id);
      SELECT * INTO contract FROM public.fixed_income_investments WHERE id=NEW.investment_id;
      IF NOT FOUND OR contract.owner_id IS DISTINCT FROM NEW.owner_id OR NEW.as_of<contract.application_date
         OR NEW.as_of>(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date THEN
        RAISE EXCEPTION 'Invalid observation contract, owner or date' USING ERRCODE='23514'; END IF;
      IF NEW.kind='OPENING' THEN
        IF EXISTS(SELECT 1 FROM public.fixed_income_observations WHERE investment_id=NEW.investment_id)
          OR EXISTS(SELECT 1 FROM public.fixed_income_lots WHERE investment_id=NEW.investment_id) THEN
          RAISE EXCEPTION 'Opening requires contract without history' USING ERRCODE='23514'; END IF;
      ELSIF NOT EXISTS(SELECT 1 FROM public.fixed_income_observations WHERE investment_id=NEW.investment_id AND kind='OPENING') THEN
        RAISE EXCEPTION 'Opening required before reconciliation' USING ERRCODE='23514';
      END IF;
      SELECT max(day) INTO last_day FROM (
        SELECT as_of AS day FROM public.fixed_income_observations WHERE investment_id=NEW.investment_id
        UNION ALL SELECT date FROM public.fixed_income_movements WHERE investment_id=NEW.investment_id) dates;
      IF NEW.as_of<last_day THEN RAISE EXCEPTION 'Retroactive observation' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END; $$""")
    op.execute("""CREATE FUNCTION public.fi_tracking_movement_guard() RETURNS trigger LANGUAGE plpgsql
    SET search_path=pg_catalog,public AS $$
    DECLARE start_day date; latest_day date;
    BEGIN
      PERFORM pg_advisory_xact_lock(20001,NEW.investment_id);
      SELECT min(as_of),max(as_of) INTO start_day,latest_day FROM public.fixed_income_observations WHERE investment_id=NEW.investment_id;
      IF NEW.date<=start_day OR NEW.date<latest_day THEN RAISE EXCEPTION 'Movement precedes observed position' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END; $$""")
    # Necessary extension of 003: only the first-application rule changes for opened contracts.
    op.execute("""CREATE OR REPLACE FUNCTION public.fi_validate_lot() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
    DECLARE contract public.fixed_income_investments%ROWTYPE; start_day date;
    BEGIN
      PERFORM pg_advisory_xact_lock(20001,NEW.investment_id);
      SELECT * INTO contract FROM public.fixed_income_investments WHERE id=NEW.investment_id;
      IF NOT FOUND OR contract.owner_id IS DISTINCT FROM NEW.owner_id
        OR NEW.application_date<contract.application_date OR NEW.application_date>contract.maturity_date
        OR NEW.application_date>(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date THEN
        RAISE EXCEPTION 'Invalid lot contract, owner or date' USING ERRCODE='23514'; END IF;
      SELECT as_of INTO start_day FROM public.fixed_income_observations WHERE investment_id=NEW.investment_id AND kind='OPENING';
      IF start_day IS NOT NULL AND NEW.application_date<=start_day THEN RAISE EXCEPTION 'Lot must follow opening' USING ERRCODE='23514'; END IF;
      IF start_day IS NULL AND NOT EXISTS(SELECT 1 FROM public.fixed_income_movements WHERE investment_id=NEW.investment_id)
        AND NEW.application_date<>contract.application_date THEN
        RAISE EXCEPTION 'First application must match contract date' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END; $$""")
    for name, event, function in (("fi_observation_insert", "INSERT", "fi_validate_observation"), ("fi_append_only", "UPDATE OR DELETE", "fi_reject_mutation")):
        op.execute(f"CREATE TRIGGER {name} BEFORE {event} ON public.fixed_income_observations FOR EACH ROW EXECUTE FUNCTION public.{function}()")
    op.execute("CREATE TRIGGER fi_no_truncate BEFORE TRUNCATE ON public.fixed_income_observations FOR EACH STATEMENT EXECUTE FUNCTION public.fi_reject_mutation()")
    op.execute("CREATE TRIGGER fi_00_tracking_guard BEFORE INSERT ON public.fixed_income_movements FOR EACH ROW EXECUTE FUNCTION public.fi_tracking_movement_guard()")
    op.execute("REVOKE ALL ON TABLE public.fixed_income_observations FROM PUBLIC")
    op.execute("REVOKE ALL ON SEQUENCE public.fixed_income_observations_id_seq FROM PUBLIC")
    for role in ("anon", "authenticated", "service_role"):
        op.execute(f"""DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
          REVOKE ALL ON TABLE public.fixed_income_observations FROM {role};
          REVOKE ALL ON SEQUENCE public.fixed_income_observations_id_seq FROM {role}; END IF; END; $$""")
    for function in ("fi_validate_observation", "fi_tracking_movement_guard"):
        op.execute(f"REVOKE ALL ON FUNCTION public.{function}() FROM PUBLIC")


def downgrade():
    raise RuntimeError("Downgrade destrutivo bloqueado; preservar snapshots e usar migration corretiva")
