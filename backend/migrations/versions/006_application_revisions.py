"""Immutable application revisions and canonical effective ledger (no public write API)."""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"

# Frozen migration SQL: do not import mutable application modules.
PROJECTION_SQL = "SELECT m.id, m.investment_id, m.lot_id, m.owner_id, m.kind,\n CASE WHEN r.kind='REPLACE' THEN r.replacement_date ELSE m.date END AS date,\n CASE WHEN r.kind='REPLACE' THEN r.replacement_amount ELSE m.principal_amount END AS principal_amount,\n m.cash_received, m.created_at\n FROM fixed_income_movements m\n LEFT JOIN fixed_income_application_revisions r ON r.application_id=m.id\n AND r.revision=(SELECT max(r2.revision) FROM fixed_income_application_revisions r2 WHERE r2.application_id=m.id)\n WHERE r.kind IS NULL OR r.kind='REPLACE'"


def upgrade():
    op.create_table("fixed_income_application_revisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("application_id", sa.Integer, sa.ForeignKey("fixed_income_movements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("owner_id", sa.Uuid, nullable=True),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(7), nullable=False),
        sa.Column("replacement_date", sa.Date, nullable=True),
        sa.Column("replacement_amount", sa.Numeric(20,8), nullable=True),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("request_id", sa.Uuid, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("application_id", "revision", name="fi_revision_number"),
        sa.CheckConstraint("kind IN ('REPLACE','VOID')", name="fi_revision_kind"),
        sa.CheckConstraint("revision > 0 AND length(trim(reason)) BETWEEN 1 AND 1000", name="fi_revision_metadata"),
        sa.CheckConstraint("(kind='VOID' AND replacement_date IS NULL AND replacement_amount IS NULL) OR (kind='REPLACE' AND replacement_date IS NOT NULL AND replacement_amount IS NOT NULL AND replacement_amount > 0 AND replacement_amount <= 999999999999.99999999)", name="fi_revision_payload"))
    op.create_index("ix_fixed_income_application_revisions_application_id", "fixed_income_application_revisions", ["application_id"])
    op.create_index("ix_fixed_income_application_revisions_owner_id", "fixed_income_application_revisions", ["owner_id"])
    op.execute("CREATE UNIQUE INDEX fi_revision_request_owner ON public.fixed_income_application_revisions(owner_id,request_id) WHERE owner_id IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX fi_revision_request_local ON public.fixed_income_application_revisions(request_id) WHERE owner_id IS NULL")
    op.execute("ALTER TABLE public.fixed_income_application_revisions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.fixed_income_application_revisions FORCE ROW LEVEL SECURITY")
    rule = "(owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid OR (owner_id IS NULL AND current_setting('app.auth_mode',true)='local'))"
    op.execute(f"CREATE POLICY api_owner ON public.fixed_income_application_revisions FOR ALL USING ({rule}) WITH CHECK ({rule})")
    op.execute("CREATE FUNCTION public.fi_effective_movements() RETURNS SETOF public.fixed_income_movements LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $projection$ " + PROJECTION_SQL + " $projection$")
    op.execute("""CREATE FUNCTION public.fi_revision_before() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
    DECLARE original public.fixed_income_movements%ROWTYPE; previous public.fixed_income_application_revisions%ROWTYPE;
    BEGIN
      IF current_setting('transaction_isolation') <> 'read committed' THEN RAISE EXCEPTION 'READ COMMITTED required' USING ERRCODE='23514'; END IF;
      SELECT * INTO original FROM public.fixed_income_movements WHERE id=NEW.application_id;
      IF NOT FOUND OR original.kind<>'APPLICATION' OR original.owner_id IS DISTINCT FROM NEW.owner_id THEN
        RAISE EXCEPTION 'Invalid application or owner' USING ERRCODE='23514'; END IF;
      PERFORM pg_advisory_xact_lock(20001,original.investment_id);
      IF EXISTS(SELECT 1 FROM public.fixed_income_investment_archives WHERE investment_id=original.investment_id) THEN
        RAISE EXCEPTION 'Archived contract' USING ERRCODE='23514'; END IF;
      SELECT * INTO previous FROM public.fixed_income_application_revisions WHERE application_id=NEW.application_id ORDER BY revision DESC LIMIT 1;
      IF previous.kind='VOID' OR NEW.revision<>coalesce(previous.revision,0)+1 THEN
        RAISE EXCEPTION 'Stale revision or terminal VOID' USING ERRCODE='23514'; END IF;
      NEW.created_at := clock_timestamp();
      RETURN NEW;
    END; $$""")
    op.execute("""CREATE FUNCTION public.fi_revision_after() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
    DECLARE original public.fixed_income_movements%ROWTYPE; contract public.fixed_income_investments%ROWTYPE;
      opening_day date; first_day date; prior_day date;
    BEGIN
      SELECT * INTO original FROM public.fixed_income_movements WHERE id=NEW.application_id;
      SELECT * INTO contract FROM public.fixed_income_investments WHERE id=original.investment_id;
      SELECT as_of INTO opening_day FROM public.fixed_income_observations WHERE investment_id=original.investment_id AND kind='OPENING';
      IF NEW.kind='REPLACE' AND (NEW.replacement_date<contract.application_date OR NEW.replacement_date>contract.maturity_date
        OR NEW.replacement_date>(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date
        OR NEW.replacement_date<=opening_day) THEN RAISE EXCEPTION 'Invalid replacement date' USING ERRCODE='23514'; END IF;
      IF NEW.kind='VOID' AND EXISTS(SELECT 1 FROM public.fixed_income_movements WHERE lot_id=original.lot_id AND kind='REDEMPTION') THEN
        RAISE EXCEPTION 'VOID conflicts with existing redemptions' USING ERRCODE='23514'; END IF;
      SELECT min(date) INTO first_day FROM public.fi_effective_movements() WHERE investment_id=original.investment_id AND kind='APPLICATION';
      IF opening_day IS NULL AND first_day IS NOT NULL AND first_day<>contract.application_date THEN
        RAISE EXCEPTION 'First effective application must match contract date' USING ERRCODE='23514'; END IF;
      IF EXISTS(SELECT 1 FROM public.fi_effective_movements() a JOIN public.fi_effective_movements() d ON d.lot_id=a.lot_id
          WHERE a.id=NEW.application_id AND d.kind='REDEMPTION' AND d.date<a.date)
        OR EXISTS(SELECT 1 FROM (SELECT sum(CASE WHEN kind='APPLICATION' THEN principal_amount ELSE -principal_amount END)
          OVER(PARTITION BY lot_id ORDER BY date,id ROWS UNBOUNDED PRECEDING) AS balance
          FROM public.fi_effective_movements() WHERE investment_id=original.investment_id) b WHERE balance<0) THEN
        RAISE EXCEPTION 'Correction conflicts with existing redemptions' USING ERRCODE='23514'; END IF;
      SELECT coalesce((SELECT replacement_date FROM public.fixed_income_application_revisions
        WHERE application_id=NEW.application_id AND revision<NEW.revision ORDER BY revision DESC LIMIT 1),original.date) INTO prior_day;
      -- Refuse crossing any already recorded whole-contract observation in either direction.
      IF NEW.kind='REPLACE' AND EXISTS(SELECT 1 FROM public.fixed_income_observations WHERE investment_id=original.investment_id
          AND as_of>=least(prior_day,NEW.replacement_date) AND as_of<greatest(prior_day,NEW.replacement_date)) THEN
        RAISE EXCEPTION 'Replacement crosses an existing observation' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END; $$""")
    op.execute("CREATE TRIGGER fi_revision_insert BEFORE INSERT ON public.fixed_income_application_revisions FOR EACH ROW EXECUTE FUNCTION public.fi_revision_before()")
    op.execute("CREATE TRIGGER fi_revision_validate AFTER INSERT ON public.fixed_income_application_revisions FOR EACH ROW EXECUTE FUNCTION public.fi_revision_after()")
    op.execute("CREATE TRIGGER fi_revision_append_only BEFORE UPDATE OR DELETE ON public.fixed_income_application_revisions FOR EACH ROW EXECUTE FUNCTION public.fi_reject_mutation()")
    op.execute("CREATE TRIGGER fi_revision_no_truncate BEFORE TRUNCATE ON public.fixed_income_application_revisions FOR EACH STATEMENT EXECUTE FUNCTION public.fi_reject_mutation()")
    op.execute("REVOKE ALL ON TABLE public.fixed_income_application_revisions FROM PUBLIC")
    op.execute("REVOKE ALL ON SEQUENCE public.fixed_income_application_revisions_id_seq FROM PUBLIC")
    for role in ("anon", "authenticated", "service_role"):
        op.execute(f"""DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
          REVOKE ALL ON TABLE public.fixed_income_application_revisions FROM {role};
          REVOKE ALL ON SEQUENCE public.fixed_income_application_revisions_id_seq FROM {role}; END IF; END; $$""")
    for function in ("fi_effective_movements", "fi_revision_before", "fi_revision_after"):
        op.execute(f"REVOKE ALL ON FUNCTION public.{function}() FROM PUBLIC")
    op.execute("""CREATE OR REPLACE FUNCTION public.fi_validate_lot() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
    DECLARE contract public.fixed_income_investments%ROWTYPE; start_day date;
    BEGIN
      IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Fixed-income writes require READ COMMITTED isolation' USING ERRCODE='23514'; END IF;
      PERFORM pg_advisory_xact_lock(20001,NEW.investment_id);
      SELECT * INTO contract FROM public.fixed_income_investments WHERE id=NEW.investment_id;
      IF NOT FOUND OR contract.owner_id IS DISTINCT FROM NEW.owner_id
        OR NEW.application_date<contract.application_date OR NEW.application_date>contract.maturity_date
        OR NEW.application_date>(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date THEN
        RAISE EXCEPTION 'Invalid lot contract, owner or date' USING ERRCODE='23514'; END IF;
      IF EXISTS (SELECT 1 FROM public.fixed_income_investment_archives WHERE investment_id=NEW.investment_id) THEN
        RAISE EXCEPTION 'Archived contract cannot receive new lots' USING ERRCODE='23514'; END IF;
      SELECT as_of INTO start_day FROM public.fixed_income_observations WHERE investment_id=NEW.investment_id AND kind='OPENING';
      IF start_day IS NOT NULL AND NEW.application_date<=start_day THEN RAISE EXCEPTION 'Lot must follow opening' USING ERRCODE='23514'; END IF;
      IF start_day IS NULL AND NOT EXISTS(SELECT 1 FROM public.fi_effective_movements() WHERE investment_id=NEW.investment_id)
        AND NEW.application_date<>contract.application_date THEN
        RAISE EXCEPTION 'First application must match contract date' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END; $$""")
    op.execute("""CREATE OR REPLACE FUNCTION public.fi_validate_movement() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
    DECLARE lot public.fixed_income_lots%ROWTYPE; last_date date; balance numeric; effective_day date;
    BEGIN
      IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Fixed-income writes require READ COMMITTED isolation' USING ERRCODE='23514'; END IF;
      PERFORM pg_advisory_xact_lock(20001, NEW.investment_id);
      IF EXISTS (SELECT 1 FROM public.fixed_income_investment_archives WHERE investment_id=NEW.investment_id) THEN
        RAISE EXCEPTION 'Archived contract cannot receive new movements' USING ERRCODE='23514'; END IF;
      SELECT * INTO lot FROM public.fixed_income_lots WHERE id = NEW.lot_id;
      IF NOT FOUND OR lot.investment_id <> NEW.investment_id OR lot.owner_id IS DISTINCT FROM NEW.owner_id
         OR (NEW.kind='APPLICATION' AND NEW.date < lot.application_date)
         OR NEW.date > (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date THEN
        RAISE EXCEPTION 'Invalid movement lot, owner or date' USING ERRCODE='23514'; END IF;
      SELECT max(date) INTO last_date FROM public.fi_effective_movements() WHERE investment_id = NEW.investment_id;
      IF NEW.date < last_date THEN RAISE EXCEPTION 'Retroactive movement is not allowed' USING ERRCODE='23514'; END IF;
      IF NEW.kind = 'APPLICATION' THEN
        IF NEW.date <> lot.application_date THEN RAISE EXCEPTION 'Application must match lot date' USING ERRCODE='23514'; END IF;
      ELSE
        SELECT date INTO effective_day FROM public.fi_effective_movements() WHERE lot_id=NEW.lot_id AND kind='APPLICATION';
        IF effective_day IS NULL OR NEW.date<effective_day THEN RAISE EXCEPTION 'Missing effective application or invalid redemption date' USING ERRCODE='23514'; END IF;
        SELECT coalesce(sum(CASE WHEN kind = 'APPLICATION' THEN principal_amount ELSE -principal_amount END), 0)
          INTO balance FROM public.fi_effective_movements() WHERE lot_id = NEW.lot_id;
        IF NEW.principal_amount > balance THEN RAISE EXCEPTION 'Redemption exceeds available principal' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END; $$""")
    op.execute("""CREATE OR REPLACE FUNCTION public.fi_validate_observation() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
    DECLARE contract public.fixed_income_investments%ROWTYPE; last_day date;
    BEGIN
      IF current_setting('transaction_isolation') <> 'read committed' THEN RAISE EXCEPTION 'READ COMMITTED required' USING ERRCODE='23514'; END IF;
      PERFORM pg_advisory_xact_lock(20001,NEW.investment_id);
      IF EXISTS (SELECT 1 FROM public.fixed_income_investment_archives WHERE investment_id=NEW.investment_id) THEN
        RAISE EXCEPTION 'Archived contract cannot receive new observations' USING ERRCODE='23514'; END IF;
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
        UNION ALL SELECT date FROM public.fi_effective_movements() WHERE investment_id=NEW.investment_id) dates;
      IF NEW.as_of<last_day THEN RAISE EXCEPTION 'Retroactive observation' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END; $$""")


def downgrade():
    raise RuntimeError("Destructive downgrade blocked; preserve revisions and use a corrective migration")
