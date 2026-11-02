# Changelog

## v3.0.0 — candidata local (não publicada)

- Acesso Supabase por convite, sem cadastro público, membership ativo e confirmação server-side do e-mail antes de ativar novas contas.
- Convites administrativos limitados, expirados e revogáveis; contas isoladas por proprietário com RLS/FORCE RLS e quotas persistentes da Íris (5/minuto e 50/dia).
- Exportação privada schema 3 inclui registros owner-scoped e metadados básicos de conta; metas locais são anexadas pelo navegador.
- Comparador de CDI/Ibovespa/IPCA removido da UI/API; a série CDI/Selic necessária à renda fixa permanece.
- Exclusão própria com confirmação textual e autenticação recente; as fases financeiras, identidade Supabase e finalização são retomáveis. Ledgers continuam append-only para runtime; o executor SQL é NOLOGIN, sem BYPASSRLS e sem membership em outras roles.
- Loader CLI sem rota HTTP: UUIDs explícitos, admin allowlist, projeto Supabase/DB coincidente, membership ativo, carteira vazia, validação do cenário, observações por data e transação atômica. Registros e fontes ficam identificados como fictícios; alvos não vazios ou já usados são recusados.
- Validação local da candidata final: resultados registrados em [validation.md](docs/validation.md); a integração PostgreSQL usa exclusivamente containers descartáveis.
- Não houve exclusão de conta real, execução da fixture em conta real, migration de produção, push ou deploy.

## v2.0.0 — análise patrimonial com cobertura explícita (publicada segundo relato do proprietário)

- Substituída a antiga seção de evolução histórica desativada por observações patrimoniais datadas, fonte informada, cobertura de CDB e total apenas quando as classes cobertas permitem.
- Adicionada migration append-only 010 com RLS/FORCE RLS, endpoint privado de leitura/gravação idempotente e verificação de permissões no PostgreSQL descartável.
- Adicionados CDI, Ibovespa e IPCA em meses completos comuns; janela parcial é identificada e o gráfico não é apresentado como retorno da carteira.
- Adicionado relatório filtrável de dividendos e JCP com totais mensais e por ativo, usando somente eventos manuais efetivos.
- A Íris recebeu conhecimento estático dos indicadores e limites da v2.0 e um contexto de tela restrito a rótulos permitidos. Nenhum valor, ativo, operação, filtro ou token da carteira é enviado como contexto à Groq.
- O procedimento de backup/restauração versionado passou a reconhecer o schema 010 e a tabela patrimonial; os arquivos 009 permanecem compatíveis com arquivos históricos.
- Metadados locais do frontend, pacote Python e FastAPI/OpenAPI alinhados a `2.0.0`.
- Validação local: backend **419 aprovados/1 ignorado**, PostgreSQL 17 descartável com migrations 001–010 e backup/restore `IDBKP010` aprovados, frontend **230 testes aprovados**, build aprovado (2.384 módulos). Sem chamadas Groq/Brapi/BCB, banco remoto, migration de produção, commit, push ou deploy; detalhes em `docs/validation.md`.
- Cobertura limitada a observações prospectivas. Caixa não entra no total patrimonial; TWR/XIRR continuam indisponíveis; a janela Brapi de três meses pode tornar a comparação 3M parcial.

## v1.3.0 — históricos individuais de ações (implementada localmente; não publicada)

- Adicionado provider histórico Brapi Free com `adjustedClose`, uma chamada por ticker, cache por janela efetiva e serialização/limite local por processo.
- O período é limitado aos últimos três meses. 6M/1A/MAX são marcados parciais, com cobertura efetiva exibida; a comparação limita os pontos ao intervalo comum entre ativos e mantém lacunas sem interpolação.
- Histórico agregado de patrimônio permanece indisponível pelo plano Free, que não fornece os campos originais `rawClose` exigidos pelo cálculo atual.
- Validação local: backend 404 aprovados/1 ignorado, frontend 224 aprovados e build aprovado (2.382 módulos). Integrações externas foram mockadas.
- Nenhuma chamada real à Brapi, alteração de `.env`, banco, commit, tag ou deploy foi feita nesta preparação.

## v1.2.1 — estabilização (implementada localmente; não publicada)

- Corrigida a semântica de cobertura histórica quando o provider encurta o intervalo solicitado.
- Exportação identificada como operações de ações em JSON e acompanhada das exclusões; não é backup integral.
- A Íris informa que as perguntas são enviadas à Groq e recomenda não incluir informações pessoais ou financeiras.
- Estado sem pontos do histórico CDB orienta registrar observação datada e não presume valores anteriores.
- Naquele candidato, as versões foram alinhadas a `1.3.0`; o candidato v2.0.0 atual incorpora a estabilização, os históricos e a análise patrimonial.

## v1.2.0 — Íris, assistente de educação financeira (publicada segundo o proprietário)

- Adicionada a Íris: chat educativo opcional na área privada autenticada, com chave somente no backend, conhecimento estático e sem acesso à carteira.
- Demonstração pública sem assistente; indisponibilidade da chave/cota não bloqueia o dashboard.
- Integração Groq Free com `qwen/qwen3.8-27b`; chamadas reais foram validadas pelo proprietário. Sem faturamento ou fallback pago.
- Publicação da v1.2.0 e operação em produção confirmadas pelo proprietário; os painéis e a sessão autenticada não foram reconsultados nesta atualização documental.
- Validação local registrada antes da publicação: 393 testes backend aprovados (1 ignorado), 221 frontend aprovados e build de produção aprovado.
- A Íris é restrita à área privada autenticada; a demonstração pública permanece offline, sem chat e sem chamada ao endpoint de IA.

O roadmap para próximas versões está em [Investment Dashboard v2.0 e v3.0](docs/INVESTMENT_DASHBOARD_V2_ROADMAP.md). As versões públicas deste changelog não são as etiquetas internas das fases técnicas antigas.

## v1.0.1 — correção do runner de integração PostgreSQL

- Corrigida a resolução de imports do runner `backend/tests/run_postgres.py` em ambientes de CI Linux e execuções iniciadas fora do diretório `backend`, usando o caminho do próprio arquivo como referência.
- Adicionado teste de regressão para execução a partir de diretório de trabalho arbitrário. Não altera endpoints, cálculos, schema, migrations ou dados.
- Commit `329ba67` (`fix(ci): resolve backup imports in PostgreSQL runner`); tag remota `v1.0.1` foi observada nesse commit. A verificação mais recente do GitHub Actions e dos SHAs implantados não faz parte desta atualização documental.

## v1.0.0 — publicada

Investment Dashboard reúne controle manual de ações e renda fixa, eventos de caixa/proventos, composição, histórico, relatórios imprimíveis, simulador e metas financeiras locais. A demonstração pública é separada da área privada; a carteira privada usa Supabase Auth, API FastAPI e isolamento por proprietário/RLS.

### Incluído

- Ações, compras/vendas, renda fixa CDB e registro manual de aportes, retiradas, dividendos e JCP.
- Histórico filtrável, composição atual com cobertura declarada, relatórios privados e impressão para PDF.
- Simulador local com cenários e hipóteses editáveis; metas financeiras locais por identidade, sem sincronização entre dispositivos.
- Demonstração com dados fictícios, documentação de segurança e um procedimento de backup manual único.

### Validação registrada para o candidato v1.0.0

- Frontend: 217 testes aprovados em 28 arquivos; `npm run build` aprovado (TypeScript + Vite).
- Dependências frontend: `npm audit` não reportou vulnerabilidades conhecidas.
- Backend: 382 aprovados, 1 ignorado (integração PostgreSQL opt-in) em Python 3.12 descartável; aviso de depreciação `TestClient`/httpx. O hotfix posterior tem sua própria validação em `docs/validation.md`.
- PostgreSQL 17 descartável: cadeia de migrations até 009 e round-trip sintético de backup/restauração com eventos, políticas/RLS, grants e isolamento aprovados.
- Backup real: artefato fora do repositório, 101085 bytes; SHA-256 foi recalculado e coincidiu com o registro fornecido pelo proprietário. A restauração desse artefato ainda não foi ensaiada; exige autorização específica para fornecer a frase localmente.
- Smoke público daquela preparação: Vercel `/`, `/login` e `/metas` responderam HTTP 200 com o shell SPA; Render `/health` respondeu HTTP 200. Não foram autenticadas contas nem confirmados os SHAs implantados naquela checagem.

### Limites conhecidos

- A Fase 5.6, retorno histórico completo e benchmarks permanecem fora desta release; não há dados suficientes para calcular TWR/XIRR ou patrimônio histórico completo com confiança.
- Preços e avaliações podem estar parciais ou indisponíveis; estimativas não são retorno garantido. Metas não são sincronizadas.
- O backup único cobre o schema `public` exportável; não recupera Supabase Auth, arquivos binários do Storage, roles globais, configurações externas ou alterações posteriores ao dump.
- O proprietário confirmou manualmente login/logout, navegação, áreas principais, demo e layout desktop/celular. Isolamento manual entre duas contas, inspeção detalhada de Network/CSP e restore do arquivo real não foram marcados como concluídos; ver `docs/v1.0-release-readiness.md`.

## Auditoria inicial de preparação v1.0 — 30/10/2026 (registro histórico)

- Auditoria local confirmou `main`/`origin/main` em `1a7e4d8`; páginas recentes publicadas na Vercel conforme relato do proprietário. Smoke GET: Render `/health` e frontend privado Vercel responderam HTTP 200; autenticação e painel não foram verificados.
- Frontend: 217 testes em 28 arquivos e build passaram. Backend em Python 3.12/Docker: 374 aprovados, 1 ignorado; teste PostgreSQL 17 descartável com migrations até 009: 1 aprovado.
- Naquele ponto, README, status de segurança, roadmap, handoff e checklist foram revisados; o backup real ainda não havia sido gerado. A entrada é um snapshot histórico, anterior à geração autorizada do backup e às tags v1.0.x; o estado mais recente está no [plano mestre](docs/INVESTMENT_DASHBOARD_MASTER_PLAN.md) e em `docs/validation.md`.

## Fase 5.5 — integrada à `main`; publicação reportada pelo proprietário

- Criadas as metas financeiras locais em entregas 5.5A, 5.5B e 5.5C, com CRUD, acompanhamento manual ou por custo/principal investido, avisos de cobertura e planejamento hipotético de aportes.
- Metas ficam no navegador privado e por identidade; não sincronizam entre dispositivos, não aparecem na demo e não alteram o banco. A projeção usa o motor do simulador, com taxas editáveis e limite de 600 meses.
- Frontend no commit da fase: 217 testes aprovados em 28 arquivos. Backend não alterado. A validação atual via container está descrita em [validação](docs/validation.md).
- A fase foi integrada pela PR #11; esse registro não confirma o estado atual do painel de produção.

## Fases 5.3/5.4 — `feat/v5.3-reports` (integradas localmente)

- Removida a importação CSV da interface, do cliente privado e da API; cadastro manual de operações/eventos e Histórico permanecem.
- Os gráficos de composição de ações e renda fixa agora usam duas colunas equilibradas; em telas estreitas, são empilhados. Valores e cálculos não mudaram.
- Fases 5.3A–C: relatórios privados de aportes, composição e movimentações, com filtros, indicadores e opção de impressão para PDF.
- Fase 5.4: simulador local com três cenários hipotéticos, juros compostos e ajuste opcional pela inflação; sem persistência ou acesso à carteira.
- Nenhuma tabela, dado financeiro ou migration foi removido/revertido; nenhuma alteração foi feita no banco de produção.

## v4.0.0 — publicada (29/10/2026)

Publicação e verificações operacionais confirmadas pelo proprietário. Os endpoints privados de operações, valuation, performance e históricos respondem; sem provedor aprovado, os endpoints históricos respondem com estado de indisponibilidade conforme projetado. Esta entrada não registra SHA implantado nem revisão remota do banco, que não foram conferidos diretamente nesta atualização.

### Adicionado

- Resumo privado atual em `GET /api/dashboard/performance`, integrando fluxos registrados,
  capital em posições abertas, composição e resultado de ações somente com dados disponíveis.
- Painel `PortfolioInsights` com resultado realizado + resultado não realizado coberto,
  avisos de cobertura e cotações stale, sem alegar retorno percentual total.
- Divisão dinâmica dos módulos de gráficos/páginas: o chunk inicial caiu de 806,13 kB para
  443,68 kB no build local medido.

### Corrigido

- Precisão local do cálculo de custo médio para operações no limite de `NUMERIC(20,8)`;
  casos de teste reproduziram a perda de dígito no produto quantidade × preço e um resíduo
  mínimo de custo após venda total com média decimal repetitiva.
### Limites

- Resultado realizado considera somente taxas registradas e é antes de impostos. Cotações
  atuais são estimativas; a indicação stale pede conferência na corretora.
- Fluxo líquido registrado não equivale a depósito externo, patrimônio ou rentabilidade.
- Estimativas de CDB continuam por contrato na interface existente; posições declaradas
  seguem separadas do principal dos lotes.
- Histórico individual/comparativo de preços permanece sem fonte aprovada e desabilitado.
- Sem migration para esta entrega. A publicação da v4.0.0 foi confirmada pelo proprietário; a verificação atual não reabre nem altera o deploy.

## v3.0.4 — notas preparadas em 29/10/2026

> Notas para a release oficial. Nenhuma tag, GitHub Release, deploy ou migration foi criada
> nesta auditoria. O responsável reporta o deployment; o SHA implantado ainda requer
> conferência no painel Vercel.

### Adicionado

- Histórico privado e cronológico de operações de ações e CDB em `/historico`, com filtros
  por período, classe e ativo.
- Série unificada baseada em movimentos efetivos, respeitando revisões `REPLACE` e `VOID` e
  o isolamento por proprietário.
- Indicadores de compras/aplicações, vendas líquidas/resgates de principal, fluxo líquido,
  capital aplicado em posições abertas e composição por classes.
- Gráficos de fluxos com filtros temporais, tooltips monetários e layout responsivo.

### Regras e limites

- Vendas líquidas e resgates de principal são fluxos de saída; não são tratados integralmente
  como lucro/rendimento. Fluxo líquido não é patrimônio nem retorno da carteira.
- Posições manuais de CDB sem base confiável permanecem fora dos agregados de composição.
- Valores de mercado derivados de cotações externas são estimativas e devem ser conferidos
  na corretora.
- Histórico de preços de ações da 3.0.3 permanece preservado e desabilitado por padrão por
  `EQUITY_HISTORY_ENABLED=false`; cotações pontuais usam o controle independente de mercado.
- Nenhuma migration é necessária para a 3.0.4.

### Validação reportada nesta auditoria

- Backend focalizado: 232 aprovados.
- Frontend: 149 aprovados em 14 arquivos de teste.
- Build de produção: concluído; o Vite reporta chunk principal acima de 500 kB.
