"""Executa integração 001–008 e ensaio pg_dump/restore em containers efêmeros."""
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
from uuid import uuid4


def network_create_args(network):
    return ("network", "create", "--driver", "bridge",
            "--opt", "com.docker.network.bridge.host_binding_ipv4=127.0.0.1", network)


def container_run_args(name, network, db_name, password, run_id):
    return ("run", "--pull=never", "-d", "--rm", "--name", name,
            "--label", f"com.investment-dashboard.homologation={run_id}",
            "--network", network, "--env", f"POSTGRES_PASSWORD={password}",
            "--env", f"POSTGRES_DB={db_name}", "--publish=127.0.0.1::5432/tcp",
            "--tmpfs", "/var/lib/postgresql/data", "postgres:17-alpine")


def parse_loopback_port(mapping):
    matches = [re.fullmatch(r"127\.0\.0\.1:(\d+)", line.strip()) for line in mapping.splitlines()]
    ports = [int(match.group(1)) for match in matches if match]
    if len(ports) != 1 or not 1 <= ports[0] <= 65535 or len(mapping.splitlines()) != 1:
        raise ValueError("exigido exatamente um 127.0.0.1:<porta> em 5432/tcp")
    return ports[0]


def sanitize_postgres_output(value, secret_values=()):
    value = value or ""
    value = re.sub(r"(?i)postgres(?:ql)?(?:\+[a-z0-9_.-]+)?://[^\s'\"]+", "[DATABASE_URL REDACTED]", value)
    value = re.sub(r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", value)
    value = re.sub(r"(?i)Authorization:\s*Bearer\s+\S+", "Authorization: Bearer [REDACTED]", value)
    for secret in secret_values:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value.strip()


def run_restore_role_setup(docker, container, database, roles_sql, password):
    result = subprocess.run(
        [docker, "exec", "-i", "-e", f"PGPASSWORD={password}", container, "psql", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1",
         "-p", "5432", "-U", "postgres", "-d", database],
        input=roles_sql, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode:
        stdout = sanitize_postgres_output(result.stdout, (password,)) or "(vazio)"
        stderr = sanitize_postgres_output(result.stderr, (password,)) or "(vazio)"
        raise RuntimeError(
            "Falha ao preparar roles fictícias no destino descartável de restore; "
            f"psql exit code={result.returncode}; stdout={stdout}; stderr={stderr}"
        )
    return result


def wait_for_postgres(docker, container, database, password, attempts=60, interval=0.5):
    command = [docker, "exec", container, "pg_isready", "-h", "127.0.0.1", "-p", "5432",
               "-U", "postgres", "-d", database]
    last = None
    for _ in range(attempts):
        last = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if last.returncode == 0:
            return
        time.sleep(interval)

    state = subprocess.run(
        [docker, "inspect", "--format",
         '{{.State.Status}}|running={{.State.Running}}|exit={{.State.ExitCode}}|health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}',
         container], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    logs = subprocess.run([docker, "logs", "--tail", "80", container], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    probe = sanitize_postgres_output((last.stdout if last else "") + (last.stderr if last else ""), (password,))
    state_text = sanitize_postgres_output(state.stdout or state.stderr, (password,))
    logs_text = sanitize_postgres_output(logs.stdout + logs.stderr, (password,))
    raise RuntimeError(
        f"PostgreSQL descartável {container}/{database} não ficou pronto via TCP 127.0.0.1:5432; "
        f"pg_isready exit={last.returncode if last else 'n/a'}: {probe or '(vazio)'}; "
        f"container={state_text or '(indisponível)'}; logs={logs_text or '(vazio)'}"
    )


def main():
    docker = "docker"
    run_id = uuid4().hex[:12]
    name = f"investment-homologation-source-{run_id}"
    restore_name = f"investment-homologation-restore-{run_id}"
    network = f"investment-homologation-net-{run_id}"
    source_db = f"investment_source_{run_id}"
    restore_db = f"investment_restore_{run_id}"
    password = secrets.token_urlsafe(24)
    temp_root = Path(os.environ.get("INVESTMENT_TEMP_DIR", ""))
    if not temp_root.is_absolute() or not temp_root.is_dir():
        raise RuntimeError("INVESTMENT_TEMP_DIR precisa apontar para uma pasta temporária existente")
    if os.name == "nt" and str(temp_root.resolve()).lower() != r"e:\investmentdashboard\temp":
        raise RuntimeError("O temporário deste ensaio deve ficar em E:\\InvestmentDashboard\\temp")
    backup_path = None
    network_created = False
    def run(*args):
        result = subprocess.run([docker, *args], capture_output=True, text=True)
        if result.returncode:
            # Do not include argv (it contains the disposable database password).
            detail = (result.stderr or result.stdout or "sem diagnóstico do Docker").strip()
            detail = detail.replace(password, "[redacted]")[:2000]
            raise RuntimeError(f"Docker falhou em '{args[0]}': {detail}")
        return result.stdout.strip()

    def owned_container(container_name):
        result = subprocess.run(
            [docker, "inspect", "--format",
             '{{index .Config.Labels "com.investment-dashboard.homologation"}}',
             container_name], capture_output=True, text=True
        )
        return result.returncode == 0 and result.stdout.strip() == run_id

    def published_loopback_port(container_name):
        try:
            mapping = run("port", container_name, "5432/tcp")
        except RuntimeError as exc:
            inspect = subprocess.run(
                [docker, "inspect", "--format",
                 "{{json .HostConfig.PortBindings}}|{{json .NetworkSettings.Ports}}|{{.HostConfig.NetworkMode}}",
                 container_name], capture_output=True, text=True
            )
            detail = inspect.stdout.strip() if inspect.returncode == 0 else "docker inspect indisponível"
            raise RuntimeError(
                f"Container {container_name} não publicou 5432/tcp; esperado 127.0.0.1:<porta dinâmica>. "
                f"PortBindings|Ports|NetworkMode={detail}. {exc}"
            ) from exc
        try:
            return parse_loopback_port(mapping)
        except ValueError as exc:
            raise RuntimeError(f"Mapeamento Docker inválido para {container_name}: {mapping!r}; {exc}") from exc
    try:
        if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
            raise RuntimeError("Docker override presente; somente o contexto local padrão é permitido")
        endpoint = run("context", "inspect", "default", "--format", "{{ .Endpoints.docker.Host }}").lower()
        if not endpoint.startswith(("npipe:", "unix:")):
            raise RuntimeError("Endpoint Docker não local; ensaio cancelado")
        run("info", "--format", "{{.ServerVersion}}")
        # This runner never pulls: CI preloads postgres:17-alpine before this step.
        # Keep the inspection so a missing image fails before any container setup.
        run("image", "inspect", "--format", "{{.Id}}", "postgres:17-alpine")
        # Docker Desktop 29 did not expose a host binding on the previous --internal
        # network. A dedicated bridge permits host loopback access; the runner still
        # forces all application DB/Auth configuration to its disposable localhost DB.
        run(*network_create_args(network))
        network_created = True
        run(*container_run_args(name, network, source_db, password, run_id))
        wait_for_postgres(docker, name, source_db, password)
        port = published_loopback_port(name)
        source_url = f"postgresql+psycopg://postgres:{password}@127.0.0.1:{port}/{source_db}"
        # Explicit local test settings override any .env and prevent accidental external DB/Auth use.
        env = {k: v for k, v in os.environ.items() if k not in {
            "DATABASE_URL", "MIGRATION_DATABASE_URL", "TEST_DATABASE_URL", "SUPABASE_URL",
            "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY", "API_TOKEN", "BRAPI_TOKEN",
            "AUTH_MODE", "ENVIRONMENT", "ALLOWED_USER_IDS", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_BIN",
            "PGHOST", "PGPORT", "PGUSER", "PGDATABASE", "PGPASSWORD", "PGSERVICE", "PGSERVICEFILE",
            "PGSSLMODE", "PGSSLROOTCERT", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
            "http_proxy", "https_proxy", "all_proxy",
        } and not k.startswith("PG")}
        env.update({"TEST_DATABASE_URL": source_url, "DATABASE_URL": source_url,
                    "MIGRATION_DATABASE_URL": source_url, "ENVIRONMENT": "test",
                    "AUTH_MODE": "local", "API_TOKEN": "fictional-disposable-test-token",
                    "SUPABASE_URL": "", "CORS_ORIGIN": "http://localhost:5173",
                    "ALLOWED_USER_IDS": "[]", "MARKET_DATA_ENABLED": "false", "BRAPI_TOKEN": "",
                    "TEMP": str(temp_root), "TMP": str(temp_root), "TMPDIR": str(temp_root),
                    "INVESTMENT_TEMP_DIR": str(temp_root), "PYTHONDONTWRITEBYTECODE": "1",
                    "NO_PROXY": "*"})
        backend = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-m", "pytest", "-vv", "--tb=long", "--show-capture=all", "-p", "no:cacheprovider", "tests/test_postgres.py"], env=env, cwd=backend)
        if result.returncode:
            return result.returncode

        print("INTEGRACAO_POSTGRESQL_001_008=PASSOU")
        print("Criando backup lógico fictício e iniciando servidor de restore independente...")
        dump = subprocess.run([docker, "exec", "-e", f"PGPASSWORD={password}", name, "pg_dump", "-h", "127.0.0.1", "-p", "5432",
                               "-U", "postgres", "-Fc", source_db], capture_output=True)
        if dump.returncode:
            detail = (dump.stderr or b"Falha sem diagnostico").decode(errors="replace").replace(password, "[redacted]")[:2000]
            raise RuntimeError(f"pg_dump falhou: {detail}")
        fd, backup_path = tempfile.mkstemp(prefix=f"investment-dashboard-{run_id}-", suffix=".dump", dir=temp_root)
        with os.fdopen(fd, "wb") as backup_file:
            backup_file.write(dump.stdout)
        run(*container_run_args(restore_name, network, restore_db, password, run_id))
        wait_for_postgres(docker, restore_name, restore_db, password)
        roles_sql = """CREATE ROLE investment_runtime LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE investment_test_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS;
CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN;
"""
        # Roles are cluster-global; create them in the guaranteed postgres maintenance DB.
        run_restore_role_setup(docker, restore_name, "postgres", roles_sql, password)
        with open(backup_path, "rb") as backup_file:
            restored = subprocess.run([docker, "exec", "-i", "-e", f"PGPASSWORD={password}", restore_name, "pg_restore", "--exit-on-error",
                                       "-h", "127.0.0.1", "-p", "5432", "-U", "postgres", "-d", restore_db],
                                      stdin=backup_file, capture_output=True)
        if restored.returncode:
            detail = (restored.stderr or b"Falha sem diagnostico").decode(errors="replace").replace(password, "[redacted]")[:2000]
            raise RuntimeError(f"pg_restore falhou: {detail}")
        restore_port = published_loopback_port(restore_name)
        restore_url = f"postgresql+psycopg://postgres:{password}@127.0.0.1:{restore_port}/{restore_db}"
        # Compare row counts, Alembic, catalog security flags and two-owner visibility.
        from verify_backup_restore import snapshot
        source_snapshot = snapshot(source_url)
        restored_snapshot = snapshot(restore_url)
        if source_snapshot != restored_snapshot:
            raise RuntimeError("Snapshot de contagens, RLS/grants ou isolamento divergiu após restore")
        print(f"BACKUP_RESTORE=PASSOU; bytes={len(dump.stdout)}; sha256={__import__('hashlib').sha256(dump.stdout).hexdigest()}")
        print("RESTORE_HEAD=008; CONTAGENS_RLS_GRANTS_ISOLAMENTO=IGUAIS")
        return 0
    finally:
        # Only containers created by this invocation are stopped; no volumes are mounted or removed.
        for container_name in (name, restore_name):
            if owned_container(container_name):
                stopped = subprocess.run([docker, "stop", container_name], capture_output=True)
                if stopped.returncode:
                    print(f"AVISO: não foi possível parar container descartável {container_name}", file=sys.stderr)
        if network_created:
            removed = subprocess.run([docker, "network", "rm", network], capture_output=True)
            if removed.returncode:
                print(f"AVISO: não foi possível remover rede descartável {network}", file=sys.stderr)
        if backup_path and os.path.exists(backup_path):
            os.unlink(backup_path)


if __name__ == "__main__":
    sys.exit(main())
