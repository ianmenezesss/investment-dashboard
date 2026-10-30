# Roadmap mestre — Investment Dashboard

Atualizado em 29/10/2026. Este documento é a fonte principal de verdade do planejamento. Ele registra o estado observado no repositório e decisões expressas pelo proprietário; não autoriza implementação, compra, ativação de provedor, migration, commit, push, merge, release ou deploy.

## Estados usados

- **Concluído:** código e critérios da fase foram entregues. A disponibilidade externa ainda pode ter uma dependência declarada.
- **Em desenvolvimento:** implementação autorizada e em curso.
- **Planejado:** proposta registrada, ainda sem autorização de implementação.
- **Bloqueado:** depende de dados, licença, infraestrutura ou decisão ainda ausente.
- **Opcional:** pode ser omitido sem impedir a finalidade do produto pessoal.
- **Descontinuado:** decisão explícita de não seguir com uma ideia. Nenhuma proposta histórica é descontinuada por este documento.

“Concluído tecnicamente” não significa “ativado em produção”. O CHANGELOG registra somente software efetivamente entregue; este roadmap pode registrar propostas e bloqueios.

## Decisões de produto registradas

1. O produto deve funcionar **sem despesa obrigatória**, tanto para o proprietário como para a futura expansão restrita. Priorizar software aberto, planos gratuitos enquanto disponíveis, registros manuais e CSV. Serviço que exija pagamento nunca será requisito funcional.
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
| v5.0.0 | **Em desenvolvimento local** | 5.0A concluída; 5.1 implementada e validada localmente. 5.2–5.6 permanecem planejadas ou condicionais; Simulador e Metas continuam placeholders. |
| Investment Dashboard 2.0 | **Planejado, após estabilidade pessoal** | Expansão por convite, com isolamento rigoroso e operação sustentável sem despesa obrigatória. |

Referências de implementação e evidência: [revisão da 3.0.4](phase-3.0.4-final-review.md), [fase 4.1](phase-4.1-individual-equity-history.md) e [fase 4.2](phase-4.2-asset-comparison.md).

## Histórico do planejamento e funcionalidades preservadas

A arquitetura original agrupava em fases numeradas: fundação de ações; contas/corretoras, edição e proventos; renda fixa; medição com snapshots, caixa externo, benchmarks e TWR/XIRR; planejamento com simulador, metas e relatórios; e uso remoto seguro. A execução evoluiu em versões 1.x, 2.x, 3.x e 4.x diferentes da numeração inicial. Os documentos históricos não são reescritos para sugerir que a numeração atual existia desde o começo.

- **Entregue em fases anteriores:** ledger de ações com custo médio; demo offline; Supabase Auth privado, autorização por proprietário e RLS; renda fixa CDB com principal, revisões REPLACE/VOID, observações manuais e estimativa CDI sob premissas; cotações pontuais; histórico unificado de operações; fluxos e composição por bases declaradas.
- **Ainda não entregue ou incompleto:** contas/corretoras, edição transacional geral de operações, dividendos/JCP, eventos societários no livro financeiro, depósitos e saques externos, saldo de caixa, suporte IPCA no motor de rendimento, cotações manuais com fonte e timestamp como base de valuation, importação revisável, relatórios completos, metas e simulador.
- **Pós-lançamento anteriormente proposto e preservado:** importação CSV, integração bancária, conciliação automatizada e reconstrução somente a partir de documentos existentes. Integração bancária permanece opcional e não pode exigir serviço pago.
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

A **5.0A — Navegação responsiva e identidade dinâmica** está concluída, conforme [plano 5.0A](phase-5.0A-responsive-navigation-user-identity.md). A 5.1 está implementada e validada localmente; a implementação da 5.2 aguarda a definição de um formato CSV autorizado e anonimizado. A Fase 5.0 do app mantém placeholders de **Simulador** e **Metas**. As etapas seguintes continuam condicionais aos critérios, dependências e decisões descritos no [plano mestre v5](phase-5-master-plan.md); não representam funcionalidades já implementadas.

| Fase proposta | Conteúdo | Prioridade / dependências |
|---|---|---|
| 5.0A — Navegação e identidade | Sidebar responsiva/acessível; nome e avatar derivados da sessão autenticada; fronteira demo/privado mantida. | Concluída em branch específica; sem migration e sem custo obrigatório. |
| 5.1 — Eventos e fluxo de caixa | Aportes/retiradas externas, dividendos/JCP e observações societárias com origem declarada; revisão append-only. | Implementada e validada localmente; migration 009 ainda não aplicada a banco persistente. Detalhes em [plano 5.1](phase-5.1-cash-flow-and-income-events.md). |
| 5.2 — Importação CSV revisável | Prévia, validação, detecção de duplicatas, mapeamento e confirmação explícita. | Aguardando escolha da instituição e fixture CSV anonimizada; não iniciar interpretação de formato por suposição. |
| 5.3 — Relatórios e exportação | Relatório de operações/posições e exportações consistentes com o filtro e o proprietário. | Exportação JSON atual não equivale a relatórios completos. |
| 5.4 — Simulador | Aportes hipotéticos, taxas, prazo e reinvestimento como cenários editáveis. | Escopo original e placeholder; não requer histórico real se as hipóteses forem explícitas. |
| 5.5 — Metas | Patrimônio-alvo, prazo, progresso e projeção com base claramente identificada. | Escopo original e placeholder; depende da definição da base do progresso. |
| 5.6 — Histórico de carteira e benchmarks | TWR/MWR e comparação com benchmarks somente após entradas e avaliações suficientes. | Condicional, possivelmente com persistência nova; fornecedor continua sujeito à regra gratuita. |

**Opcionais preservados:** conexões bancárias/Open Finance, integração automática com corretores, suporte a outros formatos de importação, conciliação e fontes comerciais. São propostas condicionais; devem ter substituto manual/CSV gratuito e não podem ser requisitos do produto.

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
| Metas | Definição de “patrimônio atual” e método de progresso; sem isso, explicar indisponibilidade. |
| Importação segura | Formato mapeado, prévia, idempotência/dedupe e preservação de eventos originais. |
| Multiusuário | Conta e convite, autorização, isolamento, suporte, privacidade, limites, backup e observabilidade. |

## Estimativas e prioridades

Premissa: uma pessoa desenvolvedora, dias de trabalho focado, dependências locais disponíveis e escopo limitado. Não são datas ou compromissos. Esperas por fonte, licença, políticas de hospedagem ou decisão do proprietário não estão incluídas.

| Marco | Prioridade | Esforço indicativo | Incerteza/bloqueio |
|---|---:|---:|---|
| 4.3A | Alta para v4 | 5–8 dias | Corrigir precisão somente se testes mostrarem perda material. |
| Verificação e release v4 | Alta | 2–4 dias | Confirmações manuais dos ambientes e rollback. |
| 5.1 | Concluída localmente | — | Migration 009 testada somente em PostgreSQL descartável; sem backfill. |
| Primeiro formato 5.2 | Aguardando insumo | 7–14 dias após definição | Requer instituição escolhida e fixture CSV anonimizada. |
| 5.3 | Média | 5–10 dias | Formatos e filtros. |
| 5.4 e 5.5 | Média | 8–15 dias somadas | Persistir simulações/metas exigiria schema; apenas cenário temporário talvez não. |
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
