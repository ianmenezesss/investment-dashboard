# Validação do Investment Dashboard

## Fase 2.0.8.2-A — base de revisões de aplicações

- Partida confirmada no commit local 5def47d e árvore limpa. Nenhum commit novo foi criado.
- Backend executado: **275 passed, 1 skipped, 1 warning**. O skip é a integração opt-in
  sem TEST_DATABASE_URL; warning conhecido TestClient/httpx.
- Frontend executado: **128 passed** em 10 arquivos. TypeScript e build aprovados;
  permanece o warning de chunk acima de 500 kB (~1.100 kB).
- **Integração PostgreSQL descartável: 1 passed, 1 warning em 2.95s**, resultado
  informado pelo usuário na revisão final. O agente não reexecutou essa integração.
  O runner atual chama tests/test_postgres.py, que migra 001–002, depois 003 e head (006),
  preserva registros anteriores e executa verify_fixed_income_postgres,
  verify_opening_postgres, verify_archive_postgres e verify_revisions_postgres.
  O verificador de renda fixa exige alembic_version=006. Esta confirmação é da cobertura
  do código atual; o resultado de execução é atribuído ao usuário.
- Verificações estáticas executadas: AST Python em 63 arquivos e git diff --check aprovados.
  Auditoria de publicação analisou candidatos, 3 artefatos e histórico Git, sem assinatura
  de segredo ou segredo conhecido detectado. Runner PowerShell executado: interrompeu no
  preflight Docker com exit 1 na implementação anterior, gerando transcript. Na revisão final,
  somente as suítes locais foram repetidas pelo agente; PostgreSQL permanece como relato do usuário.
- Migrations 001–005 preservadas. A 006 não foi aplicada em banco persistente/remoto.
  Sem endpoints de correção/anulação ou grants automáticos de escrita ao runtime.
- [Arquitetura, inventário dos leitores, riscos e comando PowerShell](phase-2.0.8.2-revision-foundation.md).

## Implementação local 2.0.8.1 — arquivamento de contratos CDB vazios

- Arquivamento implementado por tombstone append-only em migration 005, sem alterar ou
  remover contratos, lotes, movimentações ou observações. RLS/FORCE RLS, grants mínimos,
  lock transacional compartilhado e bloqueio de novas dependências estão cobertos no código
  e no teste de integração descartável. A migration foi aplicada somente pelo teste em
  PostgreSQL descartável; não foi aplicada em ambiente persistente ou de produção.
- **Suíte backend completa: 266 aprovados, 1 ignorado** (267 coletados). O único skip é
  `test_migrations_persistence_and_chronological_validation`, pois a execução direta não
  recebe `TEST_DATABASE_URL`. Um aviso existente de depreciação do `TestClient`/httpx permanece.
- **128 testes frontend aprovados** em 10 arquivos. Incluem confirmação explícita,
  cancelamento, sucesso com ocultação da listagem ativa e conflito de elegibilidade.
- **TypeScript e build privado aprovados** (`npm run build -- --configLoader native`).
  Permanece o aviso conhecido de bundle acima de 500 kB (chunk principal ~1.100 kB).
- A revisão da falha do runner encontrou uma asserção inválida no verifier de arquivamento:
  ele esperava a lista de CDBs de A vazia, embora verificadores anteriores já tivessem
  criado outros contratos ativos para A. A asserção foi corrigida para comparar o conjunto
  anterior com o posterior e confirmar que somente o contrato arquivado desapareceu.
- O código de integração PostgreSQL descartável foi ampliado para migration 005: isolamento,
  grants e imutabilidade do tombstone; RLS A/B/sem identidade; rejeição de dependências;
  preservação da linha original; e concorrência entre arquivamento e aplicação. **Resultado
  informado pelo usuário: 1 teste aprovado e 1 warning** no runner descartável. A inspeção
  confirma que `test_migrations_persistence_and_chronological_validation` migra até `head`
  (005) e chama `verify_archive_postgres`; a asserção compara contratos ativos antes/depois.
  O agente não repetiu a integração nesta revisão: Docker está instalado, mas o ambiente negou
  acesso ao Docker Engine pelo named pipe. Nenhum container, download ou banco remoto foi
  usado nesta revisão.
- O runner agora exige a imagem já em cache (`--pull=never`) e mostra detalhes seguros do
  erro Docker/traceback completo. Script PowerShell com transcript em `%TEMP%`:
  `backend/tests/run_postgres_diagnostic.ps1`. Executar do diretório `backend` com
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\run_postgres_diagnostic.ps1`.
- Nesta revisão, suíte backend: **266 aprovados, 1 ignorado** (o teste PostgreSQL opt-in sem
  `TEST_DATABASE_URL`) e um warning conhecido de depreciação `TestClient`/httpx; frontend:
  **128 aprovados**; TypeScript e build aprovados. O build mantém o warning conhecido de chunk
  acima de 500 kB (~1.100 kB). Auditoria de publicação analisou 158 arquivos candidatos,
  3 artefatos e histórico Git; nenhum segredo conhecido/assinatura foi detectado. `git diff
  --check` aprovado, com avisos Git apenas de normalização LF/CRLF. Nenhum dado real, produção,
  push ou deploy foi acessado/executado.
- Plano e limites: [Fase 2.0.8.1](phase-2.0.8.1-empty-cdb-archive.md).

## Revisão final 2.0.7 — 28/10/2026

- Auditoria estática direcionada da migration 004 já aplicada (sem conexão ao Supabase),
  policy/Force RLS, constraints, índices, triggers, endpoint/auth/isolamento e separação
  observação-ledger; nenhuma falha de segurança que justificasse alterar migration ou regra.
- Frontend recebeu dicas acessíveis para principal, lotes, histórico, posição observada,
  estimativas e tributos, com origem visual informada/calculada/estimada.
- **118 testes aprovados no total.** O responsável executou no Windows 75 testes backend
  focais e 1 teste de integração PostgreSQL descartável; resultado informado pelo usuário,
  não reexecutado pelo agente. O foco backend cobriu abertura, renda fixa, estimativas e
  segurança; o runner de integração usa PostgreSQL Docker efêmero.
- **42 testes frontend focais aprovados** (`FixedIncomePage.test.tsx` e
  `MarketDashboard.test.tsx`), incluindo tooltip por foco/teclado, abertura sem lote
  fictício, principal desconhecido, sequência de observações, auth e troca de identidade.
  `tsc -b` aprovado.
- **Build privado aprovado** com `vite build --configLoader native`; chunk JS de 1,099 kB e
  aviso do Vite acima de 500 kB permanecem. TypeScript e build passaram anteriormente e não
  foram reexecutados nesta revisão de preparação.
- Revisão do diff para release: as alterações de aplicação são de apresentação/acessibilidade;
  nenhuma fórmula/cálculo financeiro, autenticação, autorização, endpoint/contrato API,
  backend ou migration foi alterado. O diff contém somente frontend, documentação e um
  teste frontend. `git diff --check` passou; Git emitiu apenas avisos de conversão LF/CRLF.
- Revisão estática dos arquivos alterados/novos não encontrou credenciais, tokens reais,
  URL privada com segredo, informação pessoal ou registros financeiros reais. Números em
  testes são fixtures/boundaries sintéticos; preços em `phase-3.0-technical-plan.md` são
  referências públicas de planos de fornecedores. Nenhum deploy ou consulta remota foi feito.
- `scripts/audit_publication.py` aprovado após as alterações: 154 arquivos candidatos,
  3 artefatos de build e histórico Git analisados; nenhum segredo conhecido/assinatura
  detectado e padrões de ignore confirmados. A auditoria não substitui revisão manual de
  conteúdo arbitrário; o diff também foi revisado manualmente.
- Consultas SQL de metadados estritamente somente leitura, checklist de conta secundária e
  recomendação para preservar o contrato de teste estão em
  [revisão final 2.0.7](phase-2.0.7-final-review.md).
- Nenhum registro, segredo, ambiente de produção ou demonstração pública foi acessado ou
  alterado. Nenhuma migration, commit, push ou deploy executado.
- Desde essa revisão, o responsável informou Supabase em `004 (head)`, RLS/FORCE RLS e
  grants mínimos confirmados, com site e fluxos de CDB funcionando. Estado remoto não foi
  verificado independentemente; homologação com a segunda conta segue pendente.

## Revisão de prontidão 2.0.6 — 28/10/2026

- Commit `385120723a183f0964652682a99a7e64ab281ab9` presente; `main` limpo, um commit
  à frente de `origin/main`.
- Revisão direcionada da migration 004, dependência 003, constraints, índices, FK,
  RLS/Force RLS, triggers append-only/cronologia/concorrência e endpoints de observação;
  sem correções de código necessárias.
- Testes focais não foram reexecutados: `.venv` aponta para Python indisponível e o Python
  empacotado disponível não tem pytest. Integração PostgreSQL (1) e suites da Fase 2.0.5
  permanecem aprovadas conforme o registro abaixo, sem nova execução nesta revisão.
- Nenhum build novo (sem mudança de aplicação); testes anteriores/builds público e privado
  estão registrados na seção Fase 2.0.5.
- Nenhuma operação remota. Backup, migration 004, grants, Render/Vercel, allowlist real,
  homologação da segunda conta e confirmação da demo continuam pendentes.
- Runbook e checklist: [prontidão de produção 2.0.6](phase-2.0.6-production-readiness.md).

## Fase 2.0.5 — abertura consolidada e conciliação

- **264 testes backend aprovados** (22 novos): snapshot não cria aporte/lote, principal
  desconhecido null, tributos combinados/discriminados/parciais, ganho independente,
  datas/valores inválidos, duplicação, histórico existente, novos lotes e conciliação,
  401/404/owner e erro 422 sem reproduzir input privado. Motor preservado; escopo explícito
  exclui capital consolidado, com valores indisponíveis null, sem chamada SGS indevida.
- **1 integração PostgreSQL 17 aprovada** em container próprio descartável/tmpfs: 001–004,
  regressões de ações e ledger, RLS direta para A/B/sem contexto, runtime sem bypass,
  privilégios/default Supabase, UPDATE/DELETE/TRUNCATE bloqueados, constraints SQL,
  cronologia e concorrência de duas aberturas (201/409). Nenhum volume pessoal usado.
- **125 testes frontend aprovados** (oito novos): abertura BRL, revisão antes de POST,
  erro monetário, principal desconhecido/confirmado, tributos discriminados/ausentes,
  voltar ao formulário, nova observação após resgate e ausência de aplicação/estimativa
  fictícia, 401/403/422 no novo fluxo e bloqueio de envio duplicado/fechamento pendente.
  Regressões de autenticação, troca de conta, ações e demo offline preservadas.
- **Builds público e privado aprovados**, TypeScript/Vite; sem credenciais reais.
  Avisos conhecidos de bundle >500 kB e TestClient/httpx continuam não bloqueantes.
- Chrome headless com fixture exclusivamente fictícia: desktop 1440×1000 e móvel 390×844,
  sem overflow horizontal; modal móvel ~366,6 px, rolagem interna e foco visível.
- Auditoria de publicação aprovada: **151 candidatos, 3 artefatos públicos e histórico Git**,
  sem segredos conhecidos/assinaturas detectados; regras de ignore verificadas. Revisão
  manual dos arquivos alterados confirmou exemplos/fixtures fictícios, sem novos logs de
  valores privados. Nenhum arquivo staged; `git diff --check` passou. Scanner não garante
  ausência de dados pessoais arbitrários: repetir revisão humana antes de commit futuro.
- Somente migration nova 004; 001–003 intactas. Nenhum registro real reescrito, nenhum seed
  privado, mudança de auth, fonte externa ou armazenamento financeiro privado no browser.
- Sem commit/push/deploy/migration remota. Homologação real da conta secundária e grants
  remotos **não verificados**. Procedimento, rollback e limites em
  [Fase 2.0.5](phase-2.0.5-opening-balance.md).

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
