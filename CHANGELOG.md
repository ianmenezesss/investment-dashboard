# Changelog

## Em desenvolvimento — `feat/v5.3-reports`

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
