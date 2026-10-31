# Changelog

## v1.0.0 — candidata local; release ainda não publicada

Investment Dashboard reúne controle manual de ações e renda fixa, eventos de caixa/proventos, composição, histórico, relatórios imprimíveis, simulador e metas financeiras locais. A demonstração pública é separada da área privada; a carteira privada usa Supabase Auth, API FastAPI e isolamento por proprietário/RLS.

### Incluído

- Ações, compras/vendas, renda fixa CDB e registro manual de aportes, retiradas, dividendos e JCP.
- Histórico filtrável, composição atual com cobertura declarada, relatórios privados e impressão para PDF.
- Simulador local com cenários e hipóteses editáveis; metas financeiras locais por identidade, sem sincronização entre dispositivos.
- Demonstração com dados fictícios, documentação de segurança e um procedimento de backup manual único.

### Validação desta preparação

- Frontend: 217 testes aprovados em 28 arquivos; `npm run build` aprovado (TypeScript + Vite).
- Dependências frontend: `npm audit` não reportou vulnerabilidades conhecidas.
- Backend: 382 aprovados, 1 ignorado (integração PostgreSQL opt-in) em Python 3.12 descartável; aviso de depreciação `TestClient`/httpx.
- PostgreSQL 17 descartável: cadeia de migrations até 009 e round-trip sintético de backup/restauração com eventos, políticas/RLS, grants e isolamento aprovados.
- Backup real: artefato fora do repositório, 101085 bytes; SHA-256 foi recalculado e coincidiu com o registro fornecido pelo proprietário. A restauração desse artefato ainda não foi ensaiada; exige autorização específica para fornecer a frase localmente.
- Smoke público: Vercel `/`, `/login` e `/metas` responderam HTTP 200 com o shell SPA; Render `/health` respondeu HTTP 200. Não foram autenticadas contas nem confirmados os SHAs implantados.

### Limites conhecidos

- A Fase 5.6, retorno histórico completo e benchmarks permanecem fora desta release; não há dados suficientes para calcular TWR/XIRR ou patrimônio histórico completo com confiança.
- Preços e avaliações podem estar parciais ou indisponíveis; estimativas não são retorno garantido. Metas não são sincronizadas.
- O backup único cobre o schema `public` exportável; não recupera Supabase Auth, arquivos binários do Storage, roles globais, configurações externas ou alterações posteriores ao dump.
- A revisão visual desktop/celular, fluxos autenticados de produção e inspeção da CSP/rede da demo ainda requerem homologação manual. Não foi criado tag ou GitHub Release.

## Auditoria inicial de preparação v1.0 — 30/10/2026 (registro histórico)

- Auditoria local confirmou `main`/`origin/main` em `1a7e4d8`; páginas recentes publicadas na Vercel conforme relato do proprietário. Smoke GET: Render `/health` e frontend privado Vercel responderam HTTP 200; autenticação e painel não foram verificados.
- Frontend: 217 testes em 28 arquivos e build passaram. Backend em Python 3.12/Docker: 374 aprovados, 1 ignorado; teste PostgreSQL 17 descartável com migrations até 009: 1 aprovado.
- Naquele ponto, README, status de segurança, roadmap, handoff e checklist foram revisados; o backup real ainda não havia sido gerado. O status atual está registrado na entrada candidata v1.0.0 acima e em `docs/validation.md`.

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
