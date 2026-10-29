"""Restore a user-provided Supabase custom dump into an isolated local PostgreSQL 17."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from uuid import uuid4


BACKUP = Path(r"E:\Users\IAN\Backups\InvestmentDashboard\investment-dashboard-pre-004-2026-10-28_14-23.dump")
MIGRATION_TABLES = {
    "001": {"operations"},
    "002": {"operations"},
    "003": {"operations", "fixed_income_investments", "fixed_income_lots", "fixed_income_movements"},
    "004": {"operations", "fixed_income_investments", "fixed_income_lots", "fixed_income_movements", "fixed_income_observations"},
    "005": {"operations", "fixed_income_investments", "fixed_income_lots", "fixed_income_movements", "fixed_income_observations", "fixed_income_investment_archives"},
    "006": {"operations", "fixed_income_investments", "fixed_income_lots", "fixed_income_movements", "fixed_income_observations", "fixed_income_investment_archives", "fixed_income_application_revisions"},
    "007": {"operations", "fixed_income_investments", "fixed_income_lots", "fixed_income_movements", "fixed_income_observations", "fixed_income_investment_archives", "fixed_income_application_revisions"},
    "008": {"operations", "fixed_income_investments", "fixed_income_lots", "fixed_income_movements", "fixed_income_observations", "fixed_income_investment_archives", "fixed_income_application_revisions"},
}
PROJECT_TABLES = set().union(*MIGRATION_TABLES.values())


def safe_output(value, password):
    text = (value or "").decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")
    text = text.replace(password, "[REDACTED]")
    text = re.sub(r"(?i)(postgres(?:ql)?://[^\s:/@]+:)[^@\s]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"(?i)(authorization\s*[=:]\s*Bearer\s+)[^\s,;]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)((?:password|passwd|token|secret|api[_-]?key|authorization)\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[REDACTED]", text)
    # PostgreSQL DETAIL/CONTEXT/STATEMENT may contain real row values.
    text = re.sub(r"(?im)^\s*(DETAIL|CONTEXT|STATEMENT|HINT):.*$", r"\1: [REDACTED]", text)
    return text[:3000]


def postgres_restore_args(container, database, password):
    return ("exec", "-e", f"PGPASSWORD={password}", container, "pg_restore", "--exit-on-error", "--schema=public",
            "--no-owner", "--no-privileges", "-h", "127.0.0.1", "-p", "5432",
            "-U", "postgres", "-d", database, "/backup/input.dump")


def docker_run_args(container, database, password, backup, run_id):
    return ("run", "--pull=never", "-d", "--rm", "--name", container,
            "--label", f"com.investment-dashboard.realbackup={run_id}", "--network", "none",
            "-e", f"POSTGRES_PASSWORD={password}", "-e", f"POSTGRES_DB={database}",
            "--tmpfs", "/var/lib/postgresql/data", "--mount",
            f"type=bind,source={backup},target=/backup/input.dump,readonly", "postgres:17-alpine")


def psql_command(container, database, sql):
    return ["docker", "exec", "-e", "PGPASSWORD=disposable", container, "psql", "-X",
            "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1", "-p", "5432", "-U", "postgres",
            "-d", database, "-At", "-c", sql]


def parse_archive_index(toc):
    """Return public project tables and their TABLE DATA entries from pg_restore --list."""
    table_names, data_names = set(), set()
    entry = re.compile(r"^\s*(?:;\s*)?\d+;\s+\d+\s+\d+\s+(TABLE(?: DATA)?)\s+(\S+)\s+(\S+)\s+(\S+)\s*$")
    for line in toc.splitlines():
        match = entry.match(line)
        if match:
            kind, schema, table, _owner = match.groups()
            if schema == "public" and table in PROJECT_TABLES | {"alembic_version"}:
                (data_names if kind == "TABLE DATA" else table_names).add(table)
    return table_names, data_names


def expected_tables_for_revision(revision):
    try:
        return MIGRATION_TABLES[revision]
    except KeyError as exc:
        raise RuntimeError(f"Versão Alembic não mapeada para validação: {revision}") from exc


def validate_archive_schema(revision, archive_tables, restored_tables):
    expected = expected_tables_for_revision(revision)
    archive_tables = archive_tables & PROJECT_TABLES
    restored_tables = restored_tables & PROJECT_TABLES
    missing_from_archive = sorted(expected - archive_tables)
    if missing_from_archive:
        raise RuntimeError(f"Índice do dump incompleto para Alembic {revision}; tabelas esperadas ausentes: {', '.join(missing_from_archive)}")
    extra_in_archive = sorted(archive_tables - expected)
    if extra_in_archive:
        raise RuntimeError(f"Índice do dump contém tabelas posteriores/incompatíveis com Alembic {revision}: {', '.join(extra_in_archive)}")
    missing = sorted(expected - restored_tables)
    if missing:
        raise RuntimeError(f"Restore incompleto para Alembic {revision}; tabelas esperadas no schema restaurado ausentes: " + ", ".join(missing))
    unexpected = sorted(restored_tables - expected)
    if unexpected:
        raise RuntimeError(f"Schema restaurado não corresponde ao Alembic {revision}; tabelas inesperadas: " + ", ".join(unexpected))
    return expected


def main():
    temp = Path(os.environ.get("INVESTMENT_TEMP_DIR", ""))
    if not temp.is_dir() or (os.name == "nt" and str(temp.resolve()).lower() != r"e:\investmentdashboard\temp"):
        raise RuntimeError("INVESTMENT_TEMP_DIR deve ser E:\\InvestmentDashboard\\temp")
    if not BACKUP.is_file():
        raise RuntimeError(f"Backup não encontrado: {BACKUP}")
    if input("Este processo cria e remove somente um container/banco descartável local. Digite DESCARTAVEL para continuar: ").strip() != "DESCARTAVEL":
        raise RuntimeError("Confirmação DESCARTAVEL não recebida")
    run_id = uuid4().hex[:12]
    container = f"investment-realbackup-restore-{run_id}"
    name = f"investment_restore_{run_id}"
    password = secrets.token_urlsafe(24)
    created = False
    restore_ok = False
    schema_validation_started = False
    schema_ok = False
    log_path = temp / f"investment-realbackup-restore-{run_id}.log"
    lines = [f"Restore descartável de backup Supabase; run={run_id}",
             f"Backup SHA256={hashlib.sha256(BACKUP.read_bytes()).hexdigest()}; bytes={BACKUP.stat().st_size}"]

    def docker(*args, input_data=None):
        result = subprocess.run(["docker", *args], input=input_data, capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError(f"docker {args[0]} exit={result.returncode}: {safe_output(result.stderr or result.stdout,password)}")
        return result.stdout

    def exec_psql(sql, database="postgres"):
        command = psql_command(container, database, sql)
        command[3] = f"PGPASSWORD={password}"
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError(f"psql database={database} exit={result.returncode}: {safe_output(result.stderr,password)}")
        return result.stdout.strip()

    try:
        docker("info", "--format", "{{.ServerVersion}}")
        docker("image", "inspect", "postgres:17-alpine")
        docker(*docker_run_args(container, name, password, BACKUP, run_id))
        created = True
        for _ in range(60):
            probe = subprocess.run(["docker", "exec", container, "pg_isready", "-h", "127.0.0.1", "-p", "5432", "-U", "postgres", "-d", name], capture_output=True)
            if probe.returncode == 0:
                break
            time.sleep(0.5)
        else:
            logs = subprocess.run(["docker", "logs", "--tail", "80", container], capture_output=True, text=True, encoding="utf-8", errors="replace")
            raise RuntimeError(f"PostgreSQL descartável não ficou pronto; pg_isready={safe_output(probe.stderr,password)}; logs={safe_output(logs.stdout+logs.stderr,password)}")

        toc = docker("exec", container, "pg_restore", "--list", "/backup/input.dump")
        archive_tables, archive_data = parse_archive_index(toc)
        if not archive_tables:
            raise RuntimeError("Índice do dump não contém tabelas financeiras public reconhecidas")
        lines.append("Archive TOC project tables=" + json.dumps(sorted(archive_tables)))
        lines.append("Archive TOC table-data entries=" + json.dumps(sorted(archive_data)))

        roles_and_helpers = """CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN;
CREATE ROLE authenticator NOLOGIN NOINHERIT; CREATE ROLE investment_runtime LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE SCHEMA auth;
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS $$ SELECT COALESCE(NULLIF(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb) $$;
CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('request.jwt.claim.role',true),'') $$;
CREATE EXTENSION IF NOT EXISTS pgcrypto; CREATE EXTENSION IF NOT EXISTS "uuid-ossp";"""
        exec_psql(roles_and_helpers)
        lines.append("ROLES_AND_LOCAL_AUTH_SHIMS=CREATED (no auth user tables restored)")
        # Restore only project objects in public. Role ownership/ACLs are intentionally
        # not replayed; RLS policies and constraints are restored and verified below.
        restore_command = ["docker", *postgres_restore_args(container, name, password)]
        result = subprocess.run(restore_command,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError(f"pg_restore exit={result.returncode}: {safe_output(result.stderr,password)}")
        restore_ok = True
        schema_validation_started = True
        version_rows = exec_psql("SELECT row_to_json(v)::text FROM public.alembic_version v", name).splitlines()
        if len(version_rows) != 1:
            raise RuntimeError(f"Esperava uma única versão Alembic; linhas encontradas={len(version_rows)}")
        version = json.loads(version_rows[0])
        revision = str(version.get("version_num", ""))
        table_names = exec_psql("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' AND (table_name IN ('operations','alembic_version') OR table_name LIKE 'fixed_income_%') ORDER BY table_name", name).splitlines()
        restored_project_tables = set(table_names) & PROJECT_TABLES
        expected = validate_archive_schema(revision, archive_tables, restored_project_tables)
        counts = {}
        for table in table_names:
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
                raise RuntimeError("Nome de tabela inesperado no catálogo public")
            counts[table] = int(exec_psql(f'SELECT count(*) FROM public."{table}"', name))
        if not counts:
            raise RuntimeError("Restore terminou sem tabelas financeiras public para validar")
        missing_data_tables = sorted(archive_data - set(counts))
        if missing_data_tables:
            raise RuntimeError("Entradas TABLE DATA não recuperadas como tabelas consultáveis: " + ", ".join(missing_data_tables))
        constraints = int(exec_psql("SELECT count(*) FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid WHERE r.relnamespace='public'::regnamespace AND r.relname LIKE 'fixed_income_%' AND c.convalidated", name))
        unvalidated = int(exec_psql("SELECT count(*) FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid WHERE r.relnamespace='public'::regnamespace AND r.relname LIKE 'fixed_income_%' AND NOT c.convalidated", name))
        if constraints == 0:
            raise RuntimeError("Nenhuma constraint validada encontrada nas tabelas fixed_income_")
        if unvalidated:
            raise RuntimeError(f"Encontradas {unvalidated} constraints não validadas em tabelas fixed_income_")
        rls = exec_psql("SELECT relname || '=' || relrowsecurity || '/' || relforcerowsecurity FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p') AND (relname='operations' OR relname LIKE 'fixed_income_%') ORDER BY relname", name).splitlines()
        policies = int(exec_psql("SELECT count(*) FROM pg_policy p JOIN pg_class r ON r.oid=p.polrelid WHERE r.relnamespace='public'::regnamespace AND (r.relname='operations' OR r.relname LIKE 'fixed_income_%')", name))
        rls_state = dict(value.split("=", 1) for value in rls)
        expected_rls_tables = ({"operations"} if revision >= "002" else set()) | {
            table for table in expected if table.startswith("fixed_income_")
        }
        missing_rls = sorted(expected_rls_tables - rls_state.keys())
        unsafe_rls = sorted(table for table in expected_rls_tables if rls_state.get(table) != "true/true")
        if missing_rls or unsafe_rls:
            raise RuntimeError(f"RLS/FORCE RLS ausente ou desabilitado; ausentes={missing_rls}; inseguros={unsafe_rls}")
        if revision >= "002" and policies == 0:
            raise RuntimeError("Nenhuma policy RLS encontrada nas tabelas financeiras")
        extensions = exec_psql("SELECT extname FROM pg_extension ORDER BY extname", name).splitlines()
        schema_ok = True
        lines.append("Alembic=" + json.dumps(version, sort_keys=True))
        lines.append(f"Schema esperado pela migration {revision}=" + json.dumps(sorted(expected)))
        lines.append(f"Compatibilidade com head 008={'PASS' if revision == '008' else 'NOT_CURRENT'}")
        lines.append("Public project table row counts=" + json.dumps(counts, sort_keys=True))
        lines.append("Restored TABLE DATA entry row counts=" + json.dumps({table: counts[table] for table in sorted(archive_data)}, sort_keys=True))
        lines.append("TABLE_DATA_RECOVERY=PASS (pg_restore exit-on-error; all indexed data tables queryable)")
        lines.append(f"validated fixed-income constraints={constraints}; RLS policies={policies}")
        lines.append("RLS/FORCE RLS=" + json.dumps(rls))
        lines.append("Extensions=" + json.dumps(extensions))
        lines.append("Nota: identidade SQL e isolamento autenticado da aplicação não são homologados por este restore; ACLs são deliberadamente omitidas e políticas são verificadas no catálogo.")
        return_code = 0
    except Exception as exc:
        lines.append(safe_output(str(exc), password))
        return_code = 1
    finally:
        lines.append("RESTORE_OK=" + ("PASS" if restore_ok else "FAIL"))
        lines.append("VALIDACAO_SCHEMA_OK=" + ("PASS" if schema_ok else "FAIL" if schema_validation_started else "NOT_RUN"))
        if created:
            owned = subprocess.run(["docker", "inspect", "--format", '{{index .Config.Labels "com.investment-dashboard.realbackup"}}', container], capture_output=True, text=True)
            if owned.returncode == 0 and owned.stdout.strip() == run_id:
                subprocess.run(["docker", "stop", container], capture_output=True)
        log_path.write_text("\n".join(lines)+"\n", encoding="utf-8")
        print(f"Log: {log_path}; result={return_code if 'return_code' in locals() else 1}")
    return return_code if 'return_code' in locals() else 1


if __name__ == "__main__":
    sys.exit(main())
