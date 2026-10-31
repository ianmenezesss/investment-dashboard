# Investment Dashboard

Plataforma full stack para acompanhamento de investimentos em ações brasileiras. Reúne operações, posições por custo médio, resultados realizados e visualizações em uma interface responsiva em português, com valores em reais e persistência PostgreSQL.

**Estado do produto: candidato v1.0.0 em revisão final; ainda não publicado como release GitHub.** A `main` inclui autenticação Supabase, dashboard de carteira, ações, renda fixa, eventos financeiros, Histórico, relatórios, simulador e metas. O proprietário confirmou manualmente login/logout, navegação e páginas funcionais, demonstração pública e layout desktop/celular; esta revisão não confirma independentemente a configuração dos painéis nem os SHAs servidos. A demonstração pública foi projetada para operar offline com dados fictícios. Metas são salvas localmente por identidade no navegador e não sincronizam entre dispositivos. Consulte o [roadmap](docs/roadmap.md), o [handoff](docs/v5-development-handoff.md) e o [checklist v1.0.0](docs/v1.0-release-readiness.md) para limitações e critérios.

Tecnologias: React 19, TypeScript, Vite, Tailwind, componentes shadcn/Radix, Recharts, Lucide, React Router, TanStack Query; Python 3.12+, FastAPI, SQLAlchemy, Alembic, Pydantic, PostgreSQL 17, Pytest e PyJWT com criptografia.

Documentação:

- [Arquitetura, fórmulas e próximas fases](docs/architecture.md).
- [Configurar e testar Supabase Auth localmente](docs/supabase-auth.md).
- [Separação entre demonstração e carteira privada](docs/demo-and-private.md).
- [Como testar a demonstração interativa](docs/interactive-demo.md).
- [Auditoria de segurança e arquivos alterados](docs/security-audit.md).
- [Configuração futura de Vercel, Render e Supabase](docs/deployment.md).
- [Testes e limites da verificação](docs/validation.md).
- [Checklist de aceitação para a v1.0](docs/v1.0-release-readiness.md).
- [Rascunho das notas de lançamento v1.0.0](docs/release-notes-v1.0.0.md) e [changelog](CHANGELOG.md).

## Fase 1

- Dashboard responsivo com custo da posição, compras e resultado realizado.
- Gráfico interativo de fluxo das operações e composição por custo.
- Cadastro de compras/vendas, custo médio com taxas e validação de posição cronológica.
- Histórico com pesquisa, ordenação por data e exclusão confirmada.
- Persistência PostgreSQL, migrações Alembic, exportação JSON e token de acesso local.
- Demonstração interativa opcional, com localStorage exclusivo para dados fictícios e separada dos registros reais.

Os cálculos disponíveis distinguem custo, principal, fluxos, cotações atuais e valores de mercado com cobertura. Eles não equivalem automaticamente à rentabilidade total da carteira. Histórico consolidado, TWR/MWR e benchmarks permanecem condicionados à existência de avaliações históricas completas, fluxos confiáveis e fontes adequadas. A demo usa somente dados fictícios e não acessa a API privada.

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

Para testar somente a demonstração pública localmente, copie `frontend/.env.public.example` para `frontend/.env.local` e reinicie o Vite. Não coloque segredos em variáveis `VITE_*`. O build de produção continua demonstrativo por padrão; `VITE_APP_MODE=private` habilita explicitamente a interface Supabase e exige configuração própria. `VITE_PUBLIC_DEMO=true` sempre força demonstração e bloqueia chamadas privadas.

Para usar o usuário Supabase que você criou, siga [docs/supabase-auth.md](docs/supabase-auth.md): configure `AUTH_MODE=supabase`, `SUPABASE_URL` e `ALLOWED_USER_IDS` no backend, sem alterar `DATABASE_URL`; use o modelo `frontend/.env.supabase.example` no frontend. O login não atribui registros locais antigos à conta: eles continuam preservados com proprietário nulo.

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

## Backup e recuperação

O botão **Exportar** salva um JSON dos registros cobertos pela API; não deve ser tratado como cópia completa do PostgreSQL, de configurações hospedadas ou das metas locais do navegador. As metas não sincronizadas precisam de estratégia própria se a preservação delas for importante.

Os comandos a seguir se aplicam somente ao PostgreSQL local do Compose:

```powershell
docker compose exec db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/investment.dump'
docker compose cp db:/tmp/investment.dump ./investment.dump
```

Guarde o arquivo fora do repositório. Para ensaiar uma restauração, use outro banco descartável e valide antes de qualquer substituição. O volume Docker local persiste entre reinicializações; não o remova se contiver dados pessoais.

Para a v1.0.0 foi gerado um único backup manual do schema `public` fora do repositório; tamanho e SHA-256 foram conferidos. Não há agendamento, retenção de múltiplas cópias ou serviço pago. O arquivo é um dump custom PostgreSQL cifrado com AES-256-GCM; o restore do artefato real em PostgreSQL descartável ainda depende de autorização para informar a frase localmente. Auth, binários do Storage e configurações externas não fazem parte desse backup. Escopo e limitações estão em [docs/manual-backup.md](docs/manual-backup.md).

## Segurança e escopo

Os comandos locais e o Compose usam somente loopback. O token fica apenas na memória da página e é descartado ao recarregar. Não exponha o servidor Vite como servidor de produção. Não há APIs financeiras externas ou cotações automáticas.

O backend possui um modo Supabase opt-in com verificação criptográfica de JWT, allowlist de UUIDs, filtros por proprietário e RLS. O frontend privado agora possui login por e-mail/senha, sem cadastro público, e sessão por aba em sessionStorage. A configuração externa ainda é necessária; o modelo de deploy público continua exclusivo da demonstração. Assinaturas HS256 são recusadas; use chaves assimétricas ES256/RS256 no Supabase.

Produção rejeita o token local, exige CORS HTTPS exato, PostgreSQL com TLS verificável e papel de runtime sem superusuário, bypass RLS ou propriedade da tabela. Todos os endpoints financeiros exigem autenticação. Erros de banco retornam mensagens genéricas e respostas da API usam `Cache-Control: no-store`.

Antes de publicar no GitHub, siga os comandos e a revisão de arquivos de [docs/deployment.md](docs/deployment.md). Não foi executado `git push` ou deploy automaticamente.
