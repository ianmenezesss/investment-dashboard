# Fase 1.9.5 — clareza financeira e homologação

## Entrega

O dashboard privado distingue a valorização do preço negociado sem taxas do resultado
financeiro sobre o custo de aquisição com taxas. Não muda o cálculo legado de custo,
compras acumuladas, vendas ou resultado realizado. A demonstração continua local e offline.

### Bases e fórmulas

Todas as bases partem das mesmas operações privadas, ordenadas por data e id, capturadas
uma única vez pelo endpoint autenticado `GET /api/dashboard/valuation`.

- Compra: base sem taxas aumenta em `quantidade × preço negociado`.
- Venda parcial: remove `base sem taxas / quantidade anterior × quantidade vendida`.
  Assim, a média ponderada restante é preservada; uma compra posterior recalcula a média.
- Encerramento completo: zera essa base. Uma recompra inicia uma nova posição.
- `purchase_cost_without_fees`: base de compra sem taxas da posição ainda aberta.
- `average_trade_price`: essa base dividida pela quantidade atual. É média ponderada,
  não o preço da primeira/última compra nem média de todas as compras já encerradas.
- `average_price` (existente): custo aberto com taxas de compra dividido pela quantidade.
- `price_appreciation_percent`: `(valor de mercado − base sem taxas) / base sem taxas × 100`.
- `unrealized_profit` (existente): `valor de mercado − custo aberto com taxas de compra`.
- `return_percent` (existente): `resultado não realizado / custo aberto × 100`.
- `realized_profit` permanece exatamente o resultado legado das vendas: receitas de venda
  menos taxas de venda registradas e custo proporcional de aquisição, incluindo taxas de compra.

Exemplo fictício: 10 ações a R$ 20 com R$ 20 de taxas custam R$ 220. Com cotação R$ 21,
o ativo valorizou 5%, mas o resultado não realizado é −R$ 10 (−4,55% sobre custo).
Outro exemplo: compras 10×10 com taxa 2 e 10×30 com taxa 4; venda de 5×25 com taxa 1;
nova compra de 5×40 com taxa 2. Restam 20 ações, base sem taxas 500, custo 506,50,
médias 25 e 25,325. Com cotação 30: valorização 20%, resultado não realizado 93,50;
resultado realizado separado de 22,50.

O novo cálculo puro usa `Decimal` com precisão 64 e ROUND_HALF_EVEN. O ledger existente
mantém sua precisão e comportamento, sem recomputar resultados realizados. Não há nova
aritmética financeira no React: o frontend apenas formata strings decimais, com arredondamento
half-even a duas casas na apresentação. Médias diferentes podem aparentar igualdade após arredondar.

### Disponibilidade e limites

- Sem cotação utilizável, as médias históricas continuam disponíveis, mas valorização,
  mercado e resultado não realizado são null. Base ausente/inconsistente não é inferida
  do custo com taxas. Base zero não gera percentual.
- Campos novos são aditivos e anuláveis; frontend tolera backend anterior exibindo
  “Indisponível” nos novos indicadores, sem inventar valores durante atualização separada.
- Cobertura parcial mantém totais null e subtotal explicitamente parcial; atrasos, fonte,
  horário de cotação e horário de captura continuam identificados.
- Não são calculados variação diária, retorno total/anualizado, proventos, efeitos de
  eventos corporativos não registrados, inflação ou impostos. Resultados dependem das operações cadastradas.
- Resultado não realizado não é lucro líquido definitivo: custos futuros de venda e tributos
  não estão incluídos. Resultado realizado considera taxas registradas, mas não calcula impostos.

## Interface e acessibilidade

Tabela privada mostra média negociada sem taxas, média de custo com taxas, cotação,
valorização sem taxas e resultado sobre custo. Ajuda educativa curta funciona por ponteiro,
foco de teclado e toque; Escape fecha o tooltip. Tooltips usam portal para evitar corte na
tabela rolável. Descrição de resultado realizado esclarece taxas e tributos apenas no privado.
Cards, erros, carregamento, snapshot anterior durante atualização e horários foram preservados.

## Consumo gratuito

Nenhuma chamada nova: uma leitura de operações alimenta as duas bases e o QuoteService
existente. Permanecem cache por ticker por 1.800 s, deduplicação, concorrência 1, cache
negativo de 60 s, timeout, cooldown e teto de 12.000 tentativas por processo. O frontend
mantém staleTime de 30 min, sem polling ou retries automáticos do snapshot.
Atualização manual e mutações podem reconsultar o endpoint; cache válido evita HTTP externo.
O cache/teto em RAM reiniciam no restart e não são compartilhados entre workers/instâncias;
acompanhar consumo real no painel do fornecedor. Nenhuma garantia de cota mensal global é criada.
Os limites comerciais do plano não foram revalidados nesta fase; não houve consumo de API real.

## Validação local

Resultado: 108 testes backend e 96 frontend aprovados; builds demo e privado aprovados.

```powershell
Set-Location C:\Users\IAN\ProjetosVSCode\investment-dashboard\backend
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_postgres.py --tb=short
Set-Location ..\frontend
npm.cmd test
```

Builds sem credenciais reais, sobrescrevendo o ambiente apenas do processo:

```powershell
$env:VITE_PUBLIC_DEMO='true'; $env:VITE_APP_MODE='demo'
$env:VITE_AUTH_MODE='supabase'; $env:VITE_API_BASE_URL=''
$env:VITE_SUPABASE_URL=''; $env:VITE_SUPABASE_PUBLISHABLE_KEY=''
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Build demo falhou' }
$env:VITE_PUBLIC_DEMO='false'; $env:VITE_APP_MODE='private'
$env:VITE_API_BASE_URL='https://investment-dashboard-3ogz.onrender.com'
npm.cmd run build
```

Não usar esses valores vazios para publicar: encerrar esse terminal após a validação.
Testes usam HTTP simulado e SQLite em memória. PostgreSQL opcional não foi executado;
não houve alteração de banco local/remoto, migrations, RLS, autenticação, infraestrutura ou credenciais.
Chrome headless com fixture fictício isolado em 390×844: documento com 390 px;
tabela de 1.456 px em região de 340 px, sem overflow horizontal da página.
Isso não comprova login real ou comportamento publicado. Builds mantêm aviso conhecido
de bundle acima de 500 kB; suíte backend mantém aviso de depreciação do TestClient/httpx.

## Homologação em produção — manual, após publicação autorizada

1. Backend atualizado antes do frontend: confirmar os três campos novos na resposta
   autenticada de valuation; comparar operações já conhecidas, sem alterar registros reais.
2. Conferir médias com/sem taxas, venda parcial, resultado realizado separado e horários.
   Usar fixtures em ambiente de teste para cenários ausentes na carteira real.
3. Confirmar null para totais incompletos, aviso de atraso e estado de falha sem zero fictício.
4. Validar login, troca de aba sem flash, recarga, logout e bloqueio sem sessão;
   verificar acesso entre contas de teste autorizadas, sem expor seus dados.
5. Conferir teclado, Escape, tooltips, tela móvel e rolagem da tabela.
6. Na demo pública, verificar navegação/operações offline e nenhuma chamada privada/brapi.
7. Observar rede e painel da brapi: navegação não cria consultas de cotações extras;
   cache do backend atende atualizações repetidas dentro de 30 min.

Nenhum deploy, push, commit ou tag executado. Sugestão:
`feat(phase-1.9.5): improve financial clarity and validate market dashboard`.
