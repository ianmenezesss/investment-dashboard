# Checklist operacional v3.0.0

## Validação local

- [x] Convites restritos, confirmação do e-mail pelo Supabase Auth e memberships por UUID.
- [x] RLS/FORCE RLS e testes negativos de isolamento entre proprietários.
- [x] Exclusão própria autenticada e retomável, com executor restrito para os ledgers append-only.
- [x] Loader CLI da fixture `v2-demo-scenario.json`, admin-only, transacional e limitado a carteira vazia.
- [x] Testes backend/frontend, build, `git diff --check`, migration 012 e integração PostgreSQL descartável com backup/restore.
- [x] Nenhuma chamada a serviço real, escrita em conta real, push, release ou deploy nesta validação.

## Publicação controlada

- [ ] Confirmar backup válido da revisão que está atualmente no PostgreSQL de destino; armazenar fora do repositório e testar restore apenas em banco descartável.
- [ ] Confirmar que a role usada pela migration pode criar a role restrita e alterar o owner das funções, sem conceder privilégios ao runtime.
- [ ] Confirmar variáveis existentes do Render: `AUTH_MODE=supabase`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `INVITATION_ADMIN_IDS`, `APP_PUBLIC_URL` e CORS privado.
- [ ] Manter cadastro público Supabase desabilitado; validar convite, confirmação de e-mail, redirect e política de senha.
- [ ] Aplicar em sequência apenas as migrations que faltarem até `012`; verificar RLS/FORCE RLS, role `investment_deletion_executor`, grants e owners das funções antes do deploy.
- [ ] Publicar backend e frontends privado/público; verificar health, login por convite, isolamento, demonstração pública e ausência de funcionalidades privadas no build público.
- [ ] Testar a interface privada com conta de teste autorizada e sem enviar dados financeiros reais à Íris.

## Popular uma conta de teste

Use somente depois do deploy e com um UUID Supabase dedicado, autorizado e com membership ativo, em uma carteira sem qualquer registro. O procedimento exato está em [segurança e operações administrativas](security-and-invitations.md#loader-da-fixture-ficticia). O script é local/CLI, não é endpoint e não aceita fixture alternativa.

Não execute o loader ou a exclusão em uma conta real durante a homologação. Nenhum item desta lista autoriza operação de produção, push, tag ou deploy.
