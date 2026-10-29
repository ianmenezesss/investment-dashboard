# Fase 3.0.3 — histórico de ações

**Estado: implementação local para revisão; não publicada.** Não houve push, deploy,
migration nem consulta à carteira de produção nesta entrega.

## Fonte e condições de uso

A implementação usa a brapi, que já fornece as cotações pontuais do projeto. Em
29/10/2026, a documentação oficial descreve o endpoint diário de preços e o endpoint de
proventos/eventos em ações. Foi feita uma consulta pública sintética de ITUB4 para um ano:
o endpoint respondeu com pregões, mas sem `rawClose` (a amostra sem autenticação não prova
que qualquer plano de produção tenha acesso ao campo).

O cálculo exige `includeRaw=true` e usa exclusivamente `rawClose`, sem fallback para
`close` ou `adjustedClose`. A documentação reserva `raw*` ao plano Pro; o fechamento
ajustado inclui desdobramentos e proventos e não é compatível diretamente com quantidade
histórica para mark-to-market. O endpoint de dividendos informa fatores de eventos em
ações, usados na data ex (`exDate`) antes das operações do dia. A consulta ao provider
retorna indisponibilidade explícita se esses campos não vierem.

Na consulta de 29/10/2026, o preço anunciado do Pro era R$ 116,66/mês equivalente,
cobrado R$ 1.399,90 por ano. O Startup era R$ 99,99/mês equivalente, R$ 1.199,90 por ano,
mas não fornece `rawClose`; portanto não atende ao valuation implementado. Preço e ofertas
podem mudar e devem ser conferidos antes de qualquer contratação.

Os termos da brapi permitem integrações em sistemas internos, mas proíbem redistribuir ou
sublicenciar os dados e criar proxy/wrapper para oferecer acesso público. Esta integração
fica atrás da autenticação/owner scope do dashboard pessoal; não deve ser aberta a terceiros
sem esclarecimento de licença. A brapi não é distribuidora licenciada da B3, não garante
completude/precisão e não oferece SLA. A página oficial mostrava histórico acima de dez anos
no Pro e preço anual sujeito a alteração (consultar a página antes de contratar). O escopo
é apenas uso pessoal privado, sem recomendação de investimento.

Fontes oficiais conferidas em 29/10/2026:

- [Histórico de preços brapi](https://brapi.dev/docs/acoes/historico)
- [Dividendos e eventos em ações brapi](https://brapi.dev/docs/acoes/dividendos)
- [Planos e limites brapi](https://brapi.dev/pricing)
- [Termos de uso brapi](https://brapi.dev/legal/terms-of-use)
- [Uso da brapi em sistemas internos](https://brapi.dev/faq/posso-usar-a-brapi-para-construir-um-app-comercial-ou-para-minha-empresa)
- [Histórico de cotações B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/)

O download de histórico no site da B3 não foi usado: a própria página veda coleta
automatizada. O objetivo foi evitar raspagem e não assumir direitos que o projeto não tem.

Yahoo Finance também não foi escolhido: a ajuda oficial documenta download histórico CSV
como recurso Yahoo Finance Gold e avisa que disponibilidade depende da licença do instrumento;
ela não documenta um endpoint estável de market data B3. Os termos da API Yahoo vedam coleta
automatizada por fora de APIs autorizadas. Uma biblioteca não oficial que raspe o endpoint de
gráficos não satisfaria os critérios de acesso e licença desta fase. Fontes: [ajuda de dados
históricos do Yahoo](https://help.yahoo.com/kb/finance/certain-amounts-sln2311.html)
e [termos da API Yahoo](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apitnc/index.html).

## Contrato e cálculo

- Endpoint privado: `GET /api/dashboard/equity-history?period=1M|3M|6M|1A|Tudo`.
- A autenticação Supabase/local existente e `private_db` protegem a rota; operações são
  consultadas por `owner_id`. Símbolos registrados não válidos não são enviados à fonte.
- O fechamento diário é valorado com as quantidades BUY/SELL reconstruídas até a data.
  Eventos fatorados na data ex são aplicados primeiro; operações daquela data em seguida;
  ambos refletem o fechamento do mesmo pregão.
- Cada ponto expõe valor de mercado, subtotal coberto, fluxo líquido histórico e a diferença
  entre os dois. Diferença não é rentabilidade ou lucro: caixa, proventos, tributos e outros
  fluxos não estão modelados. CDB e observações de renda fixa não entram nesta série.
- O endpoint devolve valores financeiros como strings decimais calculadas com `Decimal`.
  Ausência de preço resulta em `null` para o total e em lacuna no gráfico; nunca se replica
  o último preço. Datas anteriores à primeira operação registrada não são desenhadas e
  fazem a janela aparecer como parcial.
- A cobertura `complete` indica que a resposta da fonte forneceu os dados necessários para
  os pregões exibidos; não é auditoria independente da cobertura/fidelidade da brapi.
  Tickers rebatizados ou eventos sem fator/data ex válida ficam indisponíveis.
- Cache é somente em memória no processo, por consulta e por 30 minutos em respostas
  completas (60 segundos após erro). Não foi criado armazenamento histórico ou migration.
  Reinício do processo Render limpa o cache.
- A chave brapi só é enviada no cabeçalho pelo backend. O demo público não monta o componente
  nem consulta a rota privada.

## Interface

O painel privado aparece na Visão geral e em Ações, abaixo de “Fluxos e composição da
carteira”. Os períodos são 1M, 3M, 6M, 1A e Tudo. A linha verde é valor de mercado das
ações; a azul é fluxo líquido acumulado em ações (compras e taxas menos vendas líquidas de
taxas). O aviso explicita fonte, base do preço e exclusões. Um plano sem `rawClose` mostra
um aviso e não troca para um preço ajustado.

O eixo do gráfico anterior de fluxos de capital também foi corrigido: valores abaixo de mil
aparecem como moeda BRL completa; abreviação compacta conserva casas suficientes para não
duplicar ticks próximos.

## Banco, configuração e validação

Não há mudança de schema nem migration. A feature depende da configuração já usada para
cotações (`MARKET_DATA_ENABLED=true` e `BRAPI_TOKEN` configurado com acesso aos campos
`rawClose` e eventos). Não há variável nova nem credencial do provider no frontend.

Testes adicionados cobrem precisão Decimal, compras em datas diferentes, venda parcial e
total, desdobramento, janela anterior à primeira operação, falta de preço, cobertura
parcial, resposta sem `rawClose`, timeout/indisponibilidade HTTP/rate limit via erros
controlados, cache, autenticação e isolamento A/B. Testes Vitest cobrem renderização,
tooltip, filtro, loading/erro/vazio, cobertura e formatação do eixo.

Os valores têm finalidade informativa, não representam preço oficial em tempo real, retorno
total ou patrimônio completo. Revalidar acesso real a `rawClose` na chave de produção antes
de qualquer publicação; esta tarefa não inspecionou nem alterou segredos ou produção.
