# Handoff de desenvolvimento — Investment Dashboard v5.0.0

**Atualizado em:** 30/10/2026. Branch de trabalho `feat/v5.5-goals`, criada da `main` e `origin/main` sincronizadas em `d80b69c`. Fases 5.0A, 5.1, 5.3A–C, 5.4 e 5.5A–C implementadas localmente. 5.2A (importação CSV) retirada por decisão do proprietário e 5.2B suspensa. A implementação 5.5 está em três commits separados, sem merge, push ou deploy. A migration 009 e o banco de produção não foram alterados nem acessados nesta etapa; o proprietário informa que 009 foi aplicada.

## Estado de partida

- v4.0.0 está publicada conforme confirmação do proprietário. As verificações operacionais confirmadas incluem HTTP 200 nos endpoints de operações, valuation, performance e históricos; históricos sem fonte aprovada continuam indisponíveis como projetado. Não foi feita verificação independente dos painéis de produção nesta atualização.
- Fase 5.0A implementada localmente na branch `feat/v5-0a-responsive-navigation-identity`: navegação mobile/desktop acessível e identidade de apresentação derivada da sessão. Sem mudanças no backend, schema, migrations, permissões ou dependências.
- 4.1 e 4.2 têm contratos privados, interfaces e testes, mas dados históricos reais seguem indisponíveis: não há provedor aprovado e as flags ficam false.
- 4.3A entrega `GET /api/dashboard/performance` e resumo atual em `PortfolioInsights`, usando o ledger/serviços financeiros existentes. Sem migration.
- 4.4 está corretamente bloqueada, sem série de patrimônio inventada, enquanto faltam fluxos externos, eventos/proventos e avaliações históricas compatíveis.
- `/simulador` continua independente da carteira. `/metas` oferece CRUD e planejamento local, segregado pela identidade autenticada e sem sincronização entre dispositivos. Detalhes em [Fase 5.5](phase-5.5-goals.md).
- Fase 5.1: eventos manuais privados de aporte/retirada externa, dividendos/JCP e observação societária; histórico unificado e totais de caixa/proventos; `REPLACE`/`VOID` append-only e auditáveis. Especificação: [Fase 5.1](phase-5.1-cash-flow-and-income-events.md).
- Migration `009_financial_events.py` cria as tabelas append-only de eventos. O proprietário informa que foi aplicada ao Supabase de produção e que as tabelas existem; a execução desta etapa não acessou nem alterou o banco. Não reverter 009 nem apagar tabelas/dados.
- Importação CSV 5.2A removida da UI, do cliente e da API; o endpoint em lote não está disponível. O registro histórico está em [documentação 5.2](phase-5.2-csv-import.md). Adaptadores 5.2B suspensos.
- 5.3A–C oferece aportes agrupados por mês/ano, distribuição por classe/ativo, tabela de movimentos/eventos com filtros e impressão do relatório filtrado para PDF via navegador. Reusa endpoints autenticados existentes, sem API ou migration nova.
- 5.4 oferece cenários conservador/moderado/otimista com taxa editável, aporte inicial/mensal, prazo, timing início/fim do mês, inflação opcional e valores nominais/reais. Fórmula efetiva mensal, Decimal, sem dependência externa e sem persistência.
- Validação desta etapa: frontend completo **217 testes/28 arquivos aprovados**; build e detalhes em [validação](validation.md). A suíte backend não iniciou: o `.venv` aponta para um executável Python da Microsoft Store inacessível neste ambiente. O backend não foi modificado; a integração PostgreSQL e produção não foram acessadas.
- Demonstração pública continua sem acesso ao relatório privado; o simulador é independente e funciona sem serviços externos.
- Nesta etapa: distribuição lado a lado dos dois gráficos de composição, com empilhamento em telas estreitas; sem alteração de dados ou cálculos.
- Estado de validação local e ressalvas operacionais estão em [revisão final da v4](phase-4.0-final-review.md).

## Arquitetura e decisões reutilizáveis

- Backend: FastAPI, SQLAlchemy, PostgreSQL, Alembic; valores monetários trafegam/persistem como `Decimal`/strings decimais. Testes de PostgreSQL devem usar `backend/tests/run_postgres.py`, que prepara containers descartáveis sem volumes persistentes.
- Frontend: React, TypeScript, Vite, TanStack Query, Supabase Auth. `PrivateRepository` é HTTP autenticado; demo usa `DemoRepository` offline. Páginas pesadas são carregadas sob demanda.
- Operações de ações usam `summarize()` com custo médio cronológico e taxas registradas; ordem diária usa data + ID. Cálculos de custo têm contexto local Decimal de 64 dígitos para proteger produtos `NUMERIC(20,8)`.
- Movimentos efetivos de CDB vêm de `effective_movements()` e preservam `REPLACE`/`VOID`. Não reconstruir um segundo ledger nem tratar resgate de principal como rendimento.
- A avaliação por cotação pontual usa `QuoteService`, valida preço/moeda/frescura e informa cobertura. Histórico de preço é serviço separado e não deve afetar cotação atual.
- `owner_id`, autenticação, RLS, papel runtime restrito, `no-store` e isolamento demo/privado são requisitos de arquitetura, não melhorias opcionais.
- A 5.1 registra dividendos/JCP e depósitos/saques externos; ainda não há saldo de caixa conciliado nem snapshots históricos completos. Não calcular TWR/XIRR ou retorno total sem dados e avaliações adequados.

## Prioridades propostas

1. **5.1 — Eventos e fluxo de caixa:** concluída localmente; critérios, contrato, limitações e testes estão em [documentação da Fase 5.1](phase-5.1-cash-flow-and-income-events.md).
2. **5.2 — Importação:** retirada; adaptadores suspensos até nova decisão.
3. **5.3 — Relatórios:** implementada. Manter rótulos de cobertura, bases e período/filtros explícitos; PDF usa impressão nativa.
4. **5.4 — Simulador:** implementada localmente; não conectar à carteira nem promover premissas a previsão. Testes cobrem casos extremos e cálculo real/nominal.
5. **5.5 — Metas:** implementada localmente em três entregas. Manual confirmado ou custo/principal de posições abertas com cobertura; capital investido não é patrimônio a mercado. Sem API nova ou migration. Revisar a branch antes de integrar.
6. **5.6 — Desempenho histórico/benchmarks:** próximo planejamento, ainda condicional a 4.4, eventos 5.1, avaliações datadas comparáveis, cobertura suficiente e fonte permitida. Não iniciar implementação automaticamente.

O plano aprovado em [`phase-5-master-plan.md`](phase-5-master-plan.md) continua como fonte da sequência e escopo. O [`multiuser-expansion-plan.md`](multiuser-expansion-plan.md) é uma proposta separada e posterior à estabilidade pessoal; não o substituir por este handoff.

## Migrations e estratégia de testes

- 5.1 criou migration 009 com tabelas append-only, chaves idempotentes, datas observadas, `owner_id`, RLS/FORCE RLS, revisões e grants mínimos. O proprietário informa que foi aplicada ao Supabase de produção; não houve verificação independente nesta etapa. Não existe backfill; não reexecutar nem reverter sem conferir o estado do banco.
- Não converter operações antigas em depósitos/proventos sem evidência. Não atribuir `owner_id` retroativamente sem processo autorizado e backup.
- Testar fórmulas com `Decimal`, datas e casos extremos antes da interface; cobrir vendas parciais/reinvestimento, taxas, eventos corrigidos/anulados e ausência de fonte.
- Para cada endpoint novo, testar auth, acesso cruzado, RLS, `no-store`, erros e dados vazios. Exercitar migrations/restore apenas com runner PostgreSQL descartável.
- Frontend: loading/error/empty/unavailable/partial, acessibilidade teclado, responsividade, demo offline e ausência de valores inventados. A 5.5 cobre manual/partial/unavailable e mantém taxas como hipóteses editáveis.
- Sem dados reais de investimentos nos testes. Fixtures devem ser fictícias e permanecer claramente isoladas.

## Decisões que exigem revisão do proprietário

- Sem despesa obrigatória; sem API paga como dependência, Open Finance pago ou scraping.
- Sem cadastro público irrestrito; eventual expansão multiusuário somente por convite/aprovação.
- Administrador não recebe acesso automático às carteiras. Convidados recebem somente carteira própria.
- Demonstração pública permanece offline, sem API privada, Auth ou banco de investimentos.
- Revisar regras fiscais, rendimentos, transferências, retenção, privacidade e qualquer migration antes de incorporá-los.
- Publicações, configurações remotas, migrations em produção e mudanças de permissões permanecem manuais e sujeitas a autorização explícita.

## Documentos de referência

- [Roadmap mestre](roadmap.md)
- [Fase 4.3A](phase-4.3-financial-performance-plan.md)
- [Fase 4.4 e dependências](phase-4.4-historical-performance-plan.md)
- [Plano mestre v5](phase-5-master-plan.md)
- [Expansão multiusuário](multiuser-expansion-plan.md)
- [Arquitetura](architecture.md)
