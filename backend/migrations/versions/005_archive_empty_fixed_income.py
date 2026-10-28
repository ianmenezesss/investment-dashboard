"""Append-only archive markers for empty fixed-income contracts."""
from alembic import op
import sqlalchemy as sa


revision = "005"
down_revision = "004"


def upgrade():
    op.create_table("fixed_income_investment_archives",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("investment_id", sa.Integer,
            sa.ForeignKey("fixed_income_investments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("owner_id", sa.Uuid, nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("investment_id", name="fi_one_archive_per_investment"))
    op.create_index("ix_fixed_income_investment_archives_owner_id", "fixed_income_investment_archives", ["owner_id"])
    op.execute("ALTER TABLE public.fixed_income_investment_archives ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.fixed_income_investment_archives FORCE ROW LEVEL SECURITY")
    rule = "(owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid OR (owner_id IS NULL AND current_setting('app.auth_mode',true)='local'))"
    op.execute(f"CREATE POLICY api_owner ON public.fixed_income_investment_archives FOR ALL USING ({rule}) WITH CHECK ({rule})")

    # These checks run in the caller's RLS context; the common lock serializes
    # the archive decision with every existing fixed-income child insertion.
    op.execute("""CREATE FUNCTION public.fi_validate_archive() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
    DECLARE contract_owner uuid;
    BEGIN
      IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Fixed-income archive requires READ COMMITTED' USING ERRCODE='23514';
      END IF;
      PERFORM pg_advisory_xact_lock(20001, NEW.investment_id);
      SELECT owner_id INTO contract_owner FROM public.fixed_income_investments WHERE id=NEW.investment_id;
      IF NOT FOUND OR contract_owner IS DISTINCT FROM NEW.owner_id THEN
        RAISE EXCEPTION 'Invalid archive contract or owner' USING ERRCODE='23514';
      END IF;
      IF EXISTS (SELECT 1 FROM public.fixed_income_lots WHERE investment_id=NEW.investment_id)
         OR EXISTS (SELECT 1 FROM public.fixed_income_movements WHERE investment_id=NEW.investment_id)
         OR EXISTS (SELECT 1 FROM public.fixed_income_observations WHERE investment_id=NEW.investment_id) THEN
        RAISE EXCEPTION 'Only empty fixed-income contracts can be archived' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END; $$""")

    # Archived contracts cannot acquire new lots, movements or observations,
    # including through direct SQL using the application runtime role.
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
      IF start_day IS NULL AND NOT EXISTS(SELECT 1 FROM public.fixed_income_movements WHERE investment_id=NEW.investment_id)
        AND NEW.application_date<>contract.application_date THEN
        RAISE EXCEPTION 'First application must match contract date' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END; $$""")
    op.execute("""CREATE OR REPLACE FUNCTION public.fi_validate_movement() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
    DECLARE lot public.fixed_income_lots%ROWTYPE; last_date date; balance numeric;
    BEGIN
      IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Fixed-income writes require READ COMMITTED isolation' USING ERRCODE='23514'; END IF;
      PERFORM pg_advisory_xact_lock(20001, NEW.investment_id);
      IF EXISTS (SELECT 1 FROM public.fixed_income_investment_archives WHERE investment_id=NEW.investment_id) THEN
        RAISE EXCEPTION 'Archived contract cannot receive new movements' USING ERRCODE='23514'; END IF;
      SELECT * INTO lot FROM public.fixed_income_lots WHERE id = NEW.lot_id;
      IF NOT FOUND OR lot.investment_id <> NEW.investment_id OR lot.owner_id IS DISTINCT FROM NEW.owner_id
         OR NEW.date < lot.application_date
         OR NEW.date > (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date THEN
        RAISE EXCEPTION 'Invalid movement lot, owner or date' USING ERRCODE='23514'; END IF;
      SELECT max(date) INTO last_date FROM public.fixed_income_movements WHERE investment_id = NEW.investment_id;
      IF NEW.date < last_date THEN RAISE EXCEPTION 'Retroactive movement is not allowed' USING ERRCODE='23514'; END IF;
      IF NEW.kind = 'APPLICATION' THEN
        IF NEW.date <> lot.application_date THEN RAISE EXCEPTION 'Application must match lot date' USING ERRCODE='23514'; END IF;
      ELSE
        SELECT coalesce(sum(CASE WHEN kind = 'APPLICATION' THEN principal_amount ELSE -principal_amount END), 0)
          INTO balance FROM public.fixed_income_movements WHERE lot_id = NEW.lot_id;
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
        UNION ALL SELECT date FROM public.fixed_income_movements WHERE investment_id=NEW.investment_id) dates;
      IF NEW.as_of<last_day THEN RAISE EXCEPTION 'Retroactive observation' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END; $$""")

    op.execute("CREATE TRIGGER fi_archive_insert BEFORE INSERT ON public.fixed_income_investment_archives FOR EACH ROW EXECUTE FUNCTION public.fi_validate_archive()")
    op.execute("CREATE TRIGGER fi_archive_append_only BEFORE UPDATE OR DELETE ON public.fixed_income_investment_archives FOR EACH ROW EXECUTE FUNCTION public.fi_reject_mutation()")
    op.execute("CREATE TRIGGER fi_archive_no_truncate BEFORE TRUNCATE ON public.fixed_income_investment_archives FOR EACH STATEMENT EXECUTE FUNCTION public.fi_reject_mutation()")

    op.execute("REVOKE ALL ON TABLE public.fixed_income_investment_archives FROM PUBLIC")
    op.execute("REVOKE ALL ON SEQUENCE public.fixed_income_investment_archives_id_seq FROM PUBLIC")
    for role in ("anon", "authenticated", "service_role"):
        op.execute(f"""DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
          REVOKE ALL ON TABLE public.fixed_income_investment_archives FROM {role};
          REVOKE ALL ON SEQUENCE public.fixed_income_investment_archives_id_seq FROM {role}; END IF; END; $$""")
    for function in ("fi_validate_archive", "fi_validate_lot", "fi_validate_movement", "fi_validate_observation"):
        op.execute(f"REVOKE ALL ON FUNCTION public.{function}() FROM PUBLIC")


def downgrade():
    raise RuntimeError("Downgrade destrutivo bloqueado; preserve os tombstones e use migration corretiva")
