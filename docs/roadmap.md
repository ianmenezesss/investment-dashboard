# Roadmap mestre — Investment Dashboard

Atualizado em 30/10/2026. Este documento é a fonte principal de verdade do planejamento. Ele registra o estado observado no repositório e decisões expressas pelo proprietário; não autoriza compra, ativação de provedor, migration persistente, push, merge, release ou deploy.

## Estados usados

- **Concluído:** código e critérios da fase foram entregues. A disponibilidade externa ainda pode ter uma dependência declarada.
- **Em desenvolvimento:** implementação autorizada e em curso.
- **Planejado:** proposta registrada, ainda sem autorização de implementação.
- **Bloqueado:** depende de dados, licença, infraestrutura ou decisão ainda ausente.
- **Opcional:** pode ser omitido sem impedir a finalidade do produto pessoal.
- **Descontinuado:** decisão explícita de não seguir com uma ideia. Nenhuma proposta histórica é descontinuada por este documento.

“Concluído tecnicamente” não significa “ativado em produção”. O CHANGELOG registra somente software efetivamente entregue; este roadmap pode registrar propostas e bloqueios.

## Decisões de produto registradas

1. O produto deve funcionar **sem despesa obrigatória**, tanto para o proprietário como para a futura expansão restrita. Priorizar software aberto, planos gratuitos enquanto disponíveis e registros manuais. Serviço que exija pagamento nunca será requisito funcional.
2. Planos gratuitos têm limites e podem mudar, suspender ou encerrar. Configurações devem ser reavaliadas antes de releases. Falha ou limite deve degradar para indisponibilidade explícita ou fluxo manual, sem ativar cobrança automática.
3. Não há intenção atual de cobrança, assinatura, planos comerciais ou monetização.
4. Não integrar APIs pagas, Open Finance pago, scraping ou fornecedor sem validação de cobertura, licença, privacidade e custo. Ideias condicionais permanecem documentadas como alternativas futuras.
5. A expansão chamada provisoriamente **Investment Dashboard 2.0** será somente por convite ou aprovação explícita; não haverá cadastro público irrestrito.
6. Um administrador não recebe acesso automático às carteiras de convidados. Recrutadores devem usar a demonstração offline ou uma conta isolada com dados próprios, nunca a carteira real do proprietário.
7. Demo pública, carteira privada do proprietário e carteiras de convidados são fronteiras separadas.
8. Nenhum dado financeiro ou preço ausente será inventado. Estimativas, observações, fluxo e rentabilidade devem ter rótulos próprios.

## Estado das versões

| Área | Estado | Registro |
|---|---|---|
| v3.0.4 | **Concluído tecnicamente; publicação reportada** | A release está documentada e o commit f021ad8 foi registrado. A documentação anterior ressalta que SHA implantado e revisão remota do banco requerem confirmação nos respectivos painéis. |
| Histórico de preços 3.0.3 | **Bloqueado** | Código preservado; EQUITY_HISTORY_ENABLED permanece desligada por padrão. Falta fonte gratuita, permitida e adequada. |
| v4.1 — Histórico individual de ações | **Concluído tecnicamente; dados bloqueados** | Endpoint e UI usam contrato independente. INDIVIDUAL_EQUITY_HISTORY_ENABLED é false por padrão e não há provedor aprovado. |
| v4.2 — Comparação de ativos | **Concluído tecnicamente; dados bloqueados** | Endpoint e UI foram implementados com normalização e sem interpolação; dependem da mesma fonte histórica da 4.1. |
| v4.3A — Resumo financeiro atual | **Concluído e publicado** | Endpoint privado de resumo, composição/fluxos existentes, resultado de ações com cobertura e precisão Decimal corrigida. Publicação e operação confirmadas pelo proprietário; este registro não representa leitura independente dos painéis hospedados. |
| Release v4.0.0 | **Publicada; verificações operacionais reportadas como concluídas** | Proprietário confirmou `/api/operations`, `/api/dashboard/valuation`, `/api/dashboard/performance`, `/api/dashboard/equity-history`, histórico individual e comparação respondendo HTTP 200 em produção. Históricos sem provedor seguem indisponíveis de forma explícita. |
| v4.4 — Rentabilidade temporal completa | **Bloqueado / condicional** | Depende de fluxo externo classificado, eventos pertinentes e avaliações históricas comparáveis. |
| 5.0A — Navegação responsiva e identidade dinâmica | **Concluído localmente** | Menu mobile acessível, sidebar desktop recolhível, identidade visual derivada da sessão e testes; sem alteração de backend/migration. Revisão visual final do proprietário permanece antes de publicação. |
| v5.0.0 | **Em desenvolvimento local** | 5.0A, 5.1, 5.3, 5.4 e 5.5A–C implementadas localmente; branch `feat/v5.5-goals` ainda não integrada/publicada. Importação 5.2A retirada e 5.2B suspensa. 5.6 condicional. |
| Investment Dashboard 2.0 | **Planejado, após estabilidade pessoal** | Expansão por convite, com isolamento rigoroso e operação sustentável sem despesa obrigatória. |

Referências de implementação e evidência: [revisão da 3.0.4](phase-3.0.4-final-review.md), [fase 4.1](phase-4.1-individual-equity-history.md) e [fase 4.2](phase-4.2-asset-comparison.md).

## Histórico do planejamento e funcionalidades preservadas

A arquitetura original agrupava em fases numeradas: fundação de ações; contas/corretoras, edição e proventos; renda fixa; medição com snapshots, caixa externo, benchmarks e TWR/XIRR; planejamento com simulador, metas e relatórios; e uso remoto seguro. A execução evoluiu em versões 1.x, 2.x, 3.x e 4.x diferentes da numeração inicial. Os documentos históricos não são reescritos para sugerir que a numeração atual existia desde o começo.

- **Entregue em fases anteriores:** ledger de ações com custo médio; demo offline; Supabase Auth privado, autorização por proprietário e RLS; renda fixa CDB com principal, revisões REPLACE/VOID, observações manuais e estimativa CDI sob premissas; cotações pontuais; histórico unificado de operações; fluxos e composição por bases declaradas.
- **Ainda não entregue ou incompleto:** contas/corretoras, edição transacional geral de operações, saldo de caixa conciliado, suporte IPCA no motor de rendimento, cotações manuais com fonte e timestamp como base de valuation e desempenho histórico completo.
- **Retirado ou suspenso:** importação CSV e adaptadores bancários estão fora do escopo atual. Integração bancária e conciliação automatizada não devem ser iniciadas sem nova decisão.
- **Fase de medição original:** snapshots patrimoniais, fluxos externos separados de negociações e benchmarks oficiais. Continua dependente dos itens da 5.1 e da 4.4.
- **Fase de uso remoto original:** parte da base técnica já existe, mas não substitui o planejamento de onboarding, operação, recuperação, privacidade e controles para convidados.

Veja [arquitetura original](architecture.md), [demo e fronteira privada](demo-and-private.md), [configuração de Auth](supabase-auth.md), [auditoria de segurança](security-audit.md) e [plano histórico de preços](phase-3.0-technical-plan.md).

## v4.0.0 — análise financeira

### 4.1 — Histórico individual de ações

**Estado:** concluído tecnicamente, sem fonte. Endpoint privado, períodos, contrato tipado, estados de disponibilidade e UI em /acoes. Fonte desligada por flag; não reutilizar cotação pontual como série.

### 4.2 — Comparação de ativos

**Estado:** concluído tecnicamente, sem fonte. Seleção de 2–4 ativos, base 100 na data válida comum, moeda/fonte/base compatíveis, sem preenchimento de lacunas. O índice é variação de preço, não retorno total.

### 4.3A — Resumo financeiro atual

**Estado:** concluído tecnicamente e publicado conforme confirmação do proprietário. O endpoint privado `GET /api/dashboard/performance` compõe custo/resultado de ações, fluxos registrados, principal CDB efetivo, composição e cobertura das cotações atuais. `PortfolioInsights` mostra os dados pelas bases e estados documentados no [plano 4.3](phase-4.3-financial-performance-plan.md).

- Usa `Decimal`, o ledger de ações existente e `effective_movements()` para revisões REPLACE/VOID; posição declarada sem lotes fica separada.
- Resultado realizado é após taxas registradas e antes de impostos. Resultado não realizado/combinado requer cobertura de cotação completa; cotações stale são avisadas.
- Vendas e resgates não são chamados de lucro/rendimento. Fluxo líquido não é aporte externo, patrimônio ou rentabilidade. Estimativas CDB continuam individuais por contrato.
- Sem persistência nova ou migration.
- Validação local: backend 363 aprovados/1 ignorado; PostgreSQL descartável 1 aprovado; frontend 162 aprovados; build concluído.

### 4.4 — Rentabilidade temporal completa

**Estado:** bloqueado e condicional. Ver [plano 4.4](phase-4.4-historical-performance-plan.md).

Depende de registro suficiente de fluxos externos, proventos e eventos incluídos no escopo; avaliação de posições em datas adequadas; e fonte de preço gratuita com licença compatível e cobertura demonstrada. Nenhum preço atual pode preencher uma data passada. A implementação pode ficar desligada ou indisponível; uma fonte paga não será requisito.

### Release v4.0.0

**Estado:** publicada. O proprietário confirmou as verificações operacionais descritas na linha “Release v4.0.0” acima. Nesta atualização documental não houve acesso independente aos painéis de Render, Vercel ou Supabase; não se registra SHA implantado nem revisão remota do banco sem evidência desses painéis. A falta de fonte histórica não bloqueia o escopo pessoal porque 4.1/4.2 permanecem explicitamente indisponíveis e não inventam preços; as cotações atuais são independentes. A 4.4 continua bloqueada.

Critérios e processo: [critérios de release pessoal](personal-dashboard-release-criteria.md). Este registro é retrospectivo e não autoriza novo deploy.

## v5.0.0 — planejamento, dados e relatórios

A **5.0A — Navegação responsiva e identidade dinâmica**, a 5.1, os relatórios 5.3, o simulador local 5.4 e as metas locais 5.5A–C estão implementados. A importação 5.2A foi retirada e 5.2B está suspensa. O proprietário informa que a migration 009 foi aplicada ao Supabase de produção e que as tabelas de eventos existem; esta atualização não acessou nem modificou esse banco. A 5.4 continua independente da carteira. As metas ficam no navegador privado, sem sincronização nem persistência em servidor. As etapas seguintes continuam sujeitas aos critérios, dependências e decisões descritos no [plano mestre v5](phase-5-master-plan.md).

| Fase proposta | Conteúdo | Prioridade / dependências |
|---|---|---|
| 5.0A — Navegação e identidade | Sidebar responsiva/acessível; nome e avatar derivados da sessão autenticada; fronteira demo/privado mantida. | Concluída em branch específica; sem migration e sem custo obrigatório. |
| 5.1 — Eventos e fluxo de caixa | Aportes/retiradas externas, dividendos/JCP e observações societárias com origem declarada; revisão append-only. | Implementada. O proprietário informa migration 009 aplicada à produção; sem verificação independente nesta alteração. Detalhes em [plano 5.1](phase-5.1-cash-flow-and-income-events.md). |
| 5.2 — Importação CSV | Entrada CSV de eventos financeiros. | Retirada por decisão do proprietário; cadastro manual e Histórico preservados. Sem remoção de dados/tabelas e sem downgrade da 009. |
| 5.2B — Adaptadores bancários | Parsers para layouts de instituições. | Suspensa com a retirada da importação; requer nova decisão antes de retomar. |
| 5.3 — Relatórios e exportação | Aportes por mês/ano, composição por categoria/ativo, movimentos e eventos filtráveis e impressão para PDF. | Implementada no frontend privado com endpoints existentes; sem migration. PDF usa impressão nativa do navegador. |
| 5.4 — Simulador | Aporte inicial/periódico, prazo, três taxas editáveis, convenção de aporte e inflação opcional. | Implementado localmente e sem persistência; não acessa carteira nem APIs externas. |
| 5.5 — Metas | CRUD local, progresso manual confirmado ou custo/principal aberto com cobertura identificada, aporte mensal e projeções hipotéticas. | Implementada localmente em `feat/v5.5-goals`; sem API/migration; não sincroniza entre dispositivos. Base investida não é patrimônio de mercado. Revisar commits e testes antes de integrar. |
| 5.6 — Histórico de carteira e benchmarks | TWR/MWR e comparação com benchmarks somente após entradas e avaliações suficientes. | Condicional, possivelmente com persistência nova; fornecedor continua sujeito à regra gratuita. |

**Opcionais preservados:** conexões bancárias/Open Finance, integração automática com corretores, conciliação e fontes comerciais. São propostas condicionais, exigem nova avaliação e não podem ser requisitos do produto.

## Conclusão do dashboard pessoal e transição

A conclusão do dashboard pessoal é um marco de qualidade do produto, não sinônimo da release v4 ou v5. Critérios mínimos estão em [critérios do dashboard pessoal](personal-dashboard-release-criteria.md). Sem provedor histórico aprovado, pode-se concluir e estabilizar o conjunto de funcionalidades que possui dados suficientes, mantendo explicitamente a 3.0.3/4.1/4.2 indisponíveis.

A expansão para convidados só deve começar após backup/restauração ensaiados, isolamento verificado e release pessoal estável. Os critérios estão em [Investment Dashboard 2.0](multiuser-expansion-plan.md).

## Dependências principais

| Para habilitar | É necessário primeiro |
|---|---|
| Retorno total da carteira | Fluxos externos separados de operações; proventos/eventos no escopo; valor da carteira em datas de referência. |
| TWR | Avaliações imediatamente antes/depois dos fluxos externos relevantes, séries coerentes e subperíodos calculáveis. |
| MWR/XIRR | Fluxos datados completos, sinalizados corretamente e valor terminal confiável. |
| Gráfico de patrimônio histórico | Posições reconstruíveis e preços/valores observados por data para cada classe incluída. |
| Comparação/histórico de ações real | Fonte diária gratuita, licença, cobertura B3 e base de preços validadas. |
| Simulador | Premissas editáveis, fórmulas testadas e apresentação como cenário, não previsão. |
| Multiusuário | Conta e convite, autorização, isolamento, suporte, privacidade, limites, backup e observabilidade. |

Para a implementação local 5.5, a base foi delimitada: progresso manual confirmado ou custo/principal aberto calculado pelo endpoint privado existente; não é patrimônio de mercado nem inclui fluxos externos. As metas não são sincronizadas entre dispositivos.

## Estimativas e prioridades

Premissa: uma pessoa desenvolvedora, dias de trabalho focado, dependências locais disponíveis e escopo limitado. Não são datas ou compromissos. Esperas por fonte, licença, políticas de hospedagem ou decisão do proprietário não estão incluídas.

| Marco | Prioridade | Esforço indicativo | Incerteza/bloqueio |
|---|---:|---:|---|
| 4.3A | Alta para v4 | 5–8 dias | Corrigir precisão somente se testes mostrarem perda material. |
| Verificação e release v4 | Alta | 2–4 dias | Confirmações manuais dos ambientes e rollback. |
| 5.1 | Implementada | — | Proprietário informa migration 009 aplicada à produção; não verificada nesta alteração. Sem backfill. |
| 5.2 | Retirada | — | Importação CSV removida; adaptadores suspensos. |
| 5.3 | Média | 5–10 dias | Formatos e filtros. |
| 5.4 | Concluída localmente | — | Simulador matemático sem persistência e independente da carteira. |
| 5.5 | Concluída localmente | — | CRUD e planejamento sem migration; revisão e integração continuam manuais. |
| 5.6 | Condicional | 10–20+ dias de desenvolvimento | Fonte permitida e série histórica; aprovação externa sem prazo. |
| Estabilização pessoal | Alta antes de expansão | 5–10 dias distribuídos | Ensaio de recuperação e operação. |
| Preparação e MVP 2.0 | Baixa até aprovação própria | 20–40+ dias | Custos, privacidade, onboarding e suporte não definidos. |

## Processo de documentação e release

- Estados oficiais: Concluído, Em desenvolvimento, Planejado, Bloqueado, Opcional e Descontinuado.
- Roadmap é a fonte de status; documento de fase define contrato e aceite; CHANGELOG registra somente mudanças já entregues.
- Antes de release: testes backend/frontend, PostgreSQL descartável para RLS/migrations relevantes, build, links/documentação, revisão de diff e confirmação de backup/restore.
- Commits devem ser pequenos e por fase; mudanças de código e documentação do plano podem ser separadas.
- Release, migration de produção, merge, push e deploy permanecem ações manuais autorizadas.
- Um plano de rollback deve preservar schema e dados, com procedimento de aplicação e reversão verificado antes da janela de release.

## Registro de atualização

Esta consolidação registra a conclusão técnica local da 4.3A; documentos históricos das fases 1–3 permanecem preservados. 4.4 e as fases v5 seguem planejadas/bloqueadas conforme suas dependências, não como funcionalidade implementada nem autorização automática.
