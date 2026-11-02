# Segurança e operações administrativas v3.0

## Identidade e isolamento

O acesso privado usa Supabase Auth sem cadastro público. O backend confirma no Admin Auth API que convites pertencem ao e-mail confirmado; memberships e registros financeiros são owner-scoped, com RLS/FORCE RLS. A administração pode gerir convites, mas não ganha acesso às carteiras. `INVITATION_ADMIN_IDS` no Render define os administradores; `VITE_INVITATION_ADMIN_IDS` na Vercel privada serve apenas para exibir controles. Não configure essa variável no projeto público.

A página `/invite/accept` não ativa a membership ao carregar. A senha só pode ser atualizada depois que o backend confirma o UUID do convite presente no link, a identidade Supabase validada pelo Admin Auth API, o e-mail confirmado correspondente e a elegibilidade atual. O backend cria um claim aleatório de curta duração, guarda apenas seu SHA-256, bloqueia claims concorrentes e aceita o convite atomicamente uma única vez. O frontend não é autoridade de acesso. Convites para identidade Auth confirmada usam o envio de recovery do próprio Supabase somente quando a API Admin de convite retorna o código de identidade já existente; o recovery conserva o UUID do mesmo convite. Outros erros de envio não acionam esse fallback.

Um administrador pode conceder explicitamente um novo período a uma membership revogada ou expirada. A nova concessão fica direcionada ao UUID Auth já confirmado e é auditada como novo convite administrativo; ela não altera a membership nem renova o prazo enquanto estiver pendente. O período de exatamente 168 horas começa na aceitação validada pelo backend. Solicitação pública não cria nem renova membership. Contas permanentes (`access_expires_at IS NULL`) não têm comportamento alterado. Se uma conta anterior à migration 014 não tiver um `activated_at` histórico, a interface mostra “Não registrado”; a migration não infere a data a partir da criação da membership.

## Solicitação de teste por sete dias

`POST /api/access-requests` é o único endpoint público novo. Recebe apenas e-mail normalizado, não cria identidade nem membership e devolve uma confirmação genérica para nova solicitação, duplicata ou limite atingido. A migration 013 armazena os pedidos em `account_access_requests`, com RLS e FORCE RLS; anon, authenticated e service_role não recebem grants. A role `investment_runtime` só consulta a tabela no contexto de submissão limitado ou de administração. A migration 014 adiciona estado de aceitação e claim às tabelas existentes; não amplia a leitura pública. Não há endpoint público para consultar ou decidir pedidos.

O limite de produção é compartilhado por instâncias no PostgreSQL: três tentativas por hash de IP e 100 tentativas globais em janelas de 24 horas iniciadas pela primeira tentativa. Tentativas duplicadas e bloqueadas também consomem a cota; o sistema não grava os e-mails dessas tentativas. Para o serviço público no Render, usamos `CF-Connecting-IP`: o [artigo técnico do Render sobre IP de cliente](https://render.com/articles/how-render-handles-ddos-attacks) informa que o tráfego público passa pela borda Cloudflare e pelos load balancers Render. Isso é parte da infraestrutura do Render, não uma configuração Cloudflare que você precisa criar. O backend valida esse cabeçalho como um único endereço IP e ignora `X-Forwarded-For`, que não é confiável sem validação da cadeia de proxies. Se `CF-Connecting-IP` estiver ausente ou malformado, a solicitação falha fechada com HTTP 503. O IP é armazenado somente como HMAC com segredo já existente no backend. A lista não revela se o e-mail já pertence a uma conta. O painel administrativo, visível em Minha conta → Administração de convites, é a notificação obrigatória; não há envio de e-mail administrativo configurado.

Ao aprovar, o backend reserva um convite com `access_duration_days=7` e envia o convite pelo fluxo Supabase Auth existente. Falha explícita no envio revoga a reserva e retorna o pedido a pendente. Se o processo cair depois do Supabase aceitar o envio e antes da confirmação local, o pedido pode permanecer como aprovação em andamento. O admin pode cancelar essa aprovação; a reserva local é revogada, então um eventual link já enviado não ativa acesso ao dashboard. Não apague o registro da solicitação diretamente. O link de convite continua sujeito ao prazo próprio do Supabase Auth; os sete dias de acesso começam quando o convite é aceito e a membership é ativada com `access_expires_at = activation_time + 7 days`.

Todas as rotas privadas que usam `authenticate` validam a expiração no banco em cada requisição. JWT ainda válido não estende o teste. A interface direciona a pessoa expirada para Minha conta e mantém a exclusão própria autenticada disponível. Os dados não são excluídos automaticamente. Convites administrativos comuns não recebem prazo de membership e as contas atuais com `access_expires_at IS NULL` permanecem permanentes.

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

Variáveis já necessárias no Render: `ENVIRONMENT=production`, `AUTH_MODE=supabase`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` (runtime restrito), `MIGRATION_DATABASE_URL` (papel DDL aprovado), `INVITATION_ADMIN_IDS`, `APP_PUBLIC_URL` e CORS de origem HTTPS exata. A migration 014 não requer variável nova; ela reutiliza a integração Admin Auth existente. Inclua a URL privada `/invite/accept` na allowlist de redirects do Supabase Auth, além das URLs de autenticação já utilizadas. Mantenha URL/chave publishable Supabase e API base somente na Vercel privada; a demonstração pública permanece sem autenticação privada, Íris e chamadas à API privada.

Ordem operacional: (1) verificar o head real e criar backup cifrado correspondente fora do repositório; (2) ensaiar restore em PostgreSQL descartável; (3) aplicar sequencialmente as migrations ainda ausentes até 014 usando a role DDL — para a 012, ela precisa criar `investment_deletion_executor`, conceder-lhe privilégios temporários no schema para transferir ownership e depois deixar `CREATE` revogado; (4) conferir head 014, policies RLS/FORCE RLS, grants mínimos das novas colunas/tabela e grants/owners das cinco funções de exclusão; (5) publicar o backend e então os projetos Vercel privado e público, observando seus deploys automáticos; (6) verificar health, submissão neutra, admin, convite/aceitação (inclusive identidade Auth existente), reativação, expiração e demonstração pública. Não rode downgrade 012, 013 ou 014. Se a role DDL do provedor não puder criar a role ou alterar os owners, pare: não conceda `BYPASSRLS` nem privilégios de DELETE ao runtime.

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

Backups disponíveis: `backend/scripts/backup_supabase_011.py`, `backup_supabase_012.py`, `backup_supabase_013.py` e `backup_supabase_014.py`, conforme o head confirmado. O restore automatizado fornecido destina-se exclusivamente a PostgreSQL descartável. A migration aplicada em produção e a publicação exigem validação operacional separada; esta documentação não afirma que foram executadas.
