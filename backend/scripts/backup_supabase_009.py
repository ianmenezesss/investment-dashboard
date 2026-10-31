"""Create one encrypted, read-only PostgreSQL custom archive for Alembic head 009.

The output file is kept outside the repository. Plaintext exists only in the
discardable PostgreSQL client's tmpfs while the archive is verified.
"""
import argparse
import getpass
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

try:
    from .backup_archive import MAGIC, decrypt_stream, encrypt_stream, sha256_file
except ImportError:  # Allow direct execution as a script from any working directory.
    from backup_archive import MAGIC, decrypt_stream, encrypt_stream, sha256_file


IMAGE = "postgres:17-alpine"
POOLER_PORT = 5432
DATABASE = "postgres"
SERVICE_NAME = "investment-prod-backup"
BACKUP_URL_ENV = "SUPABASE_BACKUP_DATABASE_URL"
REQUIRED_TABLES = {
    "alembic_version", "operations", "fixed_income_investments", "fixed_income_lots",
    "fixed_income_movements", "fixed_income_observations", "fixed_income_investment_archives",
    "fixed_income_application_revisions", "financial_events", "financial_event_revisions",
}


def parse_database_url(value):
    if not value or value[:1] in "\"'" or value[-1:] in "\"'":
        raise ValueError(f"{BACKUP_URL_ENV} ausente ou contém aspas literais; valor não será exibido")
    try:
        parsed = urlsplit(value)
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=False)
        if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
            raise ValueError
        host, port = parsed.hostname, parsed.port or POOLER_PORT
        user, password = unquote(parsed.username or ""), unquote(parsed.password or "")
        database = unquote(parsed.path.lstrip("/"))
        allowed_host = (re.fullmatch(r"[a-z0-9-]+\.pooler\.supabase\.com", host or "")
                        or re.fullmatch(r"db\.[a-z0-9]+\.supabase\.co", host or ""))
        if (not allowed_host or port != POOLER_PORT or database != DATABASE
                or not re.fullmatch(r"[A-Za-z0-9_.-]+", user)
                or not password or "\n" in password or "\r" in password):
            raise ValueError
        if query.get("sslmode") != ["verify-full"]:
            raise ValueError
    except (ValueError, UnicodeError):
        raise ValueError(
            f"{BACKUP_URL_ENV} inválida; exige URL PostgreSQL Supabase direta ou shared Session Pooler "
            "na porta 5432, banco postgres e sslmode=verify-full"
        ) from None
    return host, port, database, user, password, query


def pgpass_field(value):
    return value.replace("\\", "\\\\").replace(":", "\\:")


def parse_toc(toc):
    tables, data = set(), set()
    pattern = re.compile(r"^\s*;?\s*\d+;\s+\d+\s+\d+\s+(TABLE(?: DATA)?)\s+(\S+)\s+(\S+)\s+(\S+)\s*$")
    for line in toc.splitlines():
        match = pattern.match(line)
        if match:
            kind, schema, table, _owner = match.groups()
            if schema == "public" and table in REQUIRED_TABLES:
                (data if kind == "TABLE DATA" else tables).add(table)
    return tables, data


def parse_archived_alembic_version(sql):
    lines = sql.splitlines()
    for index, line in enumerate(lines[:-2]):
        if re.fullmatch(r"COPY\s+public\.alembic_version\s*\(version_num\)\s+FROM stdin;", line):
            if lines[index + 2] == r"\." and lines[index + 1] == "009":
                return lines[index + 1]
    raise ValueError("Não foi possível confirmar Alembic 009 dentro do dump")


def safe_text(value, secret_values=()):
    text = value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")
    for secret in secret_values:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)postgres(?:ql)?(?:\+[a-z0-9_.-]+)?://[^\s'\"]+", "[DATABASE_URL REDACTED]", text)
    text = re.sub(r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)Authorization:\s*Bearer\s+\S+", "Authorization: Bearer [REDACTED]", text)
    text = re.sub(r"(?im)^\s*(DETAIL|CONTEXT|STATEMENT|HINT):.*$", r"\1: [REDACTED]", text)
    return text[:3000]


def docker_environment():
    env = os.environ.copy()
    for key in tuple(env):
        upper = key.upper()
        markers = ("DATABASE_URL", "CONNECTION_STRING", "PASSWORD", "PASSWD", "TOKEN", "SECRET", "API_KEY", "SUPABASE_")
        if any(marker in upper for marker in markers) or upper.endswith("_URL") or upper in {"PGPASSWORD", "PGPASSFILE"}:
            env.pop(key, None)
    return env


def choose_ca_path(query):
    url_ca = query.get("sslrootcert", [None])
    if len(url_ca) > 1:
        raise ValueError("sslrootcert duplicado na URL")
    for candidate in (os.environ.get("PGSSLROOTCERT"), url_ca[0]):
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    candidate = input("Caminho da CA raiz oficial baixada em Supabase Database Settings: ").strip()
    ca = Path(candidate).expanduser()
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
    if parts[2] != "009":
        failures.append("alembic_version")
    return failures


def validate_output(path):
    output = path.expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output.relative_to(repo_root)
    except ValueError:
        pass
    else:
        raise ValueError("O arquivo de backup precisa ficar fora do repositório")
    if output.suffix.lower() != ".idbackup":
        raise ValueError("O arquivo final precisa usar a extensão .idbackup")
    if output.exists():
        raise ValueError("O arquivo de destino já existe; o script não sobrescreve backups")
    if not output.parent.is_dir():
        raise ValueError("A pasta de destino precisa existir e estar protegida pelo usuário")
    return output


def encrypt_process_output(process, output, passphrase):
    with output.open("xb") as encrypted:
        size, digest = encrypt_stream(process.stdout, encrypted, passphrase)
        process.stdout.close()
        stderr = process.stderr.read()
        return_code = process.wait()
    if return_code:
        raise RuntimeError(f"pg_dump exit={return_code}: {safe_text(stderr)}")
    return size, digest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gera um único backup PostgreSQL 009 criptografado; não executa migrations")
    parser.add_argument("--output", required=True, type=Path, help="Arquivo .idbackup fora do repositório; não será sobrescrito")
    args = parser.parse_args(argv)
    output = validate_output(args.output)

    raw_url = os.environ.get(BACKUP_URL_ENV, "")
    host, port, database, user, password, query = parse_database_url(raw_url)
    ca_path = choose_ca_path(query)
    ca_bytes = ca_path.read_bytes()
    if b"-----BEGIN CERTIFICATE-----" not in ca_bytes or b"-----END CERTIFICATE-----" not in ca_bytes:
        raise ValueError("A CA precisa estar em PEM; nenhuma conexão foi aberta")
    passphrase = getpass.getpass("Frase de proteção do backup (mínimo 16 caracteres): ")
    if len(passphrase) < 16 or passphrase != getpass.getpass("Repita a frase de proteção: "):
        raise ValueError("As frases de proteção não coincidem ou são curtas demais")
    if input("Para iniciar somente o pg_dump read-only, digite BACKUP PRODUCTION 009: ").strip() != "BACKUP PRODUCTION 009":
        raise RuntimeError("Confirmação não recebida; nenhuma conexão foi aberta")

    run_id = uuid4().hex[:12]
    name, network = f"investment-prod-backup-{run_id}", f"investment-prod-backup-net-{run_id}"
    label = f"com.investment-dashboard.production-backup={run_id}"
    partial = output.with_name(f".{output.name}.{run_id}.partial")
    secret_values = (password, raw_url, passphrase)
    env = docker_environment()
    created_container = created_network = False
    cleanup_ok = True
    metadata = {}

    def docker(*docker_args, input_data=None, stdin=None, stdout=subprocess.PIPE):
        result = subprocess.run(["docker", *docker_args], input=input_data, stdin=stdin, stdout=stdout,
                                stderr=subprocess.PIPE, env=env, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            detail = safe_text(result.stderr, secret_values) or "sem diagnóstico"
            raise RuntimeError(f"docker {docker_args[0]} exit={result.returncode}: {detail}")
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
        docker("run", "--pull=never", "-d", "--rm", "--name", name, "--label", label, "--network", network,
               "--tmpfs", "/run/backup-secrets:rw,noexec,nosuid,nodev,size=64m",
               "--tmpfs", "/run/backup-certs:rw,noexec,nosuid,nodev,size=64k",
               "--entrypoint", "sh", IMAGE, "-c", "while :; do sleep 3600; done")
        created_container = True
        copied = subprocess.run(["docker", "exec", "-i", name, "sh", "-c",
                                 "set -eu; cat > /run/backup-certs/root.crt; chmod 644 /run/backup-certs/root.crt"],
                                input=ca_bytes, capture_output=True, env=env)
        if copied.returncode:
            raise RuntimeError("Falha ao copiar CA pública para tmpfs descartável")
        service = (f"[{SERVICE_NAME}]\nhost={host}\nport={port}\ndbname={database}\nuser={user}\n"
                   "sslmode=verify-full\nsslrootcert=/run/backup-certs/root.crt\nconnect_timeout=10\n")
        pgpass = ":".join(pgpass_field(item) for item in (host, str(port), database, user, password)) + "\n"
        for target, value in (("service.conf", service), ("pgpass", pgpass)):
            copied = subprocess.run(["docker", "exec", "-i", name, "sh", "-c",
                                     f"set -eu; umask 077; cat > /run/backup-secrets/{target}; chmod 600 /run/backup-secrets/{target}"],
                                    input=value.encode(), capture_output=True, env=env)
            if copied.returncode:
                raise RuntimeError("Falha ao preparar configuração temporária de conexão")
        pgenv = ["-e", f"PGSERVICE={SERVICE_NAME}", "-e", "PGSERVICEFILE=/run/backup-secrets/service.conf",
                 "-e", "PGPASSFILE=/run/backup-secrets/pgpass"]
        preflight_sql = ("SELECT current_database() || '|' || current_setting('server_version_num')::int / 10000 || '|' || "
                         "(SELECT string_agg(version_num, ',') FROM public.alembic_version) || '|' || current_user")
        preflight = docker("exec", *pgenv, name, "psql", "-X", "-w", "-v", "ON_ERROR_STOP=1", "-A", "-t", "-c", preflight_sql).strip()
        parts = preflight.split("|")
        failures = preflight_failures(parts, database)
        if failures:
            raise RuntimeError("Preflight falhou: " + ", ".join(failures) + "; nenhuma cópia será promovida")
        if parts[3] == "investment_runtime":
            raise RuntimeError("A conexão usa a role runtime; use uma role somente-leitura autorizada para backup")
        if not client_tls_confirmed(docker("exec", *pgenv, name, "psql", "-X", "-w", "-c", r"\conninfo")):
            raise RuntimeError("Preflight TLS do cliente falhou; nenhuma cópia será promovida")

        process = subprocess.Popen(["docker", "exec", *pgenv, name, "pg_dump", "-w", "--format=custom", "--schema=public", database],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        size, encrypted_hash = encrypt_process_output(process, partial, passphrase)
        if size <= len(MAGIC):
            raise RuntimeError("pg_dump produziu um arquivo vazio ou truncado")

        # Decrypt only into container tmpfs; do not use the plaintext until AES-GCM authenticates.
        sink = subprocess.Popen(["docker", "exec", "-i", name, "sh", "-c",
                                 "set -eu; umask 077; cat > /run/backup-secrets/archive.dump"],
                                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
        try:
            with partial.open("rb") as encrypted:
                _, plaintext_hash = decrypt_stream(encrypted, sink.stdin, passphrase)
            sink.stdin.close()
            sink_stderr = sink.stderr.read()
            if sink.wait():
                raise RuntimeError("Falha ao enviar arquivo autenticado ao tmpfs descartável: " + safe_text(sink_stderr, secret_values))
        except Exception:
            if sink.stdin and not sink.stdin.closed:
                sink.stdin.close()
            sink.kill()
            sink.wait()
            raise
        toc = docker("exec", name, "pg_restore", "--list", "/run/backup-secrets/archive.dump")
        tables, data = parse_toc(toc)
        missing_tables, missing_data = sorted(REQUIRED_TABLES - tables), sorted(REQUIRED_TABLES - data)
        if missing_tables or missing_data:
            raise RuntimeError(f"TOC incompleto; tabelas ausentes={missing_tables}; dados ausentes={missing_data}")
        docker("exec", name, "pg_restore", "--file=/dev/null", "/run/backup-secrets/archive.dump")
        version_sql = docker("exec", name, "pg_restore", "--data-only", "--table=alembic_version",
                             "--file=/dev/stdout", "/run/backup-secrets/archive.dump")
        if parse_archived_alembic_version(version_sql) != "009":
            raise RuntimeError("A versão Alembic arquivada não é 009")
        if output.exists():
            raise RuntimeError("O destino foi criado durante a execução; preservando o arquivo existente")
        os.rename(partial, output)
        metadata = {"encrypted_bytes": output.stat().st_size, "encrypted_sha256": sha256_file(output),
                    "plaintext_sha256": plaintext_hash, "alembic": "009", "format": MAGIC.decode(),
                    "tables": sorted(tables), "tls": "verify-full"}
    finally:
        if created_container:
            result = subprocess.run(["docker", "inspect", "--format", '{{index .Config.Labels "com.investment-dashboard.production-backup"}}', name],
                                    capture_output=True, text=True, env=env)
            if result.returncode == 0 and result.stdout.strip() == run_id:
                if subprocess.run(["docker", "stop", name], capture_output=True, env=env).returncode:
                    cleanup_ok = False
            else:
                cleanup_ok = False
        if created_network:
            result = subprocess.run(["docker", "network", "inspect", "--format", '{{index .Labels "com.investment-dashboard.production-backup"}}', network],
                                    capture_output=True, text=True, env=env)
            if result.returncode == 0 and result.stdout.strip() == run_id:
                if subprocess.run(["docker", "network", "rm", network], capture_output=True, env=env).returncode:
                    cleanup_ok = False
            else:
                cleanup_ok = False
        if partial.exists():
            partial.unlink()
        if not metadata and output.exists():
            output.unlink()
    if not metadata:
        raise RuntimeError("O backup não passou por todas as verificações; artefato final removido")
    if not cleanup_ok:
        raise RuntimeError("Backup verificado, mas a limpeza de recurso descartável falhou; confira apenas o nome UUID informado no erro")
    print("BACKUP_VALIDATION=PASS; AES-256-GCM=PASS; archive decompression=PASS; Alembic=009; TLS=verify-full")
    print(f"Arquivo={output}; bytes={metadata['encrypted_bytes']}; SHA256={metadata['encrypted_sha256']}")
    print("Escopo validado: schema public e tabelas de aplicação requeridas; sem migration ou escrita no banco.")
    print("Guarde a frase de proteção separadamente; sem ela, o arquivo não pode ser recuperado.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("Backup NÃO aprovado: " + safe_text(str(exc)), file=sys.stderr)
        sys.exit(1)
