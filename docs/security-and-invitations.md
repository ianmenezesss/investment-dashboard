# Segurança e operações administrativas v3.0

## Identidade e isolamento

O acesso privado usa Supabase Auth sem cadastro público. O backend confirma no Admin Auth API que convites pertencem ao e-mail confirmado; memberships e registros financeiros são owner-scoped, com RLS/FORCE RLS. A administração pode gerir convites, mas não ganha acesso às carteiras. `INVITATION_ADMIN_IDS` no Render define os administradores; `VITE_INVITATION_ADMIN_IDS` na Vercel privada serve apenas para exibir controles. Não configure essa variável no projeto público.

## Excluir a própria conta

`POST /api/account/delete` recebe somente `{"confirmation":"EXCLUIR MINHA CONTA"}`. A API exige JWT Supabase, `auth_time` de até cinco minutos, reautenticação recente no frontend e não aceita UUID de destino. A migration 012 fornece fases transacionais retomáveis: revogar membership/criar job; apagar linhas financeiras e metadados da própria conta; remover a identidade pelo Supabase Admin API; e, por fim, apagar membership/job. A auditoria final conserva apenas UUID aleatório da operação, fase e horário, sem user ID nem e-mail.

Para preservar as triggers append-only, a exclusão usa a role `investment_deletion_executor` (`NOLOGIN`, sem `BYPASSRLS`, sem membership em outras roles). Somente funções `SECURITY DEFINER` com owner nessa role podem apagar ledgers; a role runtime não recebe `DELETE` nessas tabelas. UPDATE e TRUNCATE continuam recusados. Cada fase de banco é confirmada separadamente. Se a chamada ao Supabase falhar, o job fica pendente e pode ser retomado pelo próprio titular; se a identidade já tiver sido removida ou a sessão tiver expirado, o administrador pode executar o script de retomada descrito abaixo.

Limites: a operação remove os dados do dashboard, convites relacionados e a identidade Supabase, mas não apaga dados mantidos por terceiros, backups já existentes, logs externos ou obrigações legais. A exclusão da identidade depende da disponibilidade/permissão do Supabase Admin API. Não há downgrade para migration 012. Nunca execute o endpoint ou script de retomada para excluir uma conta alheia; o script admin só finaliza um job iniciado pelo próprio usuário depois do purge financeiro.

## Loader da fixture fictícia

O único loader é `backend/scripts/load_demo_fixture.py`; não existe rota HTTP para carregá-lo. A execução exige UUID explícito do usuário e administrador, repetição dos UUIDs, project ref e frase de confirmação. O script verifica o mesmo project ref no `SUPABASE_URL` e `DATABASE_URL`, confirma ambos UUIDs pelo Supabase Admin API, exige admin da allowlist e membership ativo, e recusa marker prévio ou qualquer linha financeira da carteira. Os dados são validados e inseridos numa transação; falha causa rollback, e nova execução é recusada. Fontes, observações e nome do CDB recebem marca fictícia; a carteira privada exibe um aviso global baseado no marker para que as operações de ações sem campo de origem também sejam identificadas. Metas continuam em armazenamento local do navegador, portanto o loader não as grava no banco.

Pré-requisitos já existentes no ambiente administrativo isolado: `AUTH_MODE=supabase`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` para o projeto correto e `INVITATION_ADMIN_IDS` como JSON array contendo o UUID admin. Nunca coloque a service-role key em argumentos de comando, Vercel ou no repositório.

PowerShell, apenas com conta de teste dedicada e carteira vazia:

```powershell
Set-Location backend
$userId = "<UUID_DA_CONTA_DE_TESTE>"
$adminId = "<UUID_DO_ADMIN_AUTORIZADO>"
$projectRef = "<PROJECT_REF_CONFIRMADO>"
\.venv\Scripts\python.exe scripts\load_demo_fixture.py `
  --user-id $userId --confirm-user-id $userId `
  --admin-id $adminId --confirm-admin-id $adminId `
  --project-ref $projectRef `
  --confirm "LOAD FICTIONAL FIXTURE INTO $userId"
```

Não execute esse comando durante a preparação local. O loader recusa qualquer carteira que já contenha dados; não apaga nem sobrescreve registros.

## Retomada administrativa de exclusão

Use apenas quando há um job próprio em `financial_data_deleted` e o titular já não consegue concluir com sua sessão. Confirme manualmente o project ref e UUIDs antes de rodar:

```powershell
Set-Location backend
$userId = "<UUID_DO_JOB_PENDENTE>"
$adminId = "<UUID_DO_ADMIN_AUTORIZADO>"
$projectRef = "<PROJECT_REF_CONFIRMADO>"
\.venv\Scripts\python.exe scripts\resume_account_deletion.py `
  --user-id $userId --confirm-user-id $userId `
  --admin-id $adminId --confirm-admin-id $adminId `
  --project-ref $projectRef `
  --confirm "RESUME ACCOUNT DELETION $userId"
```

O script confirma o admin e o projeto, consulta o estado do job e nunca inicia o purge financeiro. As mesmas variáveis administrativas precisam estar somente no ambiente backend seguro.

## Publicação

Variáveis já necessárias no Render: `ENVIRONMENT=production`, `AUTH_MODE=supabase`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` (runtime restrito), `MIGRATION_DATABASE_URL` (papel DDL aprovado), `INVITATION_ADMIN_IDS`, `APP_PUBLIC_URL` e CORS de origem HTTPS exata. Nenhuma variável nova é introduzida pela migration 012. Mantenha URL/chave publishable Supabase e API base somente na Vercel privada; a demonstração pública permanece sem autenticação privada, Íris e chamadas à API privada.

Ordem operacional: (1) verificar o head real e criar backup cifrado correspondente fora do repositório; (2) ensaiar restore em PostgreSQL descartável; (3) aplicar sequencialmente as migrations ainda ausentes até 012 usando a role DDL — ela precisa criar `investment_deletion_executor`, conceder-lhe privilégios temporários no schema para transferir ownership e depois deixar `CREATE` revogado; (4) conferir head, policies RLS/FORCE RLS, role, owner/EXECUTE das cinco funções e grants restritos do runtime; (5) publicar o backend e então os projetos Vercel privado e público, observando seus deploys automáticos; (6) verificar health, login por convite, isolamento e demonstração pública. Não rode downgrade 012. Se a role DDL do provedor não puder criar a role ou alterar os owners, pare: não conceda `BYPASSRLS` nem privilégios de DELETE ao runtime.

Na migration 012, `ALTER FUNCTION ... OWNER TO investment_deletion_executor` exige que a sessão possa executar `SET ROLE` para o novo owner. A migration concede temporariamente essa capacidade ao próprio `CURRENT_USER`, transfere os cinco owners e revoga a concessão na mesma transação. Em PostgreSQL 16+, a membership temporária usa `SET TRUE, INHERIT FALSE`; em versões anteriores, usa as opções padrão da versão. O PostgreSQL pode manter a membership administrativa bootstrap (ADMIN, sem INHERIT/SET em 16+) que dá ao criador `CREATEROLE` controle sobre a role que criou; a migration permite apenas esse vínculo ao usuário DDL atual, nunca a runtime/anon/authenticated/service_role. O usuário de runtime nunca recebe `CREATEROLE`, associação ao executor nem DELETE nos ledgers. Se `alembic current` continuar em `010` após falha, a transação PostgreSQL normalmente reverte toda a 012; confirme antes de repetir, sem remover objetos manualmente:

```sql
SELECT version_num FROM alembic_version;
SELECT rolname FROM pg_roles WHERE rolname = 'investment_deletion_executor';
SELECT to_regclass('public.account_deletion_jobs') AS deletion_jobs,
       to_regclass('public.account_deletion_audit') AS deletion_audit,
       to_regclass('public.account_fixture_loads') AS fixture_loads;
SELECT to_regprocedure('public.dashboard_account_deletion_state(uuid)') AS deletion_state_function;
```

Se a revisão for `010` e todos os objetos exclusivos da migration 012 forem inexistentes, use a role DDL aprovada para executar `python -m alembic upgrade head` novamente. Se houver qualquer role/objeto 012 apesar da revisão 010, ou a repetição falhar novamente, pare e investigue o estado com o administrador do projeto; não faça `DROP`, `GRANT` amplo nem alteração da role de runtime. Após sucesso, `alembic current` deve apontar `012` e a verificação de owner/RLS/grants deve passar.

Backups disponíveis: `backend/scripts/backup_supabase_011.py` e `backend/scripts/backup_supabase_012.py`, conforme o head confirmado. O restore automatizado fornecido destina-se exclusivamente a PostgreSQL descartável. A migration aplicada em produção e a publicação exigem validação operacional separada; esta documentação não afirma que foram executadas.
