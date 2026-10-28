# Fase 1.9.4 — avaliação de mercado no dashboard privado

Entrega de 28/10/2026. Integração frontend com o contrato da Fase 1.9.3, sem mudança em backend,
auth, banco, migrations, RLS, infraestrutura, dependências ou serviços. Nenhum deploy/push/tag
foi executado. Testes e inspeção visual usaram somente dados fictícios.

## Consulta e consistência

`PrivateRepository.summary()` agora usa `GET /api/dashboard/valuation` pelo cliente HTTP
autenticado existente. Não há chamada ao fornecedor no navegador, nem chamada adicional a
`/api/quotes` ou `/api/dashboard` para montar os cards. O Bearer Supabase continua sendo enviado
somente pelo cliente privado; BRAPI_TOKEN não foi introduzido no frontend.

O novo tipo PortfolioValuation descreve as strings Decimal, posições enriquecidas, cotações
e metadados de cobertura. O tipo Summary da demo não foi modificado. Na carteira privada,
quantidade, preço médio, custo, realizado, patrimônio e não realizado vêm do mesmo snapshot.
O histórico de operações continua usando `/api/operations`; o gráfico desse histórico permanece
explicitamente rotulado como fluxo de operações, não patrimônio ou rentabilidade histórica.

React Query conserva a chave por identidade e a limpeza de cache existente no logout/troca de
conta. Usa staleTime de 30 minutos, retry=false e nenhum refetchInterval. O refoco/reconexão
padrão pode atualizar dados que já estejam stale; navegar entre páginas não refaz a consulta
enquanto o snapshot estiver fresco. A renovação do token continua revalidando autorização pelo
fluxo existente da Fase 1.8.4. Compra/exclusão invalidam o snapshot mesmo dentro do staleTime.

O botão Atualizar avaliação permite consulta sob demanda e fica desabilitado durante a busca.
Não envia force-refresh nem contorna o cache/cooldown do backend. Requisição HTTP do navegador
não significa nova chamada brapi: o cache da Fase 1.9.2 continua sendo o controle do fornecedor.

## Apresentação

Mantidos os cards de capital pelo custo, compras acumuladas e resultado realizado. No privado,
acrescentados os cards de patrimônio a mercado **estimado**, resultado não realizado e variação
percentual sobre custo aberto. Esse percentual não é retorno total, anualizado ou TWR/XIRR.

As páginas Visão geral e Ações incluem a tabela do snapshot com:

- ticker, quantidade, preço médio e custo aberto;
- preço de cotação, valor de mercado e resultado não realizado;
- variação percentual, fonte, referência temporal, cache e instante de coleta quando disponível.

O banner informa cobertura, atraso esperado de aproximadamente 30 min e ausência de tempo real.
As referências incluem horário do livro, cálculo e intervalo de cotações. Horários ISO do backend
são apresentados com data/hora em America/Sao_Paulo e rótulo Brasília; o atributo time.dateTime
preserva a referência original. A hora de coleta não substitui a hora do negócio.

| Estado | Comportamento |
| --- | --- |
| complete | Cobertura completa; valores estimados nos horários informados, com atraso do plano |
| stale | Últimos preços explicitamente desatualizados, mantendo valores e horários originais |
| partial | Totais indisponíveis; subtotal parcial destacado, contagem e tickers faltantes |
| unavailable | Preços/totais indisponíveis; custos e posições continuam visíveis |
| empty | Patrimônio/não realizado realmente zero; percentual indisponível e nenhuma posição |
| Refetch pendente | Snapshot anterior permanece visível, com aviso de atualização em andamento |
| Erro de refetch | Erro visível e snapshot identificado como última avaliação recebida, sem confirmação de atualização |
| Erro inicial da API | Tela neutra com erro e nova tentativa; sem fabricar dados ou simular logout |

401/403 continuam seguindo os guards existentes. Totais null não são convertidos em zero; nem
subtotal é exibido como total confirmado. O componente também bloqueia total conflitante se o
estado for parcial, mesmo que um payload incorreto trouxesse um valor não nulo.

A formatação nova usa decimal.js já instalado e ROUND_HALF_EVEN apenas na apresentação final,
sem conversão prévia para Number e sem recalcular as fórmulas financeiras do backend. Precisão
foi testada acima do limite de inteiro seguro JavaScript. Quantidades mostram até oito casas.

O layout preserva o tema escuro, verde-esmeralda e componentes atuais. Cards se reorganizam em
três/duas/uma colunas. A tabela tem rolagem horizontal própria, região focável, caption e cabeçalhos
com scope. Indicadores negativos têm sinal textual além da cor; status usa região aria-live.

## Demonstração e gráficos existentes

DemoRepository, fixtures financeiras da demo e seu armazenamento permaneceram intactos.
Não há MarketDashboard renderizado na demo, cliente Supabase adicional ou chamada externa.
O card demonstrativo anterior continua informando ausência de cotações, sem inventar preços.

A composição continua explicitamente **pelo custo de aquisição** nos dois modos. O gráfico
continua sendo fluxo de compras menos vendas, sem taxas. Não foram apresentados como composição
a mercado ou curva histórica de patrimônio; uma avaliação atual não permite reconstruir essa curva.

## Arquivos

- frontend/src/api.ts — tipos privados PortfolioValuation, ValuedHolding e MarketQuote.
- frontend/src/repositories/PrivateRepository.ts — endpoint de snapshot.
- frontend/src/App.tsx — consulta/cache e integração condicional do componente privado.
- frontend/src/components/MarketDashboard.tsx e market-dashboard.css — cards, cobertura e posições.
- frontend/src/components/market-format.ts — formatação decimal de apresentação.
- frontend/src/components/MarketDashboard.test.tsx — estados e precisão.
- frontend/src/test-fixtures/market.ts — snapshots fictícios somente para testes.
- frontend/src/repositories/PrivateRepository.test.ts e frontend/src/auth/auth.test.tsx —
  contrato HTTP, navegação, erros e invalidação após operações.
- Este documento e docs/validation.md.

Não há variável de ambiente nova. Permanecem VITE_APP_MODE=private, VITE_PUBLIC_DEMO=false,
VITE_AUTH_MODE=supabase, VITE_API_BASE_URL do Render e as configurações públicas Supabase.
Nunca configurar BRAPI_TOKEN como variável VITE_*.

## Verificação

- **92 testes frontend aprovados**, incluindo os testes anteriores de sessão e demo offline.
- Cobertura de complete/stale/partial/unavailable/empty, preços null, perda, horário Brasília,
  precisão decimal, refetch pendente/falho e atualização manual.
- Testes integrados verificam uma consulta inicial valuation, ausência dos endpoints separados
  de quotes/dashboard contábil, navegação sem refetch fresco e invalidação após criar/excluir
  operações fictícias, sem chamadas reais ou alterações financeiras.
- Builds público e privado executados com variáveis temporárias e sem chaves reais; resultado
  final registrado em docs/validation.md. Aviso conhecido de bundle acima de 500 kB permanece.
- Inspeção Chrome headless do componente isolado, com fixtures: desktop 1440×1050 e mobile
  390×844. Em viewport móvel real, documento com largura 390 e tabela com rolagem própria
  (1060 de conteúdo, viewport da tabela 340), sem overflow horizontal da página de teste.
  Artefatos de inspeção estão em frontend/.tmp, ignorado pelo Git.
- Não houve login real, teste de headers remotos ou validação de cotações em produção nesta fase.

## Validação manual futura em produção

Após uma publicação explicitamente autorizada:

1. Confirmar que o backend já possui a Fase 1.9.3 e o endpoint `/api/dashboard/valuation`.
   Conferir MARKET_DATA_ENABLED/BRAPI_TOKEN exclusivamente no backend, sem copiar valores
   para o frontend. Endpoint 404 exige revisar a versão publicada, não criar fallback fictício.
2. Acessar https://investment-dashboard-pvd.vercel.app e entrar com conta já autorizada.
3. Em Network, confirmar chamada ao Render terminando em `/api/dashboard/valuation`, sem
   chamadas do navegador à brapi ou à B3. Não registrar/copiar headers Authorization.
4. Com posições já existentes, conferir custo/compras/realizado e as métricas novas da mesma
   resposta; observar fonte, horários, cobertura e avisos. Não criar operações financeiras reais
   apenas para validar essa tela.
5. Navegar entre Visão geral/Ações/Histórico e alternar abas: não deve aparecer login nem
   ocorrer nova consulta de mercado enquanto o snapshot estiver fresco.
6. Atualizar manualmente, observar estado pendente e conferir o cache do backend. Se houver
   falha real, dados anteriores devem permanecer identificados e 401/403 devem bloquear acesso.
7. Testar mobile, rolagem da tabela e foco por teclado. Confirmar o modo demo sem rede privada,
   inclusive restaurando a conectividade apenas depois de navegar no dashboard demonstrativo.

Limites: fonte atrasada, sem garantia de tempo real; cobertura e recência dependem do backend.
Sem polling contínuo, a tela mostra o último snapshot e seus horários até uma nova atualização.
O percentual não inclui caixa, proventos, impostos ou fluxos de aportes. Gráficos históricos de
patrimônio não foram implementados. As limitações de licença/SLA do provedor registradas em
1.9.1/1.9.2 permanecem. Não houve alteração ou ativação de serviço pago.

Commit sugerido, não executado:

```text
feat(phase-1.9.4): display market valuation in private dashboard
```
