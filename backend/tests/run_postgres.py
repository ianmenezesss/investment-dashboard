"""Executa integração em container efêmero próprio; não usa .env nem volume pessoal."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from uuid import uuid4


def main():
    docker = os.environ.get("DOCKER_BIN", "docker")
    name = f"investment-test-{uuid4().hex[:10]}"
    password = secrets.token_urlsafe(24)
    def run(*args):
        result = subprocess.run([docker, *args], capture_output=True, text=True)
        if result.returncode:
            # Do not include argv (it contains the disposable database password).
            detail = (result.stderr or result.stdout or "sem diagnóstico do Docker").strip()
            detail = detail.replace(password, "[redacted]")[:2000]
            raise RuntimeError(f"Docker falhou em '{args[0]}': {detail}")
        return result.stdout.strip()
    try:
        run("info", "--format", "{{.ServerVersion}}")
        # Never pull or contact a registry: integration runs only with a cached image.
        run("image", "inspect", "--format", "{{.Id}}", "postgres:17-alpine")
        run("run", "--pull=never", "-d", "--rm", "--name", name, "--env", f"POSTGRES_PASSWORD={password}",
            "--env", "POSTGRES_DB=investment_tests", "--publish", "127.0.0.1::5432",
            "--tmpfs", "/var/lib/postgresql/data", "postgres:17-alpine")
        for _ in range(60):
            ready = subprocess.run([docker, "exec", name, "pg_isready", "-U", "postgres", "-d", "investment_tests"], capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Banco de testes não iniciou")
        port = run("port", name, "5432/tcp").rsplit(":", 1)[1]
        env = dict(os.environ, TEST_DATABASE_URL=f"postgresql+psycopg://postgres:{password}@127.0.0.1:{port}/investment_tests")
        return subprocess.call([sys.executable, "-m", "pytest", "-vv", "--tb=long", "--show-capture=all", "tests/test_postgres.py"], env=env, cwd=Path(__file__).resolve().parents[1])
    finally:
        # Somente o container efêmero criado por este script; sem volumes persistentes.
        subprocess.run([docker, "stop", name], capture_output=True)


if __name__ == "__main__":
    sys.exit(main())
