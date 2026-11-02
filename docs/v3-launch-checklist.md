# Checklist operacional v3.0.0

## Validação local

- [x] Convites restritos, confirmação do e-mail pelo Supabase Auth e memberships por UUID.
- [x] RLS/FORCE RLS e testes negativos de isolamento entre proprietários.
- [x] Exclusão própria autenticada e retomável, com executor restrito para os ledgers append-only.
- [x] Loader CLI da fixture `v2-demo-scenario.json`, admin-only, transacional e limitado a carteira vazia.
- [x] Testes backend/frontend, build, `git diff --check`, migrations 001–015 e integração PostgreSQL descartável com backup/restore.
- [x] Aceitação de convite validada no backend contra UUID do convite, identidade/e-mail Auth confirmado e claim temporário de uso único; reativação administrativa direcionada inicia o novo prazo somente após aceitação.
- [x] Fluxo de solicitação pública, painel admin, falha de envio, limite compartilhado e expiração de teste validados com fixtures/mocks e PostgreSQL descartável.
- [x] Painel administrativo separado em Contas, Convites e Solicitações, com busca/status/paginação no servidor; revogação de membership legada; status auditáveis de envio e reenvio limitado.
- [x] Nenhuma chamada a serviço real, escrita em conta real, push, release ou deploy nesta validação.

## Publicação controlada

- [ ] Confirmar backup válido da revisão que está atualmente no PostgreSQL de destino; armazenar fora do repositório e testar restore apenas em banco descartável.
- [ ] Confirmar que a role usada pela migration pode criar a role restrita e alterar o owner das funções, sem conceder privilégios ao runtime.
- [ ] Confirmar variáveis existentes do Render: `AUTH_MODE=supabase`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `INVITATION_ADMIN_IDS`, `APP_PUBLIC_URL` e CORS privado.
- [ ] Manter cadastro público Supabase desabilitado; validar convite, confirmação de e-mail, redirect e política de senha.
- [ ] Aplicar em sequência apenas as migrations que faltarem até `015`; verificar RLS/FORCE RLS, auditoria de envio, role `investment_deletion_executor`, grants e owners das funções antes do deploy.
- [ ] Publicar backend e frontends privado/público; verificar health, login por convite, isolamento, demonstração pública e ausência de funcionalidades privadas no build público.
- [ ] Testar a interface privada com conta de teste autorizada e sem enviar dados financeiros reais à Íris.

## Solicitações de acesso e período de teste

- A página pública `/solicitar-acesso` recebe apenas e-mail e sempre mostra a mesma confirmação para solicitações aceitas, duplicadas ou limitadas. Ela não cria conta Supabase.
- Render reutiliza as variáveis existentes `DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `API_TOKEN`, `AUTH_MODE`, `ENVIRONMENT`, `INVITATION_ADMIN_IDS`, `APP_PUBLIC_URL` e `CORS_ORIGIN`; nenhuma variável nova é necessária. O Render informa que seu tráfego público passa pela borda Cloudflare e pelos load balancers; o backend usa o `CF-Connecting-IP` fornecido pela infraestrutura, valida um IP único e ignora `X-Forwarded-For`. Sem cabeçalho válido, falha fechado com HTTP 503. Não configure proxy adicional nem habilite `X-Forwarded-For` como fonte confiável sem uma cadeia de proxies validada.
- Limites aplicados por contadores RLS no PostgreSQL compartilhado: até 3 tentativas por IP e 100 no total em janelas de 24 horas iniciadas pela primeira tentativa. Duplicatas e tentativas bloqueadas também consomem cota, sem persistir os e-mails recusados. A chave HMAC deriva de segredo já existente apenas no backend.
- Administradores consultam todos os pedidos em **Minha conta → Administração de convites → Solicitações de acesso**. Não há integração de notificação por e-mail ao administrador configurada; o painel funciona sem ela. O convite ao solicitante usa o envio do Supabase Auth já existente e está sujeito às cotas e ao SMTP do projeto.
- Aprovação cria um convite Supabase; sete dias de acesso começam quando o usuário aceita o convite e o backend ativa a membership. A validade do link é controlada separadamente pelo Supabase Auth. Membros sem data de expiração continuam permanentes.
- A página de aceitação não ativa automaticamente uma sessão antiga: exige o UUID atual do convite, identidade e e-mail confirmado no Supabase, claim backend temporário e aceitação atômica. Para uma identidade Auth confirmada já existente, o envio usa o fluxo recovery do Supabase, preservando o mesmo UUID de convite; a senha só é alterada após a elegibilidade e a reserva do claim. Reativar membership revogada/expirada exige ação administrativa explícita e não altera o período até a aceitação.
- `014_bound_invitation_reactivation.py` adiciona colunas de auditoria/claim, uma policy de leitura administrativa da membership e a função de aceitação revisada. O backup versionado correspondente é `backend/scripts/backup_supabase_014.py`; não aplicar migrations em produção sem backup e procedimento operacional aprovados.
- `015_admin_invitation_audit.py` adiciona tentativas de envio com RLS/FORCE RLS e grants restritos, preserva o registro do status informado pelo Supabase e permite revogar membership legada sem convite. A exclusão própria remove o histórico de envio associado ao excluir convites. O painel mostra “pedido aceito” sem afirmar entrega. A interface usa 5 registros por página e busca/status no backend. O backup de head 015 é `backend/scripts/backup_supabase_015.py`. Nenhuma variável de ambiente nova é necessária.
- O vencimento bloqueia rotas privadas do backend e redireciona a interface para Minha conta; os dados não são apagados e a exclusão própria segue disponível. Não teste em conta real antes de aprovar a migration e os deploys.

## Popular uma conta de teste

Use somente depois do deploy e com um UUID Supabase dedicado, autorizado e com membership ativo, em uma carteira sem qualquer registro. O procedimento exato está em [segurança e operações administrativas](security-and-invitations.md#loader-da-fixture-ficticia). O script é local/CLI, não é endpoint e não aceita fixture alternativa.

Não execute o loader ou a exclusão em uma conta real durante a homologação. Nenhum item desta lista autoriza operação de produção, push, tag ou deploy.
