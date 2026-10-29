# Fase 4.4 — Plano condicional de rentabilidade temporal

**Status:** Bloqueado por dependências de dados e fonte; proposta ainda não autorizada. Não substitui a Fase 4.3A.

## Objetivo

Medir a evolução temporal somente quando existirem fluxos corretamente classificados e valores da carteira em datas de referência. Uma cotação atual não é uma avaliação histórica. Uma série de preço de uma ação não equivale a patrimônio da carteira.

## Dados necessários

1. Movimentos externos de caixa com datas, valores, direção e proprietário, distintos de compras, vendas, aplicações, resgates e transferências internas.
2. Eventos de investimento no escopo escolhido: dividendos/JCP, amortizações, splits/bonificações e outros eventos apenas se houver evidência e regra definida.
3. Avaliações datadas de todas as posições incluídas, com fonte, base de preço, moeda, cobertura e momento de coleta.
4. Para CDB: valores observados ou metodologia estimativa validada para cada contrato, tributos e data; vencimentos/liquidez não podem ser inferidos de uma taxa isolada.
5. Identificação de posições abertas, fechadas e ativos sem dados; lacunas devem permanecer lacunas.

O histórico bruto de ações 3.0.3 existe no repositório, porém permanece opt-in/desabilitado e sua fonte não foi aprovada. Fases 4.1/4.2 não configuram provedor. Nenhuma dessas rotas deve ser ativada para cálculo até validar cobertura e termos.

## Metodologias candidatas

### TWR

Retorno ponderado pelo tempo liga os retornos dos subperíodos entre fluxos externos. Cada fluxo que altera capital externo exige valuation consistente imediatamente antes/depois ou método de encadeamento documentado. Retorno ligado:

Produto de (1 + retorno de cada subperíodo) − 1.

Não calcular se os valores nas fronteiras não existirem. Não aproximar usando compras/vendas como se fossem aportes do investidor.

### MWR / XIRR

Usa os fluxos externos com datas e um valor terminal de carteira, resolvendo a taxa anual r que zera:

Soma de CF_i / (1 + r)^((data_i − data_0)/365) = 0.

É necessária convenção de sinais, datas completas, caixa de entrada/saída e valuation terminal comparável. Fluxos internos entre ativos não podem virar aportes ou saques do investidor.

### Limites

- Não chamar o diferencial entre patrimônio atual e fluxo acumulado de rentabilidade.
- Não misturar preço bruto e preço ajustado sem reconciliar quantidades e eventos.
- Não extrapolar CDI ou cotações ausentes.
- Benchmark é comparação separada; exige moeda, datas, calendário e metodologia compatíveis.
- Resultado histórico não será líquido de imposto sem registros e escopo tributário sustentáveis.

## Fontes gratuitas e licença

Antes de qualquer fonte:
- provar dados para tickers e intervalos brasileiros representativos;
- verificar campos raw/adjusted, moeda, timezone, eventos, cobertura, atraso, quota, cache e licença para uso no dashboard privado;
- registrar origem e timestamps;
- manter segredo no backend;
- medir limites de quota usando cache/backoff e orçamento de requisições;
- exigir que o app funcione sem fonte: estados disabled/unavailable e dados ausentes nulos.

Não contratar fonte paga. Não fazer scraping de sites. Se nenhuma alternativa gratuita permitida satisfizer os critérios, manter a funcionalidade bloqueada e apresentar valores como indisponíveis. Planos gratuitos podem mudar, suspender ou remover cobertura; confirmar limites antes de cada publicação.

## API e UI futuros

Não definir endpoint de rentabilidade final até a auditoria de dados. Possível contrato: série privada por período com datas, valuation, fluxos externos, retorno do subperíodo, coverage, fonte, valuation method, moeda, timestamp, flags de estimativa e motivos de indisponibilidade.

O endpoint deve usar snapshot consistente, owner_id/RLS, Decimals como strings e impedir exposição de outros usuários. Retornar cada série e cobertura; total da carteira é null se algum componente obrigatório faltar. A UI separa evolução patrimonial, fluxos e benchmark; permite período sem fonte apenas em estado indisponível.

Feature flags históricas existentes ficam false por padrão. Não acoplar chamada histórica ao endpoint de cotações atuais.

## Persistência e migrations

Snapshots históricos de patrimônio e novos eventos provavelmente exigem migrations. Proposta de modelo append-only/versionado:
- eventos de caixa/proventos/eventos societários com proprietário, data econômica, data de registro, fonte/referência, valores Decimal e idempotência;
- valuations por proprietário, data-base, classe/ativo, moeda, valor, método e metadados de fonte/cobertura;
- revisões ou correções auditáveis sem sobrescrever trilha original.

A modelagem precisa de revisão financeira/segurança e aprovação explícita antes de migration. Não inserir retrospectivamente snapshots criados com preços atuais. Importações de históricos antigos só podem usar fontes/documentos existentes e validados.

## Testes e aceite

- fluxos externos em datas diferentes; dinheiro não investido e transferências internas;
- TWR em períodos sem fluxo e com fluxo exatamente nas fronteiras;
- XIRR com datas irregulares, valores negativos/positivos, ausência de solução e valor terminal;
- proventos/reinvestimento sem dupla contagem;
- falta de preço por data, férias/lacunas, ativos com coberturas diferentes;
- ajustes corporativos e base de preço;
- CDB open/closed, taxas incompletas, tributos e manual snapshots;
- REPLACE/VOID; Decimal, rounding e moeda;
- autenticação, proprietário/RLS, sem dados no-store/cache compartilhado;
- feature off impede rede histórica; cotação atual permanece funcional;
- aceitação da fonte/licença e disponibilidade em falha; nenhuma série inventada.

Conclusão só quando método, entradas, cobertura, fonte e visualização forem auditáveis. A ausência de fonte gratuita adequada é condição de bloqueio explícita, não motivo para preencher pontos sintéticos.
