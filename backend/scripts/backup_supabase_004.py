"""Create and verify a PostgreSQL 17 custom dump from the Supabase session pooler.

The database URL is read from the process environment but is never passed to Docker,
printed, or written to disk. The password is sent over docker exec stdin into a
0600 pgpass file on a container tmpfs.
"""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4


DESTINATION = Path(r"E:\Users\IAN\Backups\InvestmentDashboard")
IMAGE = "postgres:17-alpine"
POOLER_HOST = "aws-1-sa-east-1.pooler.supabase.com"
POOLER_PORT = 5432
DATABASE = "postgres"
SERVICE_NAME = "investment-prod-backup"
REQUIRED_TABLES = {
    "alembic_version", "operations", "fixed_income_investments", "fixed_income_lots",
    "fixed_income_movements", "fixed_income_observations",
}


def parse_database_url(value):
    if not value or value[:1] in "\"'" or value[-1:] in "\"'":
        raise ValueError("DATABASE_URL ausente ou contém aspas literais; valor não será exibido")
    try:
        parsed = urlsplit(value)
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=False)
        if parsed.scheme != "postgresql+psycopg":
            raise ValueError
        host = parsed.hostname
        port = parsed.port or POOLER_PORT
        user = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        database = unquote(parsed.path.lstrip("/"))
        if (host != POOLER_HOST or port != POOLER_PORT or database != DATABASE
                or not re.fullmatch(r"[A-Za-z0-9_.-]+", user)
                or not password or "\n" in password or "\r" in password):
            raise ValueError
        if query.get("sslmode") != ["verify-full"]:
            raise ValueError
    except (ValueError, UnicodeError) as exc:
        raise ValueError(
            "DATABASE_URL inválida para o Session Pooler esperado; exige postgresql+psycopg, "
            "host/porta/banco corretos e sslmode=verify-full"
        ) from None
    return host, port, database, user, password, query


def pgpass_field(value):
    return value.replace("\\", "\\\\").replace(":", "\\:")


def parse_toc(toc):
    tables, data = set(), set()
    line_pattern = re.compile(
        r"^\s*;?\s*\d+;\s+\d+\s+\d+\s+(TABLE(?: DATA)?)\s+(\S+)\s+(\S+)\s+(\S+)\s*$"
    )
    for line in toc.splitlines():
        match = line_pattern.match(line)
        if not match:
            continue
        kind, schema, table, _owner = match.groups()
        if schema == "public" and table in REQUIRED_TABLES:
            (data if kind == "TABLE DATA" else tables).add(table)
    return tables, data


def parse_archived_alembic_version(sql):
    lines = sql.splitlines()
    for index, line in enumerate(lines[:-2]):
        if re.fullmatch(r"COPY\s+public\.alembic_version\s*\(version_num\)\s+FROM stdin;", line):
            if lines[index + 2] != r"\.":
                break
            return lines[index + 1]
    raise ValueError("Não foi possível confirmar alembic_version dentro do dump")


def safe_text(value, secret_values=()):
    text = value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")
    for secret in secret_values:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)postgres(?:ql)?(?:\+[a-z0-9_.-]+)?://[^\s'\"]+", "[DATABASE_URL REDACTED]", text)
    text = re.sub(r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)Authorization:\s*Bearer\s+\S+", "Authorization: Bearer [REDACTED]", text)
    text = re.sub(r"(?im)^\s*(DETAIL|CONTEXT|STATEMENT|HINT):.*$", r"\1: [REDACTED]", text)
    return text[:4000]


def docker_environment():
    env = os.environ.copy()
    for key in tuple(env):
        upper = key.upper()
        sensitive_markers = ("DATABASE_URL", "CONNECTION_STRING", "PASSWORD", "PASSWD",
                             "TOKEN", "SECRET", "API_KEY", "SUPABASE_")
        if (any(marker in upper for marker in sensitive_markers) or upper.endswith("_URL")
                or upper in {"PGPASSWORD", "PGPASSFILE"}):
            env.pop(key, None)
    return env


def exec_env_args(host, port, database, user):
    return ["-e", f"PGSERVICE={SERVICE_NAME}", "-e", "PGSERVICEFILE=/run/backup-secrets/pg_service.conf",
            "-e", "PGPASSFILE=/run/backup-secrets/pgpass"]


def service_file_contents(host, port, database, user):
    return (f"[{SERVICE_NAME}]\n"
            f"host={host}\nport={port}\ndbname={database}\nuser={user}\n"
            "sslmode=verify-full\nsslrootcert=/run/backup-certs/supabase-root.crt\n"
            "connect_timeout=10\n")


def pg_dump_exec_args(exec_env, container):
    return ["exec", *exec_env, container, "pg_dump", "-w", "--format=custom"]


def pg_restore_stdin_args(container, *options):
    """Omit archive filename: pg_restore reads the Docker stdin stream."""
    return ("exec", "-i", container, "pg_restore", *options)


def choose_ca_path(query):
    url_ca = query.get("sslrootcert", [None])
    if len(url_ca) > 1:
        raise ValueError("sslrootcert duplicado na URL")
    candidates = [os.environ.get("PGSSLROOTCERT"), url_ca[0]]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    entered = input("Caminho da CA raiz oficial baixada em Supabase Database Settings: ").strip()
    ca = Path(entered).expanduser()
    if not ca.is_file():
        raise ValueError("Arquivo da CA não existe; nenhuma conexão foi aberta")
    return ca.resolve()


def client_tls_confirmed(conninfo):
    return re.search(r"(?im)^\s*SSL connection \(protocol: TLSv1\.[23]\b", conninfo) is not None


def preflight_failures(parts, database):
    if len(parts) != 4:
        return ["response_format"]
    failures = []
    if parts[0] != database:
        failures.append("database")
    if parts[1] != "17":
        failures.append("server_major")
    if parts[2] != "004":
        failures.append("alembic_version")
    return failures


def main():
    raw_url = os.environ.get("DATABASE_URL", "")
    host, port, database, user, password, query = parse_database_url(raw_url)
    ca_path = choose_ca_path(query)
    ca_bytes = ca_path.read_bytes()
    if b"-----BEGIN CERTIFICATE-----" not in ca_bytes or b"-----END CERTIFICATE-----" not in ca_bytes:
        raise ValueError("A CA precisa estar em PEM; nenhuma conexão foi aberta")
    if input("Confirme o destino informado: digite BACKUP PRODUCTION 004: ").strip() != "BACKUP PRODUCTION 004":
        raise RuntimeError("Confirmação do backup não recebida; nenhuma conexão foi aberta")

    DESTINATION.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex[:12]
    name = f"investment-prod-backup-{run_id}"
    network = f"investment-prod-backup-net-{run_id}"
    label = f"com.investment-dashboard.production-backup={run_id}"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_path = DESTINATION / f"investment-dashboard-prod-pre-2.0.8-{timestamp}.dump"
    partial_path = DESTINATION / f".{final_path.name}.{run_id}.partial"
    log_path = DESTINATION / f"investment-dashboard-prod-backup-{timestamp}-{run_id}.log"
    secret_values = (password, raw_url)
    lines = ["Supabase production backup verifier; mode=read-only pg_dump; no migrations"]
    env = docker_environment()
    created_container = False
    created_network = False
    overall_ok = False
    cleanup_ok = True

    def docker(*args, input_data=None, stdout=subprocess.PIPE, stdin=None):
        result = subprocess.run(["docker", *args], input=input_data, stdin=stdin,
                                stdout=stdout, stderr=subprocess.PIPE,
                                env=env, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            detail = safe_text(result.stderr, secret_values) or "sem diagnóstico"
            raise RuntimeError(f"docker {args[0]} exit={result.returncode}: {detail}")
        return result.stdout

    try:
        if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
            raise RuntimeError("DOCKER_HOST/DOCKER_CONTEXT override encontrado; somente Docker local padrão é aceito")
        endpoint = docker("context", "inspect", "default", "--format", "{{ .Endpoints.docker.Host }}").strip().lower()
        if not endpoint.startswith(("npipe:", "unix:")):
            raise RuntimeError("O endpoint Docker não é local; backup cancelado")
        docker("info", "--format", "{{.ServerVersion}}")
        client_version = docker("run", "--pull=never", "--rm", IMAGE, "pg_dump", "--version").strip()
        if not re.search(r"\b17(?:\.\d+)?\b", client_version):
            raise RuntimeError("A imagem em cache não fornece pg_dump PostgreSQL 17")
        docker("network", "create", "--driver", "bridge", "--label", label, network)
        created_network = True
        docker("run", "--pull=never", "-d", "--rm", "--name", name, "--label", label,
               "--network", network,
               "--tmpfs", "/run/backup-secrets:rw,noexec,nosuid,nodev,size=16k",
               "--tmpfs", "/run/backup-certs:rw,noexec,nosuid,nodev,size=64k",
               "--entrypoint", "sh", IMAGE, "-c", "while :; do sleep 3600; done")
        created_container = True
        cert_result = subprocess.run(
            ["docker", "exec", "-i", name, "sh", "-c",
             "set -eu; umask 022; cat > /run/backup-certs/supabase-root.crt; chmod 644 /run/backup-certs/supabase-root.crt"],
            input=ca_bytes, capture_output=True, env=env,
        )
        if cert_result.returncode:
            raise RuntimeError("Falha ao copiar CA pública para o tmpfs descartável do container")
        docker("exec", "-i", name, "sh", "-c",
               "set -eu; umask 077; cat > /run/backup-secrets/pgpass; chmod 600 /run/backup-secrets/pgpass",
               input_data=(":".join(pgpass_field(value) for value in
                                     (host, str(port), database, user, password)) + "\n"))
        docker("exec", "-i", name, "sh", "-c",
               "set -eu; umask 077; cat > /run/backup-secrets/pg_service.conf; chmod 600 /run/backup-secrets/pg_service.conf",
               input_data=service_file_contents(host, port, database, user))
        exec_env = exec_env_args(host, port, database, user)
        preflight_sql = ("SELECT current_database() || '|' || current_setting('server_version_num')::int / 10000 || '|' || "
                         "(SELECT string_agg(version_num, ',') FROM public.alembic_version) || '|' || current_user")
        preflight = docker("exec", *exec_env, name, "psql", "-X", "-w", "-v", "ON_ERROR_STOP=1",
                           "-A", "-t", "-c", preflight_sql).strip()
        parts = preflight.split("|")
        failures = preflight_failures(parts, database)
        if failures:
            detected = parts[2] if len(parts) == 4 and re.fullmatch(r"[0-9]{3}", parts[2]) else "indisponível"
            raise RuntimeError("Preflight falhou: " + ", ".join(failures)
                               + f"; alembic_detected={detected}; nenhuma cópia será promovida")
        if parts[3] == "investment_runtime":
            raise RuntimeError("DATABASE_URL usa a role runtime restrita; escolha uma role autorizada para backup completo")
        # pg_stat_ssl describes the pooler-to-database hop, not this client's TLS
        # session to the Supabase Session Pooler. libpq enforces verify-full via
        # the service file and CA; \conninfo confirms this client used SSL.
        conninfo = docker("exec", *exec_env, name, "psql", "-X", "-w", "-c", r"\conninfo")
        if not client_tls_confirmed(conninfo):
            raise RuntimeError("Preflight falhou: client_tls; nenhuma cópia será promovida")
        lines.append("SOURCE_PREFLIGHT=PASS; server_major=17; alembic=004; client_TLS=verify-full confirmed")
        lines.append(f"pg_dump_client={client_version}")

        # Stream directly to an exclusive partial file; credentials are never argv/env.
        with partial_path.open("xb") as output:
            process = subprocess.Popen(
                ["docker", *pg_dump_exec_args(exec_env, name)],
                stdout=output, stderr=subprocess.PIPE, env=env,
            )
            stderr = process.communicate()[1]
            if process.returncode:
                raise RuntimeError(f"pg_dump exit={process.returncode}: {safe_text(stderr, secret_values) or 'sem diagnóstico'}")
        if partial_path.stat().st_size == 0:
            raise RuntimeError("pg_dump terminou com código zero, mas o arquivo ficou vazio")
        with partial_path.open("rb") as dump_file:
            if dump_file.read(5) != b"PGDMP":
                raise RuntimeError("O arquivo não tem cabeçalho de dump custom PostgreSQL")

        with partial_path.open("rb") as dump_file:
            toc = docker(*pg_restore_stdin_args(name, "--list", "--file=/dev/stdout"), stdin=dump_file)
        tables, data_entries = parse_toc(toc)
        missing_tables = sorted(REQUIRED_TABLES - tables)
        missing_data = sorted(REQUIRED_TABLES - data_entries)
        if missing_tables or missing_data:
            raise RuntimeError(f"TOC incompleto; tabelas ausentes={missing_tables}; entradas de dados ausentes={missing_data}")

        # Force pg_restore to decompress/read every archive payload without writing
        # financial rows to terminal or log. Output is discarded inside the container.
        with partial_path.open("rb") as dump_file:
            docker(*pg_restore_stdin_args(name, "--file=/dev/null"), stdin=dump_file)
        with partial_path.open("rb") as dump_file:
            version_sql = docker(*pg_restore_stdin_args(name, "--data-only", "--table=alembic_version", "--file=/dev/stdout"),
                                 stdin=dump_file)
        if parse_archived_alembic_version(version_sql) != "004":
            raise RuntimeError("A versão Alembic extraída do dump não é 004")

        size = partial_path.stat().st_size
        digest = hashlib.sha256()
        with partial_path.open("rb") as dump_file:
            for chunk in iter(lambda: dump_file.read(1024 * 1024), b""):
                digest.update(chunk)
        # Atomic promotion only after TOC, complete decompression, and Alembic checks.
        os.rename(partial_path, final_path)
        lines.extend(("ARCHIVE_TOC=PASS; tables=" + ",".join(sorted(tables)),
                      "ARCHIVE_DATA_ENTRIES=PASS; tables=" + ",".join(sorted(data_entries)),
                      "ARCHIVE_FULL_READ=PASS; pg_restore decompressed every archive entry",
                      "ARCHIVED_ALEMBIC_VERSION=004", "BACKUP_SIZE_BYTES=" + str(size),
                      "BACKUP_SHA256=" + digest.hexdigest(), "BACKUP_FILE=" + str(final_path),
                      "BACKUP_VALIDATION=PASS"))
        overall_ok = True
    except Exception as exc:
        lines.append("BACKUP_VALIDATION=FAIL")
        lines.append(safe_text(str(exc), secret_values))
        print("Backup NÃO aprovado: " + safe_text(str(exc), secret_values), file=sys.stderr)
    finally:
        if created_container:
            result = subprocess.run(["docker", "inspect", "--format", '{{index .Config.Labels "com.investment-dashboard.production-backup"}}', name],
                                    capture_output=True, text=True, env=env)
            if result.returncode == 0 and result.stdout.strip() == run_id:
                stopped = subprocess.run(["docker", "stop", name], capture_output=True, env=env)
                if stopped.returncode:
                    cleanup_ok = False
                    lines.append("CONTAINER_CLEANUP=FAIL")
            elif result.returncode:
                cleanup_ok = False
                lines.append("CONTAINER_CLEANUP=UNVERIFIED")
            else:
                cleanup_ok = False
                lines.append("CONTAINER_CLEANUP=OWNERSHIP_MISMATCH; container left untouched")
        if created_network:
            result = subprocess.run(["docker", "network", "inspect", "--format", '{{index .Labels "com.investment-dashboard.production-backup"}}', network],
                                    capture_output=True, text=True, env=env)
            if result.returncode == 0 and result.stdout.strip() == run_id:
                removed = subprocess.run(["docker", "network", "rm", network], capture_output=True, env=env)
                if removed.returncode:
                    cleanup_ok = False
                    lines.append("NETWORK_CLEANUP=FAIL")
            elif result.returncode:
                cleanup_ok = False
                lines.append("NETWORK_CLEANUP=UNVERIFIED")
            else:
                cleanup_ok = False
                lines.append("NETWORK_CLEANUP=OWNERSHIP_MISMATCH; network left untouched")
        if partial_path.exists():
            partial_path.unlink()
        if cleanup_ok:
            lines.append("DISPOSABLE_RESOURCE_CLEANUP=PASS")
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Log: {log_path}")
    if overall_ok and cleanup_ok:
        print(f"Backup validado: {final_path}")
        print(f"Bytes={size}; SHA256={digest.hexdigest()}; Alembic=004; TLS=verify-full")
        return 0
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Configuration/confirmation errors occur before a run log is allocated.
        print("Backup NÃO aprovado: " + safe_text(str(exc)), file=sys.stderr)
        sys.exit(1)
