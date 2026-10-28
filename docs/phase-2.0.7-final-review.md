# Fase 2.0.7 — revisão final e usabilidade de renda fixa

Revisão local de 28/10/2026. Nenhum acesso a produção, migration, credencial ou dado
financeiro real foi realizado. A migration 004 existente não foi modificada. O responsável
relatou que o Supabase está em `004 (head)`, RLS/FORCE RLS ativos e grants da role runtime
conferidos; esse estado não foi verificado remotamente nesta sessão. O site e fluxos de CDB
foram reportados como operacionais.

## Segurança e posição observada

### Status para encerramento local

- Implementação local existente preservada. Nesta revisão, 42 testes frontend focais passaram,
  `tsc -b` passou e o build privado passou; permanece aviso de bundle >500 kB. Nenhuma falha
  crítica foi identificada na revisão estática.
- O responsável executou no Windows os quatro arquivos pytest focais (75 passaram) e a
  integração PostgreSQL descartável (1 passou), totalizando 118 testes com os 42 testes
  frontend. Esse resultado backend é informado pelo usuário e não foi reexecutado nesta
  revisão; TypeScript e build privados também passaram anteriormente.
- Pendência de homologação funcional: repetir fluxos com duas contas de teste e somente
  registros fictícios, verificando 404 cruzado, cache por identidade, CDB/snapshot, movimentos
  e demo offline. Não usar produção nem registros financeiros reais nessa rodada.
- O responsável relatou 004 em `head`, RLS/FORCE RLS/grants corretos e fluxos operacionais.
  Essa informação não foi verificada remotamente. A revisão independente de implantação é
  uma pendência separada e exige autorização e procedimento somente de leitura.
- Após essas validações, registrar resultado e obter autorização explícita para qualquer
  commit, push ou publicação. Nenhum deles foi executado. A versão 1.0 Final é o lançamento
  pessoal futuro; até lá, usar somente dados fictícios.

- A migration 004 declara `down_revision = "003"`; snapshots ficam em tabela própria,
  com FK do investimento, validações SQL, índice de proprietário, cronologia e índice
  único parcial de abertura. RLS e FORCE RLS estão habilitados, com policy pelo contexto
  transacional `app.user_id`; triggers validam proprietário/datas/cronologia e bloqueiam
  UPDATE, DELETE e TRUNCATE. A função de lotes e a guarda de movimentos também protegem
  a cronologia após a abertura.
- Os endpoints usam `private_db` (autenticação, allowlist e contexto do proprietário) e
  `owned_investment`; ids de outra conta resultam em 404. Validações monetárias, duplicidade
  e sequência temporal têm checagens na API e no banco. As consultas SQL abaixo são somente
  leitura e devem ser executadas pelo responsável no projeto correto, após autorização.
- A posição observada permite data-base, bruto, líquido e principal desconhecido (`null`).
  A abertura exige contrato sem histórico e só é permitida uma vez. Snapshot não cria lote
  ou movimento. O principal exibido deriva apenas dos lotes; em contrato consolidado, a UI
  deixa explícito que os lotes posteriores são separados da observação do CDB inteiro.
- **Classificação de contrato de teste:** o modelo atual não possui campo “teste/real”, e o
  registro de produção existente é imutável. A opção mais segura é mantê-lo intacto e não
  reaproveitá-lo; cadastrar cada CDB real como novo contrato e iniciar acompanhamento nele.
  A tela calcula posições por contrato e não soma esse registro ao ledger de outro CDB. O
  item antigo ainda pode aparecer na lista, portanto deve ser tratado como registro legado
  de teste. Não há classificação automática confiável sem uma mudança de produto futura;
  não foi criada migration nem sugerida edição direta de dados.

## Validação backend local — PowerShell

Execute no Windows do usuário, onde a `.venv` funcional e Docker estão disponíveis. Os
testes usam fixtures fictícias; a integração cria container PostgreSQL descartável e tmpfs.
Nenhum comando abaixo conecta ao banco de produção.

```powershell
$repo = 'C:\caminho\para\investment-dashboard' # substitua pelo diretório local do checkout
Set-Location "$repo\backend"
& .\.venv\Scripts\python.exe -m pytest -q `
  tests/test_opening_balances.py `
  tests/test_fixed_income.py `
  tests/test_fixed_income_returns_api.py `
  tests/test_security.py
if ($LASTEXITCODE -ne 0) { throw 'Testes backend focais falharam' }

# Integração 001→004, RLS, grants, imutabilidade, cronologia e concorrência;
# exige Docker funcional e executa somente no container efêmero criado pelo runner.
& .\.venv\Scripts\python.exe .\tests\run_postgres.py
if ($LASTEXITCODE -ne 0) { throw 'Integração PostgreSQL descartável falhou' }
```

Pare se a `.venv` não iniciar ou o runner não confirmar uso de banco descartável. Não
substitua a URL de produção nem exporte credenciais como atalho.

## SQL de auditoria Supabase — somente leitura

Conferir o projeto/host no Dashboard. Consultas abaixo leem metadados e privilégios, nunca
linhas financeiras. Não as executar nesta tarefa; não colar resultados que contenham
identificadores pessoais ou conexão em logs/tickets.

Checklist para execução autorizada pelo responsável, sem comandos de escrita:

- [ ] Confirmar o projeto/host e que a versão instalada é `004 (head)`; não reaplicar migration.
- [ ] Confirmar RLS e FORCE RLS em todas as tabelas do ledger e observações, com policy de
  escopo por proprietário.
- [ ] Revisar constraints, índices, FKs e triggers que protegem owner, cronologia e append-only.
- [ ] Confirmar que `investment_runtime` não é superuser, não tem BYPASSRLS e possui somente
  privilégios necessários (snapshots: SELECT/INSERT e USAGE de sequência; sem UPDATE/DELETE).
- [ ] Verificar que `anon`, `authenticated` e roles públicas não têm grants financeiros
  indevidos; comparar privilégios efetivos/herdados, sem aplicar correções amplas.
- [ ] Registrar apenas resultado pass/fail e nomes de metadados; não exportar linhas
  financeiras, tokens, connection strings ou identificadores pessoais.

```sql
-- Revisão instalada e tabela alvo
SELECT version_num FROM public.alembic_version;
SELECT to_regclass('public.fixed_income_observations') AS observations_table;

-- Tabelas protegidas; confirmar RLS e FORCE RLS em todo o ledger financeiro
SELECT c.relname, pg_get_userbyid(c.relowner) AS table_owner,
       c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('operations','fixed_income_investments','fixed_income_lots',
                    'fixed_income_movements','fixed_income_observations')
ORDER BY c.relname;

-- Constraints e chaves estrangeiras de renda fixa
SELECT conname, contype, pg_get_constraintdef(oid) AS definition
FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
  AND t.relname IN ('fixed_income_investments','fixed_income_lots',
                    'fixed_income_movements','fixed_income_observations')
ORDER BY t.relname, conname;

-- Policies efetivas declaradas
SELECT policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN ('operations','fixed_income_investments','fixed_income_lots',
                    'fixed_income_movements','fixed_income_observations')
ORDER BY tablename, policyname;

-- Triggers das observações e dos movimentos; definição e status
SELECT t.tgrelid::regclass AS table_name, t.tgname, t.tgenabled,
       pg_get_triggerdef(t.oid) AS definition
FROM pg_trigger t
WHERE NOT t.tgisinternal
  AND t.tgrelid IN (to_regclass('public.operations'),
                    to_regclass('public.fixed_income_investments'),
                    to_regclass('public.fixed_income_lots'),
                    to_regclass('public.fixed_income_movements'),
                    to_regclass('public.fixed_income_observations'))
ORDER BY table_name, t.tgname;

-- Funções acionadas e respectivos proprietários/segurança
SELECT p.oid::regprocedure AS function_name,
       pg_get_userbyid(p.proowner) AS function_owner,
       p.prosecdef AS security_definer,
       has_function_privilege('investment_runtime', p.oid, 'EXECUTE') AS runtime_execute
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.proname IN ('fi_validate_observation','fi_tracking_movement_guard',
                    'fi_validate_lot','fi_reject_mutation')
ORDER BY function_name;

-- Índices, incluindo o único parcial que bloqueia uma segunda abertura
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('operations','fixed_income_investments','fixed_income_lots',
                    'fixed_income_movements','fixed_income_observations')
ORDER BY tablename, indexname;

-- Privilégios efetivos (inclui herança de roles) e atributos da role runtime
SELECT r.rolname, r.rolsuper, r.rolbypassrls, r.rolcreaterole, r.rolcreatedb
FROM pg_roles r WHERE r.rolname = 'investment_runtime';
SELECT r.rolname AS role_name, c.relname AS table_name,
       has_table_privilege(r.rolname,c.oid,'SELECT') AS can_select,
       has_table_privilege(r.rolname,c.oid,'INSERT') AS can_insert,
       has_table_privilege(r.rolname,c.oid,'UPDATE') AS can_update,
       has_table_privilege(r.rolname,c.oid,'DELETE') AS can_delete,
       has_table_privilege(r.rolname,c.oid,'TRUNCATE') AS can_truncate
FROM pg_roles r CROSS JOIN pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE r.rolname IN ('investment_runtime','anon','authenticated','service_role')
  AND n.nspname = 'public' AND c.relkind IN ('r','p')
  AND c.relname IN ('operations','fixed_income_investments','fixed_income_lots',
                    'fixed_income_movements','fixed_income_observations')
ORDER BY r.rolname, c.relname;
SELECT r.rolname AS role_name, s.relname AS sequence_name,
       has_sequence_privilege(r.rolname,s.oid,'USAGE') AS can_use,
       has_sequence_privilege(r.rolname,s.oid,'SELECT') AS can_read,
       has_sequence_privilege(r.rolname,s.oid,'UPDATE') AS can_update
FROM pg_roles r CROSS JOIN pg_class s JOIN pg_namespace n ON n.oid = s.relnamespace
WHERE r.rolname IN ('investment_runtime','anon','authenticated','service_role')
  AND n.nspname = 'public' AND s.relkind = 'S'
  AND s.relname IN ('operations_id_seq','fixed_income_investments_id_seq',
                    'fixed_income_lots_id_seq','fixed_income_movements_id_seq',
                    'fixed_income_observations_id_seq')
ORDER BY r.rolname, s.relname;
SELECT grantee, table_name, privilege_type
FROM information_schema.table_privileges
WHERE table_schema = 'public'
  AND table_name IN ('operations','fixed_income_investments','fixed_income_lots',
                     'fixed_income_movements','fixed_income_observations')
ORDER BY grantee, table_name, privilege_type;
```

Comparar privilégios efetivos com as operações necessárias de cada tabela (por exemplo,
DELETE em `operations` existe para o endpoint de exclusão de ações); para snapshots 004,
runtime precisa SELECT/INSERT/sequence USAGE, sem UPDATE/DELETE/TRUNCATE. Roles públicas
não devem receber privilégios financeiros. Validar RLS/FORCE RLS, policy de proprietário,
triggers de INSERT/append-only/no-truncate, índices/constraints e roles sem privilégios
administrativos. Qualquer divergência exige investigação; não corrigir com grants amplos.

## Checklist de homologação com duas contas e publicação controlada

Executar os testes de escrita em ambiente de homologação/teste com contas dedicadas e dados
fictícios. Não inserir fixtures em produção. Se não houver ambiente de teste isolado, parar
antes dos passos que escrevem e solicitar autorização específica.

- [ ] Usar exclusivamente contratos, operações e valores fictícios criados para esta rodada.
- [ ] Na conta principal de testes, criar uma posição fictícia; confirmar persistência, resumo
  e histórico próprios.
- [ ] Na conta secundária, confirmar carteira separada e criar outro conjunto fictício.
- [ ] Com cada sessão, tentar acessar somente o id fictício criado pela outra conta; esperar
  404 em GET/POST cruzado. Sem sondar ids ou registros reais.
- [ ] Confirmar troca/logout/login limpa cache e não reutiliza valores entre identidades.
- [ ] Abrir CDB fictício com posição observada sem principal; confirmar data, bruto/líquido,
  nenhum lote anterior, abertura única e cronologia.
- [ ] Registrar aplicação posterior e confirmar que o principal do ledger permanece separado
  da posição observada do contrato inteiro.
- [ ] Conferir dicas com teclado (Tab/Enter/Escape), mouse e toque; texto não deve depender
  somente do hover.
- [ ] Confirmar que a demo pública segue offline e sem dados privados.
- [ ] Antes de qualquer publicação, conferir backup restaurável, versão, allowlist e leitura
  dos privilégios; publicar backend antes do frontend somente com autorização explícita.
- [ ] Confirmar `004 (head)` e desativar qualquer mecanismo de migration automática no
  deploy; a migration não deve ser reaplicada.
- [ ] Verificar health/autenticação, repetir smoke test fictício, registrar resultado e parar
  se houver divergência de RLS, identidade ou demo.

Até o lançamento da versão 1.0 Final, não cadastrar posições reais. Na preparação futura da versão 1.0,
após aprovação e homologação, cadastrar cada CDB real como contrato separado. Se já estiver
em andamento, escolher **Iniciar com saldo atual**, informar a data-base e saldos bruto/líquido
da fonte, deixar principal vazio quando desconhecido, revisar e confirmar uma vez. Não
inventar aplicações anteriores nem somar snapshot ao principal dos lotes novos. Aplicações
posteriores entram como lotes separados; observações preservam snapshots anteriores.

O responsável informou que a migração e o deploy atual estão operacionais. Homologação da
segunda conta e as consultas acima ainda dependem de execução manual autorizada; nenhuma
confirmação independente foi obtida nesta revisão.
