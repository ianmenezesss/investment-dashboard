"""Audita candidatos ao Git e histórico local sem imprimir segredos.

Não modifica o checkout nem inicializa Git nele. Não é garantia de ausência de
dados pessoais arbitrários: revisão manual dos arquivos staged continua necessária.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", "dist"}
SIGNATURES = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\b(?:ghp_|github_pat_|sb_secret_)[A-Za-z0-9_]{16,}"),
    re.compile(rb"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{16,}"),
]


def git(*args, **kwargs):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, **kwargs)


def main():
    secrets = []
    public_examples = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8-sig").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            public_examples[key] = value.strip().strip("\"'")
    reused_example = False
    # Comparação exata com segredos locais conhecidos, sem mostrar os valores.
    for directory, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in files:
            if name.startswith(".env") and not name.endswith(".example"):
                for line in (Path(directory) / name).read_text(encoding="utf-8-sig").splitlines():
                    key, sep, value = line.partition("=")
                    if sep and re.search(r"PASSWORD|TOKEN|SECRET|DATABASE_URL|SERVICE_ROLE", key, re.I):
                        value = value.strip().strip("\"'")
                        if value and value == public_examples.get(key):
                            reused_example = True
                        elif len(value) >= 8:
                            secrets.append(value.encode())

    paths = []
    for directory, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        paths.extend((Path(directory) / f).relative_to(ROOT).as_posix() for f in files)
    payload = b"\0".join(p.encode() for p in paths) + b"\0"
    with tempfile.TemporaryDirectory(prefix="investment-ignore-audit-") as tmp:
        initialized = subprocess.run(["git", "init", "--quiet", tmp], capture_output=True)
        if initialized.returncode:
            raise RuntimeError("Não foi possível preparar a auditoria de ignore")
        ignored_result = git(f"--git-dir={Path(tmp) / '.git'}", f"--work-tree={ROOT}", "check-ignore", "--no-index", "-z", "--stdin", input=payload)
        if ignored_result.returncode not in (0, 1):
            raise RuntimeError("Não foi possível verificar os padrões de ignore")
        ignored = set(ignored_result.stdout.decode().strip("\0").split("\0"))
    tracked = []
    history = []
    if (ROOT / ".git").exists():
        result = git("ls-files", "-z")
        if result.returncode:
            raise RuntimeError("Não foi possível ler os arquivos rastreados")
        tracked = result.stdout.decode().strip("\0").split("\0")
        result = git("rev-list", "--all", "--objects")
        if result.returncode:
            # Repositório inicializado sem commits não tem histórico.
            result = git("rev-parse", "--verify", "HEAD")
            if result.returncode == 0:
                raise RuntimeError("Não foi possível auditar o histórico")
        else:
            history = result.stdout.decode().splitlines()
    problems = set()
    candidates = (set(paths) - ignored) | set(tracked)
    for name in sorted(candidates):
        path = ROOT / name
        if not path.is_file():
            continue
        if name in ignored and name in tracked:
            problems.add(f"{name}: arquivo privado/gerado já rastreado")
        content = path.read_bytes()
        if any(secret in content for secret in secrets) or any(pattern.search(content) for pattern in SIGNATURES):
            problems.add(f"{name}: possível segredo, conteúdo omitido")
    artifacts = [path for path in (ROOT / "frontend" / "dist").rglob("*") if path.is_file()]
    for path in artifacts:
        content = path.read_bytes()
        if any(secret in content for secret in secrets) or any(pattern.search(content) for pattern in SIGNATURES):
            problems.add("Build público: possível segredo, conteúdo omitido")
    for entry in history:
        oid, _, name = entry.partition(" ")
        if git("cat-file", "-t", oid).stdout.strip() != b"blob":
            continue
        content = git("cat-file", "blob", oid).stdout
        if any(secret in content for secret in secrets) or any(pattern.search(content) for pattern in SIGNATURES):
            problems.add("Histórico Git: possível segredo em blob; conteúdo e identificação omitidos")
        if name and (Path(name).name.startswith(".env") and not name.endswith(".example")):
            problems.add("Histórico Git: arquivo de ambiente privado encontrado")
    # Confirmar explicitamente padrões que protegem os arquivos mais importantes.
    fixtures = [".env", ".env.local", "backend/.env", "frontend/.env.production", "portfolio.sql", "backup.dump", "exports/portfolio.json", "investment-registros.json", "private/credentials.json", "server.log", "frontend/.env.example", ".env.example"]
    with tempfile.TemporaryDirectory(prefix="investment-fixtures-") as tmp:
        subprocess.run(["git", "init", "--quiet", tmp], check=True, capture_output=True)
        result = git(f"--git-dir={Path(tmp) / '.git'}", f"--work-tree={ROOT}", "check-ignore", "--no-index", "-z", "--stdin", input=b"\0".join(p.encode() for p in fixtures) + b"\0")
        ignored_fixtures = set(result.stdout.decode().strip("\0").split("\0"))
        for name in fixtures:
            if (name in ignored_fixtures) == name.endswith(".example"):
                problems.add(f"{name}: regra de ignore inadequada")
    print(f"Arquivos candidatos analisados: {len(candidates)}")
    print(f"Artefatos públicos analisados: {len(artifacts)}")
    print("Histórico Git: analisado" if (ROOT / ".git").exists() else "Histórico Git: inexistente neste projeto")
    if reused_example:
        print("Aviso local: há configuração sensível ainda igual a placeholder público; não reutilizar em produção")
    for problem in sorted(problems):
        print(problem)
    if problems:
        return 1
    print("Auditoria de publicação: nenhum segredo conhecido ou assinatura detectado nos candidatos; padrões de ignore verificados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
