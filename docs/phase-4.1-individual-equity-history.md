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

## Fonte e habilitação

Nenhuma integração externa é configurada nesta etapa. `INDIVIDUAL_EQUITY_HISTORY_ENABLED`
é uma flag separada e permanece `false` por padrão. Mesmo se ativada sem provedor, a API
responde `unavailable/provider_not_configured`; não gera, estima ou reutiliza cotações atuais
como série histórica. A ativação depende de validação de cobertura, dados e licença.

## Migrações

Não há persistência de preços e nenhuma migration é necessária. O contrato é somente leitura
e usa as operações existentes apenas para verificar que o ativo pertence à carteira.
