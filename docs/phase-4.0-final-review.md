# Revisão técnica final — Investment Dashboard v4.0.0

**Revisado em:** 29/10/2026
**Estado original da revisão:** release candidate local tecnicamente validado, antes das confirmações de publicação descritas no aditivo ao final deste documento.

## Escopo entregue

- **4.1 — Histórico individual de ações:** rota privada e contrato provider-neutral em `/acoes`; `INDIVIDUAL_EQUITY_HISTORY_ENABLED=false` por padrão e nenhum provedor real configurado. Cotação pontual permanece independente.
- **4.2 — Comparação de ativos:** seleção de 2–4 posições abertas, períodos da 4.1, índice base 100 sobre datas/preços comuns, sem interpolação. Depende do provedor histórico que ainda não foi aprovado.
- **4.3A — Resumo financeiro atual:** `GET /api/dashboard/performance`, composto dos livros atuais de ações e CDB, avaliação por cotações pontuais e composição. Interface no `PortfolioInsights`; sem página financeira duplicada.
- **4.4 — Rentabilidade temporal completa:** bloqueada. Não há fluxos externos classificados, proventos/eventos suficientes e fonte de valuations históricas aprovada. Nenhuma cotação atual é usada para reconstruir datas passadas.

## Regras financeiras implementadas

- Compras de ações: quantidade × preço + taxas registradas.
- Vendas: caixa líquido = quantidade × preço − taxas registradas; custo removido usa o custo médio vigente no ledger; resultado realizado = caixa líquido − custo removido, antes de impostos.
- Principal CDB aberto e resgatado usa movimentos efetivos de `effective_movements()`. `REPLACE`/`VOID` não duplicam ou mantêm movimentos anulados. Caixa recebido não é interpretado como rendimento.
- Fluxo líquido registrado = compras + aplicações − vendas após taxas − principal resgatado. É fluxo das operações conhecidas, não depósito externo, patrimônio ou rentabilidade.
- Capital aplicado contabilizado em posições abertas = custo de aquisição aberto de ações com taxas + principal efetivo aberto em lotes CDB. Posições declaradas sem lotes ficam separadas.
- Resultado não realizado usa cotações pontuais atuais e custo aberto. Resultado combinado só é retornado com cobertura completa das ações abertas; cotação stale aparece com aviso. Isso não é retorno total nem líquido de impostos.
- Rendimento bruto/líquido CDB permanece por contrato na página de renda fixa, nas condições do motor existente. Este resumo não soma estimativas CDB nem inventa rendimento realizado.
- A multiplicação de entradas permitidas por `NUMERIC(20,8)` excedia a precisão padrão Decimal em um caso limite. Outro caso reproduziu um resíduo `1E-64` depois da liquidação de custo médio repetitivo. `summarize()` agora usa contexto local de 64 dígitos e remove a base exata quando a venda liquida a posição, sem alterar o contexto Decimal global.

## API, segurança e persistência

- `GET /api/dashboard/performance` usa autenticação privada, `private_db`, `owner_id` do servidor/RLS, respostas `no-store` e tipos Pydantic. Não aceita identidade do cliente para escolher a carteira.
- A rota lê os registros do proprietário, reutiliza `summarize()`, `aggregate_capital_flows()`, `aggregate_composition()`, `effective_movements()` e `value_portfolio()`. A consulta de cotações atuais continua no serviço `QuoteService`; a rota não chama serviço histórico.
- Não houve mudança de schema nem migration. A validação PostgreSQL foi executada apenas pelo runner do repositório em containers locais efêmeros, com tmpfs e sem volumes persistentes.
- Auditoria local do repositório/build: 227 arquivos candidatos e 20 artefatos públicos analisados; nenhum segredo conhecido ou assinatura de segredo detectado. Isso não substitui a revisão dos painéis/variáveis hospedados.
- `npm audit --audit-level=high`: zero vulnerabilidades no lockfile auditado em 29/10/2026.

## Falhas investigadas e resolvidas

- A primeira suíte frontend após integrar o novo endpoint teve 8 falhas em 16 testes. A causa comum era o mock de `auth.test.tsx`: respostas para `dashboard/performance` caíam no fallback `[]`, mas `PortfolioInsights` passou a consumir o contrato financeiro. O mock agora responde o contrato vazio tipado, preservando as verificações de autenticação. A checagem de participações nulas foi ajustada para aceitar `null` e `undefined` com segurança.
- Antes dessas alterações, a suíte frontend tinha 160 testes aprovados; depois da correção de contrato e do caso de cotação stale: 162 aprovados.
- O caso citado de `ObservedHistory` já possui validação do array `points` no query function; o teste envia uma resposta malformada sem `points` e confirma estado de erro sem acesso a `.length`. Não foi a causa das falhas de autenticação desta rodada.
- O principal bundle inicial media 806,13 kB e ultrapassava o aviso de 500 kB. O carregamento das páginas/gráficos foi dividido sob demanda; o chunk inicial atual mede 443,68 kB e o maior chunk também fica abaixo de 500 kB. Não foi alterada a configuração de CI.

## Validação executada

| Verificação | Resultado |
|---|---|
| Backend completo (`pytest -q`) | 363 aprovados, 1 ignorado, 1 aviso em 70,95 s. O ignorado requer `TEST_DATABASE_URL`; foi exercitado separadamente pelo runner PostgreSQL. |
| Backend focalizado de 4.1/4.2/4.3A, auth, cotação atual, CDB e ledger | 219 aprovados, 1 aviso. |
| PostgreSQL descartável | 1 aprovado; migrations 001–008, persistência/validação cronológica e backup/restore; verificação confirmou head 008 e igualdade de contagens/RLS/grants entre origem e restore. |
| Frontend completo | 162 aprovados em 16 arquivos de teste. |
| Build de produção | Passou; chunk inicial 443,68 kB, maior chunk 443,68 kB; sem aviso de chunk acima de 500 kB. |
| `npm audit --audit-level=high` | Passou; 0 vulnerabilidades. |
| Auditoria de publicação | Passou; nenhum segredo conhecido/assinatura detectado nos candidatos, artefatos e histórico analisados. |
| Workflow GitHub Actions | YAML parseado; a etapa cria `INVESTMENT_TEMP_DIR` com `mktemp -d` e instala trap de limpeza. Nenhuma execução hospedada após os commits foi observada. |
| `git diff --check` | Executado antes dos commits finais; sem erros de whitespace. |

Os testes do Recharts exibem avisos de largura/altura zero em `jsdom`; são limites do layout de teste sem viewport, não falha de build. O backend emite um aviso de depreciação de `starlette.testclient` com HTTPX; não bloqueia a suíte.

## Pendências e decisão de release

### Não bloqueiam tecnicamente a v4.0.0

- Fonte histórica real e licenciada para 3.0.3/4.1/4.2/4.4. Os recursos continuam indisponíveis/desligados e não inventam preços.
- Rendimento CDB agregado ou retorno de carteira; faltam dados/método, e as estimativas CDB continuam por contrato.
- Simulador e Metas, placeholders destinados à v5.

### Conferências operacionais antes de qualquer publicação

1. Confirmar no GitHub Actions uma execução verde sobre o SHA que será publicado; o ambiente local não verifica a execução hospedada.
2. Conferir no Render/Vercel/Supabase as variáveis e serviços reais, sem inferir valores a partir do `.env.example`.
3. Confirmar a revisão remota PostgreSQL `008` e papel de runtime restrito em consulta somente leitura; nenhuma conexão de produção foi usada nesta rodada.
4. Fazer validação manual autenticada no ambiente alvo: login/logout, leitura ações/CDB, resumo financeiro com carteira real do proprietário, demo offline, flags históricas desligadas e layout mobile.
5. Confirmar backup/restauração e o alvo de rollback de aplicação. Não há migration nesta versão, logo rollback de app não exige downgrade de schema.

**Decisão:** *pronta com ressalvas para revisão manual de release*. Os critérios técnicos locais foram atendidos; esta revisão não declara produção validada nem autoriza publicação. O bloqueio da 4.4 permanece explícito e não é motivo para fabricar dados ou ativar uma fonte não validada.

## Commits locais deste ciclo

| SHA | Mensagem | Escopo |
|---|---|---|
| `822408d` | `docs: v4.0.0 consolidate roadmap and future expansion plans` | Sete documentos de roadmap/planejamento, sem implementação. |
| `e00f367` | `fix: v4.0.0 preserve exact Decimal cost basis` | Precisão Decimal e liquidação exata do custo aberto, com regressões. |
| `8db78d8` | `feat: 4.3A implement financial performance summary` | Endpoint, contrato, agregação existente, painel e testes. |
| `d82c891` | `perf: v4.0.0 optimize frontend bundle` | Imports de páginas/gráficos sob demanda. |

Um commit documental final desta revisão é criado após a validação e inclui CHANGELOG, roadmap, arquitetura, revisão da v4 e handoff v5. Nenhum destes commits foi enviado ao GitHub.

## Rollback de aplicação

Se uma publicação futura apresentar falha, interromper o tráfego/retornar o frontend privado e backend ao artefato ou commit anteriormente estável usando os controles manuais de cada plataforma. Como não há migration nova, não executar downgrade nem restaurar o banco por causa desta versão. Verificar login, endpoint de valuation e operação de leitura após rollback. Manter export/backup conforme a política do ambiente.

## Aditivo — publicação e verificações operacionais reportadas

O proprietário confirmou que a v4.0.0 foi publicada e que, em produção, `/api/operations`, `/api/dashboard/valuation`, `/api/dashboard/performance`, `/api/dashboard/equity-history`, histórico individual e comparação respondem HTTP 200. Também confirmou que o histórico agregado apresenta indisponibilidade por configuração e os históricos individual/comparativo permanecem indisponíveis enquanto não houver provedor aprovado. O erro 503 do histórico agregado foi corrigido e confirmado em produção.

Este aditivo registra evidência fornecida pelo proprietário em 29/10/2026; não afirma acesso independente aos painéis de hospedagem, ao SHA implantado ou à revisão do PostgreSQL. As limitações de fonte histórica e da Fase 4.4 continuam abertas.
