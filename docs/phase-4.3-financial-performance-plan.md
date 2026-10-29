# Fase 4.3A — Plano de resumo financeiro atual

**Status:** Planejado. Este documento especifica uma implementação futura e não autoriza alterações no código, schema, banco ou publicação.

## Objetivo e escopo

Exibir um resumo privado que separe fluxos operacionais, base das posições abertas e resultado de ações. Não chamar fluxo líquido de retorno e não tentar representar patrimônio consolidado com classes ou datas-base incompatíveis.

A primeira entrega pode funcionar sem provedor histórico e sem novas migrations. Histórico temporal completo fica fora do escopo e está condicionado à [Fase 4.4](phase-4.4-historical-performance-plan.md).

## Fontes e regras existentes a reutilizar

- Operações de ações: tabela Operation, tipos BUY/SELL, quantidade, preço, taxas e data; API atual valida e isola proprietário.
- Cálculo por custo médio: app.finance.summarize; compras incluem taxas no custo e vendas retiram custo proporcional à quantidade vendida.
- Avaliação atual de ações: app.valuation.value_portfolio e serviço pontual de cotação. Estados stale, parcial, unavailable e empty devem permanecer.
- Movimentos efetivos CDB: fixed_income.projection.effective_movements; preservar REPLACE/VOID e owner_id.
- Principal aberto: ledger de renda fixa, sem classificar principal resgatado como rendimento.
- Estimativas CDB: motor 2.0.3 e taxas SGS existentes, somente com convenção, calendário, perfil e cobertura compatíveis.
- Observações manuais: informar como posição declarada com data-base; não mesclar automaticamente a principal/lotes.

Referências: [avaliação atual](phase-1.9.3-portfolio-valuation.md), [clareza financeira](phase-1.9.5-financial-clarity.md), [estimativas CDB](phase-2.0.3-fixed-income-returns.md) e [revisões CDB](phase-2.0.8.2-revision-foundation.md).

## Definições e fórmulas

**Compras registradas em ações**
Soma, para BUY, de quantidade × preço + taxas.

**Aplicações registradas em CDB**
Soma do principal dos movimentos APPLICATION efetivos.

**Vendas líquidas registradas**
Soma, para SELL, de quantidade × preço − taxas registradas.

**Principal resgatado**
Soma do principal de REDEMPTION efetivo. Não soma rendimento hipotético nem presume que todo o caixa recebido é lucro.

**Fluxo líquido registrado**
Compras de ações + aplicações CDB − vendas líquidas − principal resgatado. Mede apenas esses registros de investimento. Não mede depósitos externos, saldo de caixa, lucro ou retorno da carteira.

**Custo aberto de ações**
Saldo calculado pelo ledger a custo médio, incluindo taxas de compra da posição remanescente.

**Principal CDB aberto**
Soma do saldo efetivo dos lotes. Contratos em tracking_mode consolidado continuam fora desse agregado; observações declaradas ficam em série separada.

**Resultado realizado em ações**
Para cada venda, receita de venda após taxas − custo médio proporcional removido. Inclui apenas taxas registradas; não é líquido após impostos.

**Resultado não realizado em ações**
Valor de mercado das posições abertas − custo aberto. Só se todas as posições incluídas tiverem cotação utilizável será mostrado o resultado agregado. Se cobertura for parcial, mostrar resultados individuais cobertos e subtotal, sem rotular subtotal como total da carteira.

**Resultado combinado de ações**
Resultado realizado + resultado não realizado, apenas com cobertura completa do conjunto de posições abertas e ledger válido. Rotular como resultado acumulado em ações antes de impostos, sujeito aos eventos que o ledger realmente registra. Não converter em percentual de rentabilidade temporal.

**Estimativa CDB**
Reutilizar os campos brutos/líquidos do motor atual, com status, fonte BCB/SGS, data, versão, premissas e alertas. Não derivar juros realizados ou impostos realizados de cash_received. Valor líquido estimado não é cotação de resgate nem saldo bancário oficial.

## Exemplo explicativo

Comprar 10 ações a R$ 20,00 com R$ 2,00 de taxas resulta em custo R$ 202,00. Vender 4 a R$ 25,00 com R$ 1,00 de taxa: caixa líquido R$ 99,00, custo removido R$ 80,80, resultado realizado R$ 18,20. Restam 6 ações e custo aberto R$ 121,20. A R$ 24,00, valor estimado R$ 144,00 e resultado não realizado R$ 22,80. A variação aberta de 18,81% é apenas sobre o custo remanescente, não total ou anualizada.

CDB: aplicação R$ 1.000 e resgate de R$ 400 de principal deixam R$ 600 em principal aberto. Caixa recebido pode ser exibido como dado informado, mas a diferença para o principal não deve ser inferida como rendimento realizado sem um contrato financeiro que defina sua composição e tributos.

## Contrato de API proposto

Endpoint privado sugerido: GET /api/dashboard/performance.

A resposta deve ser um snapshot em data de referência, com strings decimais e estado/cobertura por componente. Campos conceituais:

- as_of e ledger_as_of;
- flows: equity_purchases_with_fees, cdb_applications_principal, equity_sales_net_fees, cdb_principal_redemptions, net_recorded_flow;
- equities: open_cost, realized_profit_pre_tax, market_value, unrealized_profit, combined_result, return_on_open_cost, coverage, quote timestamps, missing tickers;
- fixed_income: effective_open_principal, contract estimates bruta/líquida com status/fonte/premissas, consolidated observations em seção separada;
- portfolio: total_current_value null quando bases ou cobertura não permitirem comparação; portfolio_return_percent null com reason;
- diagnostics: empty, partial, stale, unavailable, complete, por bloco.

Sem parâmetro owner_id controlado pelo cliente. Usar autenticação, private_db, owner_id/RLS, headers no-store e consultas dos movimentos CDB pela projeção efetiva. Não criar um endpoint público nem duplicar fórmulas no frontend. Contrato Pydantic/OpenAPI deve serializar Decimal como string.

Cotações podem ter instantes distintos; retornar o intervalo quoted_at_min/max e identificar atraso. Um campo total só existe se todo o conjunto declarado tiver valor comparável; do contrário retornar null e componentes/subtotais com escopo explícito.

## Interface planejada

Ampliar PortfolioInsights e MarketDashboard, sem nova página:

- Seções separadas: fluxo registrado, posições abertas, resultado realizado e não realizado.
- Manter CDB bruto/líquido estimado na interface CDB ou mostrar um resumo de valores elegíveis com premissas e estados.
- Estado vazio e estados loading, error, partial, stale, unavailable.
- BRL e datas pt-BR; valores enviados como Decimal string. Não fazer cálculo financeiro com Number no frontend.
- Renda fixa manual continua em observações separadas.
- Gráfico atual permanece identificado como gráfico de fluxo. Não desenhar patrimônio histórico na 4.3A.

## Migrations e persistência

Nenhuma migration para a agregação somente leitura. Não persistir snapshots fictícios nem reutilizar observações CDB como valuation global.

Depósitos/saques, proventos, eventos societários e avaliações históricas exigem estudo e provável persistência append-only própria; são escopo separado e podem requerer migrations aprovadas.

## Testes necessários

Backend puro/API:
- sem operações e posições vazias;
- compras múltiplas, vendas parciais e totais, taxas e custo médio;
- resultado positivo e negativo;
- soma de realizado e não realizado com cotação completa;
- preço ausente, stale, inválido ou moeda errada;
- oito casas decimais, multiplicações grandes, arredondamento e consistência de centavos;
- diferentes datas e janelas, sem reescrever histórico;
- CDB aplicação/resgate, cash_received null/presente, taxa ausente, produto não suportado;
- REPLACE/VOID não duplicam valores;
- posição manual não entra no total de ledger;
- autenticação ausente e isolamento owner_id/RLS;
- flag histórica desligada não chama provedor e cotação atual continua independente.

Frontend:
- vazio, carregamento, erro, stale e cobertura parcial;
- formatação brasileira de valores e datas;
- textos não chamam fluxo de patrimônio, retorno ou lucro;
- subtotal não aparece como total;
- layout móvel, tooltips e navegação preservados.

## Dependências, riscos e aceite

Risco de arredondamento a auditar: finance.summarize usa Decimal, mas não configura contexto local de alta precisão como outros cálculos. Teste primeiro com limites NUMERIC(20,8); só mudar cálculo se houver diferença material comprovada e teste de regressão.

Critérios de aceite: autenticação/owner isolation; nenhuma operação ou dados reais alterados; fórmulas batem com fixtures aritméticos; total indisponível sob cobertura incompleta; CDB estimate marcado e não confundido com realização; demo continua offline; testes relacionados, suíte frontend e build aprovados; docs atualizadas; nenhuma migration sem justificativa/aprovação.

## Sequência e controle

1. Aprovar escopo e nomes dos indicadores.
2. Escrever testes de serviço antes de agregar.
3. Implementar serviço backend reutilizando funções existentes.
4. Adicionar endpoint owner-scoped e contrato tipado.
5. Integrar componentes atuais e estados visuais.
6. Atualizar documentação de fase e roteiro manual.
7. Rodar backend, PostgreSQL descartável quando aplicável, frontend, build e diff check.
8. Revisar diff e criar um commit local exclusivo da 4.3 somente após autorização. Deploy/migration ficam fora sem autorização.
