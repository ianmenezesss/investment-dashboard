# Investment Dashboard

Plataforma full stack para acompanhamento de investimentos em ações brasileiras. Reúne operações, posições por custo médio, resultados realizados e visualizações em uma interface responsiva em português, com valores em reais e persistência PostgreSQL.

**Fase atual: 1.5 — segurança e preparação para publicação.** O código foi preparado para um repositório público e uma demonstração sem conexão com dados pessoais. Nenhum repositório remoto ou deploy foi criado nesta etapa.

Tecnologias: React 19, TypeScript, Vite, Tailwind, componentes shadcn/Radix, Recharts, Lucide, React Router, TanStack Query; Python 3.12+, FastAPI, SQLAlchemy, Alembic, Pydantic, PostgreSQL 17, Pytest e PyJWT com criptografia.

Documentação:

- [Arquitetura, fórmulas e próximas fases](docs/architecture.md).
- [Separação entre demonstração e carteira privada](docs/demo-and-private.md).
- [Auditoria de segurança e arquivos alterados](docs/security-audit.md).
- [Configuração futura de Vercel, Render e Supabase](docs/deployment.md).
- [Testes e limites da verificação](docs/validation.md).

## Fase 1

- Dashboard responsivo com custo da posição, compras e resultado realizado.
- Gráfico interativo de fluxo das operações e composição por custo.
- Cadastro de compras/vendas, custo médio com taxas e validação de posição cronológica.
- Histórico com pesquisa, ordenação por data e exclusão confirmada.
- Persistência PostgreSQL, migrações Alembic, exportação JSON e token de acesso local.
- Demonstração opcional, em memória e separada dos registros reais.

O patrimônio a mercado está indisponível até cadastrar cotações em uma fase posterior. Os valores da demonstração são fictícios, sem vínculo com preços reais. Compras de ativos não equivalem a aportes externos; o gráfico atual mostra fluxo de operações. CDBs, simulador, metas, proventos e benchmarks estão planejados; não foram implementados nesta fase.

## Requisitos

Node.js 22.12+ (ou 24+), npm, Python 3.12+ e Docker Desktop com engine em execução (ou PostgreSQL local).

## Configuração (PowerShell)

Abra o terminal na pasta `investment-dashboard`:

```powershell
Copy-Item .env.example .env
```

Edite `.env`: escolha senha local do PostgreSQL e um token longo e aleatório. Atualize `DATABASE_URL` com a mesma senha; caracteres especiais devem ser codificados como URL. Não versione esse arquivo. O exemplo serve apenas de modelo.

```powershell
docker compose up -d db
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Use `python3.12.exe` no lugar de `python` se necessário no Windows. Os comandos do backend devem ser executados dentro de `backend`, para resolver o `.env` da raiz.

Para reproduzir exatamente as dependências Python verificadas, instale primeiro `pip install -r requirements.lock.txt` no ambiente virtual. O resultado das verificações e suas limitações está em [docs/validation.md](docs/validation.md).

Em outro terminal, na raiz:

```powershell
cd frontend
npm install
npm run dev
```

Abra http://localhost:5173. Digite o `API_TOKEN` configurado e clique em **Conectar**. Ou clique em **Explorar demonstração** para conferir o dashboard sem backend. A demonstração desabilita gravações. Ao alternar para demonstração ou desconectar, as consultas são canceladas e o cache privado é descartado.

Para testar somente a demonstração pública localmente, copie `frontend/.env.public.example` para `frontend/.env.local` e reinicie o Vite. Não coloque segredos em variáveis `VITE_*`. Todo build de produção desta fase inicia na demonstração e bloqueia chamadas à API privada, mesmo sem essa variável.

API: http://127.0.0.1:8000/docs. Diagnóstico com banco: http://127.0.0.1:8000/health. Endpoints `/api/*` exigem `Authorization: Bearer <API_TOKEN>`.

## Verificação

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tests/run_postgres.py
```

```powershell
cd frontend
npm run build
npm test
```

Os testes financeiros não dependem do banco. Os testes HTTP usam SQLite em memória, sem carregar suas credenciais. `tests/run_postgres.py` cria um container efêmero independente, testa migrações, escrita, isolamento e RLS e encerra apenas esse container. Exige Docker em execução e a imagem postgres:17-alpine. No Windows, se Docker não estiver no PATH, configure `$env:DOCKER_BIN = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'`. Nunca aponte `TEST_DATABASE_URL` para um banco com registros reais.

Para auditar arquivos antes de publicar, na raiz:

```powershell
backend\.venv\Scripts\python.exe scripts/audit_publication.py
```

O scanner verifica regras de ignore, candidatos e, se existir, histórico Git. Não substitui a revisão manual de arquivos staged nem a detecção de dados pessoais arbitrários.

## Backup

O botão **Exportar** salva um JSON dos registros da API (ou um arquivo claramente identificado de demonstração). Não há importação automática nesta fase. Para backup completo do PostgreSQL:

```powershell
docker compose exec db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/investment.dump'
docker compose cp db:/tmp/investment.dump ./investment.dump
```

Guarde o backup fora do repositório. Para restaurar, use `pg_restore` em um banco separado e valide antes de substituir o original. O volume Docker preserva dados entre reinicializações. Não remova o volume com seus dados pessoais.

## Segurança e escopo

Os comandos locais e o Compose usam somente loopback. O token fica apenas na memória da página e é descartado ao recarregar. Não exponha o servidor Vite como servidor de produção. Não há APIs financeiras externas ou cotações automáticas.

O backend possui um modo Supabase opt-in com verificação criptográfica de JWT, allowlist de UUIDs, filtros por proprietário e RLS. Está desativado por padrão e ainda depende da configuração externa descrita em [deploy](docs/deployment.md). O frontend privado com login por e-mail/senha é uma próxima etapa: o build público atual nunca serve como interface para a carteira privada.

Produção rejeita o token local, exige CORS HTTPS exato, PostgreSQL com TLS verificável e papel de runtime sem superusuário, bypass RLS ou propriedade da tabela. Todos os endpoints financeiros exigem autenticação. Erros de banco retornam mensagens genéricas e respostas da API usam `Cache-Control: no-store`.

Antes de publicar no GitHub, siga os comandos e a revisão de arquivos de [docs/deployment.md](docs/deployment.md). Não foi executado `git push` ou deploy automaticamente.
