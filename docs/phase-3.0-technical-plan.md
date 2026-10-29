# Fase 3.0 — plano técnico para gráficos e evolução patrimonial

**Estado revisado em 29/10/2026:** 3.0.1 e 3.0.2 constam como publicadas conforme relato
do responsável. A implementação histórica de preços 3.0.3 está preservada no código, mas
segue pendente de fonte adequada, cobertura/campos e termos confirmados. A 3.0.4 está
concluída e validada localmente para revisão; não foi publicada nesta rodada. Não houve
migration nem alteração de dados de produção. A revisão funcional e os critérios de publicação
da 3.0.4 estão em [revisão final da Fase 3.0.4](phase-3.0.4-final-review.md).

## Fonte de verdade e indicadores entregues

- O histórico de operações do usuário é a fonte principal da verdade para compras, vendas,
  aplicações e resgates registrados. Preços de mercado não corrigem esse ledger.
- `GET /api/dashboard/movements` oferece o histórico cronológico privado de ações e CDB;
  CDBs usam `effective_movements()` para respeitar REPLACE/VOID.
- `GET /api/dashboard/capital-flows?period=1M|3M|6M|1A|Tudo` expõe compras de ações com
  taxas, aplicações de principal, vendas líquidas após taxas, resgates de principal e valores
  acumulados. O saldo desse fluxo não é lucro, patrimônio nem retorno da carteira.
- `GET /api/dashboard/composition` expõe custo de aquisição aberto em ações e principal
  efetivo aberto em CDB. Observações declaradas sem reconciliação não são somadas às posições
  do ledger.
- `GET /api/dashboard/equity-history` continua sendo uma série estimada a partir de fonte
  externa, separada do histórico de operações; sua adequação para publicação permanece
  pendente conforme [Fase 3.0.3](phase-3.0.3-equity-history.md).
- O resultado realizado de ações permanece conforme `backend/app/finance.py`: venda líquida
  de taxas menos custo médio atribuível à quantidade vendida, com taxas de compra na base.
  Não inclui tributos. Resgate de CDB não é rendimento; `cash_received` pode estar ausente e
  não é usado como rendimento realizado.

## Inventário da base existente

### Ações

- `backend/app/models.py` guarda `Operation` com proprietário, ticker, tipo BUY/SELL, data,
  quantidade, preço e taxas em `NUMERIC(20,8)`.
- `GET /api/operations` e `GET /api/dashboard` leem o ledger filtrado por `owner_id`;
  `summarize()` reconstrói posições e custo médio com `Decimal`.
- `GET /api/dashboard/valuation` devolve snapshot atual com cotação pontual do `QuoteService`
  (`brapi`), status, cobertura e timestamps. Não é uma série de preços históricos.
- `frontend/src/App.tsx` mantém os indicadores existentes de ações e compõe `PortfolioInsights`
  e `EquityHistory` na Visão geral e em Ações. `PortfolioInsights` representa fluxos de
  capital registrados e bases abertas, enquanto `EquityHistory` é uma estimativa de mercado.

### Renda Fixa

- `fixed_income_investments`, `fixed_income_lots` e `fixed_income_movements` registram
  contratos, aplicações e amortizações de principal. A Fase 2.0.8 acrescentou revisões
  append-only REPLACE/VOID: saldos, rendimentos e gráficos futuros devem usar exclusivamente
  a projeção efetiva do ledger, nunca somar movimentos originais e revisões. Eventos e
  snapshots são privados por `owner_id`; endpoints usam `private_db` e as migrations aplicam RLS.
- `fixed_income_observations` preserva posição informada em datas escolhidas. Ela não cria
  histórico anterior à data declarada nem snapshots diários automáticos.
- `GET /api/fixed-income/investments`, detalhe, `/movements` e `/observations` expõem os
  dados existentes com paginação. `GET /{id}/returns` estima CDI dos lotes elegíveis por
  uma data consultada; não é rendimento realizado nem uma série histórica patrimonial.
- `cash_received` em um resgate pode estar ausente e, isoladamente, não decompõe principal,
  rendimento, IR e IOF efetivamente retidos.

### Autorização, demo e componentes

- Endpoints privados usam `private_db`, identidade autenticada, allowlist e filtros por
  proprietário; os dados são guardados em RLS. Query keys do frontend incluem identidade.
- `PUBLIC_DEMO` e `DemoRepository` separam a demonstração offline da API privada. A demo
  não deve consumir endpoint nem receber fonte de dados privados.
- Recharts já está instalado; a implementação futura deve reutilizá-lo. `MarketDashboard`,
  `FixedIncomePage`, `FixedIncomeReturns`, formatadores BRL e `FinancialHint` são pontos de
  reuso candidatos. Não há justificativa identificada para adicionar biblioteca de gráficos.

## Proposta inicial — Fase 3.0.1: indicadores e cobertura

**Objetivo:** fixar o significado de cada indicador e comprovar quais séries podem ser
compostas com dados disponíveis, antes de criar gráfico, endpoint, coleta ou persistência.
O resultado da 3.0.1 será um contrato e matriz de cobertura revisáveis, ilustrados somente
com dados fictícios. Não é autorização para implementar outras etapas da Fase 3.0.

### Dicionário inicial de indicadores

| Indicador | Definição proposta | Disponibilidade atual | Regra de apresentação |
| --- | --- | --- | --- |
| Fluxo líquido de operações | Valor bruto de compras menos vendas por data; taxas separadas, e fluxo de caixa com taxas apenas quando incluídas explicitamente. | Ledger de ações; o gráfico existente omite taxas. | Chamar de fluxo de operações, jamais patrimônio, aporte líquido ou rentabilidade. |
| Quantidade mantida por ativo | Saldo de BUY menos SELL até a data, com eventos corporativos tratados se afetarem a quantidade. | Reconstituível do ledger, sujeito a consistência e ajustes corporativos ainda não modelados. | Mostrar quantidade e data; não inferir valor sem preço válido na mesma base. |
| Valor de mercado de ações | Quantidade válida na data × fechamento sem ajuste de retorno na mesma moeda; splits alteram quantidade e dividendos exigem tratamento separado. | Inviável como série histórica até escolher e validar fonte, símbolos, OHLC e eventos. | Distinguir preço de tela de retorno total; não usar adjustedClose como mark-to-market sem reconciliar proventos/eventos. |
| Fluxo de principal da renda fixa | Aplicações menos amortizações/resgates de principal, por data. | Ledger de movimentos existente. | Fluxo de capital, não saldo, patrimônio ou rendimento. |
| Posição observada de renda fixa | Valor bruto/líquido explicitamente informado numa data. | Observações pontuais declaradas pelo usuário. | Ponto isolado; sem interpolação, retroação ou soma automática com lotes posteriores. |
| Estimativa CDI por lote | Estimativa atual conforme premissas do contrato e CDI coberto até a data consultada. | Endpoint atual por lote/data; não persiste série patrimonial diária. | Rotular como estimativa, com data, premissas e cobertura; não chamar de rendimento realizado. |
| Patrimônio total histórico | Soma de componentes não sobrepostos e valorados na mesma data-base/moeda: ações, renda fixa, caixa e demais classes suportadas. | Indisponível: não há série persistida de preços, caixa completo ou reconciliação suficiente das observações/lotes. | Retornar `unavailable`, sem substituir lacunas por zero ou extrapolar. |
| Rentabilidade da carteira | Retorno calculado com série de valor e fluxos externos devidamente classificados, mais proventos, custos, tributos e eventos pertinentes. | Indisponível: ledger não define todos os fluxos externos/caixa e não há base histórica completa. | Não derivar de compras-vendas nem apresentar variação de patrimônio como retorno. |

### Matriz de cobertura e filtros

A matriz da 3.0.1 deve registrar, por ticker e classe: origem/campo, moeda, frequência,
primeira e última data observadas, falhas no intervalo, atraso, ajustes, limite/licença,
timestamp de captura, posição reconstruível e status de cada métrica. Para carteira, deve
listar componentes incluídos/excluídos e motivo; uma classe com lacuna relevante impede
chamar o agregado de total completo.

Filtros desejados: **1M, 3M, 6M, 1A e Máximo disponível**. Um filtro só pode ser descrito
como cobertura integral quando a fonte e a carteira cobrem toda a janela pedida. Quando a
cobertura começar depois do início solicitado, exibir a data efetiva e status parcial, ou
marcar a janela indisponível; não encurtar silenciosamente o intervalo. “Máximo disponível”
significa desde a primeira data validada para aquela métrica, nunca desde a primeira data
do app se não houver dados. Em carteira, a cobertura deve considerar a interseção dos
ativos exigidos pela métrica e dados observados de renda fixa, e explicitar exclusões.
Fim de semana/feriado, fechamento mensal, timezone, preço stale e tolerância de lacuna
precisam de definição aprovada antes de usar preenchimento do último fechamento.

Contrato conceitual de status: `complete` = todos os componentes necessários e datas-base
presentes; `partial` = série útil com componentes/datas ausentes, enumerados e quantificados;
`unavailable` = fórmula não pode ser calculada sem fabricar dados ou ambiguidade. Cada ponto
carrega data efetiva, moeda, origem, timestamp/data de referência e qualidade da cobertura.
Valores ausentes são `null`, nunca zero. Somente valores fictícios podem compor exemplos,
fixtures, snapshots de demonstração ou homologação.

### Entregáveis e critérios de aceite da 3.0.1

1. Documento de semântica aprovado para cada métrica: fórmula, sinais, taxas, moeda, data-base,
   fonte, ajustes, limites e itens explicitamente fora do cálculo.
2. Matriz de cobertura inicial por classe/ticker/endpoints atuais, indicando `available`,
   `partial` ou `unavailable`; ela deve deixar explícito que não há histórico de preços
   persistido e que observações de renda fixa são pontos isolados.
3. Contrato tipado de resposta de cobertura e amostras JSON inteiramente sintéticas, caso a
   3.0.1 passe a exigir contrato de API; nenhuma resposta de exemplo pode ser gravada em
   banco real ou aparecer como dado real na demo.
4. Plano de testes unitários com valores `Decimal`: compra/venda e taxas; BUY/SELL cruzando
   a janela; cotação ausente ou atrasada; preço raw versus adjusted; dia sem pregão; janela
   sem série suficiente; ausência de caixa/dividendos; observação antes/depois de lote; e
   status parcial/indisponível. Cobrir identidade A/B e `PUBLIC_DEMO` offline com fixtures.
5. Sem aceitar teste cujo resultado transforme falta de dado em `0`, extrapole a cotação de
   hoje para datas passadas, some observação integral aos lotes ou chame fluxo de retorno.
6. A matriz deve mostrar quais filtros 1M/3M/6M/1A/Máximo ficam integrais, parciais ou
   indisponíveis para cada série fictícia e qual informação aparece ao usuário. Nenhum
   período deve prometer uma cobertura não observada.

Esta entrega é principalmente de definição e prova documental. Se for autorizada uma mudança
de código depois, preferir funções puras de normalização/coverage e schemas de resposta sem
gravar dados; criação de endpoint, consulta histórica externa ou persistência permanece
decisão posterior.

### Alternativas de fontes históricas de ações (levantamento em 28/10/2026)

| Opção | Cobertura, confiabilidade e limites | Licença, custo publicado e adequação |
| --- | --- | --- |
| brapi (provedor atual da cotação pontual) | Endpoint diário OHLC, adjustedClose e volume; a janela máxima depende do plano, há símbolos sem cobertura e respostas acima do limite falham. Free: 3 meses/15 mil chamadas mensais; Startup: 1 ano/150 mil; Pro: mais de 10 anos/500 mil. Histórico disponível não garante cobertura de todo ticker. Para valuation exige distinguir preço cru de ajustado; campos `raw*` exigem Pro. A FAQ informa que não é distribuidora/redistribuidora licenciada da B3 e não oferece SLA ou contrato individual; considerar risco de disponibilidade/retificação e conferir restrições da fonte por ativo. | Menor esforço de integração. Página exibia R$ 0, R$ 99,99/mês (Startup anual equivalente) e R$ 116,66/mês em promoção para Pro anual (R$ 1.399,90 cobrados ao ano); confirmar valores e termos na contratação. Uso em apps comerciais é previsto nos planos pagos, mas redistribuição e restrições da fonte precisam ser esclarecidas por escrito, principalmente para exibição a usuários convidados. Pode servir à avaliação de protótipo/fase pessoal, sem constituir escolha. |
| B3 / distribuição autorizada | Fonte primária; série histórica desde 1986, na moeda/forma de cotação da época e sem ajustes por inflação ou proventos, com arquivos ZIP/TXT volumosos e layout próprio. A página histórica declara os dados como propriedade da B3 e proíbe coleta automatizada. A FAQ de Market Data descreve tratamento sem custo/prévia autorização para EOD/histórico D-1 obtido por plataforma, mas isso não revoga o bloqueio de coleta automatizada publicado na página histórica; qualquer ingestão precisa de canal permitido e termos confirmados. Para acesso em tempo real/atrasado, contrato e tarifas fixas/variáveis podem se aplicar. | Direitos e tarifário dependem de uso próprio, terminal e redistribuição; custo requer cotação/contrato conforme cenário. Alta autoridade de origem, porém alto esforço de ingestão e risco de licença para uso neste app; só avaliar por canal e contrato compatíveis. |
| Twelve Data | Lista B3/BVMF com dados EOD; exchange page indica Grow mínimo individual e Venture mínimo business. Créditos por minuto são ponderados por endpoint/símbolo; cobertura e profundidade por ativo precisam ser confirmadas. | Grow pessoal era listado a US$79/mês com 377 créditos API/minuto e display interno. A página comercial lista Venture a US$499/mês (US$414/mês equivalente anual com 17% de desconto), 2.584 API + 2.500 WS créditos, external display e EOD global; uma página oficial de suporte também anuncia Venture a partir de US$149/mês, então validar cotação e nível de créditos. Enterprise é listado a US$1.099/mês e inclui external distribution; add-on de EOD external distribution tem preço customizado. Planos pessoais não autorizam redistribuição; preços EOD fora dos EUA exigem aprovação comercial e licenças da bolsa podem se aplicar. Confirmar por escrito se gráficos derivados por usuário/portfólio são permitidos e qual plano cobre o cenário. É opção de estudo para a futura expansão, não selecionada. |
| Alpha Vantage | Documenta série diária global raw com mais de 25 anos; série diária ajustada/eventos corporativos é premium. É necessário testar cobertura e nomenclatura de todos os tickers B3 antes de contar com ela; listagem global não assegura suporte a cada ativo. Free: 25 requisições/dia; paid tiers retiram limite diário e escalam por requisições/minuto. | A tela pública de planos exibe escolha de tiers premium mas não apresentou preço legível nesta verificação; conferir a cotação vigente antes de comparar custo. Uso comercial requer contato/licença, e a licença padrão é pessoal, não transferível/não sublicenciável. A série adjusted inclui dividendos e splits; valuation precisa raw price/quantidade reconciliada. Pode ser economicamente atraente para experimentar, mas cobertura B3, quota e display para a versão multiusuário precisam de validação contratual. |

Confiabilidade deve ser comparada com um conjunto fictício de tickers cobrindo ações,
ETFs/FIIs se estiverem no escopo: completude de pregões, ajustes, revisões, ticker renames,
timestamps, códigos de falha, uptime/SLA e processo de retificação. O registro acima é uma
fotografia pública de preço/termos; limites e ofertas mudam e não são garantia contratual.
O levantamento de 28/10/2026 não escolhia fonte. A implementação local da 3.0.3 usa brapi
condicionalmente a uma credencial/plano que forneça `rawClose` e eventos de ações; isso não
significa que uma fonte adequada esteja confirmada ou selecionada para publicação. Não libera
exibição a convidados, redistribuição nem contratação automática. O projeto não tem orçamento
para API paga; avaliar fontes gratuitas permitidas em trabalho futuro. Consulte
[Fase 3.0.3](phase-3.0.3-equity-history.md) para termos, integração e limites atuais.

Links oficiais consultados: [histórico e ajustes brapi](https://brapi.dev/docs/acoes/historico),
[preços brapi](https://brapi.dev/pricing), [termos brapi](https://brapi.dev/legal/terms-of-use),
[FAQ comercial e limites de licença/distribuição brapi](https://brapi.dev/faq/posso-usar-a-brapi-para-construir-um-app-comercial-ou-para-minha-empresa),
[dados históricos da B3](https://www.b3.com.br/main.jsp?doui_processActionId=setLocaleProcessAction&locale=pt_BR&lumA=1&lumII=2C9E0371634B781701634B7C27111B5F&lumPageId=8A6A8C244DE7C289014DE80C873C130E),
[FAQ Market Data B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/distribuidores/perguntas-frequentes/),
[exchanges Twelve Data](https://twelvedata.com/exchanges),
[planos pessoais](https://twelvedata.com/pricing),
[planos comerciais](https://twelvedata.com/pricing-business),
[termos de uso comercial/pessoal Twelve Data](https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage),
[preços Venture de referência](https://support.twelvedata.com/en/articles/11116616-non-profit-organisation-subscription),
[Alpha Vantage docs](https://www.alphavantage.co/documentation/),
[limites gratuitos Alpha Vantage](https://www.alphavantage.co/support/api-key/),
[termos Alpha Vantage](https://www.alphavantage.co/terms_of_service/).

## O que pode ser calculado sem criar história

1. A quantidade de ações mantida numa data pode ser reconstruída a partir de BUY/SELL até
   essa data. Para estimar patrimônio nessa data também é necessário preço histórico válido
   daquele ativo, com moeda, ajuste corporativo, data e origem conhecidos.
2. Aplicações e amortizações de principal da Renda Fixa podem ser agregadas por data. Isso é
   fluxo de principal, não patrimônio e não retorno.
3. Uma posição observada pode ser exibida exatamente nas datas registradas. Não interpolar
   entre observações nem retroagir valor atual para períodos anteriores.
4. Resultado de CDI disponível hoje é estimativa condicionada a premissas e cobertura.
   Não converter estimativa em rendimento realizado ou em histórico confirmado.
5. Quando falta preço, snapshot, base monetária ou há possível sobreposição entre posição
   observada e lotes posteriores, o total da carteira deve ficar incompleto/indisponível ou
   explicar a exclusão. Nunca somar duas vezes nem trocar ausência por zero.

## Contrato de dados e endpoint candidato

O endpoint candidato para uma série geral permanece referência conceitual; a 3.0.3 usa uma
rota privada específica descrita em [Fase 3.0.3](phase-3.0.3-equity-history.md). Para novas
séries, avaliar uma leitura owner-scoped, por exemplo
`GET /api/dashboard/history?from=YYYY-MM-DD&to=YYYY-MM-DD&interval=month`. A resposta deve
carregar pontos normalizados com data, moeda, métricas separadas, cobertura/estado,
referências das fontes e instante do snapshot. Valores monetários devem ser serializados
como strings decimais; o backend deve calcular agregados com `Decimal` e limites explícitos.
O endpoint deve executar poucas consultas agrupadas com índices por proprietário/data,
evitar N+1 e respeitar `statement_timeout`/limites de período. Ainda não está decidido se
será necessário persistir preços/snapshots históricos; qualquer schema novo exige proposta,
aprovação e migration independente.

## Entregas pequenas e verificáveis

| Etapa proposta | Resultado e validação mínima |
| --- | --- |
| **3.0.1 — definições e cobertura** | Concluída conforme estado de publicação informado pelo responsável. |
| **3.0.2 — fluxos de capital** | Concluída conforme estado de publicação informado pelo responsável; métricas de fluxo continuam separadas de patrimônio e rentabilidade. |
| **3.0.3 — preço histórico de ações** | Implementação preservada; fonte/termos/cobertura apropriados para a execução ainda não validados. Não declarar concluída. Detalhes no documento da subfase. |
| **3.0.4 — histórico, capital e composição** | Concluída e validada localmente: histórico unificado, fluxos acumulados e composição por bases abertas; sem migration. Não publicada nesta rodada. Ver revisão final. |
| **3.0.5 — evolução e interface** | A proposta anterior de filtros, gráficos, tooltips, responsividade e estados foi incorporada à interface 3.0.3/3.0.4. Nenhum escopo adicional foi aprovado. |

Cada etapa pode ser interrompida sem falsificar histórico. Não implementar Fase 3.0 até o
responsável aprovar escopo, definições e próxima entrega.

## Riscos e decisões para aprovação

- **Preços históricos:** existe integração de código com brapi, mas o acesso adequado a
  `rawClose`, eventos societários, cobertura e termos de uso no ambiente de execução segue
  sem validação suficiente. Não contratar API paga nesta fase. Avaliar futuramente fontes
  gratuitas permitidas, mesmo com atraso/cobertura parcial; se indisponível, manter a série
  como indisponível e não inventar dados.
- **Retorno:** definir se/como incluir proventos, taxas, impostos, depósitos/resgates e
  eventos corporativos. Fluxo de caixa não é retorno; valorização não é lucro realizado.
- **Renda Fixa observada:** posição inteira pode incluir aplicações posteriores. Definir
  eventual política de inclusão do snapshot e dos lotes; até lá, impedir soma ambígua.
- **Datas e filtros:** definir dia/mês/ano, timezone, data de fechamento, feriados,
  intervalos máximos e comportamento em datas sem observações/preços.
- **Persistência:** aprovar previamente se snapshots ou preços precisam de retenção local,
  custo, política de expiração e eventual migration. Não preencher lacunas retroativamente.
- **Composição:** aprovar classes de ativo e denominadores; itens sem cobertura não podem
  desaparecer silenciosamente do percentual.
- **Acesso:** confirmar RLS por tabela/endpoint e teste com duas contas fictícias. Nenhuma
  permissão administrativa deve ser introduzida para agregar a carteira.
- **Licenças:** aprovar direitos distintos para uso pessoal (1.0) e eventual display a
  convidados (2.0), cache, retenção e métricas derivadas; direitos para exibir cotações não
  implicam licença de redistribuição. Obter confirmação contratual antes de selecionar fonte.

## Não escopo desta autorização

O escopo acima descreveu o plano inicial e não autorizou automaticamente endpoints,
migrations, coleta de preços, simulador, meta, convite ou cadastro público. Os itens que
vieram a ser implementados e seu estado atual estão no início deste documento. Fases 4, 5
e 6, lançamento pessoal 1.0 e expansão por convite 2.0 continuam apenas no roadmap. Convites
pertencem exclusivamente à nova versão 2.0, não à Fase 6.0. A demo pública segue offline e
com conteúdo fictício separado.
