# Validação do Investment Dashboard

## Fase 2.0.4 — interface privada de renda fixa

- **117 testes frontend aprovados**, incluindo 21 novos: contratos CDI/prefixado, aplicação,
  resgate parcial/total, principal/caixa, oito casas, paginação, estimativas/null, loading,
  erros/retry, 401/403, troca de identidade, envio duplicado, Escape/foco e botão contextual.
- App integrado confirma formulário CDB em Renda fixa e formulário de ações em Ações;
  rota forçada de CDB na demo não faz HTTP privado nem inicializa sessão Supabase.
- **242 testes backend e 1 integração PostgreSQL aprovados**, sem alterações no backend,
  sem API SGS/brapi real, usando banco descartável com tmpfs e credencial temporária.
- **Builds público e privado aprovados**, com TypeScript, sem chaves reais. Aviso conhecido
  de bundle >500 kB permanece, assim como depreciação TestClient/httpx no backend.
- Chrome headless com fixtures locais: desktop 1440×1000 e móvel 390×844; documento móvel
  390 px, tabela 650 px em região 340 px e modal ~366,6 px, sem overflow da página.
- Cliente HTTP/QueryClient/Auth existentes reutilizados; nenhum storage financeiro privado,
  nenhuma migration/dependência/configuração remota nova. UI usa somente APIs existentes.
- Sem deploy/commit/push. Homologação autenticada real dos deploys continua pendente.
  Ver [contratos, limitações e roteiro](phase-2.0.4-fixed-income-ui.md).

## Fase 2.0.3 — estimativas de rentabilidade CDB/CDI

- Base inspecionada: commit 1baf46743211c6ee3b4026b2d7932d65b12c8b4b (2.0.2).
- **242 testes backend aprovados**, incluindo 57 novos; SGS exclusivamente simulado.
  Cenários 100/110/120% CDI, lotes distintos, resgates parciais/totais, IR em 180/181/
  360/361/720/721 dias, IOF dias 1–30, arredondamento, precisão intermediária e contexto
  Decimal externo, calendário, lacunas, maturidade e falhas de fornecedor.
- **1 teste integrado PostgreSQL aprovado**, ampliado com o endpoint de rentabilidade sob
  RLS/role restrita: conta B não lê contrato A, leitura não cria movimentos, estimativas
  reconciliam com fixture. Migrations e invariantes das fases anteriores preservadas.
- Endpoint novo usa snapshot SQL único por proprietário e libera transação antes do SGS.
  Principal é separado de rendimentos; valores incompletos são null; tributos realizados
  são informação insuficiente, sem deduzir impostos a partir do caixa recebido.
- Convenção/calendário/perfil tributário explícitos. Calendário revisado cobre 2024–2026;
  outros anos e condições contratuais não modeladas não recebem estimativas inventadas.
- Sem mudanças em modelos, APIs anteriores, migrations, RLS, auth, ações ou frontend/demo.
  Frontend/builds não reexecutados: nenhuma alteração nesses arquivos. Aviso conhecido
  TestClient/httpx permanece. Sem commit/push/deploy/migration de produção.
- **Homologação autenticada real no Render não executada**: nenhuma sessão/JWT fornecida
  ou utilizada. Procedimento manual e premissas em [Fase 2.0.3](phase-2.0.3-fixed-income-returns.md).

## Fase 2.0.2 — CDI e Selic via BCB/SGS

- Adaptador HTTPX isolado para SGS 12 (CDI) e 11 (Selic), % ao dia, com Decimal,
  conversão de datas brasileiras, cache LRU expirável e controle local de chamadas.
- Consulta privada em `/api/fixed-income/rates/{11|12}`, com autenticação existente,
  sem banco ou exposição de informações financeiras de usuários. Sem preenchimento
  de dias ausentes, sem cache vencido em erro, sem cálculo de rendimento ou impostos.
- 185 testes backend aprovados (46 novos), com HTTP SGS totalmente simulado; cobertura
  de taxas/datas inválidas, conflitos, listas vazias, rede/status/timeouts, cache e limites.
- 1 teste PostgreSQL integrado aprovado em container descartável, preservando migrations,
  RLS, principal e histórico da 2.0.1. Nenhuma chamada à API SGS real nos testes.
- Frontend, demo, ações, FIIs/ETFs, brapi, autenticação e schema do banco preservados;
  nenhuma migration/dependência/secreto novo. Nenhuma configuração adicional obrigatória
  no Render; acesso HTTPS ao SGS precisa ser homologado após publicação autorizada.
- Aviso conhecido de depreciação TestClient/httpx permanece. Sem deploy/commit/push.
- Ver [contrato, fonte oficial e limites](phase-2.0.2-bcb-rates.md).

## Fase 2.0.1 — modelagem contábil de renda fixa

- 139 testes backend aprovados, incluindo 31 casos novos de contratos CDB, aplicações,
  lotes, resgates parciais/totais, principal versus caixa, precisão, datas e isolamento API.
- 96 testes frontend e builds público/privado aprovados, sem alterar frontend, demo ou ações.
- Migration aditiva 003: contratos, lotes e eventos imutáveis, RLS forçada por proprietário,
  validações/locks PostgreSQL, sem calcular rendimentos ou impostos. DDL renderizado em
  memória e cadeia 001→002→003 verificada; isso não substitui executar em PostgreSQL real.
- Validação PostgreSQL real concluída em 28/10/2026: **1 teste de integração aprovado**,
  incluindo a cadeia 001→002→003, preservação de ação anterior à 003, RLS forçada e
  isolamento direto entre usuários, vínculos e lote sem aplicação, histórico imutável,
  cronologia e rejeição de isolamento transacional incompatível.
- GRANTs SELECT/INSERT e USAGE nas sequências confirmados; UPDATE/DELETE/TRUNCATE negados.
  Defaults permissivos simulados para anon/authenticated/service_role foram revogados
  pela 003; nenhum privilégio PUBLIC restou nas tabelas/sequências novas.
- Dois resgates concorrentes de 70 sobre principal 100: apenas um aceito, saldo 30.
  Resgate total posterior deixou saldo zero e preservou eventos; novo resgate foi rejeitado.
  NUMERIC(20,8) preservou exatamente 999999999999.12345678 pela API/PostgreSQL.
- Executor `backend/tests/run_postgres.py`: container próprio PostgreSQL 17-alpine com
  tmpfs, porta aleatória, senha temporária e remoção ao terminar. Compose tem somente
  o banco persistente `db`; não foi iniciado nem utilizado para testes. Nenhum volume pessoal tocado.
- Regressões backend reexecutadas: **139 aprovadas**. Não foram necessárias correções
  de aplicação/migration; apenas ampliação dos testes e atualização documental.
- Permanecem avisos conhecidos de TestClient/httpx e bundle >500 kB; nenhum erro nos checks executados.
- Migrations executadas somente no banco local descartável de testes; nenhum acesso ao
  Supabase, alteração de dados reais ou deploy/commit/push/tag. Fase 2.0.1 pronta para
  homologação controlada, condicionada ao diagnóstico/backup/permissões do ambiente alvo.
- Ver [modelo, endpoints e procedimento manual Supabase](phase-2.0.1-fixed-income-model.md).

## Fase 1.9.5 — clareza financeira e homologação

- 108 testes backend e 96 frontend aprovados, sem API real ou banco externo.
- Novos cenários: valorização positiva com perda após taxas, compras múltiplas, vendas
  parciais, recompra após encerramento, precisão Decimal, base zero e cotação ausente.
- Resultado realizado/custo legados preservados; autenticação, isolamento e demo offline
  continuam cobertos pelas suítes existentes. PostgreSQL opcional não executado.
- Builds público e privado aprovados. Permanecem os avisos conhecidos de bundle >500 kB
  e depreciação TestClient/httpx, sem falhas.
- Fixture local Chrome 390×844: documento 390 px, tabela 1.456 px em região rolável de 340 px.
  Homologação real de produção permanece manual; nenhum deploy, push, commit ou tag.
- Ver [fórmulas, limites e checklist da Fase 1.9.5](phase-1.9.5-financial-clarity.md).

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
