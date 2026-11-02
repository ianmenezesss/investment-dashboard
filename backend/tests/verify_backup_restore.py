"""Read-only catalog, row/data fingerprint and owner-isolation checks for disposable restores."""
import hashlib
from sqlalchemy import create_engine, text


TABLES = (
    "operations", "fixed_income_investments", "fixed_income_lots",
    "fixed_income_movements", "fixed_income_observations",
    "fixed_income_investment_archives", "fixed_income_application_revisions",
    "financial_events", "financial_event_revisions", "portfolio_valuation_observations",
    "account_members", "account_invitations", "account_deletion_jobs",
    "account_deletion_audit", "account_fixture_loads", "account_access_requests", "account_access_request_limits",
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
            if result["head"] != "014":
                raise AssertionError("Banco restaurado não está no Alembic head 014")
            result["counts"] = {
                table: connection.scalar(text(f'SELECT count(*) FROM public."{table}"'))
                for table in TABLES
            }
            result["data_sha256"] = {}
            for table in TABLES:
                key = ("user_id" if table in ("account_members", "account_deletion_jobs", "account_fixture_loads")
                       else "scope_key" if table == "account_access_request_limits" else "id")
                rows = connection.execute(text(f'SELECT row_to_json(t)::text FROM (SELECT * FROM public."{table}" ORDER BY {key}) AS t')).scalars()
                digest = hashlib.sha256()
                for row in rows:
                    digest.update(row.encode("utf-8"))
                    digest.update(b"\n")
                result["data_sha256"][table] = digest.hexdigest()
            if not result["counts"]["fixed_income_movements"] or not result["counts"]["fixed_income_investments"]:
                raise AssertionError("Restore não contém fixtures fictícias de ledger")
            if not result["counts"]["financial_events"] or not result["counts"]["financial_event_revisions"]:
                raise AssertionError("Restore não contém fixtures fictícias de eventos financeiros/revisões")
            result["constraints"] = connection.scalar(text("""
                SELECT count(*) FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid
                WHERE r.relnamespace='public'::regnamespace AND (r.relname='operations' OR r.relname LIKE 'fixed_income_%' OR r.relname LIKE 'financial_event%')
                  AND c.convalidated
            """))
            if not result["constraints"]:
                raise AssertionError("Nenhuma constraint validada encontrada após restore")
            result["rls"] = {
                row[0]: (row[1], row[2]) for row in connection.execute(text("""
                SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class
                WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p')
                  AND (relname='operations' OR relname LIKE 'fixed_income_%' OR relname LIKE 'financial_event%' OR relname IN ('portfolio_valuation_observations','account_members','account_invitations','account_deletion_jobs','account_deletion_audit','account_fixture_loads'))
                ORDER BY relname
            """)).all()
            }
            if not result["rls"] or not all(flags == (True, True) for flags in result["rls"].values()):
                raise AssertionError("RLS/FORCE RLS não foi preservado nas tabelas de renda fixa")
            result["policies"] = connection.execute(text("""
                SELECT tablename, policyname, permissive, roles::text, cmd, qual, with_check
                FROM pg_policies WHERE schemaname='public'
                ORDER BY tablename, policyname
            """)).all()
            policy_tables = {row[0] for row in result["policies"]}
            if not set(result["rls"]).issubset(policy_tables):
                raise AssertionError("Policies RLS ausentes em tabelas financeiras")
            result["append_only_triggers"] = sorted(connection.execute(text("""
                SELECT c.relname || '.' || t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                WHERE NOT t.tgisinternal AND c.relname IN ('fixed_income_investment_archives','fixed_income_application_revisions','financial_events','financial_event_revisions','portfolio_valuation_observations')
            """)).scalars().all())
            if not any("fixed_income_investment_archives.fi_archive_append_only" == name for name in result["append_only_triggers"]):
                raise AssertionError("Trigger append-only de arquivamento ausente após restore")
            if not any("fixed_income_application_revisions.fi_revision_append_only" == name for name in result["append_only_triggers"]):
                raise AssertionError("Trigger append-only de revisões ausente após restore")
            if not any("financial_events.financial_events_append_only" == name for name in result["append_only_triggers"]):
                raise AssertionError("Trigger append-only de eventos financeiros ausente após restore")
            if not any("financial_event_revisions.financial_event_revisions_append_only" == name for name in result["append_only_triggers"]):
                raise AssertionError("Trigger append-only de revisões financeiras ausente após restore")
            if not any("portfolio_valuation_observations.portfolio_valuation_observations_append_only" == name for name in result["append_only_triggers"]):
                raise AssertionError("Trigger append-only de observações patrimoniais ausente após restore")
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
            result["account_grants"] = connection.execute(text("""
                SELECT has_table_privilege('investment_runtime','public.account_members','SELECT'),
                       has_table_privilege('investment_runtime','public.account_members','INSERT'),
                       has_table_privilege('investment_runtime','public.account_members','UPDATE'),
                       has_table_privilege('investment_runtime','public.account_invitations','SELECT'),
                       has_table_privilege('investment_runtime','public.account_invitations','INSERT'),
                       has_column_privilege('investment_runtime','public.account_invitations','revoked_at','UPDATE'),
                       has_table_privilege('investment_runtime','public.account_invitations','DELETE'),
                       has_function_privilege('investment_runtime','public.accept_dashboard_invitation(uuid,text)','EXECUTE'),
                       has_function_privilege('investment_runtime','public.revoke_dashboard_account(uuid,uuid)','EXECUTE'),
                       has_function_privilege('investment_runtime','public.consume_dashboard_assistant_quota(uuid)','EXECUTE')
            """)).one()
            if result["account_grants"] != (True, False, False, True, True, True, False, True, True, True):
                raise AssertionError("Grants do runtime de convites/membership estão excessivos ou incompletos")
            result["deletion_security"] = connection.execute(text("""
                SELECT has_function_privilege('investment_runtime','public.dashboard_account_deletion_state(uuid)','EXECUTE'),
                       has_function_privilege('investment_runtime','public.begin_dashboard_account_deletion(uuid,text)','EXECUTE'),
                       has_function_privilege('investment_runtime','public.purge_dashboard_account_data(uuid)','EXECUTE'),
                       has_function_privilege('investment_runtime','public.mark_dashboard_auth_identity_deleted(uuid)','EXECUTE'),
                       has_function_privilege('investment_runtime','public.finish_dashboard_account_deletion(uuid)','EXECUTE'),
                       has_table_privilege('investment_runtime','public.operations','DELETE'),
                       has_table_privilege('investment_runtime','public.financial_events','DELETE'),
                       has_table_privilege('investment_runtime','public.account_members','DELETE'),
                       has_table_privilege('investment_runtime','public.account_invitations','DELETE'),
                       has_table_privilege('investment_runtime','public.account_deletion_jobs','SELECT'),
                       has_table_privilege('investment_runtime','public.account_deletion_audit','SELECT'),
                       has_table_privilege('investment_runtime','public.account_fixture_loads','SELECT'),
                       has_table_privilege('investment_runtime','public.account_fixture_loads','INSERT'),
                       has_table_privilege('investment_runtime','public.account_fixture_loads','DELETE')
            """)).one()
            if result["deletion_security"] != (True, True, True, True, True, True, False, False, False, False, False, True, True, False):
                raise AssertionError("O escopo do procedimento de exclusão/loader divergiu dos grants aprovados")
            result["deletion_executor"] = connection.execute(text("""
                SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolreplication,
                       (SELECT count(*) FROM pg_auth_members m WHERE m.roleid=r.oid OR m.member=r.oid),
                       has_table_privilege(r.rolname,'public.operations','DELETE'),
                       has_table_privilege(r.rolname,'public.financial_events','DELETE'),
                       has_table_privilege(r.rolname,'public.operations','TRUNCATE')
                FROM pg_roles r WHERE rolname='investment_deletion_executor'
            """)).one()
            if result["deletion_executor"] != (False, False, False, False, False, False, 0, True, True, False):
                raise AssertionError("A role restrita de exclusão está configurada incorretamente")
            result["deletion_function_owners"] = connection.execute(text("""
                SELECT bool_and(prosecdef AND pg_get_userbyid(proowner)='investment_deletion_executor')
                FROM pg_proc WHERE oid IN (
                  'public.dashboard_account_deletion_state(uuid)'::regprocedure,
                  'public.begin_dashboard_account_deletion(uuid,text)'::regprocedure,
                  'public.purge_dashboard_account_data(uuid)'::regprocedure,
                  'public.mark_dashboard_auth_identity_deleted(uuid)'::regprocedure,
                  'public.finish_dashboard_account_deletion(uuid)'::regprocedure)
            """)).scalar_one()
            if result["deletion_function_owners"] is not True:
                raise AssertionError("Funções de exclusão não pertencem à role executor restrita")
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
                ("public.portfolio_valuation_observations", "public.portfolio_valuation_observations_id_seq"),
            ):
                grants = connection.execute(privilege_sql, {"table": table, "sequence": sequence}).one()
                if grants != (True, True, False, False, False, True):
                    raise AssertionError(f"Grants mínimos divergiram em {table}")
                result["grants"][table] = grants
                result["sequence_state"][sequence] = connection.execute(
                    text(f"SELECT last_value, is_called FROM {sequence}")
                ).one()

        with engine.begin() as connection:
            connection.execute(text("GRANT SELECT ON public.account_members, public.account_invitations TO investment_test_runtime"))
        result["owner_visible"] = {}
        for owner in OWNERS:
            with engine.begin() as connection:
                connection.execute(text("SET LOCAL ROLE investment_test_runtime"))
                connection.execute(text("SELECT set_config('app.auth_mode','supabase',true), set_config('app.user_id',:owner,true), set_config('app.admin_id',:admin,true)"), {"owner": owner, "admin": owner if owner == OWNERS[0] else ""})
                visible = connection.scalar(text("SELECT count(*) FROM public.fixed_income_investments"))
                foreign = connection.scalar(text("SELECT count(*) FROM public.fixed_income_investments WHERE owner_id <> CAST(:owner AS uuid)"), {"owner": owner})
                archive_foreign = connection.scalar(text("SELECT count(*) FROM public.fixed_income_investment_archives WHERE owner_id <> CAST(:owner AS uuid)"), {"owner": owner})
                financial_visible = connection.scalar(text("SELECT count(*) FROM public.financial_events"))
                financial_foreign = connection.scalar(text("SELECT count(*) FROM public.financial_events WHERE owner_id <> CAST(:owner AS uuid)"), {"owner": owner})
                revisions_visible = connection.scalar(text("SELECT count(*) FROM public.financial_event_revisions"))
                revision_foreign = connection.scalar(text("SELECT count(*) FROM public.financial_event_revisions WHERE owner_id <> CAST(:owner AS uuid)"), {"owner": owner})
                wealth_visible = connection.scalar(text("SELECT count(*) FROM public.portfolio_valuation_observations"))
                wealth_foreign = connection.scalar(text("SELECT count(*) FROM public.portfolio_valuation_observations WHERE owner_id <> CAST(:owner AS uuid)"), {"owner": owner})
                member_visible = connection.scalar(text("SELECT count(*) FROM public.account_members"))
                own_member_visible = connection.scalar(text("SELECT count(*) FROM public.account_members WHERE user_id=CAST(:owner AS uuid)"), {"owner": owner})
                foreign_member_visible = connection.scalar(text("SELECT count(*) FROM public.account_members WHERE user_id<>CAST(:owner AS uuid)"), {"owner": owner})
                # Migration 014 permits an allowlisted admin transaction to read
                # all membership rows; regular members still see only themselves.
                expected_member_total = result["counts"]["account_members"] if owner == OWNERS[0] else 1
                expected_foreign_members = expected_member_total - 1
                if own_member_visible != 1 or foreign_member_visible != expected_foreign_members or member_visible != expected_member_total:
                    raise AssertionError(f"Isolamento RLS de membership falhou no restore (admin={owner == OWNERS[0]}, own={own_member_visible}, foreign={foreign_member_visible}, total={member_visible})")
                invite_visible = connection.scalar(text("SELECT count(*) FROM public.account_invitations"))
                if (owner == OWNERS[0] and invite_visible < 1) or (owner != OWNERS[0] and invite_visible != 0):
                    raise AssertionError("Isolamento RLS de convites administrativos falhou no restore")
                if not visible or not financial_visible or not revisions_visible or foreign or archive_foreign or financial_foreign or revision_foreign:
                    raise AssertionError("Isolamento RLS por proprietário falhou no restore")
                if wealth_visible != (1 if owner == OWNERS[0] else 0) or wealth_foreign:
                    raise AssertionError("Isolamento RLS das observações patrimoniais falhou no restore")
                result["owner_visible"][owner] = (visible, foreign, archive_foreign, financial_visible, financial_foreign,
                                                   revisions_visible, revision_foreign, wealth_visible, wealth_foreign)
        return result
    finally:
        engine.dispose()
