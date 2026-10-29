# Fase 4.3A — Resumo financeiro atual

**Status:** Concluído tecnicamente em 29/10/2026. Esta documentação descreve o código entregue; não declara publicação em produção nem autoriza migrations ou deploy.

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
Soma do saldo efetivo dos lotes. Observações manuais de posição sem lotes permanecem em série separada e não entram no agregado de principal.

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

## Contrato implementado

Endpoint privado `GET /api/dashboard/performance`, com autenticação e consulta derivada do proprietário obtido no contexto do servidor/RLS. Não aceita `owner_id` como fonte de autorização e responde `Cache-Control: no-store`. Não cria um segundo ledger.

O modelo Pydantic `FinancialPerformance` devolve valores financeiros como strings decimais e contém:

- `as_of` e `ledger_as_of`;
- `flows`: compras com taxas, aplicações de principal, vendas após taxas, resgates de principal, totais registrados e fluxo líquido registrado;
- `capital`: custo aberto de ações, principal efetivo CDB, total de posições abertas contabilizadas e participações por classe;
- `equities`: payload da avaliação atual existente, resultado realizado, cobertura, timestamps, tickers sem cotação e resultado combinado antes de impostos, quando completo;
- `fixed_income`: principal efetivo aberto e posições declaradas separadas. Rendimento bruto/líquido segue calculado por contrato na página existente de renda fixa e não é reestimado nem agregado por esta rota;
- `composition`: componentes e bases de ações, principal CDB e observações manuais;
- `portfolio`: valor de mercado consolidado e percentual de retorno permanecem `null`, pois faltam bases comparáveis e dados temporais.

O endpoint usa `private_db`, consultas explicitamente filtradas por `owner_id`, `effective_movements()` para REPLACE/VOID e o `QuoteService` pontual já existente. O snapshot de ledger é calculado antes de liberar a transação para chamadas de cotação. Não chama o serviço de histórico de preços.

As cotações atuais continuam sujeitas aos limites de validade e aos estados da avaliação. Quando a cobertura é parcial, o total de mercado e o resultado combinado são `null`; com cotação utilizável mas stale, a estimativa combinada é identificada visualmente como desatualizada.

## Interface implementada

`PortfolioInsights` apresenta os fluxos registrados, capital em posições abertas, composição pelas bases registradas e resultado acumulado em ações. Mostra cobertura incompleta, falha, carregamento e carteira sem movimentos; a cotação stale recebe aviso e instrução de conferência na corretora. O fluxo de capital continua rotulado como fluxo, não patrimônio ou rentabilidade. As estimativas CDB continuam na interface existente por contrato; posições declaradas permanecem separadas.

O frontend formata valores e percentuais para exibição; fórmulas financeiras e somas contábeis permanecem no backend. Não há retorno percentual total nem gráfico histórico de patrimônio nesta fase.

## Migrations e persistência

Nenhuma migration para a agregação somente leitura. Não persistir snapshots fictícios nem reutilizar observações CDB como valuation global.

Depósitos/saques, proventos, eventos societários e avaliações históricas exigem estudo e provável persistência append-only própria; são escopo separado e podem requerer migrations aprovadas.

## Validação executada

- `backend/tests/test_performance_api.py`: carteira vazia, compra/venda parcial, taxas, resultado positivo/negativo, cobertura parcial, CDB application/redemption, `cash_received` sem inferência de rendimento, REPLACE/VOID, posição declarada separada, autorização e isolamento por proprietário.
- `backend/tests/test_finance.py`: custo médio e taxas preexistentes, liquidação total e venda cronológica; testes reproduzem e protegem multiplicação de valores máximos NUMERIC(20,8) sem truncamento e remoção exata de custo em liquidação total com média decimal repetitiva.
- Backend completo: 363 aprovados, 1 ignorado; integração PostgreSQL descartável: 1 aprovado, com migrations 001–008, persistência, RLS, isolamento e backup/restore.
- Frontend completo: 162 aprovados; estados de carregamento/erro/vazio, cobertura parcial, formatação monetária e aviso de cotação stale.
- Build: concluído após divisão dinâmica de módulos pesados; bundle inicial medido em 443,68 kB (antes 806,13 kB), maior chunk 443,68 kB.

`ObservedHistory` já valida `Array.isArray(response.points)` no query function e tem teste de resposta malformada que confirma estado de erro sem dereferenciar `.length` indefinido.

## Limitações e aceite observado

Não há depósitos/saques externos nem proventos no ledger. Portanto fluxo líquido não é aporte externo nem retorno. Resultado realizado considera só taxas gravadas e é antes de impostos. Resultado não realizado e combinado usam cotações pontuais, nunca uma série histórica; são estimativas quando aplicável. Cotação stale é avisada. Dados CDB brutos/líquidos permanecem por contrato, sem serem confundidos com caixa ou rendimento realizado. Sem migration; nenhuma integração de histórico foi ativada.

Critérios técnicos da fase foram atendidos localmente: autenticação e owner isolation, projeção efetiva CDB, parcial/stale/unavailable, Decimal, demo offline, integração Postgres descartável e testes/build completos. Publicação v4 ainda requer conferências operacionais documentadas em [revisão final](phase-4.0-final-review.md); o bloqueio de série histórica da 4.4 permanece.
