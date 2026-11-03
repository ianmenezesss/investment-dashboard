"""Exact backup catalogs and isolated configuration of the read-only archive CLI."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

try:
    from .backup_archive import MAGIC, MAGIC_010, MAGIC_011, MAGIC_012, MAGIC_013, MAGIC_014, MAGIC_015, MAGIC_016, MAGIC_018
except ImportError:
    from backup_archive import MAGIC, MAGIC_010, MAGIC_011, MAGIC_012, MAGIC_013, MAGIC_014, MAGIC_015, MAGIC_016, MAGIC_018


TABLES_009 = frozenset({
    "alembic_version", "operations", "fixed_income_investments", "fixed_income_lots",
    "fixed_income_movements", "fixed_income_observations", "fixed_income_investment_archives",
    "fixed_income_application_revisions", "financial_events", "financial_event_revisions",
})
TABLES_010 = TABLES_009 | {"portfolio_valuation_observations"}
TABLES_011 = TABLES_010 | {"account_members", "account_invitations"}
TABLES_012 = TABLES_011 | {"account_deletion_jobs", "account_deletion_audit", "account_fixture_loads"}
TABLES_013 = TABLES_012 | {"account_access_requests", "account_access_request_limits"}
TABLES_014 = TABLES_013
TABLES_015 = TABLES_014 | {"account_invitation_send_attempts"}
# Migration 018 stores assistant quotas/leases in account_members, whose full
# rows are dumped. It does not create a separate usage or lease table.
TABLES_018 = TABLES_015 | {"account_access_administrators", "account_access_audit"}
VERSIONS = {
    MAGIC: ("009", TABLES_009), MAGIC_010: ("010", TABLES_010),
    MAGIC_011: ("011", TABLES_011), MAGIC_012: ("012", TABLES_012),
    MAGIC_013: ("013", TABLES_013), MAGIC_014: ("014", TABLES_014),
    MAGIC_015: ("015", TABLES_015), MAGIC_016: ("016", TABLES_015), MAGIC_018: ("018", TABLES_018),
}

DELETION_EXECUTOR_FUNCTIONS = (
    "dashboard_account_deletion_state(uuid)", "begin_dashboard_account_deletion(uuid,text)",
    "purge_dashboard_account_data(uuid)", "mark_dashboard_auth_identity_deleted(uuid)",
    "finish_dashboard_account_deletion(uuid)",
)
ACCESS_EXECUTOR_FUNCTIONS = (
    "dashboard_admin_authorized()", "revoke_dashboard_account(uuid,uuid)",
    "reserve_dashboard_reactivation(uuid,uuid,uuid,text)",
    "reserve_dashboard_assistant_request(uuid,uuid,integer,integer,integer)",
    "release_dashboard_assistant_request(uuid,uuid)",
)


def executor_function_signatures(revision: str) -> tuple[str, ...]:
    if revision not in {version for version, _tables in VERSIONS.values()}:
        raise ValueError("Revisão de backup não suportada")
    return (() if int(revision) < 12 else DELETION_EXECUTOR_FUNCTIONS
            + (ACCESS_EXECUTOR_FUNCTIONS if revision == "018" else
               ("revoke_dashboard_account(uuid,uuid)", "reserve_dashboard_reactivation(uuid,uuid,uuid,text)")
               if revision == "016" else ()))


def configure_backup(revision: str):
    profile = next(((magic, tables) for magic, (version, tables) in VERSIONS.items() if version == revision), None)
    if profile is None:
        raise ValueError("Revisão de backup não suportada")
    # Each profile gets its own function globals. A newer backup must never
    # silently change the preflight or table requirements of an older profile.
    name = f"{__package__}._backup_profile_{revision}" if __package__ else f"_backup_profile_{revision}"
    spec = spec_from_file_location(name, Path(__file__).with_name("backup_supabase_009.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError("Implementação de backup indisponível")
    configured = module_from_spec(spec)
    spec.loader.exec_module(configured)
    configured.REVISION = revision
    configured.MAGIC, tables = profile
    configured.REQUIRED_TABLES = set(tables)
    return configured
