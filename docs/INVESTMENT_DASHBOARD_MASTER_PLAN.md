# Investment Dashboard — Master Plan v1 → v2

**Documento central de continuidade.** Atualizado em 31/10/2026. O plano consolida o que o repositório e o histórico Git sustentam, separando implementação local, relatos do proprietário sobre produção e propostas futuras. A v1.2 está implementada localmente conforme a seção F, mas este documento não autoriza migrações, acesso a dados de produção, publicação ou contratação de serviços. v1.1 e v2.0 permanecem propostas.

## Como interpretar este documento

- **Implementado no código:** confirmado por código e/ou testes do checkout indicado; não prova sozinho qual SHA está em produção.
- **Publicado segundo o proprietário/Git:** relato do proprietário ou tag encontrada no Git. Painéis Vercel, Render e Supabase não foram inspecionados nesta atualização.
- **Parcial / indisponível:** há interface ou contrato, mas falta fonte, configuração ou cobertura que permita apresentar dados reais.
- **Planejado / proposto:** não implementado e não aprovado para execução automática.
- Documentos de fases antigas preservam decisões e evidência da época. Quando seus cabeçalhos divergirem do estado atual, use este master plan para estado e roadmap atuais, e os documentos de fase para detalhes históricos.

## A. Visão geral do projeto

### Objetivo, público e proposta

O Investment Dashboard é um dashboard pessoal de investimentos brasileiros e um projeto de portfólio técnico. Ele organiza operações manuais de ações e renda fixa, fluxo de caixa/proventos registrados, composição com bases explicitadas, relatórios, cenários de simulação e metas. Seu valor demonstrável está em regras financeiras auditáveis, separação entre demonstração e carteira privada, autenticação/isolamento e tratamento explícito de cobertura incompleta.

O usuário principal é o proprietário da carteira. Recrutadores podem explorar a demonstração pública de dados fictícios. A futura expansão para um grupo pequeno por convite é uma proposta v2.0; não há intenção aprovada de transformar a aplicação em cadastro público irrestrito, produto comercial ou serviço com despesas obrigatórias.

### Arquitetura atual

```text
Navegador React/Vite
  ├─ Demonstração: DemoRepository → fixtures/localStorage fictícios; sem API privada
  └─ Área privada: Supabase Auth → JWT → PrivateRepository (HTTP)
                                     ↓
                             FastAPI / SQLAlchemy
                                     ↓
                  PostgreSQL / Supabase + owner_id + RLS
```

| Camada | Tecnologia / responsabilidade |
|---|---|
| Frontend | React 19, TypeScript, Vite, React Router, TanStack Query, Recharts, Tailwind, componentes Radix/shadcn e Decimal.js para apresentação/cálculos locais apropriados. |
| API | Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2, PyJWT/JWKS e psycopg. Rotas privadas validam token e consultam o banco sob contexto transacional de identidade. |
| Banco | PostgreSQL; migrations Alembic em `backend/migrations/versions`; valores contábeis `NUMERIC(20,8)`. Head no checkout: `009_financial_events`. |
| Identidade | Supabase Auth no modo privado; JWT assimétrico ES256/RS256, issuer/audience/expiração, allowlist de UUIDs e autorização por proprietário. O cliente não recebe chave de serviço do Supabase. |
| Hospedagem reportada | Frontend Vercel, API Render e banco/Auth Supabase. Esta documentação não lê secrets nem confirma variáveis, SHAs implantados, plano contratado ou configurações atuais dos painéis. |
| Desenvolvimento | Frontend local por Vite; API local FastAPI; PostgreSQL local via Compose ou PostgreSQL descartável em containers para integração. |

### Mapa do repositório

| Caminho | Conteúdo |
|---|---|
| `frontend/src/App.tsx`, `runtime.ts` | Composição da aplicação, rotas/páginas, seleção demo/privada e bloqueios de modo público. |
| `frontend/src/repositories/DemoRepository.ts` | Fixture e estado demonstrativo, isolados da API privada. |
| `frontend/src/repositories/PrivateRepository.ts` | Cliente autenticado e contratos dos endpoints. |
| `frontend/src/auth/` | Login/sessão Supabase, identidade da UI e transições de sessão. |
| `frontend/src/reports/`, `simulator/`, `goals/` | Relatórios/print, simulação independente e metas persistidas no navegador por identidade. |
| `backend/app/main.py` | Aplicação FastAPI, endpoints base, middlewares e tratamento de erros. |
| `backend/app/auth.py`, `access.py`, `database.py` | JWT, contexto de proprietário/RLS e configuração de banco/produção. |
| `backend/app/finance.py`, `valuation.py`, `performance.py`, `portfolio.py` | Custo médio, valuation atual, agregados de performance atual e composição/fluxos registrados. |
| `backend/app/fixed_income/`, `financial_events.py` | Ledger CDB, projeção/revisões/observações e eventos de caixa/proventos. |
| `backend/app/market_data/`, `bcb_rates/` | Cotações pontuais e integração de taxas BCB/SGS; serviços históricos permanecem separados e condicionais. |
| `backend/migrations/versions/` | Cadeia de migrations 001–009. |
| `backend/tests/`, `frontend/src/**/*.test.*` | Testes unitários, de API, auth, componentes e cálculo; integração PostgreSQL opt-in/runner descartável. |
| `scripts/`, `backend/scripts/` | Auditoria de publicação e utilitários de backup/restore; arquivos de backup devem permanecer fora do Git. |
| `docs/` | Decisões, registros de fases, segurança, deploy, backups, release e planejamento. Este arquivo centraliza estado e próximos passos. |

### Fluxo de dados e fronteiras

- A demonstração pública usa `DemoRepository` e dados fictícios, com configuração pública separada e bloqueio de rede privada (`VITE_PUBLIC_DEMO=true` força demo; produção é demo por padrão salvo configuração explícita `VITE_APP_MODE=private`). A intenção e os testes do código protegem a fronteira; a CSP e as chamadas efetivas dos domínios publicados ainda precisam ser conferidas no ambiente real para um atestado operacional atual.
- A área privada autentica no Supabase e envia bearer JWT à API. O backend verifica assinatura por JWKS e UUID permitido; `private_db` configura `app.user_id`/`app.auth_mode` na transação, e as consultas também filtram por `owner_id`. RLS/FORCE RLS e grants restritos são parte do modelo, não substitutos para autorização no backend.
- Operações antigas de modo local podem ter `owner_id IS NULL`; o login não as vincula automaticamente. Não atribuir registros sem reconciliação autorizada.
- Metas são armazenadas no `localStorage` com chave separada por identidade autenticada; não sincronizam entre perfis/dispositivos e não integram a demo. Simulador é local e não consulta a carteira.
- Valores de mercado/retornos históricos exigem fontes e bases compatíveis. A ausência é preservada como parcial/indisponível/null, sem preencher com cotações atuais ou dados inventados.

### Estado Git e versões

Na análise deste documento, o checkout estava em `main`, árvore limpa, com `HEAD` e referência local `origin/main` no commit `329ba67` (`fix(ci): resolve backup imports in PostgreSQL runner`). A tag local `v1.0.0` aponta para o commit `1d54a36`; o registro de verificação remota consultado anteriormente nesta sessão encontrou a tag remota `v1.0.1` no commit `329ba67`. A consulta remota não pôde ser repetida ao final por falha de DNS; status de GitHub Actions e URL da página GitHub Release não foram revalidados nesta tarefa documental. `v1.9.5` é um marco antigo de fase, não versão posterior à v1.0.0.

O proprietário informou que a v1.0.0 foi publicada e a correção v1.0.1 foi publicada. Isso, somado às tags/commits descritos, é evidência Git; não constitui confirmação independente da versão servida pelos painéis Vercel/Render.

## B. Histórico do desenvolvimento

As fases 2.0.x de renda fixa são nomenclatura técnica anterior à v2.0 multiusuário. A v2.0 descrita neste documento é expansão de produto por convite.

| Fase / período | Objetivo e entrega real | Decisões e problemas resolvidos | Testes/evidência e situação | Adiado, retirado ou limitado |
|---|---|---|---|---|
| 1.0 — fundação | Dashboard responsivo de ações, compras/vendas, custo médio com taxas, resultado realizado, histórico, gráfico de fluxo, API e PostgreSQL/Alembic. | Ledger cronológico; data + ID ordenam operações do dia; venda sem posição e exclusão que invalida vendas são rejeitadas. Fluxo de negociação não é curva patrimonial. | Regras financeiras, API, persistência/build e migrações; detalhes em `docs/architecture.md` e `docs/validation.md`. | Edição/paginação, caixa contábil, dividendos, CDB, preços externos e retorno temporal fora da base original. |
| 1.5 — segurança/publicação | Hardening inicial e preparação para publicar código sem segredos ou dados pessoais. | `.gitignore`, auditoria de publicação, erros genéricos, parâmetros ocultos; eliminou token compartilhado como modelo de produção e preparou separação segura. | Registro histórico em `docs/security-audit.md`; não confundir conclusão daquela auditoria com pentest ou auditoria atual de painéis. | MFA, rate limit distribuído, pentest e validação operacional contínua não são atestados. |
| 1.6–1.6.3 — demo e Supabase Auth | Demo interativa com carteira fictícia; login privado Supabase, sessão, navegação, troca de identidade e limpeza de cache; confirmação acessível. | `DemoRepository` offline/localStorage e `PrivateRepository` HTTP separados; demo não usa Auth/API; modo demo limpa estado privado. | Testes de auth, demo, sessão, modo, ausência de chamadas HTTP e regressão do seed. | Sem cadastro público; registros locais legados não são vinculados automaticamente. Configuração real de CSP/Network requer verificação do domínio. |
| 1.7–1.8.4 — publicação e navegação | Fronteiras Vercel pública/privada, configuração de deploy, sessão por aba e navegação responsiva. | Demo permanece padrão; build privado é explícito; sessão em `sessionStorage`, estado de consulta por identidade e headers/csp específicos. | Cobertura e documentos: `docs/deployment.md`, `docs/private-frontend-production.md`, `docs/phase-1.8.4-session-navigation.md`. | Ativação/configuração externa depende dos painéis e ambientes. |
| 1.9.1–1.9.5 — dados de mercado e clareza financeira | Cotações atuais, avaliação de posições abertas, páginas privadas de valuation e clareza de bases/cobertura. | Serviço de quote separado de histórico; valida ticker/moeda/data/frescura; dados insuficientes ficam parciais/indisponíveis. | Testes de provedor mockado, valuation, estados stale/partial/unavailable, auth e UI; históricos/fontes descritos em `docs/phase-1.9.*`. | Provedor gratuito/licenciado não é garantido; market data opcional; preço atual não é histórico nem patrimônio total. Tag `v1.9.5` é marco histórico. |
| 2.0.1 — modelagem de renda fixa | Contratos CDB, lotes e movimentos de aplicação/resgate. | Distinguir cadastro de produto, principal aplicado e movimentos efetivos; não inferir saldo bancário. Migration 003. | Testes de regras e PostgreSQL documentados em `docs/phase-2.0.1-fixed-income-model.md`. | Liquidez, condições contratuais e regras tributárias não podem ser inferidas de uma taxa isolada. |
| 2.0.2–2.0.4 — taxas, estimativas e interface | Fonte pública BCB/SGS para taxas; motor de estimativa CDB/CDI; interface privada. | Estimativas por contrato com convenção/calendário, fonte, status e premissas; estimativa não é resgate cotado. | Provedor com fixtures, cálculos, estados/contratos e UI em `docs/phase-2.0.2*` a `2.0.4*`. | IPCA/benchmark amplo e rendimento realizado fiscalmente conciliado não são fornecidos universalmente. |
| 2.0.5 — abertura e observações | Abertura consolidada para posições fixas que não têm histórico de lotes completo. | Snapshot manual append-only com data-base; não inventar aplicações/lotes retrospectivos. | `docs/phase-2.0.5-opening-balance.md`, `docs/validation.md`. | Observação manual fica separada do ledger de lotes e não entra em agregados sem base segura. |
| 2.0.6–2.0.7 — prontidão/segurança | Revisões de grants, RLS, papéis, precisão e compatibilidade de deploy. | Papel runtime não deve ser owner, superuser nem BYPASSRLS; migrations aplicadas por papel DDL; consultas filtradas por owner. | Homologação documentada nos registros 2.0.6/2.0.7. Evidência histórica não prova a role atual do Render. | Migração de produção requer confirmar schema/role de destino e autorização. |
| 2.0.8.1 — arquivamento de contrato vazio | Arquivar contrato vazio sem apagar trilha financeira. | Tombstone, FK/constraints, RLS/FORCE RLS, append-only e restrições de grant. Migration 005. | Testes de contrato, imutabilidade, grants e acesso. | Downgrades destrutivos não são caminho de recuperação. |
| 2.0.8.2–2.0.8.4 — revisões de aplicações e prontidão | Revisões auditáveis REPLACE/VOID, prévia, idempotência e revisão operacional de release. | Migrations 006–008, projeção efetiva, trilha append-only, funções invocadoras, grants mínimos e papel runtime separado. | Testes de cadeia, cronologia, retries, owner/RLS e UI; `docs/phase-2.0.8.*`. | Conexão efetiva/role da hospedagem e compatibilidade remota nunca se inferem só da migration local. |
| 3.0 — fluxos/composição | Histórico de fluxos de capital, composição e totais registrados. | Separação entre compras/aplicações, vendas/resgates, custo/principal, posições declaradas e valor de mercado. | Integração de agregadores em `backend/app/portfolio.py`; estado de cobertura explícito. | Fluxo líquido não é lucro, aporte externo, patrimônio ou retorno. |
| 3.0.3 — histórico de ações | Fundação para histórico de preços/avaliações por ativo. | Serviço e flag separados de quotes pontuais; sem reaproveitar cotação atual como preço passado. | Testes por fonte/provedor simulados e estados de indisponibilidade. | Feature flags false; provedor e licença não aprovados. |
| 3.0.4 — Histórico unificado | Timeline privada de operações, movimentos efetivos e eventos, filtros e gráficos de fluxo. | Respeita revisões REPLACE/VOID, owner/RLS e semântica financeira de cada movimento. | Review e testes em `docs/phase-3.0.4-final-review.md`. | Não é série de patrimônio ou retorno. |
| 4.0 — resumo financeiro atual | Compor fluxo registrado, capital aberto e valuation atual sem declarar retorno de carteira. | Endpoint `GET /api/dashboard/performance`; `Decimal`; cotação stale/parcial; total de mercado/retorno consolidado permanecem null quando incompletos. | `backend/tests/test_performance_api.py`, suite/build e revisão em `docs/phase-4.0-final-review.md`. | Não inclui série histórica consolidada. Resultado de ações é antes de impostos e sob os eventos registrados. |
| 4.1–4.2 — histórico individual/comparação | Interfaces e contratos privados para histórico de preço de ativo e índice comparativo entre posições. | Normalização em data comum, moeda/fonte/base compatíveis, sem interpolação; ativos precisam pertencer à carteira. | Cobertura de API/UI com provedores simulados; docs `phase-4.1` e `phase-4.2`. | Sem provedor configurado/aprovado; indisponível/disabled por padrão. O índice de preço não é retorno total. |
| 4.3A — desempenho atual | Painel de desempenho atual reaproveitando ledger, projeção CDB, composição e valuation. | Campos de cobertura e base; valor consolidado e retorno percentual continuam indisponíveis. | Backend/API e frontend verificados; sem migration. Ver `phase-4.3-financial-performance-plan.md`. | Rendimentos CDB continuam por contrato, não agregados como retorno de carteira. |
| 4.4 — desempenho temporal | Planejamento de TWR/MWR, snapshots e avaliações consistentes. | Requer valores datados em torno dos fluxos externos e composição comparável. | Documento condicional `phase-4.4-historical-performance-plan.md`; não implementado. | Bloqueado até dados, fonte/licença e método aprovados; nenhuma migration desse escopo executada. |
| 5.0A — navegação/identidade | Sidebar/drawer responsivos, identidade dinâmica e sessão privada. | Sem mudança em banco/API; preservar demo offline e limpar dados/caches ao trocar sessão. | Testes de UI/auth/teclado conforme registro da fase. | Refinos visuais/acessibilidade detalhada podem continuar como melhoria, não como feature nova. |
| 5.1 — eventos financeiros | Cadastro manual de aporte/retirada externa, dividendos, JCP e observações societárias; revisões e Histórico unificado. | Ledger append-only com idempotência, owner e RLS. Migration 009 cria `financial_events` e `financial_event_revisions`; sem backfill automático. | Testes financeiros e PostgreSQL descartável 001–009. O proprietário informou aplicação em produção; não houve leitura do banco nesta auditoria. | Eventos societários observacionais não alteram posição/custo; transferências não devem duplicar caixa. |
| 5.2A/5.2B — importação | Importação genérica CSV foi implementada e depois retirada por decisão do proprietário; preparação de adaptadores futuros foi suspensa. | Cadastro manual e Histórico permanecem; não apagar dados/tabelas, não reverter migration 009. | Registro: `docs/phase-5.2-csv-import.md`, `phase-5.2b-adapter-readiness.md`; os recursos CSV não devem ser descritos como disponíveis. | Reintrodução exige nova decisão; automação/importadores de corretora não fazem parte do produto atual. |
| 5.3 — relatórios | Relatórios privados de aportes, composição, movimentações, filtros e impressão para PDF via browser. | Reusa APIs existentes; totais movimentados não são rentabilidade. | Testes frontend, build e backend conforme `docs/validation.md`; sem migration/API nova. | PDF é saída de impressão do navegador, não geração/arquivo PDF server-side. |
| 5.4 — simulador | Cenários locais conservador/moderado/otimista, aportes, prazo, taxa e inflação opcional. | Hipóteses editáveis; taxa anual efetiva convertida em mensal; sem acesso à carteira nem persistência. | Testes de taxa zero/negativa, timing, inflação, valores inválidos e build. | Projeção não é previsão, recomendação ou garantia; não há vinculação automática a metas/portfolio. |
| 5.5A–C — metas | CRUD local, estados ativa/concluída/vencida/sem prazo, progresso manual ou por custo/principal investido, plano de aportes por cenário. | Isolamento pela chave de identidade no navegador; base investida não é patrimônio de mercado; reusa endpoint performance e matemática do simulador. | `phase-5.5-goals.md`: cobertura de validação, isolamento, partial/unavailable e extremos; sem backend/migration. | Não sincroniza dispositivos; localStorage pode ser perdido; sem valor de mercado consolidado. |
| 5.6 — histórica/benchmarks | Estudo para evolução patrimonial e rentabilidade real histórica. | Planejamento já existente; depende de séries completas e metodologia/benchmark compatíveis. | Não implementada; ver 4.4 e roadmap anterior. | Não usar cotação de hoje como passado; fica proposta condicional da v1.1. |
| v1.0.0 / v1.0.1 | v1.0.0 agrupa funções principais; v1.0.1 corrige import no runner CI PostgreSQL para funcionar fora do CWD do backend. | Manter tag `v1.0.0` imutável; correção está no commit posterior `329ba67`, com tag remota `v1.0.1` observada. | Evidência de release conforme Git e relato do proprietário; status atual do Actions/painéis não verificado nesta atualização. | Releases da v1.0.x não comprovam publicação da implementação local v1.2 nem conclusão das propostas 4.4, 5.6, v1.1 ou v2.0. |

Detalhes e logs históricos estão em [validação](validation.md), [segurança](security-audit.md), [documentação v5](phase-5-master-plan.md), [handoff v5](v5-development-handoff.md) e documentos individuais listados em cada linha. Esses artefatos podem ter cabeçalhos de status antigos; este resumo não os reescreve como evidência atual.

## C. Estado funcional atual da v1

| Área | Estado | Evidência e limite que deve aparecer ao usuário |
|---|---|---|
| Demonstração | **Implementado no código; validação operacional parcial** | Seed fictício, persistência demo local e repository sem API privada. CSP/Network efetivos do domínio público devem ser rechecados se for necessário atestado atual. |
| Login/logout privado | **Implementado; produção parcialmente validada pelo proprietário** | Supabase Auth, JWT/JWKS, allowlist, sessão por aba, estados de erro; não há signup público. Testes confirmam regras locais, mas não provam config atual do painel. |
| Ações, compras e vendas | **Implementado** | Ledger por custo médio cronológico, taxas, validação de venda e resultado realizado. Não inclui por si só saldo em caixa ou retorno total. |
| Cotações/valuation atual | **Parcial / dependente de configuração e fonte** | Serviço pontual valida preço/moeda/timestamp/stale/cobertura; total agregado fica nulo se falta componente. Fonte e termos devem ser revalidados antes de ativar. |
| Renda fixa/CDB | **Implementado para ledger/estimativas contratadas, com limites** | Produtos, lotes, aplicação/resgate, saldo/principal, observações, revisões, taxas BCB/SGS e estimativas por contrato. Estimativa não é saldo de resgate garantido ou rendimento efetivamente recebido. |
| Fluxos/eventos | **Implementado** | Eventos manuais privados de caixa, dividendos/JCP e revisão append-only. Migration 009 é o head no código; estado atual do Supabase não foi consultado nesta tarefa. |
| Histórico | **Implementado para movimentos registrados** | Timeline unificada com filtros e estados; não é avaliação patrimonial histórica. Históricos de preço podem ficar indisponíveis. |
| Dashboard, composição, gráficos | **Implementado com cobertura/bases definidas** | Capital investido/custo/principal e valuation atual não se confundem; fluxos não são retorno. |
| Relatórios/PDF | **Implementado** | Relatórios privados reaproveitam endpoints; PDF via impressão nativa. Não há arquivo/relatório server-side persistido. |
| Simulador | **Implementado** | Cálculo local com cenários editáveis, inflação opcional e premissas; não consulta saldo da carteira. |
| Metas | **Implementado com persistência local** | Progresso manual ou custo/principal investido; metas não sincronizam e não aparecem na demo; uma limpeza do armazenamento do navegador pode removê-las. |
| Patrimônio e rentabilidade totais históricas | **Não implementado / deliberadamente indisponível** | Falta série completa e comparável de valuation/fluxos. TWR/XIRR e benchmarks não devem ser inferidos. |
| Backup | **Um backup manual único feito, integridade reportada verificada; restore real pendente** | `docs/manual-backup.md`. Restore sintético em PostgreSQL descartável passou; arquivo real não foi restaurado. Não contém Auth, Storage ou config externa. |

### Segurança e operações

Confirmado no código: CORS por origem exata, erros SQL genéricos sem parâmetros no log, headers `no-store`, validação JWT e allowlist, consultas por proprietário, RLS contextual, papel runtime verificado em produção para não ser superuser/BYPASSRLS/owner de `operations`, TLS PostgreSQL `verify-full` requerido quando `ENVIRONMENT=production`, frontend demo/privado separado. O checker de role da aplicação examina uma tabela crítica, mas não substitui a revisão completa de role/grants no banco ativo.

Não está comprovado neste documento: teste de duas contas reais publicadas, leitura do schema/`alembic_version` no Supabase, network/CSP atual da demo, rota/commit ativo do Render, configuração de Auth e variáveis dos painéis, restore do backup real, pentest, MFA, limite de requisição distribuído, alerta/incident response e recuperação de Supabase Auth/Storage. Para detalhes e classificação da aceitação da v1.0, ver `docs/v1.0-release-readiness.md` e `docs/security-audit.md`.

### Testes e versões

Registros existentes mostram a v1.0 com frontend 217 testes em 28 arquivos, build Vite/TypeScript aprovado, npm audit sem vulnerabilidade conhecida na árvore consultada e backend 382 aprovados/1 ignorado em Python 3.12 descartável; PostgreSQL 17 descartável percorreu 001–009 e testou backup/restore sintético, RLS/grants e dois proprietários. Após o hotfix do runner `329ba67`, o registro da correção indica suite backend 383 aprovados/1 ignorado; a integração CI tinha sido a falha que motivou o hotfix. Estes são resultados de execuções registradas, não reexecutados nesta documentação. O Actions atual deve ser consultado no GitHub antes de uma futura alteração.

## D. Pendências e itens deixados pelo caminho

| Item | Origem / estado real | Razão ou dependência conhecida | Sugestão |
|---|---|---|---|
| Importação CSV genérica | Planejada e implementada numa fase; **retirada** da UI/cliente/API. | Proprietário decidiu simplificar; cadastro manual e Histórico foram preservados. Nenhum dado/tabela/migration deve ser removido por causa disso. | Não trazer de volta sem decisão nova. |
| Adaptadores de corretora/banco e importação ampliada | 5.2B preparada documentalmente; **suspensa**. | Requer formatos, estabilidade, privacidade, idempotência e conciliação; dependência externa/maintenance. | Opcional futura, só com caso de uso. |
| Contas/corretoras múltiplas e transferências | Ideias do planejamento antigo; **parcial/sem ledger de caixa de contas**. | Requer semântica de transferências e eventos, conciliação e prevenção de duplicidade. | Não exigir para a v1 atual; avaliar após teste de uso. |
| Dividendos/JCP/eventos societários | Eventos em dinheiro registrados manualmente; **parcial** para histórico completo e ações societárias que mudam quantidade/custo. | A 009 registra eventos e revisão, mas evento observacional societário não altera posições. | Definir casos e proveniência antes de ampliar accounting. |
| Histórico individual de preços | Contratos/API/UI existem; **indisponível por padrão**. | Provedor não configurado/aprovado; licença, ajuste de preços, corporate actions e cobertura. | Só habilitar com fonte validada, termos e cache. |
| Comparação de ações | UI e contrato existem; **indisponível por fonte**. | Requer séries compatíveis e datas comuns; índice de preços não equivale a retorno total. | Reavaliar junto de 1.1. |
| Série de patrimônio consolidado | Planejada 4.4/5.6; **não implementada**. | Faltam snapshots de todas as classes, fluxos externos históricos, CDBs comparáveis e fonte histórica. | Principal frente financeira de v1.1, condicionada a coleta futura. |
| TWR | Planejado/bloqueado. | Requer valuation imediatamente antes/depois dos fluxos externos ou encadeamento justificado, datas e cobertura. | Não publicar antes dos testes e dados necessários. |
| MWR / XIRR | Candidato, não implementado. | Requer todos fluxos externos assinados/datados e valuation terminal comparável; precisa de solução numérica e tratamento de múltiplas/ausentes raízes. | Pode ser mais adequado a retorno do investidor, mas só com entradas completas. |
| Benchmarks | Planejados, não integrados como comparação de retorno. | Fonte, licença, calendário, moeda, base ajustada e alinhamento de datas. Taxa BCB/SGS usada em renda fixa não é benchmark da carteira por si só. | Depois de estabilizar a série própria e escolher fontes. |
| Persistência/sincronização de metas | LocalStorage por identidade, **não sincronizado**. | Foi escolha para evitar API/migration; dados dependem de dispositivo/perfil do browser. | Candidato opcional 1.1 se necessidade real superar custo e risco de migration. |
| Backup operacional | Um único backup manual existente; **não há rotina automática ou restore real comprovado**. | Estratégia intencional de portfólio; Auth/Storage/configuração ficam de fora. | Antes de alterar esquema ou abrir v2, decidir backup/restore adequado e ensaiar em clone. |
| Multiusuário por convite | Documentado, **não implementado**. | Requer onboarding controlado, tabelas/tokens/auditoria possíveis, RLS e processo operacional. | v2.0, após ameaça, privacidade e recuperação. |
| Agente de IA | **Íris implementada e validada localmente; ainda não publicada**. | Groq Free opcional, conhecimento estático, sem dados da carteira; inspeção visual autenticada e configuração de produção pendentes. | v1.2 conforme seção F; não entregar ferramentas de escrita. |
| MFA, rate limit, observabilidade/alerta, operação de incidentes | Parcial/pendente de validação ou capacidade na hospedagem atual. | Requer confirmar planos atuais, implantação, custo e requisitos de uso externo. | Reavaliar antes de convidar terceiros, não presumir como bloqueio de portfólio pessoal sem evidência de risco imediato. |
| Precisão de metadado da API | `backend/app/main.py` mantém `FastAPI(version="0.1.5")`, enquanto pacote/release é v1.x. | Divergência observável de metadado OpenAPI; não altera cálculo/endpoints por si só. | P1 de higiene: corrigir em commit de código separado quando houver solicitação de correção, não nesta tarefa documental. |

Outras ideias antigas de expansão, agregação financeira, serviços premium, Open Finance e scraping permanecem opcionais ou fora da decisão de custo obrigatório zero. Não constituem “funcionalidade já feita”.

## E. Planejamento v1.1 — evolução financeira histórica

### Necessidade e escopo

A Fase 5.6 já aparece nos planos 4.4/5.x e é relevante para uma versão financeira posterior, mas não é necessária para descrever honestamente a v1.0.1. A primeira entrega 1.1 deve ser uma auditoria dos dados disponíveis e da coleta futura, não um gráfico que sugira que existam valores históricos completos. Uma série iniciada após a implementação pode mostrar evolução prospectiva; não pode reconstruir passado ausente.

O repositório possui: ledger de ações (data/quantidade/preço/taxas), eventos financeiros manuais desde a adoção da 009, ledger de lotes/movimentos CDB com revisões e observações CDB datadas; cotação pontual atual pode ser opcional; históricos de preço por ativo e comparação têm contrato, mas fonte não configurada. Não se encontrou uma série histórica consolidada, datada e comparável de todas as posições/caixa. A API atual define explicitamente valor consolidado e rentabilidade total como indisponíveis/null. Observações de posição não são automaticamente valuations da carteira.

| Subfase proposta | Conteúdo | Pré-requisitos e aceite | Complexidade |
|---|---|---|---|
| 1.1.1 — auditoria de dados/proveniência | Inventariar fontes reais, datas, eventos, cobertura por classe, lacunas e qualidade; especificar glossário capital investido vs patrimônio vs retorno. | Fixtures e consulta somente leitura; nenhum dado retrospectivo inventado; plano de coleta futuro aprovado. | M |
| 1.1.2 — snapshots prospectivos | Definir observação consistente de posições por data, valores, método, fonte, moeda, cotação/data, cobertura e trilha de correção; avaliar schema/migration append-only. | Aprovação financeira/segurança do modelo; migration testada 001–head em PostgreSQL descartável, owner/RLS/grants, backup e plano operacional antes da produção. Sem backfill sintético. | L |
| 1.1.3 — séries por classe/ativo | Gráficos por período para snapshots confirmados, ações e renda fixa, separando valor conhecido, estimativa e ausente. | Completude declarada; preço atual nunca retrodatado; comparabilidade de valor e moedas testada. | L |
| 1.1.4 — fluxos e valorização | Visualizar aportes/saques externos, operações e variação de valuation em séries separadas. | Definir transferências/reinvestimento e evento/cashflow sem dupla contagem; reconcile com ledgers. | M/L |
| 1.1.5 — métricas de retorno | Avaliar TWR e MWR/XIRR conforme dados; expor fórmula, intervalo, fluxo, cobertura e falha quando não há solução. | Testes de fronteiras, datas irregulares, dias sem cotação, fluxo inicial/final, arredondamento, nulls e prova manual. Sem retorno “aproximado” rotulado como real. | L |
| 1.1.6 — benchmarks | Comparar somente séries com fonte permitida, mesma moeda, calendário/base e período alinhados. | Termos/licença/requisições/cobertura revistos; falha vira indisponível; sem scraping. | M/L |
| 1.1.7 — acabamento e metas | Avaliar sincronização opcional das metas, filtros de relatórios e acessibilidade dos gráficos. | Caso de uso real, autenticação/owner e migration se houver persistência; metas locais mantidas se não aprovada. | S/M |

### Metodologias e cautelas

- **TWR (time-weighted return):** encadeia retornos entre fluxos externos, reduzindo o efeito do timing/tamanho de aportes do investidor. Exige valuations consistentes em cada fronteira de fluxo e política clara para fluxos intraperíodo. Sem observações adequadas, resultado indisponível.
- **MWR/XIRR:** encontra taxa anualizada que iguala valor presente de fluxos datados e valuation terminal. Exige sinais/datas completos, todos os fluxos externos relevantes e uma avaliação final comparável. Pode não haver raiz única; algoritmo deve informar falha/múltiplas soluções e precisão. Não tratar compras/vendas/aplicações internas como aporte externo.
- **Valorização de preço:** retorno de preço por si só não inclui dividendos, impostos, taxas nem ações corporativas; preço bruto/ajustado não pode ser misturado sem reconciliação de quantidades e eventos.
- **Renda fixa:** cálculo por contrato e data, taxa, calendário, indexador, impostos, liquidez e resgates; CDB não pode ser tratado como valuation de mercado uniforme. Observação manual exige rótulo e data-base.
- **Benchmark:** comparação é outra série, não prova desempenho; precisa base de preço, moeda, calendário e período comuns. Datas sem dados permanecem lacunas, não interpolação silenciosa.

### Testes e gate de entrada

Antes de qualquer UI de performance: amostras de dados fictícios com cobertura completa e parcial; fluxos em fronteiras e intraperíodo; transferência interna; proventos/reinvestimento; CDB aberto/fechado; ajuste corporativo e preço bruto/ajustado; ausência/staleness; idempotência; consistência entre tela/API/ledger; Decimal e precisão; proprietário/RLS/cache; migrations/restore descartável. O gate para dados reais requer fonte, licença, método, cobertura, frequência de snapshots, custo e comportamento de indisponibilidade explicitados.

## F. v1.2 — assistente de educação financeira Íris

**Status: implementada e validada localmente; ainda não publicada.** A Íris usa Groq Free opcional com `qwen/qwen3.8-27b`; não há faturamento, fallback pago, recomendações de investimento, memória persistente nem acesso a dados da carteira.

### Escopo e arquitetura implementada

- O chat React só é montado na área privada quando há sessão Supabase autenticada. A demonstração pública permanece independente e não chama o endpoint da assistente.
- O frontend envia a pergunta ao `POST /api/assistant/chat` no FastAPI usando o fluxo autenticado existente. A autenticação e os limites são aplicados no backend.
- A chave `GROQ_API_KEY` é lida somente pelo backend. O modelo recebe a pergunta e o arquivo estático `assistant_knowledge.md`; não recebe tokens de autenticação nem dados financeiros da carteira.
- A conversa fica apenas no estado React da sessão. Não há persistência, ferramenta, RAG ou operação financeira. Se a IA ou a cota estiver indisponível, o restante do dashboard continua utilizável.
- A Íris explica conceitos básicos e o funcionamento documentado do dashboard; não recomenda ativos, não prevê retornos nem afirma conhecer a carteira.

### Validação e pendências para publicação

- Chamadas reais locais ao endpoint via Groq/Qwen retornaram HTTP 200; a última resposta sobre o uso do dashboard terminou com `finish_reason=stop` e estava completa.
- As suítes automatizadas e o build de produção foram aprovados nas validações locais reportadas. A interface autenticada ainda não foi inspecionada visualmente em navegador; a cobertura visual disponível é por componentes/testes mockados.
- Antes de publicar, configurar manualmente `GROQ_API_KEY` no Render, as variáveis Supabase/CORS no backend e as variáveis públicas de build do projeto Vercel privado. Aguardar aprovação do proprietário; esta validação não executou commit, push ou deploy.

## G. Planejamento v2.0 — onboarding controlado por convite

**Status:** proposta já registrada em `docs/multiuser-expansion-plan.md`; objetivo central é um grupo pequeno, selecionado, com convite/aprovação. Não é a Fase técnica 2.0.x de renda fixa. Cadastro aberto e monetização não estão aprovados.

### Fluxo sugerido

1. Administrador autorizado cria convite para um endereço/caso aprovado; segredo aleatório com entropia adequada é mostrado uma vez e armazenado apenas como hash; prazo curto, uso único, revogação e contador/limite de tentativas.
2. Endpoint backend/serviço administrativo protegido verifica hash, validade, estado, limite e vínculo esperado; não confiar no frontend nem em `user_metadata` editável. Se Supabase Admin API for necessário, sua credencial fica apenas em serviço backend isolado, nunca em Vite/browser/logs.
3. Provisionar ou habilitar identidade Supabase Auth individual com signup público geral desligado; confirmar e-mail/senha/reset e vínculo estável do UUID. Corrida/replay de convite deve ser atômica.
4. Ao autenticar, carteira começa vazia e recebe apenas linhas do próprio UUID; nunca copiar a carteira do proprietário por padrão. O administrador gerencia metadados de acesso e convites, sem ler conteúdo financeiro.
5. Revogar convite impede aceite; suspender/remover acesso exige política clara sobre registros já persistidos, exportação/exclusão, retenção e auditoria. Revogar sessão/JWT emitido pode não surtir efeito imediato; definir mitigação para conta bloqueada.

### Arquitetura, segurança e banco

- Manter JWT/JWKS, `owner_id` não fornecido pelo browser, filtros explícitos no servidor, `RLS`/`FORCE ROW LEVEL SECURITY`, papel runtime mínimo e `no-store`. Validar duas ou mais identidades em todas as rotas, relatórios, export, cache, prompts de IA e consultas de ativos.
- Desenhar threat model antes de migration: possível tabela `invitations` (token hash, destinatário opcional, created_by, expires_at, consumed_at, revoked_at, status/attempts) e log de auditoria enxuto; minimizar PII, impedir enumeração e replay, indexar unique constraints e transações atômicas. Avaliar Auth hook/Edge Function vs endpoint backend sem expor service role.
- Separar função de administração do acesso financeiro. Admin não recebe SELECT às carteiras. Sem usar grant amplo ou service role no cliente para contornar RLS.
- Definir rate limit por conta/IP, quotas de IA e fontes de preço, limites de usuários, alerta/custo, logs sem payload e processo de incidente. Acesso de convidado requer política de privacidade/retensão/atendimento e revisão LGPD aplicável.
- Migração da allowlist atual deve ser gradual: primeiro provisionar identidade/convite, testar carteira vazia, observar, só depois revisar a forma de allowlist. Não autoatribuir dados locais com owner nulo; o proprietário continua conta distinta.
- Manter demo pública offline. Recrutador não recebe acesso à conta/carteira pessoal; se houver conta demo privada, usar fixture isolada, explicitamente fictícia e sem cópia do proprietário.

### Entregas propostas e aceite

| Entrega | Escopo/depêndencias | Critérios objetivos | Complexidade |
|---|---|---|---|
| 2.0.1 — modelo de acesso/threat model | Limite de convidados, papéis, retenção/remoção, Auth/Supabase, convite, custos e plano de recuperação. | Diagrama de fluxo, abuso/replay/expiração, revisão de privacy, plano de migração e restore aprovados antes de DDL. | M |
| 2.0.2 — invites backend/admin | Tabela/serviço se necessário, criação/revogação, hash, expiração, consumo atômico, auditoria mínima. | Testes token válido/expirado/revogado/replay, concorrência e tentativas; RLS/grants e segredo fora do browser/logs. | L |
| 2.0.3 — onboarding Supabase | Tela/aceite, Auth provisionado com signup público bloqueado, sessão e recuperação de senha. | Convite só ativa identidade esperada; abuso/enumeração negados; contingência de e-mail/expiração clara. | M/L |
| 2.0.4 — isolamento multiusuário | Ensaiar APIs, endpoints, relatórios, exportações, cache, metas e funcionalidades futuras de IA com A/B/C. | Nenhum dado cruzado; RLS + filtros backend; runtime sem bypass; segurança negativa em recursos alheios. | L |
| 2.0.5 — operação limitada | Rate/quotas, monitoramento agregado, backup/restore, resposta a incidente, suporte e remoção/retention. | Teste de restore descartável; sem custo obrigatório/alerta de limite; procedimento de revogação e portabilidade praticado. | M/L |
| 2.0.6 — piloto convidado | Grupo minúsculo após aprovação operacional; documentação e canais de suporte. | Consentimento e privacidade claros; nenhuma falha de acesso cruzado; limites/abuso observados; go/no-go manual. | M |

**Go/no-go v2:** signup irrestrito permanece negado; convites one-time/expiráveis/revogáveis; carteira própria vazia; admin sem leitura financeira; demo isolada; acesso cruzado coberto por teste e RLS; backup/restore e exclusão/exportação definidos; custos/quota previsíveis; nenhuma migration de produção sem backup e autorização. IA não deve receber finanças privadas de convidados sem política e consentimento próprios.

## Roadmap consolidado

Complexidade é relativa (S pequena, M média, L grande) e não equivale a calendário ou orçamento aprovado. “Origem” distingue decisão existente de proposta nova desta sessão.

| Versão | Funcionalidade | Estado | Prioridade | Dependências | Complexidade | Critério de conclusão | Origem |
|---|---|---|---|---|---|---|---|
| v1.0.x | Ledger ações/CDB, eventos, Histórico, dashboard, relatórios, simulador, metas, auth/demo | Implementado; produção reportada pelo proprietário; ressalvas operacionais descritas | Manter/estabilizar | Hospedagem, Supabase, cotações opcionais | — | Build/testes de commit, estados financeiros honestos e acesso privado seguro | Código, testes, tags e docs |
| v1.0.x | Backup manual único/recuperação real | Parcial (arquivo íntegro reportado; restore real pendente) | P1 antes de mudança de schema ou convidados | Frase/cópia protegida, PostgreSQL descartável e escopo documentado | M | Restore do artefato em banco descartável, validar objetos/linhas/RLS sem tocar produção | `manual-backup.md` |
| v1.0.x | Verificação das origens demo/privada, release/deploy SHAs, contas reais | Necessita validação | P1 antes de compartilhar com terceiros | Acesso autorizado aos painéis e sessão de teste | S/M | Provar CSP/Network demo, commit implantado e login autorizado; nunca registrar finanças | Checklist v1.0 |
| v1.0.x | Metadado FastAPI `0.1.5` vs release 1.x | Parcial (higiene) | P2 | Alteração de código em tarefa futura | S | OpenAPI version coerente com estratégia de versionamento; teste | Inspeção do código |
| v1.1.1 | Auditoria de dados, fonte e proveniência histórica | Planejado, próximo passo recomendado | P0 da 1.1 | Inventário com dados fictícios/metadados, licença | M | Mapa por ativo/classe/período/cobertura e decisão de coleta | 4.4/5.6 e proposta refinada |
| v1.1.2 | Snapshots prospectivos versionados | Planejado | P1 | Semântica, migration append-only, backup e RLS | L | Snapshots auditáveis sem backfill inventado; migration e integração descartável aprovadas | 4.4/5.6 |
| v1.1.3 | Gráficos de patrimônio por período e fluxos vs valorização | Planejado condicional | P1 | Série suficiente para componentes escolhidos | L | Datas, base, origem, coverage/lacunas visíveis; total indisponível se incompleto | 4.4/5.6 |
| v1.1.4 | TWR/MWR/XIRR | Planejado condicional | P1/P2 | Fluxos externos, boundaries/terminal values, cálculos reconciliáveis | L | Fórmulas reproduzíveis e resultados recusados quando insuficientes | 4.4/5.6 |
| v1.1.5 | Benchmark | Planejado opcional | P2 | Fonte/licença, moeda/calendário/base compatíveis | M/L | Sem interpolação nem comparar séries incompatíveis | Roadmap 5.6 |
| v1.1.x | Sincronizar metas e acabamento de relatórios | Proposto, opcional | P2 | Caso de uso, persistência/privacidade | M | Funciona sob owner/RLS e não mistura demo nem identidade | Nova sugestão; confirmar escopo |
| v1.2.1–.4 | Chat privado Íris, conhecimento estático, limites, segurança e validação | Implementado e validado localmente; publicação pendente | P0 antes da publicação | Inspeção visual autenticada e configuração manual Render/Vercel | M | 393 testes backend aprovados (1 skip), 221 testes frontend, build aprovado e chamadas reais completas; demo sem chat e sem dados da carteira | Seção F e Etapa 5 |
| v1.2.5 | Ferramentas, memória ou contexto financeiro | Fora do escopo da v1.2; adiados e sujeitos a aprovação separada | P2 | Consentimento, avaliação de ameaça, isolamento e retenção | L | Nenhum dado pessoal ou capacidade adicional sem decisão separada | Opcional, não implementado |
| v2.0.1 | Modelo restrito de convites/abuso/privacidade | Planejado em documento anterior | P0 da expansão | Threat model, custo, suporte, política de dados | M | Plano de convite, remoção, custos, migration/restore aprovado | `multiuser-expansion-plan.md` |
| v2.0.2–.3 | Criação/revogação/aceite/Provisionamento Supabase | Planejado | P1 | Auth/admin backend, signup geral fechado, tokens hashed | L | Convite único, expira, revoga, não enumera e não vaza | Documento anterior |
| v2.0.4 | Isolamento A/B/N no sistema todo (incl. IA) | Planejado | P0 antes de convidados | owner/RLS/backend/cache/export/AI quotas | L | A, B e admin não atravessam fronteiras; testes reais e descartáveis | Documento anterior |
| v2.0.5–.6 | Operação, piloto convidado e saída segura | Planejado | P1 | Restore, monitoramento, incidentes, privacidade/limites | M/L | Go/no-go objetivo, pequeno piloto, revogação/removal/exclusão testados | Documento anterior |
| Futuro | Open Finance, scraping, APIs pagas/CSV/adaptadores, monetização/cadastro público | Opcional, suspenso ou descartado do escopo atual | P2/sem aprovação | Decisão específica e análise de custo/termos/segurança | L | Aprovação expressa; custo obrigatório zero permanece princípio atual | Docs custo/5.2/multiuser |

## H. Guia para futuras sessões

### Estado para retomar

- Checkout desta preparação: `main` em `c9ee2e0`, com alterações locais da v1.2 e documentação, sem arquivos staged nem commit desta etapa; migrations locais 001→009 com um head `009_financial_events`.
- Release v1.0.0 foi publicada segundo o proprietário; tag local existente aponta para `1d54a36`. Tag remota v1.0.1 no commit `329ba67` foi observada em consulta anterior; a reconsulta falhou por DNS. Não criar/mover tags ou release sem pedido.
- Última correção técnica: import do runner PostgreSQL resolvido usando `Path(__file__).resolve().parents[1]` em `backend/tests/run_postgres.py`, eliminando dependência do CWD. A alteração está em `329ba67`; ela não altera a lógica financeira, schema ou DB.
- Migration 009 existe e é head no código. Estado corrente do banco de produção não foi consultado; documentação do proprietário relata que foi aplicada. Não rodar migration ou query de produção sem autorização específica.
- Backup único cifrado fora do repo; documento não inclui frase/hash/DSN. Restore real ainda não foi ensaiado; somente dados fictícios e banco descartável foram usados nos testes sintéticos registrados.
- Próxima tarefa da v1.2: concluir a inspeção visual autenticada em navegador e configurar manualmente as variáveis de produção no Render e no projeto Vercel privado; depois aguardar aprovação do proprietário antes da publicação. v1.1 e v2.0 permanecem propostas futuras.

### Comandos locais

Use o checkout existente; não crie uma cópia do projeto sem necessidade.

```powershell
# Frontend
Set-Location C:\Users\IAN\ProjetosVSCode\investment-dashboard\frontend
npm ci
npm test
npm run build

# Backend (usar o virtualenv local funcional, sem alterar Python global)
Set-Location C:\Users\IAN\ProjetosVSCode\investment-dashboard\backend
.\.venv\Scripts\python.exe -m pytest -q

# Migrações somente em PostgreSQL local descartável, DATABASE_URL apontando para esse banco
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic upgrade head

# Integração PostgreSQL; exige Docker configurado e roda apenas containers descartáveis
.\.venv\Scripts\python.exe tests\run_postgres.py
```

Os requisitos exatos estão em `backend/requirements.lock.txt`; comandos de inicialização e variáveis exemplificadas estão no README e nos documentos de deploy. Nunca use URL/credenciais de produção em teste, não coloque segredo em saída e confira variáveis antes de uma migração.

### Decisões que devem ser preservadas

1. Demo pública sempre fictícia/offline e isolada do HTTP privado/Auth.
2. Autenticação obrigatória na área privada; owner vem do JWT validado no servidor, nunca do payload do cliente.
3. Manter `owner_id`, filtros SQL, RLS/FORCE RLS, papel runtime mínimo, TLS verificado e `Cache-Control: no-store`.
4. Financeiro usa `Decimal` no backend; não contar taxas, fluxos externos, compras, vendas, resgates, proventos ou transferências duas vezes.
5. Distinguir custo aberto, principal, capital investido, valor de mercado, posição observada, fluxo e rentabilidade. Nunca preencher dado ausente.
6. Não retroagir cotações atuais para montar série histórica; não executar TWR/XIRR sem dados requeridos.
7. Metas e simulador atuais são locais; metas não sincronizam; taxas são cenários hipotéticos.
8. A migração/alteração do banco de produção requer autorização e plano seguro. Não editar `alembic_version` manualmente.
9. Nenhuma chave de LLM no browser, nenhuma ferramenta de escrita do agente e nenhum envio de dados financeiros ao modelo sem decisão específica de privacidade.
10. Expansão v2 é restrita por convite; não abrir signup público nem dar acesso de administrador a carteiras.

### Referências essenciais

- [README e setup](../README.md)
- [Roadmap](roadmap.md)
- [CHANGELOG](../CHANGELOG.md)
- [Arquitetura e regras financeiras](architecture.md)
- [Separação demo/privado](demo-and-private.md)
- [Auth Supabase](supabase-auth.md)
- [Auditoria de segurança](security-audit.md)
- [Validação acumulada](validation.md)
- [Critérios de release pessoal](personal-dashboard-release-criteria.md)
- [Aceitação v1.0](v1.0-release-readiness.md)
- [Backup único e limites](manual-backup.md)
- [Planejamento 4.4 histórico](phase-4.4-historical-performance-plan.md)
- [Plano 5.x](phase-5-master-plan.md) e [metas 5.5](phase-5.5-goals.md)
- [Expansão multiusuário por convite](multiuser-expansion-plan.md)

---

**Resumo executivo:** a v1.0.1 foi publicada segundo relato/tag Git; o código da v1.2 adiciona a Íris, assistente educacional privada sem dados da carteira, e está validado localmente, mas ainda não foi publicado. Restam inspeção visual autenticada em navegador e configuração manual de produção, seguidas de aprovação do proprietário. A série histórica continua ausente por decisão de integridade financeira; v1.1 e convites multiusuário v2.0 permanecem propostas futuras.
