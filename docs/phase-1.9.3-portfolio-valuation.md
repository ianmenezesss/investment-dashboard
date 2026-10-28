# Fase 1.9.3 — patrimônio em ações e resultado não realizado

Entrega de 28/10/2026. Backend apenas: cálculo puro com Decimal e novo endpoint autenticado.
Sem novos serviços, dependências, variáveis de ambiente, tabelas ou migrations. Nenhum deploy,
push, tag, chamada real à brapi ou alteração no banco foi executado.

## Separação entre livro contábil e avaliação

`app/finance.py::summarize` permanece intacto: ordenação por data/id, quantidade, custo médio,
taxas, receitas de venda e resultado realizado são os mesmos. POST/DELETE, exportação e o
GET `/api/dashboard` anterior não foram modificados para consultar cotações.

`app/valuation.py::value_portfolio` recebe um snapshot desse resumo e Quotes normalizadas da
Fase 1.9.2. A função não lê banco, não chama HTTP e não modifica os argumentos. O endpoint novo
reutiliza o QuoteService existente: mesmos cache, concorrência, timeout, token e plano gratuito.

As posições abertas são exclusivamente as de `summary.holdings`. Posições zeradas não pedem
cotação nem entram no patrimônio. Realizado histórico continua disponível mesmo sem posições.

## Fórmulas

Para uma posição aberta, com quantidade q, custo remanescente C e preço válido P:

| Indicador | Fórmula |
| --- | --- |
| Quantidade atual | Compras menos vendas, já apuradas cronologicamente pelo livro |
| Custo da posição | Custo de aquisição remanescente, incluindo taxas de compra |
| Preço médio | C/q do livro, sem novo arredondamento intermediário |
| Valor de mercado | q × P |
| Lucro/prejuízo não realizado | q × P − C |
| Variação percentual sobre custo aberto | (q × P − C) / C × 100, se C > 0 |

Na carteira, `valuation.open_cost = soma(C)` apenas das posições abertas. Com todas as cotações
utilizáveis, `market_value = soma(q × P)` e não realizado é `market_value − open_cost`.
O percentual agregado usa essa diferença dividida pelo custo total aberto: não é a média simples
dos percentuais individuais. Custo zero implica percentual null, sem divisão por zero.

Compra: quantidade × preço + taxas. Em venda parcial, o livro baixa custo proporcional pelo
preço médio e calcula realizado como receita líquida das taxas de venda menos custo baixado.
A avaliação não modifica esse realizado e não desconta taxas de uma venda hipotética futura.

Exemplo fictício coberto por teste:

1. Comprar 10 ações a R$ 20 com R$ 2 de taxas: custo R$ 202, preço médio R$ 20,20.
2. Vender 4 a R$ 25 com R$ 1 de taxa: líquido R$ 99, custo baixado R$ 80,80,
   **resultado realizado R$ 18,20**.
3. Restam 6 ações com custo R$ 121,20. Cotação de R$ 24: patrimônio R$ 144 e
   **não realizado R$ 22,80**; variação sobre custo aberto ≈ 18,81%.
4. Mudar apenas a cotação muda o não realizado, mas mantém os R$ 18,20 realizados.

Compras acumuladas não são aportes líquidos nem patrimônio. Não adicionar receita das vendas
novamente ao patrimônio em ações. Não há controle de saldo em caixa nesta versão.

## Decimal, precisão e arredondamento

Todas as novas operações monetárias usam Decimal em contexto local de 64 dígitos e
ROUND_HALF_EVEN; esse contexto não altera o contexto global nem recalcula os resultados
contábeis existentes. A precisão suporta a multiplicação de quantidades/preços com oito casas
sem a perda de dígitos que um produto grande teria em 28 dígitos significativos.

O contrato Pydantic serializa valores monetários, quantidades e percentuais como **strings**,
incluindo no OpenAPI do endpoint. Não converte Decimal para float no JSON. Valores não são
quantizados para centavos no backend: arredondamento visual pertence à Fase 1.9.4 e não deve
ser reutilizado como entrada de cálculos. Testes verificam 0,6 exato e exibição HALF_EVEN de
0,295 → 0,30 e 0,285 → 0,28.

Os campos contábeis superiores, inclusive acquisition_cost e realized_profit, são copiados
do livro anterior. `valuation.open_cost` soma somente os custos das posições abertas com o
novo contexto. Isso também exclui resíduos decimais mínimos que o cálculo contábil legado
eventualmente deixe em uma posição já encerrada, sem reescrever seu resultado realizado.
No caso vazio/liquidado: patrimônio e não realizado zero, percentual null, estado empty.

## Cotações ausentes, inválidas e atrasadas

Além da normalização do QuoteService, a função pura verifica status ok/stale, preço positivo
finito, moeda BRL, timestamp com timezone e identidade do ticker. Rejeita preço com mais de
oito casas, acima de 1e12, timestamp além de 60 s no futuro, cotação com mais de 96 h ou
duplicidade ambígua para o mesmo ticker. Outros tickers da lista de Quotes são ignorados.

- Nenhum preço de compra, zero ou preço inventado substitui cotação indisponível.
- Ao faltar qualquer cotação utilizável, market_value e resultado/percentual agregados ficam
  **null**. `partial_market_value` é só o subtotal coberto, nunca patrimônio total confirmado.
- Os cálculos individuais das posições cobertas continuam disponíveis. Posições sem preço
  conservam quantidade, custo e preço médio, com métricas de mercado null.
- Com todos os preços utilizáveis, porém algum marcado stale ou com idade superior a 75 min,
  o total é calculado como **estimativa desatualizada**, com status stale.
- `is_complete=true` significa cobertura de todas as posições, não tempo real nem dado atual.
- São preservados provider, quoted_at, fetched_at, from_cache, is_stale, reason e demais
  metadados do serviço. O intervalo quoted_at_min/max mostra a diversidade de instantes usados.

O plano gratuito tem atraso; ok não significa cotação em tempo real. As janelas de idade não
são calendário de pregão. Último negócio em fim de semana/feriado continua identificado pelo
horário original; não se afirma que o mercado está aberto ou fechado.

## Novo contrato para a Fase 1.9.4

**GET `/api/dashboard/valuation`**, com Authorization Bearer da sessão Supabase existente.
No futuro, PrivateRepository deverá chamar `request('dashboard/valuation', token, { signal })`,
com um tipo próprio para a resposta; não combinar saldos e preços de duas respostas distintas.
O cliente deve invalidar essa consulta em criação/exclusão de operação e trocar/limpar cache
por identidade, como já faz no fluxo privado. Nada disso foi implementado no frontend agora.

| Campo da resposta | Tipo/significado |
| --- | --- |
| ledger_as_of | Instante UTC em que o livro foi capturado |
| acquisition_cost, total_purchases, sale_proceeds, realized_profit | Strings Decimal do resumo contábil original |
| market_value | String Decimal do patrimônio em ações ou null |
| holdings[] | ticker, quantity, cost, average_price; quote; market_value, unrealized_profit e return_percent da posição |
| valuation.calculated_at | Instante UTC da avaliação, após a busca de preços |
| valuation.status | complete, stale, partial, unavailable ou empty |
| valuation.is_complete | Cobertura de preços de todas as posições abertas; true também no caso vazio |
| valuation.open_cost | Custo total das posições abertas |
| valuation.unrealized_profit, return_percent | Strings Decimal ou null quando a cobertura é incompleta |
| valuation.partial_market_value, covered_cost | Subtotal a mercado e custo somente das posições cobertas |
| valuation.covered_positions, total_positions | Contagens de posições cobertas e abertas |
| valuation.missing_tickers | Tickers sem preço utilizável |
| valuation.quoted_at_min, quoted_at_max | Menor/maior horário entre cotações usadas; null quando nenhuma |

Estados:

| status | Mercado agregado |
| --- | --- |
| complete | Todas as posições com preço utilizável, sem stale; atraso do provedor ainda existe |
| stale | Cobertura completa com ao menos uma cotação desatualizada; exibir estimativa/horário |
| partial | Ao menos uma posição coberta e outra sem preço; total null |
| unavailable | Posições abertas, nenhuma com preço utilizável; total null |
| empty | Nenhuma posição aberta; total zero, percentual null, sem chamadas ao fornecedor |

Falta de cotação/fornecedor retorna 200 com esses metadados, não falha da autenticação.
401/403 de acesso continuam tendo o significado original. Não há endpoint novo público,
parâmetro para escolher owner_id ou fallback para outra fonte.

Na Fase 1.9.4, o percentual deve ser rotulado **variação sobre o custo das posições abertas**,
não retorno histórico/total da carteira. Não inclui caixa, renda fixa, proventos, impostos,
aportes/resgates, TWR/XIRR ou anualização. Splits, bonificações e mudanças de ticker não corrigem
automaticamente o livro: suas quantidades precisam representar a posição econômica correta.
O snapshot atual não reconstrói um gráfico histórico de patrimônio.

## Isolamento e consistência

O snapshot usa private_db e records com filtro do proprietário, sem mudanças em auth/RLS.
Resumo e avaliação são da mesma leitura; a transação é encerrada antes do HTTP externo.
Só os tickers abertos dessa leitura chegam ao serviço. Uma operação registrada durante a
consulta aparecerá em novo snapshot, não será misturada ao anterior; ledger_as_of deixa isso claro.

O cache reutilizado contém preços públicos, nunca respostas de carteira. Dois usuários com
o mesmo ticker compartilham a cotação, mas recebem quantidades/custos/resultados próprios.
As respostas mantêm Cache-Control: no-store. Não se envia identidade ou operações à brapi.
GET /api/dashboard, /api/quotes, /health, POST/DELETE e exportação preservam o comportamento anterior.

## Arquivos e verificação

- Novo backend/app/valuation.py: função pura e modelos de resposta.
- backend/app/main.py: snapshot privado e endpoint /api/dashboard/valuation.
- Novos backend/tests/test_valuation.py e test_valuation_api.py.
- Este documento e docs/validation.md.

Executado, sem consumo real da API:

```powershell
# Na pasta backend
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_postgres.py --tb=short
# Na pasta frontend
npm test
```

**96 testes backend aprovados**, incluindo 23 novos: lucro/prejuízo, múltiplas compras,
taxas, venda parcial/total, liquidação com resíduo, carteira vazia, cobertura parcial/ausente,
stale/timestamps, precisão, arredondamento e preservação do realizado. Os testes de API usam
SQLite em memória e HTTPX MockTransport, verificando autorização antes do banco, filtro por
proprietário, cache de preço compartilhado sem misturar carteiras e transação encerrada antes
da rede. Os **78 testes frontend também passaram**, incluindo demonstração sem rede privada.

PostgreSQL opcional foi excluído; não houve alteração de RLS que exigisse executar migrations
em banco de teste. Não foram necessários novos builds frontend, pois não houve alteração de
frontend/configuração/dependências. Homologação real do endpoint depende de publicação futura
autorizada; não foi executada nesta fase. Continua o aviso existente de depreciação Starlette/httpx.

Commit sugerido, não executado:

```text
feat(phase-1.9.3): implement portfolio market valuation
```
