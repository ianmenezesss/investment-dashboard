"""Smoke test do processo HTTP; não substitui integração PostgreSQL."""
import os
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


if __name__ == "__main__":
    env = dict(os.environ, DATABASE_URL="sqlite://", API_TOKEN="startup-check-only")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8017"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for attempt in range(30):
            if process.poll() is not None:
                raise RuntimeError("Servidor encerrou antes de iniciar")
            try:
                with urlopen("http://127.0.0.1:8017/openapi.json", timeout=1) as response:
                    assert response.status == 200
                    print("Backend iniciou: OpenAPI HTTP 200 (sem validar PostgreSQL)")
                    break
            except URLError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Servidor não iniciou no prazo")
    finally:
        process.terminate()
        process.wait(timeout=10)
