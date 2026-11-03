"""Current and repaired backup profiles; synthetic archives only, no network."""
import importlib
import io
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import backup_supabase_009 as legacy
from scripts.backup_archive import MAGIC, MAGIC_014, MAGIC_015, MAGIC_016, MAGIC_018, SUPPORTED_MAGICS, decrypt_stream, encrypt_stream
from scripts.backup_profiles import VERSIONS, executor_function_signatures
import restore_supabase_backup as restore


def test_catalog_covers_every_authenticated_marker_without_accepting_unversioned_heads():
    assert set(VERSIONS) == set(SUPPORTED_MAGICS) == set(restore.VERSIONS)
    assert {revision for revision, _tables in VERSIONS.values()} == {"009", "010", "011", "012", "013", "014", "015", "016", "018"}


@pytest.mark.parametrize("revision,magic", [("014", MAGIC_014), ("015", MAGIC_015), ("016", MAGIC_016), ("018", MAGIC_018)])
def test_profile_requires_exact_revision_tables_and_matching_restorer(revision, magic):
    wrapper = importlib.import_module(f"scripts.backup_supabase_{revision}")
    configured = wrapper.configure()
    assert configured.REVISION == revision
    assert configured.MAGIC == magic
    assert configured.REQUIRED_TABLES == VERSIONS[magic][1] == restore.VERSIONS[magic][1]
    assert configured.preflight_failures(("postgres", "17", revision, "backup_reader"), "postgres") == []
    for wrong_revision in {"009", "013", "015", "016", "018"} - {revision}:
        assert configured.preflight_failures(("postgres", "17", wrong_revision, "backup_reader"), "postgres") == ["alembic_version"]
        with pytest.raises(ValueError, match="Alembic"):
            configured.parse_archived_alembic_version(f"COPY public.alembic_version (version_num) FROM stdin;\n{wrong_revision}\n\\.\n")


def test_profile_configuration_does_not_contaminate_older_format_globals():
    before = legacy.REVISION, legacy.MAGIC, set(legacy.REQUIRED_TABLES)
    current = importlib.import_module("scripts.backup_supabase_018").configure()
    repaired = importlib.import_module("scripts.backup_supabase_014").configure()
    assert (legacy.REVISION, legacy.MAGIC, legacy.REQUIRED_TABLES) == before
    assert current.REVISION == "018" and repaired.REVISION == "014"
    assert "account_access_audit" in current.REQUIRED_TABLES
    assert "account_access_audit" not in repaired.REQUIRED_TABLES
    assert current.parse_archived_alembic_version("COPY public.alembic_version (version_num) FROM stdin;\n018\n\\.\n") == "018"
    assert repaired.parse_archived_alembic_version("COPY public.alembic_version (version_num) FROM stdin;\n014\n\\.\n") == "014"


def test_head018_dump_requires_audit_registry_and_full_membership_table():
    configured = importlib.import_module("scripts.backup_supabase_018").configure()
    assert {"account_access_administrators", "account_access_audit", "account_members", "account_invitation_send_attempts"} <= configured.REQUIRED_TABLES
    names = sorted(configured.REQUIRED_TABLES)
    toc = "\n".join(
        [f"{100+i}; 1259 10 TABLE public {name} postgres" for i, name in enumerate(names)]
        + [f"{200+i}; 0 10 TABLE DATA public {name} postgres" for i, name in enumerate(names)]
    )
    assert configured.parse_toc(toc) == (set(names), set(names))
    missing_audit_data = "\n".join(line for line in toc.splitlines() if "TABLE DATA public account_access_audit " not in line)
    assert configured.parse_toc(missing_audit_data)[1] != configured.REQUIRED_TABLES


@pytest.mark.parametrize("magic", [MAGIC_014, MAGIC_015, MAGIC_016, MAGIC_018])
def test_repaired_and_current_archive_formats_round_trip_and_cannot_be_relabelled(tmp_path, magic):
    output = tmp_path / f"synthetic-{magic.decode()}.idbackup"
    payload = b"synthetic custom archive including all public schema rows"
    with output.open("wb") as destination:
        encrypt_stream(io.BytesIO(payload), destination, "Synthetic-only-passphrase-2026", magic=magic)
    assert restore.validate_backup(output) == output.resolve()
    assert restore.archive_version(output) == VERSIONS[magic][0]
    plaintext = io.BytesIO()
    decrypt_stream(io.BytesIO(output.read_bytes()), plaintext, "Synthetic-only-passphrase-2026")
    assert plaintext.getvalue() == payload
    changed = MAGIC + output.read_bytes()[len(MAGIC):]
    if magic != MAGIC:
        with pytest.raises(ValueError, match="Autenticação"):
            decrypt_stream(io.BytesIO(changed), io.BytesIO(), "Synthetic-only-passphrase-2026")


def test_restore_reinstates_all_new_restricted_function_owners_only_for_head018():
    current = set(executor_function_signatures("018"))
    previous = set(executor_function_signatures("015"))
    assert len(previous) == 5
    assert current - previous == {
        "dashboard_admin_authorized()", "revoke_dashboard_account(uuid,uuid)",
        "reserve_dashboard_reactivation(uuid,uuid,uuid,text)",
        "reserve_dashboard_assistant_request(uuid,uuid,integer,integer,integer)",
        "release_dashboard_assistant_request(uuid,uuid)",
    }
    assert executor_function_signatures("009") == ()
    with pytest.raises(ValueError, match="não suportada"):
        executor_function_signatures("017")
    assert len(executor_function_signatures("016")) == 7


@pytest.mark.parametrize("revision", ["014", "015", "016", "018"])
def test_repaired_backup_cli_help_runs_from_any_directory_without_connections(tmp_path, revision):
    script = Path(__file__).resolve().parents[1] / "scripts" / f"backup_supabase_{revision}.py"
    result = subprocess.run([sys.executable, str(script), "--help"], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert f"PostgreSQL {revision}" in result.stdout
    assert "--output" in result.stdout
    assert "SUPABASE" not in result.stderr
