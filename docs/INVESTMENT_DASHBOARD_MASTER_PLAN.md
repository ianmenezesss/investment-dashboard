# Investment Dashboard — Master Plan v1 → v2

**Documento central de continuidade.** Atualizado em 31/10/2026. O plano consolida o que o repositório e o histórico Git sustentam, separando implementação local, relatos do proprietário sobre produção e propostas futuras. Não autoriza desenvolvimento de v1.1, v1.2 ou v2.0, migration, acesso a dados de produção, publicação ou contratação de serviços.

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
| v1.0.0 / v1.0.1 | v1.0.0 agrupa funções principais; v1.0.1 corrige import no runner CI PostgreSQL para funcionar com execução fora do CWD do backend. | Manter tag `v1.0.0` imutável; correção é commit posterior `329ba67` e tag remota observada `v1.0.1`. | Evidência de release conforme Git e relato do proprietário; atual status do Actions/painéis não verificado nesta atualização. | Não confundir release/tag com conclusão das propostas 4.4, 5.6, v1.1, v1.2 ou v2.0. |

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
| Agente de IA | **Nova proposta aprovada para planejamento nesta solicitação; ainda não implementada**. | Requer política de dados, avaliação de qualidade, provedor/infra e limites. | v1.2 conforme seção F; não entregar ferramentas de escrita. |
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

## F. Planejamento v1.2 — agente de IA

**Status: ideia nova aprovada para entrar no roadmap; não implementada.** O objetivo é demonstrar aplicação de IA útil ao produto, não automatizar investimento.

### Objetivos e limites

1. **Educação financeira:** explicar renda fixa/variável, CDB, CDI, Selic, inflação, ações, proventos, juros compostos, risco e diversificação em linguagem acessível.
2. **Assistente do produto:** responder como cadastrar compra, encontrar Histórico, usar simulador/metas, entender rendimentos, bases e mensagens de indisponibilidade com base no comportamento real e documentado do build ativo.

O agente não será consultor personalizado, não recomendará compra/venda, não prometerá retorno e não inventará dados/funcionalidades. Primeira versão é leitura e explicação; sem mutações, ordens, cadastro, chamada livre de banco ou execução de compras/vendas.

### Arquitetura recomendada

```text
React chat privado → FastAPI (JWT, allowlist, rate/budget limits)
                  → orquestrador estreito e provider adapter
                  → modelo sem credencial no frontend
                  → resposta com fonte/estado e aviso de incerteza
```

- Começar com backend intermediário FastAPI para proteger a chave, aplicar limite por identidade, redactar logs, impor timeout, modelo/token ceiling e auditar custo sem armazenar pergunta financeira por padrão. Nenhuma `VITE_*` guarda secret.
- Criar corpus pequeno, versionado e curado com documentação vigente: navegação, contrato real de API, definições financeiras, limitações, `README`, changelog e páginas de ajuda. Metadados incluem caminho/commit/versão e seção; respostas sobre o app retornam referências clicáveis internas.
- Para esse corpus inicial, começar por recuperação determinística por tema/termos ou índice simples. RAG vetorial só se avaliação mostrar melhoria material em cobertura/qualidade e manutenção; não é requisito por moda. Nenhuma indexação de operações pessoais.
- LLM recebe só a pergunta e trechos públicos do corpus. Nenhum endpoint financeiro ou dado pessoal entra no contexto no MVP. Se, no futuro, houver consulta estruturada, será por funções nomeadas, parâmetros validados e autorização de servidor, resposta agregada mínima, somente leitura e consentimento claro; jamais SQL arbitrário ou ferramenta escolhida pelo texto do modelo.
- Se modelo ou limite cair, chat informa indisponibilidade e mantém restante do dashboard funcionando. Cotas por usuário, limite de tokens por chamada/sessão, timeout, retries limitados, limite diário, teto de custo e disable switch.
- Usar esquema de saída validado (resposta, referências, tipo: educação/ajuda/limite) e checar links/citações no backend. “Guardrails” de prompt não substituem controle de acesso. Tratar mensagens, textos recuperados e saídas do modelo como conteúdo não confiável; escapar HTML e manter zero ferramentas privilegiadas. A orientação OWASP ressalta que filtros textuais não formam uma fronteira de segurança; autorização deve ser imposta fora do modelo.
- Observabilidade sem conteúdo financeiro ou tokens: latência, erro por classe, modelo, contagem/tokens/custo agregado e versão do corpus; política de retenção curta e declarada para conteúdo se vier a ser necessário.

### Etapas, dependências e critérios

| Entrega | Escopo | Aceite | Complexidade |
|---|---|---|---|
| 1.2.1 — MVP do chat | UI React acessível, estado de conversa efêmero, POST autenticado à API, adapter de provedor, resposta sem contexto financeiro. | API key só backend; 401/403 e rate limits corretos; timeout/falha clara; chamadas não mudam ledger; demo não inicia nem expõe chat privado sem especificação própria. | M |
| 1.2.2 — conhecimento financeiro | Perguntas educativas usando conteúdo curado e respostas com escopo, data e referência; explicar que não é recomendação individual. | Suite de perguntas/exemplos, factualidade, casos que deve recusar/explicar incerteza; sem promessa ou recomendação de ativo. | M |
| 1.2.3 — conhecimento do dashboard | Recuperar documentação real de features e limites da versão implantada. | Perguntas de navegação/cálculo apontam seção/rota válida; teste adversarial para função inexistente e versão desatualizada; preferir resposta “não documentado”. | M |
| 1.2.4 — qualidade/segurança/custo | Avaliação de respostas, prompt injection, privacidade, limites, logs, falhas de provedor e budget. | Testes automatizados/regressão, sem PII nos logs, limites comprovados, observabilidade agregada, fonte conhecida, política de dados/privacidade antes de liberar. | L |
| 1.2.5 — opções futuras | Ferramentas estruturadas somente leitura, memória de conversa ou resposta contextualizada. | Cada recurso exige decisão independente, consentimento e threat model; dados mínimos; owner check; sem alterar registros; avaliar retenção/custo. | L; opcional |

### Opções gratuitas e pagas, privacidade e custos

Preços e termos mudam; conferência documental feita em 31/10/2026 e deve ser refeita antes de codificar. Não há provedor aprovado, cota de requisições aprovada nem custo mensal fixo calculável sem modelo, limites e uso observados.

| Caminho | Custo/complexidade | Dados e adequação |
|---|---|---|
| Modelo aberto local (ex. Ollama em máquina controlada) | Sem tarifa por token/API quando executado em hardware próprio; custo de hardware/energia e operação; pode exigir GPU/memória, M/L para servir com disponibilidade. | Melhor fronteira se prompt fica local, mas manter serviço local em produção Vercel/Render não é automático; validar licença, qualidade, latência e segurança do modelo. “Gratuito” não equivale a custo operacional zero. |
| Tier gratuito hosted (ex. Gemini API Free) | Pode iniciar a $0 sujeito a quota, modelo e região; sem SLA/capacidade garantidos; limites mudam. | A tabela oficial do Gemini diferencia Free/Paid e informa uso de conteúdo para melhoria no Free para modelos listados; não enviar perguntas com dados financeiros identificáveis nesse tier sem revisão explícita. |
| API paga por tokens (OpenAI, Anthropic, Gemini paid, outros) | Sem infraestrutura de GPU própria; custo variável = tokens de entrada/saída × preço do modelo + ferramentas/armazenamento; adicionar limite rígido e orçamento. Nenhum pagamento obrigatório está aprovado. | Revisar termos, retenção e região por endpoint/plano. OpenAI declara que conteúdo de API não é usado para treino por padrão, mas há retenção operacional por endpoint/abuso; isso não é ausência de retenção. Usar dados financeiros privados requer decisão separada e minimização. |
| Hospedagem/modelo cloud via intermediário (ex. Ollama Cloud) | Conta gratuita pode incluir uso inicial limitado; uso excedente pago conforme catálogo/planos atuais. | Ainda envia prompts a infraestrutura cloud; revisar regiões, subprocessadores e compromisso de logging/retenção antes de qualquer dado privado. |

Fórmula de controle para análise antes de lançar: `custo_estimado = chamadas × (tokens_entrada/1.000.000 × preço_entrada + tokens_saida/1.000.000 × preço_saida) + ferramentas`. Registrar cenários de baixo/alto volume após telemetria não sensível; avisar teto e desligar serviço antes de cobrança acima do limite. No Free do Gemini a tabela atual indica uso de conteúdo para melhorar produtos em modelos/free tier; nas APIs OpenAI a documentação informa não treinamento por padrão, mas retenção depende do endpoint e controles. Ver fontes oficiais [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data), [Gemini pricing e uso de dados](https://ai.google.dev/gemini-api/docs/pricing), [Anthropic API](https://www.anthropic.com/claude/api), [Ollama pricing/privacy](https://ollama.com/pricing) e [OWASP Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html). Estes links descrevem condições atuais publicadas; não constituem aprovação de fornecedor.

**Recomendação:** primeiro protótipo local com corpus curado, perguntas fictícias e provider adapter substituível; avaliar local vs API paga sem tráfego de carteira. Antes de tornar público, aprovar privacidade/termos, limites e custo, e colocar avaliação de qualidade/segurança no CI. Não usar texto promocional “IA sem custo” como promessa.

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
| v1.2.1 | MVP de chat privado e adapter de modelo | Proposto aprovado para planejamento, não implementado | P1 depois da v1.1 discovery/decisão de privacidade | Backend, provider decision, budget/quotas, policy | M | Chave no servidor, sem dados financeiros, leitura-only, limite de custo | Nova ideia aprovada nesta solicitação |
| v1.2.2–.3 | Educação financeira e assistência do dashboard | Proposto | P1 | Corpus verificado, versão/ref, avaliação de factualidade | M | Não inventa rota/cálculo; referências e incerteza | Nova ideia |
| v1.2.4 | Segurança, privacidade e qualidade IA | Proposto, obrigatório antes de público | P1 | Eval set, prompt-injection threat model, observabilidade sem payload | L | Adversarial tests, limites/custo/falha, sem PII em logs | Nova ideia |
| v1.2.5 | Ferramentas read-only/memória/contexto financeiro | Adiado/opcional | P2 | Consentimento, tool whitelist, owner isolation, retenção | L | Decisão separada e teste de isolamento; padrão continua sem dados pessoais | Nova ideia, opcional |
| v2.0.1 | Modelo restrito de convites/abuso/privacidade | Planejado em documento anterior | P0 da expansão | Threat model, custo, suporte, política de dados | M | Plano de convite, remoção, custos, migration/restore aprovado | `multiuser-expansion-plan.md` |
| v2.0.2–.3 | Criação/revogação/aceite/Provisionamento Supabase | Planejado | P1 | Auth/admin backend, signup geral fechado, tokens hashed | L | Convite único, expira, revoga, não enumera e não vaza | Documento anterior |
| v2.0.4 | Isolamento A/B/N no sistema todo (incl. IA) | Planejado | P0 antes de convidados | owner/RLS/backend/cache/export/AI quotas | L | A, B e admin não atravessam fronteiras; testes reais e descartáveis | Documento anterior |
| v2.0.5–.6 | Operação, piloto convidado e saída segura | Planejado | P1 | Restore, monitoramento, incidentes, privacidade/limites | M/L | Go/no-go objetivo, pequeno piloto, revogação/removal/exclusão testados | Documento anterior |
| Futuro | Open Finance, scraping, APIs pagas/CSV/adaptadores, monetização/cadastro público | Opcional, suspenso ou descartado do escopo atual | P2/sem aprovação | Decisão específica e análise de custo/termos/segurança | L | Aprovação expressa; custo obrigatório zero permanece princípio atual | Docs custo/5.2/multiuser |

## H. Guia para futuras sessões

### Estado para retomar

- Checkout confirmado nesta tarefa: `main` em `329ba67`, árvore limpa antes das edições documentais; migrations locais 001→009 com um head `009_financial_events`.
- Release v1.0.0 foi publicada segundo o proprietário; tag local existente aponta para `1d54a36`. Tag remota v1.0.1 no commit `329ba67` foi observada em consulta anterior; a reconsulta falhou por DNS. Não criar/mover tags ou release sem pedido.
- Última correção técnica: import do runner PostgreSQL resolvido usando `Path(__file__).resolve().parents[1]` em `backend/tests/run_postgres.py`, eliminando dependência do CWD. A alteração está em `329ba67`; ela não altera a lógica financeira, schema ou DB.
- Migration 009 existe e é head no código. Estado corrente do banco de produção não foi consultado; documentação do proprietário relata que foi aplicada. Não rodar migration ou query de produção sem autorização específica.
- Backup único cifrado fora do repo; documento não inclui frase/hash/DSN. Restore real ainda não foi ensaiado; somente dados fictícios e banco descartável foram usados nos testes sintéticos registrados.
- Próxima tarefa recomendada: primeiro decidir quais validações de prontidão operacional vale fechar; depois aprovar escopo e executar somente v1.1.1 (auditoria de dados/séries), sem implementar métricas de retorno ainda. A ideia v1.2 já entrou no roadmap, mas aguarda análise de privacidade, custo e prioridade. v2 é posterior à estabilidade e recuperação.

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

**Resumo executivo:** a v1 é um produto pessoal funcional e publicada conforme relato/tag Git, com demo, acesso privado, operações, renda fixa, eventos, Histórico, relatórios, simulador e metas. A série de patrimônio/retorno histórico consolidado continua ausente por decisão de integridade financeira; o restore do backup real e algumas verificações operacionais não estão comprovados. A ordem recomendada é fechar somente validações relevantes da v1, conduzir descoberta de dados para v1.1, avaliar/autorizar uma primeira fase de agente educacional v1.2 sem contexto financeiro e tratar convites multiusuário como v2.0 após ameaça, privacidade e recuperação.
