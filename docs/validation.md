# Verificação da Fase 1.5

Verificado em 27/10/2026, sem publicação externa:

| Verificação | Resultado |
| --- | --- |
| Backend unitário e HTTP | 15 aprovados; integração opcional ignorada nessa execução |
| Integração PostgreSQL independente | 1 aprovado em container efêmero separado |
| Autorização | Todos os endpoints financeiros rejeitam ausência de token e token inválido antes de acessar o banco |
| JWT | Assinatura, expiração, issuer, audience, role e allowlist testados com chaves efêmeras |
| Isolamento | Leituras/exportações por proprietário, criação com proprietário do servidor e negação de exclusão entre usuários |
| RLS | Papel PostgreSQL sem bypass enxerga apenas o proprietário; sem contexto não enxerga registros |
| Configuração de produção | Token local/CORS aberto e papel privilegiado/RLS ausente são recusados |
| Frontend | 3 testes aprovados: navegação pública sem login/rede, bloqueio HTTP e produção sempre demonstrativa |
| Build | TypeScript e Vite aprovados |
| Dependências npm | Auditoria final com 0 vulnerabilidades reportadas após atualizar Vitest para 5.0.5 |
| Banco local | FastAPI conectado; health, dashboard, operações e exportação autenticados retornaram 200 sem exibir conteúdo |
| Migrações locais | `002` aplicada de forma aditiva; dados originais preservados |
| Integridade do schema | `alembic check` sem novas operações detectadas |
| Persistência | Confirmada após reiniciar somente `db`, sem remover volumes |
| Publicação | Scanner aprovado, regras de ignore verificadas; não havia Git local ou histórico |
| Inicialização | Uvicorn respondeu OpenAPI HTTP 200 no smoke test isolado |

O scanner detectou configuração local ainda igual ao placeholder público de senha PostgreSQL. Não é apresentada como credencial segura e não pode ser reutilizada no deploy. Foi preservada para não desalinhar a instalação; a rotação coordenada é uma pendência documentada.

Limites: JWT/JWKS real do Supabase, login remoto, rede/TLS entre provedores, deploy, execução da CI no GitHub e inspeção visual em navegador não foram validados. Vitest/jsdom verificou renderização e navegação com rede simulada. Há avisos não bloqueantes de bundle Vite acima de 500 kB, tamanho zero de gráfico no DOM de teste e depreciação do adaptador Starlette/httpx.

Os snapshots de persistência usam comparações em memória; não salvam dados financeiros, contagens ou fingerprints em relatórios. O script de diagnóstico nunca imprime DSN, tokens ou registros. A primeira tentativa de diagnóstico travou durante a conexão e foi encerrada; a repetição com timeout completou migração, reinicialização e conferência.

## Histórico: Fase 1

Verificado em 27/10/2026:

- Dependências npm instaladas, com package-lock.json.
- TypeScript e build Vite executados com sucesso.
- Servidor Vite iniciado e resposta HTTP 200 confirmada.
- Ambiente Python 3.12 criado e dependências instaladas; versões em backend/requirements.lock.txt.
- Pytest: 4 aprovados, 1 ignorado. Cobertura de custo médio, taxas, resultado realizado, venda anterior à compra, liquidação, autenticação e respostas vazias da API.
- Processo Uvicorn iniciado e OpenAPI retornou HTTP 200. Esse smoke test usa configuração SQLite, sem validar a persistência PostgreSQL.

Limites de verificação:

- Docker engine não estava em execução. Migração, gravação e teste de integração PostgreSQL não foram executados. Para validar, inicie Docker Desktop, configure `.env`, suba o banco e rode Alembic conforme README. O teste PostgreSQL opcional exige um banco exclusivo e vazio em TEST_DATABASE_URL.
- Não foi realizada inspeção visual automatizada em navegador. O servidor e o build foram verificados por HTTP e compilação.
- Vite emite aviso de bundle maior que 500 kB, relacionado ao conjunto de dependências e gráficos. Não impede a compilação; divisão de código pode ser feita na próxima evolução.
- A versão instalada de Starlette emite aviso de depreciação do adaptador de testes httpx; os testes HTTP passaram.

Nenhum registro financeiro real foi criado e nenhuma integração externa foi consultada.
