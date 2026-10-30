"""Read-only catalog, row/data fingerprint and owner-isolation checks for disposable restores."""
import hashlib
from sqlalchemy import create_engine, text


TABLES = (
    "operations", "fixed_income_investments", "fixed_income_lots",
    "fixed_income_movements", "fixed_income_observations",
    "fixed_income_investment_archives", "fixed_income_application_revisions",
    "financial_events", "financial_event_revisions",
)
OWNERS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
)


def snapshot(url: str) -> dict:
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    try:
        with engine.connect() as connection:
            result = {"head": connection.scalar(text("SELECT version_num FROM alembic_version"))}
            if result["head"] != "009":
                raise AssertionError("Banco restaurado não está no Alembic head 009")
            result["counts"] = {
                table: connection.scalar(text(f'SELECT count(*) FROM public."{table}"'))
                for table in TABLES
            }
            result["data_sha256"] = {}
            for table in TABLES:
                rows = connection.execute(text(f'SELECT row_to_json(t)::text FROM (SELECT * FROM public."{table}" ORDER BY id) AS t')).scalars()
                digest = hashlib.sha256()
                for row in rows:
                    digest.update(row.encode("utf-8"))
                    digest.update(b"\n")
                result["data_sha256"][table] = digest.hexdigest()
            if not result["counts"]["fixed_income_movements"] or not result["counts"]["fixed_income_investments"]:
                raise AssertionError("Restore não contém fixtures fictícias de ledger")
            result["constraints"] = connection.scalar(text("""
                SELECT count(*) FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid
                WHERE r.relnamespace='public'::regnamespace AND (r.relname LIKE 'fixed_income_%' OR r.relname LIKE 'financial_event%')
                  AND c.convalidated
            """))
            if not result["constraints"]:
                raise AssertionError("Nenhuma constraint validada encontrada após restore")
            result["rls"] = {
                row[0]: (row[1], row[2]) for row in connection.execute(text("""
                SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class
                WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p')
                  AND (relname LIKE 'fixed_income_%' OR relname LIKE 'financial_event%')
                ORDER BY relname
            """)).all()
            }
            if not result["rls"] or not all(flags == (True, True) for flags in result["rls"].values()):
                raise AssertionError("RLS/FORCE RLS não foi preservado nas tabelas de renda fixa")
            result["append_only_triggers"] = sorted(connection.execute(text("""
                SELECT c.relname || '.' || t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                WHERE NOT t.tgisinternal AND c.relname IN ('fixed_income_investment_archives','fixed_income_application_revisions','financial_events','financial_event_revisions')
            """)).scalars().all())
            if not any("fixed_income_investment_archives.fi_archive_append_only" == name for name in result["append_only_triggers"]):
                raise AssertionError("Trigger append-only de arquivamento ausente após restore")
            if not any("fixed_income_application_revisions.fi_revision_append_only" == name for name in result["append_only_triggers"]):
                raise AssertionError("Trigger append-only de revisões ausente após restore")
            if not any("financial_events.financial_events_append_only" == name for name in result["append_only_triggers"]):
                raise AssertionError("Trigger append-only de eventos financeiros ausente após restore")
            if not any("financial_event_revisions.financial_event_revisions_append_only" == name for name in result["append_only_triggers"]):
                raise AssertionError("Trigger append-only de revisões financeiras ausente após restore")
            result["runtime_role"] = connection.execute(text("""
                SELECT rolcanlogin, rolinherit, rolsuper, rolbypassrls,
                       rolcreatedb, rolcreaterole, rolreplication,
                       (SELECT count(*) FROM pg_auth_members m WHERE m.member=r.oid)
                FROM pg_roles r WHERE rolname='investment_runtime'
            """)).one()
            if result["runtime_role"] != (True, False, False, False, False, False, False, 0):
                raise AssertionError("A role investment_runtime perdeu atributos restritos")
            if not connection.scalar(text("SELECT has_schema_privilege('investment_runtime','public','USAGE')")):
                raise AssertionError("USAGE de schema necessário para runtime não foi preservado")
            projection = connection.execute(text("""
                SELECT has_function_privilege('investment_runtime','public.fi_effective_movements()','EXECUTE'),
                       NOT prosecdef
                FROM pg_proc WHERE oid='public.fi_effective_movements()'::regprocedure
            """)).one()
            if projection != (True, True):
                raise AssertionError("Grant ou SECURITY INVOKER da projeção efetiva divergiu")
            result["projection"] = projection
            privilege_sql = text("""
                SELECT has_table_privilege('investment_runtime',:table,'SELECT'),
                       has_table_privilege('investment_runtime',:table,'INSERT'),
                       has_table_privilege('investment_runtime',:table,'UPDATE'),
                       has_table_privilege('investment_runtime',:table,'DELETE'),
                       has_table_privilege('investment_runtime',:table,'TRUNCATE'),
                       has_sequence_privilege('investment_runtime',:sequence,'USAGE')
            """)
            result["grants"] = {}
            result["sequence_state"] = {}
            for table, sequence in (
                ("public.fixed_income_investment_archives", "public.fixed_income_investment_archives_id_seq"),
                ("public.fixed_income_application_revisions", "public.fixed_income_application_revisions_id_seq"),
                ("public.financial_events", "public.financial_events_id_seq"),
                ("public.financial_event_revisions", "public.financial_event_revisions_id_seq"),
            ):
                grants = connection.execute(privilege_sql, {"table": table, "sequence": sequence}).one()
                if grants != (True, True, False, False, False, True):
                    raise AssertionError(f"Grants mínimos divergiram em {table}")
                result["grants"][table] = grants
                result["sequence_state"][sequence] = connection.execute(
                    text(f"SELECT last_value, is_called FROM {sequence}")
                ).one()

        result["owner_visible"] = {}
        for owner in OWNERS:
            with engine.begin() as connection:
                connection.execute(text("SET LOCAL ROLE investment_test_runtime"))
                connection.execute(text("SELECT set_config('app.auth_mode','supabase',true), set_config('app.user_id',:owner,true)"), {"owner": owner})
                visible = connection.scalar(text("SELECT count(*) FROM public.fixed_income_investments"))
                foreign = connection.scalar(text("SELECT count(*) FROM public.fixed_income_investments WHERE owner_id <> CAST(:owner AS uuid)"), {"owner": owner})
                archive_foreign = connection.scalar(text("SELECT count(*) FROM public.fixed_income_investment_archives WHERE owner_id <> CAST(:owner AS uuid)"), {"owner": owner})
                financial_visible = connection.scalar(text("SELECT count(*) FROM public.financial_events"))
                financial_foreign = connection.scalar(text("SELECT count(*) FROM public.financial_events WHERE owner_id <> CAST(:owner AS uuid)"), {"owner": owner})
                revision_foreign = connection.scalar(text("SELECT count(*) FROM public.financial_event_revisions WHERE owner_id <> CAST(:owner AS uuid)"), {"owner": owner})
                if not visible or foreign or archive_foreign or financial_foreign or revision_foreign:
                    raise AssertionError("Isolamento RLS por proprietário falhou no restore")
                result["owner_visible"][owner] = (visible, foreign, archive_foreign, financial_visible, financial_foreign, revision_foreign)
        return result
    finally:
        engine.dispose()
