# Validação do Investment Dashboard

## Fase 1.9.4 — dashboard privado com avaliação de mercado

- 92 testes frontend aprovados em 9 arquivos, com snapshots/HTTP simulados e zero brapi real.
- Builds público e privado aprovados, incluindo TypeScript, sem chaves reais. Aviso conhecido
  de bundle acima de 500 kB permanece.
- Cobertura de complete/partial/stale/unavailable/empty, totais null, precisão/arredondamento,
  horários, erro/pendência de atualização e invalidação do snapshot após compra/exclusão fictícia.
- Navegação usa uma consulta valuation inicial, com staleTime de 30 min e sem polling; preserva
  os testes da sessão 1.8.4 e a demo offline. Não foram adicionadas chamadas externas à demo.
- Chrome headless: componente isolado em 1440×1050 e 390×844; viewport/documento móvel 390,
  tabela rolável com conteúdo 1060 em região de 340 px. Fixtures fictícios, sem login real.
- Sem alteração de backend, auth, RLS, migrations, dependências ou infraestrutura. Não houve
  deploy/push/tag. Homologação da interface publicada permanece pendente.
- Ver [registro e roteiro da Fase 1.9.4](phase-1.9.4-market-dashboard.md).

## Fase 1.9.3 — avaliação de posições abertas

- 96 testes backend aprovados (23 novos), sem brapi real; PostgreSQL opcional excluído.
- 78 testes frontend aprovados, preservando sessão e demo. Nenhum código frontend alterado.
- GET /api/dashboard/valuation usa snapshot privado, QuoteService existente e Decimal;
  mantém resultado realizado e retorna totais null quando a cobertura de preços é incompleta.
- Sem mudanças em auth, RLS, migrations, banco, dependências ou fases 1.9.1/1.9.2/1.8.4.
- Ver [fórmulas e contrato da Fase 1.9.3](phase-1.9.3-portfolio-valuation.md).
- Nenhum deploy, push, tag ou consumo da API real. Homologação remota permanece pendente.

## Fase 1.9.2 — infraestrutura de cotações gratuitas

- 73 testes backend aprovados, com HTTPX MockTransport/SQLite em memória; PostgreSQL opcional
  excluído. Cobre cache de 30 min, concorrência, quota, deadline, dados ausentes/inválidos,
  cooldown, stale fallback, segurança do token e isolamento por proprietário no novo endpoint.
- 78 testes frontend e builds demo/privado aprovados, sem chamadas reais de mercado ou chaves reais.
- Sem alteração de autenticação, RLS, banco, migrations, cálculos de patrimônio ou frontend.
  Fases 1.9.1 e 1.8.4 preservadas. Nenhum deploy/push/tag.
- Ver [documentação da Fase 1.9.2](phase-1.9.2-market-data.md) para configuração, limites,
  isolamento do dotenv nos testes e homologação manual futura.

## Fase 1.8.4 — sessão e navegação

Verificado em 27/10/2026, sem deploy, push ou tag:

- Regressão reproduzida antes da correção: 2 testes falharam ao exigir ausência do formulário
  durante a restauração e preservação do dashboard/cache/modal/rota após SIGNED_IN no refoco.
- Após a correção: **78 testes frontend aprovados**, em 8 arquivos. Incluem renovação do JWT
  com consulta pendente, foco repetido, erros transitórios, troca de identidade, logout remoto
  durante restauração, expiração e prioridade de 401/403 sobre falhas de outras consultas.
- **Build público e build privado aprovados**, incluindo TypeScript. Variáveis de build somente
  no processo filho, sem chave real. Aviso não bloqueante de bundle acima de 500 kB permanece.
- Nenhuma chamada real à API/Supabase: testes usam mocks. A inspeção visual no navegador da Vercel
  e a homologação de sessão real em produção continuam pendentes antes de qualquer tag.
- Nenhuma alteração em backend, migrations, RLS, banco ou cálculos financeiros. O documento
  versionado `docs/phase-1.9.1-market-data-plan.md` permaneceu sem alterações em relação ao HEAD.

Ver [registro da Fase 1.8.4](phase-1.8.4-session-navigation.md) para causa, solução e roteiro manual.
Não há changelog separado no checkout. Commit sugerido:
`fix(phase-1.8.4): prevent login flash on tab focus`.

## Histórico: Verificação da Fase 1.6.3

Em 27/10/2026, sem deploy ou push:

- **53 testes frontend aprovados**. Incluem confirmação/cancelamento, Escape, retorno do foco, preservação de carteiras v1, gravação em schema v2, restauração para seed v2, novos dados com ganhos/perdas, Ações com posições e operações e exportação demonstrativa sem rede.
- **22 testes backend aprovados**; integração opcional ignorada na suíte unitária e executada separadamente: **1 integração PostgreSQL aprovada**, em container efêmero independente.
- Builds privado e público aprovados, com artefato final público demonstrativo. Aviso não bloqueante de bundle acima de 500 kB permanece.
- Chrome headless com perfil vazio: inspeção visual em 1440×1050 e 390×844; documento móvel com largura 390, sem overflow horizontal de página. Tabelas mantêm rolagem própria.
- Modal real: foco inicial em Cancelar; Tab segue para Restaurar carteira; segundo Tab volta a Cancelar. Escape fecha. Testes verificam também foco devolvido ao botão de origem e storage intacto após cancelamento.
- Nenhum `window.alert`, `window.confirm` ou `window.prompt` permanece no código da interface. Nenhuma biblioteca nova foi instalada.
- WCAG 2.2 AA foi usada como referência de contraste, alvos, foco e semântica. Não foi realizada certificação completa ou teste manual com todos os leitores de tela.
- Nenhuma alteração de DATABASE_URL, autenticação Supabase, registros privados ou volumes Docker. Capturas de QA usam somente dados fictícios e ficam em diretório temporário ignorado pelo Git.

O schema e o seed são versionados separadamente: visitantes existentes não recebem operações novas automaticamente. Para visualizar o conjunto de 26 operações, confirmar **Restaurar carteira**. Dados corrompidos/versões desconhecidas continuam recuperando a carteira fictícia com aviso.

## Histórico: Fase 1.6.2

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
