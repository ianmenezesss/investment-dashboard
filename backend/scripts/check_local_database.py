"""Auditoria local sem imprimir DSN, registros, contagens ou fingerprints privados."""
import argparse
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from app.database import engine


def snapshot():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        rows = connection.execute(text("SELECT id, ticker, kind, date, quantity, price, fees, created_at FROM operations ORDER BY id"))
        digest = hashlib.sha256()
        for row in rows:
            digest.update(repr(tuple(row)).encode())
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        return digest.digest(), revision


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--api-check", action="store_true")
    args = parser.parse_args()
    before, revision = snapshot()
    print(f"Conexão PostgreSQL: OK; revisão Alembic: {revision}")
    if args.api_check:
        from fastapi.testclient import TestClient
        from app.database import settings
        from app.main import app
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {settings.api_token.get_secret_value()}"}
            for route in ["/health", "/api/dashboard", "/api/operations", "/api/export"]:
                assert client.get(route, headers=headers).status_code == 200
        print("Conexão FastAPI/PostgreSQL: OK; leituras autenticadas verificadas sem exibir registros")
    if args.migrate:
        command.upgrade(Config("alembic.ini"), "head")
        after, revision = snapshot()
        assert after == before, "Registros originais foram alterados"
        print(f"Migração aditiva: OK; revisão: {revision}; registros originais preservados")
    if args.restart:
        engine.dispose()
        docker = os.environ.get("DOCKER_BIN", "docker")
        result = subprocess.run([docker, "compose", "restart", "db"], cwd=Path(__file__).resolve().parents[2], capture_output=True)
        if result.returncode:
            raise RuntimeError("Não foi possível reiniciar o serviço db")
        for _ in range(60):
            try:
                after, _ = snapshot()
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("PostgreSQL não voltou a responder no prazo")
        assert before == after, "A verificação de persistência não corresponde ao estado anterior"
        print("Persistência após reinicialização: OK; registros originais preservados")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # O traceback pode incluir configuração privada; não imprimir.
        print("Verificação interrompida. Confira serviço, configuração e migrações localmente; nenhum detalhe privado foi exibido.")
        sys.exit(1)
