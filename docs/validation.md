# Verificação da Fase 1.6.2

Em 27/10/2026, sem deploy ou push:

- **48 testes frontend aprovados**: fluxo privado existente, demonstração interativa pela interface, recarga/restauração, escrita/exclusão local, validações, falha de quota, versões incompatíveis e separação dos repositórios.
- **22 testes backend aprovados**, com a integração PostgreSQL opcional ignorada nessa execução; **1 integração PostgreSQL aprovada separadamente** em container temporário exclusivo de testes.
- Quatro casos fictícios compartilhados entre Vitest e Pytest verificam custo médio, taxas, resultado realizado, liquidação e cronologia por data/ID.
- Builds privado e público aprovados; artefato final em modo público demonstrativo. Aviso não bloqueante de bundle maior que 500 kB permanece.
- Auditoria npm: **0 vulnerabilidades reportadas**. O aviso não bloqueante do adaptador Starlette/httpx nos testes backend permanece.
- Nenhuma alteração de DATABASE_URL, registros financeiros pessoais, autenticação privada, migrations ou volumes Docker. A persistência nova é exclusiva de dados fictícios no navegador.

Instruções e limites: [demonstração interativa](interactive-demo.md). A versão anterior já havia separado login/dashboard; essa fronteira permanece e os testes de autenticação existentes foram executados novamente.

## Histórico: Fase 1.6

Em 27/10/2026:

- **18 testes backend aprovados**; o teste opcional de PostgreSQL foi ignorado na execução unitária e executado separadamente: **1 integração aprovada** em container efêmero.
- **15 testes frontend aprovados**: demonstração pública, configuração de cliente, login/logout, rejeição de credenciais, recuperação validada por getUser, sessão expirada/inválida, renovação/encerramento remoto, JWT enviado à API e reação a 401.
- Builds TypeScript/Vite dos modos privado e público aprovados, sem credenciais reais. O artefato final permanece em demonstração pública.
- Auditoria npm: 0 vulnerabilidades reportadas. Scanner local verificou 61 candidatos, 3 artefatos públicos e o histórico Git, sem detectar segredos conhecidos. `git diff --check` passou.
- Leituras autenticadas da API com PostgreSQL local retornaram 200; Alembic continua em `002`. Nenhuma nova migração, atribuição de proprietário, gravação financeira ou alteração de DATABASE_URL foi executada.
- SDK Supabase simulado nos testes frontend; assinatura e JWKS testados com chaves criptográficas efêmeras no backend. O projeto Supabase real não foi usado, pois suas variáveis locais ainda não estavam preenchidas.
- Nenhum push, deploy, reset de banco ou remoção de volume pessoal.

Limites: teste real de login com a conta do proprietário, algoritmo ativo no projeto Supabase, configuração remota de inscrições, CSP privada com domínios reais e homologação em navegador permanecem pendentes. As instruções estão em [Supabase Auth](supabase-auth.md). Os avisos não bloqueantes de tamanho do bundle e depreciação do adaptador Starlette/httpx continuam.

## Histórico: Fase 1.5

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
