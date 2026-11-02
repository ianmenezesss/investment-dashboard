# Arquitetura e plano

> Este documento mantém as decisões fundacionais e a arquitetura original. Para o estado local v3.0.0, use o [registro atual de versões](INVESTMENT_DASHBOARD_V2_ROADMAP.md) e a [checklist de validação](v3-launch-checklist.md); as fases antigas abaixo são histórico, não backlog aprovado.

Atualização da candidata local v3.0.0 (02/11/2026; não publicada): migrations 011–016 adicionam membership/convites, solicitações públicas aprovadas manualmente, expiração de trial, exclusão própria retomável, proveniência do loader fictício, ativação vinculada a convite de uso único, auditoria de tentativas de e-mail e correção das funções administrativas de revogação/reativação. A migration 016 concede `CREATE` no schema `public` ao executor somente dentro da transferência de ownership e revoga o grant antes do commit. A reativação é uma concessão administrativa direcionada à identidade Auth e inicia 168 horas somente na aceitação. O painel administrativo separa contas, convites e solicitações com filtros e paginação no backend; revogar uma membership bloqueia imediatamente as rotas privadas sem apagar dados. O JWT Supabase é verificado, cada rota privada exige membership ativo não expirado e registros financeiros mantêm RLS/FORCE RLS por UUID proprietário. As funções administrativas usam o executor NOLOGIN/NOBYPASSRLS com grants mínimos; o runtime não recebe UPDATE em `account_members`. O runtime mantém os ledgers append-only. A fixture só é carregada pela CLI administrativa, em carteira vazia e numa única transação. A demonstração pública permanece sem API privada, convite e Íris.

O histórico individual Brapi usa `adjustedClose`, uma chamada por ticker, cache de 30 minutos e limitador de 12.000 chamadas/uma chamada simultânea **por processo**. O limitador não representa a cota da conta e não coordena outros workers, reinicializações ou aplicações; flags continuam opt-in. Intervalos acima de três meses são parciais. Nenhuma chamada externa foi feita nesta implementação local.

Registro histórico v4.0.0 / Fase 4.3A (29/10/2026): `GET /api/dashboard/performance` é um
snapshot privado somente de leitura que combina o ledger de ações, fluxos e projeção
efetiva CDB, composição e avaliação por cotações pontuais. Ele preserva `owner_id`,
`REPLACE`/`VOID`, `Decimal` e `Cache-Control: no-store`; resultado consolidado da carteira
e rentabilidade temporal ficam indisponíveis sem dados comparáveis. `PortfolioInsights`
apresenta as bases e estados sem chamar fluxo de patrimônio. A Fase 4.4 segue bloqueada
por ausência de eventos/fluxos externos e fonte histórica validada. Componentes de páginas
e gráficos são importados sob demanda; no build local de validação, o chunk inicial foi
reduzido de 806,13 kB para 443,68 kB.

Atualização 1.6.3: `components/ui/ConfirmDialog.tsx` reutiliza Radix Dialog existente (papel alertdialog, foco inicial em Cancelar, Escape e retorno de foco). `dashboard-ux.css` concentra os refinamentos visuais. O DemoRepository aceita schema 1 sem sobrescrita, persiste schema 2 na próxima alteração e mantém `seedVersion` independente; restauração explícita carrega o conjunto 2 com 26 registros. Regras financeiras e autenticação permanecem as mesmas.

Atualização 1.6.2: demonstração interativa com `DemoRepository` local e `PrivateRepository` HTTP separados. Somente a primeira usa localStorage; nenhum token ou dado privado é persistido ali. O cálculo Decimal.js foi alinhado ao contexto Decimal Python e possui casos de contrato em `shared/finance-cases.json`, executados pelos dois runtimes. Consulte [demonstração interativa](interactive-demo.md).

Registro da fase inicial: aplicação pessoal local, com frontend React/TypeScript/Vite e API FastAPI. O estado de produto atual também inclui históricos opcionais e observações patrimoniais; os limites estão no roadmap público.

Atualização da Fase 1.5: o build público é sempre uma demonstração sem rede privada. O acesso local por token foi preservado, e o backend ganhou um modo Supabase opt-in, autorização por proprietário e RLS. Veja [separação público/privado](demo-and-private.md), [auditoria](security-audit.md) e [deploy futuro](deployment.md). A integração externa não foi ativada.

Atualização da Fase 1.6: frontend privado com Supabase Auth implementado em `src/auth`, sem cadastro. Sessões por aba, recuperação via SDK/getUser, renovação, logout e tratamento de 401. A demonstração permanece padrão de produção, com opt-in explícito para o build privado. Configuração externa e homologação com a conta real ainda são necessárias; consulte [Supabase Auth](supabase-auth.md).

## Estrutura

```text
frontend/src/
  components/ui/   componentes de UI no padrão shadcn, Tailwind e Radix
  api.ts          contrato HTTP e tipos
  main.tsx        bootstrap React
  App.tsx         páginas e dashboard compartilhados
  runtime.ts      bloqueio da demonstração pública
  style.css       tema escuro e responsividade
backend/
  app/database.py configuração, engine e sessão SQLAlchemy
  app/models.py   modelo persistente
  app/wealth_observations.py snapshots patrimoniais observados, owner-scoped
  app/accounts.py lifecycle de convites, membership e exclusão Supabase
  scripts/        loader fictício e backup/restore versionados
  app/finance.py  cálculo por custo médio sem dependência HTTP
  app/main.py     validação, autenticação e endpoints
  app/auth.py     token local ou JWT Supabase com membership ativo
  app/access.py   identidade no contexto transacional de RLS
  migrations/    migrações Alembic versionadas
  tests/         testes das regras financeiras
compose.yaml     PostgreSQL local
```

O head local da candidata é `016_restore_admin_revocation_definer.py`, após `015_admin_invitation_audit.py`. A migration 015 cria auditoria restrita de solicitações de envio ao Supabase Auth e atualiza a função de revogação para tratar memberships legadas sem convite. A 016 restaura `SECURITY DEFINER` na revogação e reserva reativações em função privilegiada: ambas validam a role/contexto administrativo e usam o executor NOLOGIN/NOBYPASSRLS. A função de reativação repete no banco a checagem de elegibilidade, mantém o bloqueio transacional e grava o convite de sete dias; o backend verifica a allowlist administrativa e a identidade Auth confirmada. `investment_runtime` não recebe UPDATE em `account_members`, e as tabelas mantêm RLS/FORCE RLS. O histórico de envio acompanha a exclusão autorizada da linha de convite por FK `ON DELETE CASCADE`. A cadeia e a integração são validadas em PostgreSQL descartável. Nenhum estado de schema remoto é consultado por essa validação local.

## Fases e critérios do plano inicial (histórico)

1. **Fundação:** dashboard responsivo, demonstração explícita, API protegida por token, compras e vendas de ações, histórico com busca e ordenação, exclusão confirmada, custo médio, exportação JSON e migração PostgreSQL. Verificar build, testes e inicialização. O gráfico representa fluxo de compras menos vendas, não evolução de mercado.
2. **Ações completas:** contas/corretoras, edição transacional com recálculo cronológico, dividendos/JCP, cotações manuais com fonte e timestamp e interfaces para provedores. Testar reinvestimentos sem dupla contagem. Separar usuário, ativo, conta, provento e cotação em tabelas próprias.
3. **Renda fixa:** contratos e lotes individuais, aportes, resgates parciais, prefixado/CDI/IPCA, tributação por lote e calendário adequado. Confirmar regras vigentes em fontes oficiais antes de implementá-las. Diferenciar saldo estimado e saldo bancário oficial.
4. **Medição:** snapshots patrimoniais, fluxos externos separados das negociações, benchmarks oficiais, XIRR e TWR quando houver dados suficientes. Rentabilidade não será calculada a partir de fluxo de compras/vendas.
5. **Planejamento:** simulador com premissas explícitas, metas, projeções e relatórios.
6. **Uso remoto:** autenticação de usuário, autorização por proprietário, HTTPS, política de backup/restauração testada e observabilidade antes de exposição pública.

Cada fase deve ser validada antes de expandir o escopo. A navegação da demo oculta páginas privadas: metas usam armazenamento local segregado por identidade e não devem aparecer na demonstração; o simulador permanece independente da carteira.

## Decisões e dependências

- Backend Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic Settings, psycopg e Pytest.
- Frontend React, React Router, TanStack Query, Recharts, Lucide, Tailwind 4 e componentes locais no padrão shadcn/Radix.
- Valores entram como strings decimais, persistem em NUMERIC(20,8) e são calculados com Decimal. A API devolve valores monetários como strings. O frontend converte apenas para exibição e gráficos aproximados.
- O modo local conserva token apenas em memória; o modo privado usa Supabase Auth, membership ativo e filtro por proprietário. Segredos administrativos Supabase permanecem no backend e nunca em `VITE_*`.
- As mutações preservam validação cronológica, isolamento owner-scoped e RLS. A candidata v3 exige integração PostgreSQL descartável 001–016 antes de qualquer alegação de prontidão multiusuário.
- Data e ID definem a ordem de operações do mesmo dia. Uma compra inserida depois de uma venda no mesmo dia não passa retroativamente à frente dela.
- Não há caixa contábil nesta fase. Compras não equivalem a aportes externos; receita de vendas não equivale a resgate. Por isso não são mostrados patrimônio consolidado, capital líquido aportado nem retorno percentual.
- Dividendos, CDBs, CDI, IPCA, Ibovespa e cotações não são inferidos ou inventados. Nenhuma credencial externa é necessária para a Fase 1.

## Fórmulas da Fase 1

Compra: custo adicionado = quantidade × preço + taxas.

Preço médio = custo remanescente / quantidade remanescente.

Venda: custo removido = quantidade vendida × preço médio anterior.

Resultado realizado = quantidade vendida × preço de venda − taxas − custo removido.

Após venda, deduzir quantidade e custo removido. Rejeitar venda sem posição suficiente na data; rejeitar exclusão de compra que invalidaria vendas posteriores.

O gráfico de fluxo acumulado soma compras e subtrai vendas por valor bruto. Taxas ficam fora desse gráfico e dentro dos cálculos contábeis. O gráfico não é uma curva de rentabilidade nem uma curva de patrimônio.

## Limites conhecidos

Sem edição, paginação ou importação nesta fase. A exportação JSON contém os registros operacionais; o backup completo é feito via pg_dump. Não há acesso remoto pronto para produção. A configuração de runtime requer .env e PostgreSQL funcionando.
