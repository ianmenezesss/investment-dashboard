"""A/B JWT homologation against an ephemeral local PostgreSQL 17.

No auth overrides, production DB, financial fixtures from real users, or token logs.
"""
from getpass import getpass
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from run_postgres import network_create_args, container_run_args, parse_loopback_port

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def identity_from_token(token):
    import jwt
    try:
        claims = jwt.decode(token, options={"verify_signature": False, "verify_aud": False,
                                            "verify_exp": False})
        return UUID(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise ValueError("Token não contém identidade UUID válida") from None


def auth_url(value):
    parsed = urlsplit(value.strip())
    if (parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".supabase.co")
            or parsed.path or parsed.query or parsed.fragment or parsed.username):
        raise ValueError("SUPABASE_URL deve ser origem HTTPS do projeto Auth, sem caminho")
    return value.strip()


def expect(response, status, label):
    if response.status_code != status:
        raise RuntimeError(f"{label}=FAIL; HTTP={response.status_code}; expected={status}")
    print(f"{label}=PASS")
    return response.json() if response.content else None


def main():
    if input("PostgreSQL local descartável; digite DESCARTAVEL: ").strip() != "DESCARTAVEL":
        raise ValueError("Confirmação descartável ausente")
    supabase = auth_url(input("Origem HTTPS do Supabase Auth (sem chave): "))
    token_a = getpass("JWT de acesso da conta A (entrada oculta): ")
    token_b = getpass("JWT de acesso da conta B (entrada oculta): ")
    a, b = identity_from_token(token_a), identity_from_token(token_b)
    if a == b:
        raise ValueError("A e B precisam ser contas distintas")
    if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
        raise RuntimeError("Docker remoto/override não permitido")
    def docker(*args):
        result = subprocess.run(["docker", *args], capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError(f"Docker {args[0]} falhou; exit={result.returncode}")
        return result.stdout.strip()
    endpoint = docker("context", "inspect", "default", "--format", "{{ .Endpoints.docker.Host }}").lower()
    if not endpoint.startswith(("npipe:", "unix:")):
        raise RuntimeError("Docker Engine não local")
    docker("image", "inspect", "--format", "{{.Id}}", "postgres:17-alpine")
    run_id = uuid4().hex[:12]
    network = f"investment-auth-ab-net-{run_id}"
    container = f"investment-auth-ab-{run_id}"
    database = f"investment_auth_ab_{run_id}"
    password = secrets.token_urlsafe(24)
    role_password = secrets.token_urlsafe(24)
    network_created = container_created = False
    try:
        docker(*network_create_args(network))
        network_created = True
        docker(*container_run_args(container, network, database, password, run_id))
        container_created = True
        for _ in range(60):
            probe = subprocess.run(["docker", "exec", container, "pg_isready", "-h", "127.0.0.1",
                                    "-U", "postgres", "-d", database], capture_output=True)
            if probe.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("PostgreSQL descartável não ficou pronto")
        port = parse_loopback_port(docker("port", container, "5432/tcp"))
        admin_url = f"postgresql+psycopg://postgres:{password}@127.0.0.1:{port}/{database}"
        runtime_url = f"postgresql+psycopg://investment_runtime:{role_password}@127.0.0.1:{port}/{database}"
        backend = Path(__file__).resolve().parents[1]
        env = {k: v for k, v in os.environ.items() if k not in {
            "DATABASE_URL", "MIGRATION_DATABASE_URL", "TEST_DATABASE_URL", "SUPABASE_URL",
            "ALLOWED_USER_IDS", "API_TOKEN", "BRAPI_TOKEN", "DOCKER_HOST", "DOCKER_CONTEXT",
            "PGPASSWORD", "PGHOST", "PGPORT", "PGUSER", "PGDATABASE", "PGSERVICE",
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"} and not k.startswith("PG")}
        env.update({"DATABASE_URL": admin_url, "MIGRATION_DATABASE_URL": admin_url,
                    "ENVIRONMENT": "test", "AUTH_MODE": "supabase", "SUPABASE_URL": supabase,
                    "ALLOWED_USER_IDS": json.dumps([str(a), str(b)]),
                    "MARKET_DATA_ENABLED": "false", "CORS_ORIGIN": "http://localhost:5173",
                    "PYTHONDONTWRITEBYTECODE": "1", "NO_PROXY": "*"})
        def migrate(target):
            result = subprocess.run([sys.executable, "-B", "-m", "alembic", "-c", "alembic.ini",
                                     "upgrade", target], cwd=backend, env=env,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode:
                raise RuntimeError(f"Migration descartável até {target} falhou; exit={result.returncode}")
        migrate("002")
        import psycopg
        from psycopg import sql
        with psycopg.connect(admin_url.replace("postgresql+psycopg://", "postgresql://", 1), autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE ROLE investment_runtime LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT "
                                 "NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}").format(sql.Literal(role_password)))
        migrate("head")
        with psycopg.connect(admin_url.replace("postgresql+psycopg://", "postgresql://", 1), autocommit=True) as conn:
            conn.execute("GRANT USAGE ON SCHEMA public TO investment_runtime")
            conn.execute("GRANT SELECT, INSERT ON public.fixed_income_investments, public.fixed_income_lots, "
                         "public.fixed_income_movements, public.fixed_income_observations TO investment_runtime")
            conn.execute("GRANT USAGE ON SEQUENCE public.fixed_income_investments_id_seq, "
                         "public.fixed_income_lots_id_seq, public.fixed_income_movements_id_seq, "
                         "public.fixed_income_observations_id_seq TO investment_runtime")
            conn.execute("GRANT SELECT, INSERT, DELETE ON public.operations TO investment_runtime")
            conn.execute("GRANT USAGE ON SEQUENCE public.operations_id_seq TO investment_runtime")
            version = conn.execute("SELECT version_num FROM public.alembic_version").fetchone()[0]
            if version != "008":
                raise RuntimeError("Schema descartável não chegou à migration 008")
        # Import only after the local runtime URL and genuine Auth settings are installed.
        os.environ.update({k: env[k] for k in ("ENVIRONMENT", "AUTH_MODE", "SUPABASE_URL",
                            "ALLOWED_USER_IDS", "MARKET_DATA_ENABLED", "CORS_ORIGIN")})
        os.environ["DATABASE_URL"] = runtime_url
        os.environ["MIGRATION_DATABASE_URL"] = ""
        from fastapi.testclient import TestClient
        from sqlalchemy import text
        from app.database import engine
        from app.main import app
        with engine.connect() as conn:
            if conn.scalar(text("SELECT current_user")) != "investment_runtime":
                raise RuntimeError("FastAPI não usa a role runtime descartável")
        if app.dependency_overrides:
            raise RuntimeError("Overrides de autenticação inesperados")
        headers_a = {"Authorization": "Bearer " + token_a}
        headers_b = {"Authorization": "Bearer " + token_b}
        contract = {"issuer": "Banco Fictício", "product_name": "CDB Homologação A/B",
                    "product_type": "CDB", "remuneration": "FIXED", "indexer": "NONE",
                    "contracted_rate": "12", "application_date": "2025-01-01",
                    "maturity_date": "2028-01-01"}
        with TestClient(app) as client:
            expect(client.get("/api/fixed-income/investments", headers=headers_a), 200, "JWT_A_REAL")
            expect(client.get("/api/fixed-income/investments", headers=headers_b), 200, "JWT_B_REAL")
            created_a = expect(client.post("/api/fixed-income/investments", headers=headers_a, json=contract), 201, "A_CREATE_CONTRACT")
            ia = created_a["id"]
            ma = expect(client.post(f"/api/fixed-income/investments/{ia}/applications", headers=headers_a,
                                    json={"date": "2025-01-01", "principal_amount": "100"}), 201, "A_CREATE_APPLICATION")["id"]
            expect(client.get(f"/api/fixed-income/investments/{ia}", headers=headers_a), 200, "A_READ_OWN")
            expect(client.get(f"/api/fixed-income/investments/{ia}", headers=headers_b), 404, "B_READ_A_DENIED")
            expect(client.post(f"/api/fixed-income/investments/{ia}/applications", headers=headers_b,
                               json={"date": "2025-01-01", "principal_amount": "1"}), 404, "B_WRITE_A_DENIED")
            expect(client.post(f"/api/fixed-income/investments/{ia}/redemptions", headers=headers_b,
                               json={"date": "2025-01-02", "principal_amount": "1", "lot_id": 1}), 404, "B_REDEEM_A_DENIED")
            expect(client.delete(f"/api/fixed-income/investments/{ia}/archive", headers=headers_b), 404, "B_ARCHIVE_A_DENIED")
            expect(client.get(f"/api/fixed-income/investments/{ia}/applications/{ma}/revisions", headers=headers_b), 404, "B_HISTORY_A_DENIED")
            body = {"kind": "REPLACE", "expected_revision": 0, "reason": "Ajuste fictício A/B",
                    "replacement_date": "2025-01-01", "replacement_amount": "150"}
            ha = {**headers_a, "Idempotency-Key": str(uuid4())}
            hb = {**headers_b, "Idempotency-Key": str(uuid4())}
            expect(client.post(f"/api/fixed-income/investments/{ia}/applications/{ma}/revisions/preview",
                               headers=hb, json=body), 404, "B_PREVIEW_A_DENIED")
            expect(client.post(f"/api/fixed-income/investments/{ia}/applications/{ma}/revisions",
                               headers=hb, json=body), 404, "B_REVISE_A_DENIED")
            expect(client.post(f"/api/fixed-income/investments/{ia}/applications/{ma}/revisions/preview",
                               headers=ha, json=body), 200, "A_PREVIEW_OWN")
            expect(client.post(f"/api/fixed-income/investments/{ia}/applications/{ma}/revisions",
                               headers=ha, json=body), 201, "A_REVISE_OWN")
            expect(client.get(f"/api/fixed-income/investments/{ia}/applications/{ma}/revisions",
                              headers=headers_a), 200, "A_HISTORY_OWN")
            created_b = expect(client.post("/api/fixed-income/investments", headers=headers_b,
                                           json={**contract, "product_name": "CDB Homologação B"}), 201, "B_CREATE_CONTRACT")
            ib = created_b["id"]
            expect(client.post(f"/api/fixed-income/investments/{ib}/applications", headers=headers_b,
                               json={"date": "2025-01-01", "principal_amount": "75"}), 201, "B_CREATE_APPLICATION")
            expect(client.get(f"/api/fixed-income/investments/{ib}", headers=headers_a), 404, "A_READ_B_DENIED")
            expect(client.delete(f"/api/fixed-income/investments/{ib}/archive", headers=headers_a), 404, "A_ARCHIVE_B_DENIED")
            if any(item["id"] == ib for item in client.get("/api/fixed-income/investments", headers=headers_a).json()):
                raise RuntimeError("A listagem de A mostrou contrato de B")
            if any(item["id"] == ia for item in client.get("/api/fixed-income/investments", headers=headers_b).json()):
                raise RuntimeError("A listagem de B mostrou contrato de A")
            print("CROSS_OWNER_LISTS=PASS")
        print("AUTH_AB_ISOLATION=PASS; postgres=disposable; alembic=008; auth=real_JWT")
        return 0
    finally:
        if container_created:
            inspected = subprocess.run(["docker", "inspect", "--format",
                '{{index .Config.Labels "com.investment-dashboard.homologation"}}', container],
                capture_output=True, text=True)
            if inspected.returncode == 0 and inspected.stdout.strip() == run_id:
                subprocess.run(["docker", "stop", container], capture_output=True)
        if network_created:
            subprocess.run(["docker", "network", "rm", network], capture_output=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Never print exception messages: database errors can contain secrets or rows.
        print("AUTH_AB_ISOLATION=FAIL; cause=" + type(exc).__name__)
        sys.exit(1)
