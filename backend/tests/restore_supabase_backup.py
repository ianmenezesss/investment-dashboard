"""Authenticate and restore one encrypted Alembic-009 archive into disposable PostgreSQL."""
import argparse
import getpass
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from uuid import uuid4


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backup_archive import MAGIC, decrypt_stream, sha256_file


REQUIRED_TABLES = {
    "alembic_version", "operations", "fixed_income_investments", "fixed_income_lots",
    "fixed_income_movements", "fixed_income_observations", "fixed_income_investment_archives",
    "fixed_income_application_revisions", "financial_events", "financial_event_revisions",
}
RLS_TABLES = REQUIRED_TABLES - {"alembic_version"}
EVENTS = {"financial_events", "financial_event_revisions"}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Restore an encrypted backup only into a disposable local PostgreSQL")
    parser.add_argument("--backup", required=True, type=Path, help="Existing .idbackup archive outside the repository")
    parser.add_argument("--sha256", help="Optional expected SHA-256 of the encrypted file")
    return parser.parse_args(argv)


def safe_output(value, secrets_to_redact=()):
    text = (value or "").decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")
    if isinstance(secrets_to_redact, str):
        secrets_to_redact = (secrets_to_redact,)
    for secret in secrets_to_redact:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)postgres(?:ql)?(?:\+[^:/@]+)?://[^\s'\"]+", "[DATABASE_URL REDACTED]", text)
    text = re.sub(r"(?i)Authorization:\s*Bearer\s+\S+", "Authorization: Bearer [REDACTED]", text)
    text = re.sub(r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"(?im)^\s*(DETAIL|CONTEXT|STATEMENT|HINT):.*$", r"\1: [REDACTED]", text)
    return text[:2500]


def validate_backup(path, expected_hash=None):
    backup = path.expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        backup.relative_to(repo_root)
    except ValueError:
        pass
    else:
        raise RuntimeError("O backup precisa estar fora do repositório")
    if backup.suffix.lower() != ".idbackup" or not backup.is_file() or backup.stat().st_size <= len(MAGIC) + 28:
        raise RuntimeError("Informe um arquivo .idbackup existente e não vazio")
    if expected_hash:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
            raise RuntimeError("--sha256 precisa conter exatamente 64 dígitos hexadecimais")
        if sha256_file(backup).lower() != expected_hash.lower():
            raise RuntimeError("SHA-256 do arquivo criptografado não confere")
    with backup.open("rb") as source:
        if source.read(len(MAGIC)) != MAGIC:
            raise RuntimeError("Cabeçalho do backup não corresponde a IDBKP009")
    return backup


def run_docker(*args, input_data=None, env=None):
    result = subprocess.run(["docker", *args], input=input_data, capture_output=True,
                            text=isinstance(input_data, str) or input_data is None,
                            encoding="utf-8" if input_data is None or isinstance(input_data, str) else None,
                            errors="replace" if input_data is None or isinstance(input_data, str) else None,
                            env=env)
    if result.returncode:
        raise RuntimeError(f"docker {args[0]} exit={result.returncode}: {safe_output(result.stderr or result.stdout)}")
    return result.stdout


def main(argv=None):
    args = parse_args(argv)
    backup = validate_backup(args.backup, args.sha256)
    passphrase = getpass.getpass("Frase de proteção do backup: ")
    if input("Este processo cria e remove somente um container PostgreSQL descartável. Digite DESCARTAVEL: ").strip() != "DESCARTAVEL":
        raise RuntimeError("Confirmação não recebida; nenhuma restauração iniciada")
    if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
        raise RuntimeError("DOCKER_HOST/DOCKER_CONTEXT definido; destino Docker não será presumido local")
    run_id = uuid4().hex[:12]
    name, database = f"investment-restore-009-{run_id}", f"investment_restore_{run_id}"
    label_key, label_value = "com.investment-dashboard.backup-restore", run_id
    password = secrets.token_urlsafe(24)
    env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in
           ("DATABASE_URL", "CONNECTION_STRING", "PASSWORD", "PASSWD", "TOKEN", "SECRET", "API_KEY", "SUPABASE_"))}
    created = False
    result_lines = []

    def docker(*docker_args):
        return run_docker(*docker_args, env=env)

    def psql(sql, quiet=True):
        command = ["docker", "exec", "-e", f"PGPASSWORD={password}", name, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                   "-h", "127.0.0.1", "-p", "5432", "-U", "postgres", "-d", database]
        if quiet:
            command.append("-At")
        command.extend(["-c", sql])
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        if result.returncode:
            raise RuntimeError("psql falhou no PostgreSQL descartável: " + safe_output(result.stderr, (password,)))
        return result.stdout.strip()

    try:
        endpoint = docker("context", "inspect", "default", "--format", "{{ .Endpoints.docker.Host }}").strip().lower()
        if not endpoint.startswith(("npipe:", "unix:")):
            raise RuntimeError("O endpoint Docker não é local; restauração cancelada")
        docker("image", "inspect", "postgres:17-alpine")
        docker("run", "--pull=never", "-d", "--rm", "--name", name,
               "--label", f"{label_key}={label_value}", "--network", "none",
               "-e", f"POSTGRES_PASSWORD={password}", "-e", f"POSTGRES_DB={database}",
               "--tmpfs", "/var/lib/postgresql/data", "--tmpfs", "/restore:rw,noexec,nosuid,nodev,size=1g",
               "--mount", f"type=bind,source={backup},target=/backup/input.idbackup,readonly", "postgres:17-alpine")
        created = True
        for _ in range(60):
            probe = subprocess.run(["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-p", "5432", "-U", "postgres", "-d", database],
                                   capture_output=True, env=env)
            if probe.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("PostgreSQL descartável não ficou pronto")

        # The only decrypted copy is in this disposable container's tmpfs; it is never restored
        # unless the complete AES-GCM tag has been verified successfully.
        sink = subprocess.Popen(["docker", "exec", "-i", name, "sh", "-c", "umask 077; cat > /restore/input.dump"],
                                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
        try:
            with backup.open("rb") as source:
                _, plaintext_hash = decrypt_stream(source, sink.stdin, passphrase)
            sink.stdin.close()
            sink_error = sink.stderr.read()
            if sink.wait():
                raise RuntimeError("Não foi possível preparar o arquivo autenticado no tmpfs: " + safe_output(sink_error, (password, passphrase)))
        except Exception:
            if sink.stdin and not sink.stdin.closed:
                sink.stdin.close()
            sink.kill()
            sink.wait()
            raise

        toc = docker("exec", name, "pg_restore", "--list", "/restore/input.dump")
        archive_tables, archive_data = set(), set()
        pattern = re.compile(r"^\s*(?:;\s*)?\d+;\s+\d+\s+\d+\s+(TABLE(?: DATA)?)\s+(\S+)\s+(\S+)\s+(\S+)\s*$")
        for line in toc.splitlines():
            match = pattern.match(line)
            if match and match.group(2) == "public" and match.group(3) in REQUIRED_TABLES:
                (archive_data if match.group(1) == "TABLE DATA" else archive_tables).add(match.group(3))
        if archive_tables != REQUIRED_TABLES or archive_data != REQUIRED_TABLES:
            raise RuntimeError("TOC não contém todas as tabelas/entradas de dados da migration 009")
        docker("exec", name, "pg_restore", "--file=/dev/null", "/restore/input.dump")

        roles_sql = """CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN;
CREATE ROLE authenticator NOLOGIN NOINHERIT;
CREATE ROLE investment_runtime LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE investment_test_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS;
CREATE SCHEMA auth;
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS $$ SELECT COALESCE(NULLIF(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb) $$;
CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('request.jwt.claim.role',true),'') $$;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";"""
        run_docker("exec", "-i", "-e", f"PGPASSWORD={password}", name, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                   "-h", "127.0.0.1", "-p", "5432", "-U", "postgres", "-d", "postgres",
                   input_data=roles_sql, env=env)
        # Keep GRANT/REVOKE entries from the archive; ownership is recreated by the disposable superuser.
        docker("exec", name, "pg_restore", "--exit-on-error", "--schema=public", "--no-owner", "-d", database, "/restore/input.dump")
        psql("GRANT SELECT ON public.financial_events, public.financial_event_revisions "
             "TO investment_test_runtime")

        version = psql("SELECT version_num FROM public.alembic_version")
        if version != "009":
            raise RuntimeError("A versão Alembic restaurada não é 009")
        restored_tables = set(psql("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines())
        if not REQUIRED_TABLES.issubset(restored_tables):
            raise RuntimeError("Faltam tabelas da aplicação após a restauração")
        counts = {table: int(psql(f'SELECT count(*) FROM public."{table}"')) for table in sorted(REQUIRED_TABLES)}

        rls_rows = psql("SELECT relname || '=' || relrowsecurity || '/' || relforcerowsecurity FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p') AND relname <> 'alembic_version' ORDER BY relname").splitlines()
        rls = dict(row.split("=", 1) for row in rls_rows)
        if not RLS_TABLES.issubset(rls) or any(rls[t] != "true/true" for t in RLS_TABLES):
            raise RuntimeError("RLS/FORCE RLS não foi restaurado em todas as tabelas financeiras")
        policies = int(psql("SELECT count(*) FROM pg_policy WHERE polrelid IN (SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace AND relname <> 'alembic_version')"))
        if policies < len(RLS_TABLES):
            raise RuntimeError("Policies RLS insuficientes após o restore")
        for table, sequence in (
            ("public.financial_events", "public.financial_events_id_seq"),
            ("public.financial_event_revisions", "public.financial_event_revisions_id_seq"),
            ("public.fixed_income_application_revisions", "public.fixed_income_application_revisions_id_seq"),
        ):
            grants = psql("SELECT has_table_privilege('investment_runtime', '" + table + "', 'SELECT') || '|' || "
                          "has_table_privilege('investment_runtime', '" + table + "', 'INSERT') || '|' || "
                          "has_table_privilege('investment_runtime', '" + table + "', 'UPDATE') || '|' || "
                          "has_table_privilege('investment_runtime', '" + table + "', 'DELETE') || '|' || "
                          "has_table_privilege('investment_runtime', '" + table + "', 'TRUNCATE') || '|' || "
                          "has_sequence_privilege('investment_runtime', '" + sequence + "', 'USAGE')")
            if grants != "true|true|false|false|false|true":
                raise RuntimeError("Grants mínimos da role runtime não foram preservados em " + table.split(".")[-1])

        for owner in ("11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"):
            isolation = psql("BEGIN; SET LOCAL ROLE investment_test_runtime; "
                             "SELECT set_config('app.auth_mode','supabase',true); "
                             f"SELECT set_config('app.user_id','{owner}',true); "
                             "SELECT count(*) FROM public.financial_events WHERE owner_id <> current_setting('app.user_id')::uuid; ROLLBACK;")
            if not isolation.splitlines()[-2].endswith("0"):
                raise RuntimeError("Falha no teste RLS sintético por proprietário")
        result_lines = [
            "RESTORE=PASS; formato autenticado AES-256-GCM IDBKP009",
            "Alembic=009; public tables=PASS; archive data entries=PASS",
            "financial_events/revisions restaurados; contagens preservadas (podem estar vazias)=PASS",
            "RLS/FORCE RLS e policies=PASS; grants runtime SELECT/INSERT sem UPDATE/DELETE/TRUNCATE=PASS",
            "isolamento RLS para dois proprietários fictícios=PASS",
            "sha256_encrypted=" + sha256_file(backup),
            "sha256_decrypted_archive=" + plaintext_hash,
            "row_counts=" + ",".join(f"{table}:{counts[table]}" for table in sorted(counts)),
            "Nota: roles globais são recriadas como shims descartáveis; este ensaio não testa restauração de Auth, Storage ou configurações Supabase.",
        ]
    finally:
        if created:
            owned = subprocess.run(["docker", "inspect", "--format", f'{{{{index .Config.Labels "{label_key}"}}}}', name],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
            if owned.returncode == 0 and owned.stdout.strip() == label_value:
                subprocess.run(["docker", "stop", name], capture_output=True, env=env)
    print("\n".join(result_lines))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("RESTORE_FAIL: " + safe_output(str(exc)), file=sys.stderr)
        sys.exit(1)
