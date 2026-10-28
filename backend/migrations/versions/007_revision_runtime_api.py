"""Runtime grants and global chronology guard for the private revision API."""
from alembic import op

revision = "007"
down_revision = "006"


def upgrade():
    # Official deployment docs provision this exact least-privilege role separately from DDL.
    op.execute("""DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='investment_runtime') THEN
        RAISE EXCEPTION 'Required restricted runtime role investment_runtime is not provisioned';
      END IF;
      IF (SELECT NOT rolcanlogin OR rolsuper OR rolbypassrls OR rolinherit OR rolcreatedb OR rolcreaterole OR rolreplication
          FROM pg_roles WHERE rolname='investment_runtime')
        OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='investment_runtime')) THEN
        RAISE EXCEPTION 'investment_runtime must be restricted, NOINHERIT, and have no role memberships';
      END IF;
      REVOKE ALL ON TABLE public.fixed_income_application_revisions FROM investment_runtime;
      REVOKE ALL ON SEQUENCE public.fixed_income_application_revisions_id_seq FROM investment_runtime;
      REVOKE ALL ON FUNCTION public.fi_effective_movements() FROM investment_runtime;
      GRANT USAGE ON SCHEMA public TO investment_runtime;
      GRANT SELECT ON public.fixed_income_investments, public.fixed_income_lots,
        public.fixed_income_movements, public.fixed_income_observations,
        public.fixed_income_investment_archives TO investment_runtime;
      GRANT SELECT, INSERT ON public.fixed_income_application_revisions TO investment_runtime;
      GRANT USAGE ON SEQUENCE public.fixed_income_application_revisions_id_seq TO investment_runtime;
      GRANT EXECUTE ON FUNCTION public.fi_effective_movements() TO investment_runtime;
    END; $$""")
    op.execute("""CREATE OR REPLACE FUNCTION public.fi_revision_after() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$

    DECLARE original public.fixed_income_movements%ROWTYPE; contract public.fixed_income_investments%ROWTYPE;
      opening_day date; first_day date; prior_day date; previous_date date; next_date date;
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
      IF NEW.kind='REPLACE' THEN
        SELECT max(date) INTO previous_date FROM public.fi_effective_movements()
          WHERE investment_id=original.investment_id AND id<original.id AND id<>original.id;
        SELECT min(date) INTO next_date FROM public.fi_effective_movements()
          WHERE investment_id=original.investment_id AND id>original.id;
        IF previous_date IS NOT NULL AND NEW.replacement_date<previous_date
          OR next_date IS NOT NULL AND NEW.replacement_date>next_date THEN
          RAISE EXCEPTION 'Replacement violates global movement chronology' USING ERRCODE='23514';
        END IF;
      END IF;
      -- Refuse crossing any already recorded whole-contract observation in either direction.
      IF NEW.kind='REPLACE' AND EXISTS(SELECT 1 FROM public.fixed_income_observations WHERE investment_id=original.investment_id
          AND as_of>=least(prior_day,NEW.replacement_date) AND as_of<greatest(prior_day,NEW.replacement_date)) THEN
        RAISE EXCEPTION 'Replacement crosses an existing observation' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END; $$""")


def downgrade():
    # Revision history is append-only; an explicit forward migration is required.
    raise RuntimeError("Downgrade blocked; preserve revision history and use a corrective migration")
