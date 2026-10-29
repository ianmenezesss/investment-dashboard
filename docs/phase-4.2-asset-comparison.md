# Fase 4.2 — Comparação de ativos

## Escopo entregue

- Endpoint privado `GET /api/dashboard/equities/compare?tickers=ITUB4&tickers=BBAS3&period=1M`.
- Aceita de 2 a 4 tickers distintos somente quando todos estão em posições abertas
  do proprietário autenticado. Ticker ausente ou de outra conta retorna 404.
- Reutiliza `EquityPriceHistoryService` e os períodos da Fase 4.1; não usa o serviço
  de cotações pontuais nem altera dados financeiros.
- Normaliza as séries para índice 100 na primeira data com um fechamento válido e
  comum a todos os ativos. Só há pontos em datas retornadas pela fonte; datas sem
  preço ficam como `null`, sem interpolação ou preenchimento.
- A comparação é recusada quando moeda, fonte ou base de preço não são compatíveis.
  Base de preço desconhecida não é suficiente para comparar.
- A interface em `/acoes` permite selecionar de 2 a 4 posições, filtrar períodos,
  ver linhas/legendas, origem, cobertura e base, e informa indisponibilidade sem
  desenhar preços.

## Fonte, flag e limitação atual

`INDIVIDUAL_EQUITY_HISTORY_ENABLED` permanece `false` por padrão e nenhum provedor
individual está configurado. Portanto, a API de comparação retorna explicitamente
`disabled` ou `provider_not_configured`, sem chamar serviços externos e sem gerar
preços. Cotações pontuais continuam independentes. A comparação de séries reais
depende de aprovação de fonte, cobertura, licença e semântica de preços.

O índice mede variação de preço desde a data comum. Não representa retorno total,
não inclui proventos por conta própria e não usa interpolação. Dados em datas
distintas permanecem ausentes nas linhas correspondentes.

## Persistência e validação

Não há tabela, cache persistido ou migration. A comparação é calculada em memória
a partir do contrato de histórico individual. Os testes usam provedores simulados
somente em fixtures; nenhum dado demonstrativo é disponibilizado na carteira real.

Validar localmente:

```powershell
Set-Location C:\Users\IAN\ProjetosVSCode\investment-dashboard\backend
.\.venv\Scripts\python.exe -m pytest tests\test_equity_comparison.py tests\test_individual_equity_history.py

Set-Location C:\Users\IAN\ProjetosVSCode\investment-dashboard\frontend
npm test -- --run src/portfolio/AssetComparison.test.tsx src/repositories/PrivateRepository.test.ts
npm run build
```
