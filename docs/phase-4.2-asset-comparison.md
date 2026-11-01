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

## Fonte, flag e limitação atual — status v1.3

O candidato v1.3 adiciona a mesma integração opt-in Brapi Free do histórico individual:
`adjustedClose`, uma chamada por ticker, cache temporário e até 3 meses por resposta.
`MARKET_DATA_ENABLED` e `INDIVIDUAL_EQUITY_HISTORY_ENABLED` permanecem `false` por padrão.
Períodos mais longos recebem estado parcial; a comparação usa somente as datas cobertas em
comum, sem interpolação. Cotações pontuais continuam independentes. A série é de preço
ajustado, não de retorno total.

O índice mede variação de preço ajustado desde a data comum; `adjustedClose` pode
refletir ajustes por desdobramentos e proventos. Ainda assim, o índice não representa
retorno total da carteira, pois não considera quantidades, fluxos, reinvestimentos,
taxas ou impostos. Não usa interpolação. Dados em datas distintas permanecem ausentes
nas linhas correspondentes.

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
