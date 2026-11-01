# Fase 4.1 — contrato independente de histórico individual

## Entregue nesta etapa

- Endpoint privado `GET /api/dashboard/equities/{ticker}/price-history?period=1M|3M|6M|1A|MAX`.
- Consulta restrita a ações ainda abertas na carteira do proprietário autenticado; um ticker
  de outro proprietário recebe a mesma resposta 404 que um ticker ausente.
- Contrato diário com ticker, janela, moeda, fonte, base de preço, cobertura, pontos e
  disponibilidade (`available`, `disabled`, `unavailable` ou `empty`). Preços trafegam como
  strings decimais para preservar a precisão.
- Serviço e cliente HTTP do histórico separados do serviço de cotações pontuais. O tráfego
  do histórico agregado existente também usa cliente separado.
- Componente na página `/acoes` com ativo, períodos, tooltip e estados de carregamento,
  erro, indisponibilidade, carteira vazia e período sem preços.

## Fonte e habilitação — status v1.3

O candidato v1.3 adiciona integração opt-in com Brapi Free por `adjustedClose`, uma chamada
por ticker, cache temporário e limite de 3 meses por resposta. `MARKET_DATA_ENABLED` e
`INDIVIDUAL_EQUITY_HISTORY_ENABLED` permanecem `false` por padrão; sem configuração, a API
continua `disabled`/`provider_not_configured`. Períodos maiores que a janela efetivamente
retornada aparecem como parciais e sem preenchimento. O preço ajustado é destinado ao gráfico
individual e não reconstrói o valor histórico da posição.

## Migrações

Não há persistência de preços e nenhuma migration é necessária. O contrato é somente leitura
e usa as operações existentes apenas para verificar que o ativo pertence à carteira.
