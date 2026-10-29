# Handoff de desenvolvimento — próxima etapa v5.0.0

**Preparado em:** 29/10/2026. Este documento transfere contexto técnico; não inicia nem autoriza implementação da versão 5.

## Estado de partida

- Linha de desenvolvimento `feat/v4-investment-analytics`; produção v3.0.4 continua preservada na `main` até publicação manual.
- 4.1 e 4.2 têm contratos privados, interfaces e testes, mas dados históricos reais seguem indisponíveis: não há provedor aprovado e as flags ficam false.
- 4.3A entrega `GET /api/dashboard/performance` e resumo atual em `PortfolioInsights`, usando o ledger/serviços financeiros existentes. Sem migration.
- 4.4 está corretamente bloqueada, sem série de patrimônio inventada, enquanto faltam fluxos externos, eventos/proventos e avaliações históricas compatíveis.
- `/simulador` e `/metas` continuam placeholders com texto da Fase 5. Nenhuma função v5 foi implementada.
- Estado de validação local e ressalvas operacionais estão em [revisão final da v4](phase-4.0-final-review.md).

## Arquitetura e decisões reutilizáveis

- Backend: FastAPI, SQLAlchemy, PostgreSQL, Alembic; valores monetários trafegam/persistem como `Decimal`/strings decimais. Testes de PostgreSQL devem usar `backend/tests/run_postgres.py`, que prepara containers descartáveis sem volumes persistentes.
- Frontend: React, TypeScript, Vite, TanStack Query, Supabase Auth. `PrivateRepository` é HTTP autenticado; demo usa `DemoRepository` offline. Páginas pesadas são carregadas sob demanda.
- Operações de ações usam `summarize()` com custo médio cronológico e taxas registradas; ordem diária usa data + ID. Cálculos de custo têm contexto local Decimal de 64 dígitos para proteger produtos `NUMERIC(20,8)`.
- Movimentos efetivos de CDB vêm de `effective_movements()` e preservam `REPLACE`/`VOID`. Não reconstruir um segundo ledger nem tratar resgate de principal como rendimento.
- A avaliação por cotação pontual usa `QuoteService`, valida preço/moeda/frescura e informa cobertura. Histórico de preço é serviço separado e não deve afetar cotação atual.
- `owner_id`, autenticação, RLS, papel runtime restrito, `no-store` e isolamento demo/privado são requisitos de arquitetura, não melhorias opcionais.
- Não há dividendos/JCP, depósitos/saques externos, saldo de caixa nem snapshots históricos completos. Não calcular TWR/XIRR ou retorno total sem esses dados.

## Prioridades propostas

1. **5.1 — Eventos e fluxo de caixa:** iniciar por definição semântica e evidência para depósitos/saques externos, dividendos/JCP, reinvestimento e eventos societários. Separar transferências internas; preservar trilha, idempotência, proprietário e correções auditáveis. Esta é dependência para medir retorno total.
2. **5.2 — CSV revisável:** um formato por vez, processamento local/privado, preview e deduplicação, cancelamento sem escrita e confirmação explícita.
3. **5.3 — Relatórios:** filtros e exportação coerentes com o proprietário, sem confundir export JSON de operações existente com relatórios completos.
4. **5.4 — Simulador:** pode ser protótipo local sem persistência se premissas forem editáveis e cada saída for rotulada cenário hipotético, nunca previsão. O placeholder atual deve continuar honesto até aprovação do escopo.
5. **5.5 — Metas:** determinar primeiro a base “patrimônio atual”; permitir entrada manual confirmada ou indisponibilidade quando essa base não puder ser consolidada.
6. **5.6 — Rentabilidade histórica/benchmarks:** condicional a 4.4, eventos 5.1, snapshots/valores datados e fonte permitida. Não ativar por antecipação.

O plano aprovado em [`phase-5-master-plan.md`](phase-5-master-plan.md) continua como fonte da sequência e escopo. O [`multiuser-expansion-plan.md`](multiuser-expansion-plan.md) é uma proposta separada e posterior à estabilidade pessoal; não o substituir por este handoff.

## Migrations e estratégia de testes

- 5.1 provavelmente exige novos tipos/tabelas e migration; primeiro desenhar compatibilidade com ledger existente, chaves de idempotência, datas econômicas/registro, `owner_id`, RLS e política de revisão.
- Não converter operações antigas em depósitos/proventos sem evidência. Não atribuir `owner_id` retroativamente sem processo autorizado e backup.
- Testar fórmulas com `Decimal`, datas e casos extremos antes da interface; cobrir vendas parciais/reinvestimento, taxas, eventos corrigidos/anulados e ausência de fonte.
- Para cada endpoint novo, testar auth, acesso cruzado, RLS, `no-store`, erros e dados vazios. Exercitar migrations/restore apenas com runner PostgreSQL descartável.
- Frontend: loading/error/empty/unavailable/partial, acessibilidade teclado, responsividade, demo offline e ausência de valores inventados. Rodar suíte completa e build.
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
