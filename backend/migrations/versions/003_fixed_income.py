"""Append-only fixed-income principal ledger; adds only new objects."""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"

TABLES = ("fixed_income_investments", "fixed_income_lots", "fixed_income_movements")


def upgrade():
    op.create_table(TABLES[0],
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=True),
        sa.Column("issuer", sa.String(160), nullable=False),
        sa.Column("product_name", sa.String(160), nullable=False),
        sa.Column("product_type", sa.String(20), nullable=False),
        sa.Column("remuneration", sa.String(20), nullable=False),
        sa.Column("indexer", sa.String(20), nullable=False),
        sa.Column("contracted_rate", sa.Numeric(12, 8), nullable=False),
        sa.Column("application_date", sa.Date, nullable=False),
        sa.Column("maturity_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("product_type = 'CDB'", name="fi_product_supported"),
        sa.CheckConstraint("(remuneration = 'FIXED' AND indexer = 'NONE') OR (remuneration = 'CDI' AND indexer = 'CDI')", name="fi_rate_pair"),
        sa.CheckConstraint("contracted_rate > 0 AND contracted_rate < 10000", name="fi_rate_positive"),
        sa.CheckConstraint("maturity_date > application_date", name="fi_maturity"),
        sa.CheckConstraint("length(trim(issuer)) > 0 AND length(trim(product_name)) > 0", name="fi_names"))
    op.create_table(TABLES[1],
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("investment_id", sa.Integer, sa.ForeignKey("fixed_income_investments.id"), nullable=False),
        sa.Column("owner_id", sa.Uuid, nullable=True),
        sa.Column("application_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "investment_id", name="fi_lot_investment_unique"))
    op.create_table(TABLES[2],
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("investment_id", sa.Integer, sa.ForeignKey("fixed_income_investments.id"), nullable=False),
        sa.Column("lot_id", sa.Integer, nullable=False),
        sa.Column("owner_id", sa.Uuid, nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("principal_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("cash_received", sa.Numeric(20, 8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lot_id", "investment_id"], ["fixed_income_lots.id", "fixed_income_lots.investment_id"], name="fi_movement_lot_fk"),
        sa.CheckConstraint("kind IN ('APPLICATION', 'REDEMPTION')", name="fi_movement_kind"),
        sa.CheckConstraint("principal_amount > 0 AND principal_amount <= 999999999999.99999999", name="fi_principal_positive"),
        sa.CheckConstraint("cash_received IS NULL OR (kind = 'REDEMPTION' AND cash_received >= 0 AND cash_received <= 999999999999.99999999)", name="fi_cash_redemption"))
    for table in TABLES:
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])
    op.create_index("ix_fixed_income_lots_investment_id", TABLES[1], ["investment_id"])
    op.create_index("ix_fixed_income_movements_lot_id", TABLES[2], ["lot_id"])
    op.create_index("ix_fi_movements_chronology", TABLES[2], ["investment_id", "date", "id"])
    op.create_index("fi_one_application_per_lot", TABLES[2], ["lot_id"], unique=True, postgresql_where=sa.text("kind = 'APPLICATION'"))

    # Invoker functions: never bypass RLS. Fully qualified objects, no dynamic identifiers.
    op.execute("""CREATE FUNCTION public.fi_reject_mutation() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
    BEGIN RAISE EXCEPTION 'Fixed-income ledger is append-only' USING ERRCODE = '23514'; END; $$""")
    op.execute("""CREATE FUNCTION public.fi_validate_contract() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
    BEGIN
      IF NEW.application_date > (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date THEN
        RAISE EXCEPTION 'Future application date' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END; $$""")
    op.execute("""CREATE FUNCTION public.fi_validate_lot() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
    DECLARE contract public.fixed_income_investments%ROWTYPE;
    BEGIN
      SELECT * INTO contract FROM public.fixed_income_investments WHERE id = NEW.investment_id;
      IF NOT FOUND OR contract.owner_id IS DISTINCT FROM NEW.owner_id
         OR NEW.application_date < contract.application_date OR NEW.application_date > contract.maturity_date
         OR NEW.application_date > (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date THEN
        RAISE EXCEPTION 'Invalid lot contract, owner or date' USING ERRCODE = '23514';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM public.fixed_income_movements WHERE investment_id = NEW.investment_id)
         AND NEW.application_date <> contract.application_date THEN
        RAISE EXCEPTION 'First application must match contract date' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END; $$""")
    op.execute("""CREATE FUNCTION public.fi_require_application() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM public.fixed_income_movements WHERE lot_id = NEW.id AND kind = 'APPLICATION') THEN
        RAISE EXCEPTION 'Lot requires an application in the same transaction' USING ERRCODE = '23514';
      END IF;
      RETURN NULL;
    END; $$""")
    op.execute("""CREATE FUNCTION public.fi_validate_movement() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
    DECLARE lot public.fixed_income_lots%ROWTYPE; last_date date; balance numeric;
    BEGIN
      IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Fixed-income writes require READ COMMITTED isolation' USING ERRCODE = '23514';
      END IF;
      PERFORM pg_advisory_xact_lock(20001, NEW.investment_id);
      SELECT * INTO lot FROM public.fixed_income_lots WHERE id = NEW.lot_id;
      IF NOT FOUND OR lot.investment_id <> NEW.investment_id OR lot.owner_id IS DISTINCT FROM NEW.owner_id
         OR NEW.date < lot.application_date
         OR NEW.date > (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date THEN
        RAISE EXCEPTION 'Invalid movement lot, owner or date' USING ERRCODE = '23514';
      END IF;
      SELECT max(date) INTO last_date FROM public.fixed_income_movements WHERE investment_id = NEW.investment_id;
      IF NEW.date < last_date THEN
        RAISE EXCEPTION 'Retroactive movement is not allowed' USING ERRCODE = '23514';
      END IF;
      IF NEW.kind = 'APPLICATION' THEN
        IF NEW.date <> lot.application_date THEN
          RAISE EXCEPTION 'Application must match lot date' USING ERRCODE = '23514';
        END IF;
      ELSE
        SELECT coalesce(sum(CASE WHEN kind = 'APPLICATION' THEN principal_amount ELSE -principal_amount END), 0)
          INTO balance FROM public.fixed_income_movements WHERE lot_id = NEW.lot_id;
        IF NEW.principal_amount > balance THEN
          RAISE EXCEPTION 'Redemption exceeds available principal' USING ERRCODE = '23514';
        END IF;
      END IF;
      RETURN NEW;
    END; $$""")
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        rule = "(owner_id = NULLIF(current_setting('app.user_id', true), '')::uuid OR (owner_id IS NULL AND current_setting('app.auth_mode', true) = 'local'))"
        op.execute(f"CREATE POLICY api_owner ON public.{table} FOR ALL USING ({rule}) WITH CHECK ({rule})")
        op.execute(f"CREATE TRIGGER fi_append_only BEFORE UPDATE OR DELETE ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.fi_reject_mutation()")
        op.execute(f"CREATE TRIGGER fi_no_truncate BEFORE TRUNCATE ON public.{table} FOR EACH STATEMENT EXECUTE FUNCTION public.fi_reject_mutation()")
        # Supabase may have default grants; revoke only on these new objects, atomically.
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
        op.execute(f"REVOKE ALL ON SEQUENCE public.{table}_id_seq FROM PUBLIC")
        for role in ("anon", "authenticated", "service_role"):
            op.execute(f"""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
              REVOKE ALL ON TABLE public.{table} FROM {role};
              REVOKE ALL ON SEQUENCE public.{table}_id_seq FROM {role};
            END IF; END; $$""")
    op.execute("CREATE TRIGGER fi_contract_insert BEFORE INSERT ON public.fixed_income_investments FOR EACH ROW EXECUTE FUNCTION public.fi_validate_contract()")
    op.execute("CREATE TRIGGER fi_lot_insert BEFORE INSERT ON public.fixed_income_lots FOR EACH ROW EXECUTE FUNCTION public.fi_validate_lot()")
    op.execute("CREATE CONSTRAINT TRIGGER fi_lot_application AFTER INSERT ON public.fixed_income_lots DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.fi_require_application()")
    op.execute("CREATE TRIGGER fi_movement_insert BEFORE INSERT ON public.fixed_income_movements FOR EACH ROW EXECUTE FUNCTION public.fi_validate_movement()")
    for function in ("fi_reject_mutation", "fi_validate_contract", "fi_validate_lot", "fi_require_application", "fi_validate_movement"):
        op.execute(f"REVOKE ALL ON FUNCTION public.{function}() FROM PUBLIC")


def downgrade():
    raise RuntimeError("Downgrade destrutivo bloqueado; preservar histórico e usar migration corretiva")
