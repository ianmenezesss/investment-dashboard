# Reconstrução do acesso — 3 de novembro de 2026

Este documento descreve o novo contrato das migrations **017–018**. O ensaio local não comprova entrega de e-mail nem publicação em produção. A revisão do banco remoto, Site URL, SMTP, templates e ambientes Vercel/Render precisam de conferência operacional.

## Diagnóstico confirmado no código anterior

1. A aprovação era uma saga `pending → approving → envio → approved`. Em erro, revogava o convite e voltava a solicitação a pendente, mesmo quando um timeout podia ter ocorrido depois do envio. Uma queda entre as etapas deixava aprovações presas.
2. Policies e funções administrativas aceitavam `app.admin_id` como prova de privilégio. A própria conexão runtime podia definir essa variável. A migration 016 corrigia ownership, mas não essa fronteira de confiança.
3. O painel usava uma promessa conjunta para as três listagens. Uma falha escondia respostas válidas das outras abas. A listagem de contas também podia fazer cinco consultas Auth sequenciais para preencher e-mails legados.
4. O callback dependia da detecção automática do SDK; não tratava explicitamente todos os formatos, erros e limpeza das credenciais da URL. A ativação liberava a reserva mesmo quando a resposta de ativação podia ter se perdido.
5. Em produção, a solicitação pública exigia `cf-connecting-ip`, inclusive no endpoint Render. Ausência desse header causava 503; confiar nele diretamente também permitia falsificação. O sistema passa a usar o endereço normalizado pelo servidor ASGI.
6. O limite de **duas operações** estava no envio de e-mails, em `_attempt_invitation_send`, e não na Íris. O SMTP padrão Supabase realmente limita o projeto a dois e-mails/hora e destinatários da equipe. A Íris tinha outro limite: cinco/minuto e cinquenta/dia.

O `.env` local inspecionado não tinha `SUPABASE_SERVICE_ROLE_KEY`, `APP_PUBLIC_URL` ou a nova conexão administrativa. Não foram impressas credenciais. A tentativa de consulta remota somente leitura não confirmou a revisão instalada. Uma consulta HTTP pública à Vercel retornou 200 e CSP permitindo Supabase/API privada, evidência de configuração compatível com uso privado. Isso não comprova as variáveis do build: **a classificação final de `investment-dashboard-pvd.vercel.app` exige conferir o projeto e as variáveis Vercel**. O health Render não foi confirmado na consulta de rede. Não usar um domínio como redirect apenas pelo seu nome ou uso histórico.

## Responsabilidades e arquitetura

| Componente | Responsabilidade |
| --- | --- |
| Supabase Auth | Identidade, confirmação do e-mail, senha, sessões e JWT. Uma sessão Auth não concede acesso financeiro. |
| PostgreSQL | Concessões, convite vinculado ao e-mail/identidade, período de teste, solicitações, revogação e auditoria. |
| FastAPI | Verifica JWT/JWKS e confirmação Auth; aplica autorização a cada chamada privada; reserva concessões e executa tentativas de envio duráveis. |
| React | Consome callback explicitamente, remove credenciais da URL, reserva ativação, define senha e confirma acesso no backend. Exibe estados reais das três abas. |

Antes, autorização e envio estavam acoplados por compensações. Agora, a aprovação e o convite exato são gravados **na mesma transação**, antes da chamada externa. A tentativa de envio é registrada e confirmada em outra transação. Há uma caixa de saída durável representada pelo convite e pelo histórico de tentativas; o despacho é síncrono e o retry é administrativo, sem fila, cron ou infraestrutura extra. Não há reenvio automático depois de timeout.

`supabase_invitations.py` concentra o contrato HTTP do provedor, a URL de callback e os códigos de erro permitidos. Corpos livres de erro, tokens e links de uso único nunca entram na auditoria. Erro de rede, interrupção e HTTP 5xx são tratados conservadoramente como resultado incerto.

## Estados e transições

| Entidade | Estados / transições |
| --- | --- |
| Solicitação | `pending → approved` ou `pending → rejected`. Aprovação já registrada é idempotente e não reenvia. A 017 reconcilia `approving` legado: com convite vinculado preserva a concessão como aprovada; sem convite retorna a pendente. |
| Convite | `pending → accepted`, `pending → revoked`, ou expiração derivada de `expires_at`. Revogar convite aceito é proibido; revogar acesso é ação da aba Contas. |
| Tentativa | `started → requested`, `started → failed`, `started → uncertain`. `requested` significa apenas HTTP aceito pelo Supabase. `started` por mais de cinco minutos é mostrado como incerto; um reenvio controlado persiste a classificação. |
| Membership | `active` permanente ou trial; `revoked` persistido; `expired` derivado da data. Nenhum job é necessário para bloquear o teste expirado. |
| Trial | Não iniciado enquanto só existir convite. A ativação grava `activated_at` e `access_expires_at = activated_at + 168h`. Novo período exige convite administrativo direcionado à identidade existente. |
| Sessão/UI | Sem sessão → identidade verificada → autorização confirmada → carteira. Conta revogada/sem convite é bloqueada. Trial expirado mantém a área de privacidade. Erro de infraestrutura bloqueia a carteira e informa a falha de confirmação. |

Expiração e revogação não removem a identidade Auth nem dados financeiros. A revogação passa a valer na próxima chamada privada, mesmo que o JWT ainda seja válido. Cada chamada exige membership ativa no backend.

## Fluxos novos e existentes

1. **Visitante:** POST público cria solicitação pendente; nunca cria membership ou identidade Auth. A resposta é neutra e idêntica para solicitações novas, duplicadas e limitadas, para impedir enumeração. Limites atuais: três solicitações/IP/dia e cem tentativas globais/dia, persistidos no PostgreSQL. Solicitação já aprovada não se renova pelo formulário; o administrador deve agir pela aba Contas.
2. **Aprovação:** reserva convite trial e decisão em uma transação; depois tenta enviar. Uma falha retorna erro estruturado com `invitation_id`, `email_send_status` e código seguro. A aprovação fica preservada. O administrador usa o mesmo convite na aba Convites para reenviar.
3. **Usuário novo:** `/auth/v1/invite` recebe e-mail e `redirect_to` na query. O link termina na origem privada configurada e carrega o ID do convite. Não há PKCE iniciado pelo administrador: convites por e-mail precisam funcionar no navegador do destinatário.
4. **Identidade Auth já existente sem membership:** somente se `/invite` responder explicitamente `email_exists` ou `user_already_exists`, o adaptador solicita `/recover` vinculado ao mesmo convite. O histórico registra `method=recovery`; não finge envio pelo fluxo de usuário novo. Outro erro não dispara recovery.
5. **Conta ativa:** novo convite para o e-mail já conhecido é recusado com orientação para gerenciar a conta. Uma sessão existente não reinicia teste.
6. **Conta revogada ou expirada:** ação Reativar confirma o e-mail e o UUID no Admin Auth e cria convite trial com `target_user_id`. A conta só muda ao aceitar. E-mail divergente, conta administrativa e concessão concorrente são recusados.
7. **Link usado/expirado/revogado:** não obtém nova reserva. O destinatário solicita ajuda ao administrador. Para um convite interno expirado, emitir uma nova concessão conscientemente; não estender a antiga silenciosamente.
8. **Ativação:** callback implicit (`access_token`/`refresh_token`), `token_hash` com tipo `invite`/`recovery`, ou código PKCE são consumidos explicitamente; formatos misturados são recusados. PKCE só funciona quando o navegador possui o verifier original. `getUser` valida a identidade. Backend verifica a confirmação Auth e o vínculo do convite antes de conceder uma reserva de dez minutos. Depois da senha salva, resposta de ativação perdida é recuperada repetindo a mesma reserva, sem reiniciar o teste.

## Fronteira de privilégio no PostgreSQL

A 017 cria `investment_access_admin`, **NOLOGIN**, sem superuser, bypass RLS, CREATE de schema ou privilégios financeiros. O backend administrativo usa um **login distinto**, membro desse grupo. O runtime não pode integrar esse grupo, nem executar revogação/reativação privilegiadas. Alterar `app.admin_id` na conexão comum deixa de conceder administração.

`dashboard_admin_authorized()` exige membership do **`session_user` real** no grupo e UUID presente em `account_access_administrators`. A lista protegida é inicialmente preenchida por `INVITATION_ADMIN_IDS` da sessão da migration. O backend ainda exige UUID permitido e membership ativa, e recusa conexão administrativa com superuser, bypass, criação de roles/bancos, acesso financeiro ou UPDATE direto de memberships. `ADMIN_DATABASE_URL` deve apontar ao mesmo endpoint/banco de `DATABASE_URL`, com outro login e TLS `verify-full`.

Funções restritas usam `SECURITY DEFINER` e `search_path=pg_catalog,public`; o executor só recebe CREATE e membership SET temporários durante a migration. A auditoria `account_access_audit` permite INSERT/SELECT administrativos e não UPDATE/DELETE. Não há credenciais criadas pela migration.

Provisionamento manual futuro, pela conexão DDL autorizada, usando senha forte fornecida fora do Git e sem expô-la em logs:

```sql
CREATE ROLE investment_access_operator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS INHERIT;
-- Configure a senha por mecanismo seguro do cliente/gestor de segredos.
GRANT CONNECT ON DATABASE postgres TO investment_access_operator;
GRANT investment_access_admin TO investment_access_operator;
-- Nunca conceder este grupo a investment_runtime, anon, authenticated ou service_role.
```

Use conexão direta ou Session Pooler com esse login real. Não usar a conexão `postgres`, a credencial DDL ou uma conexão compartilhada que mude apenas `SET ROLE`. Configurar o login não autoriza publicações nem executa migrations automaticamente. Mudanças futuras de administradores precisam atualizar tanto `INVITATION_ADMIN_IDS` quanto o registro protegido pela conexão DDL autorizada; conferir as policies de manutenção do registro na 017.

## Configuração de frontend e Supabase

Primeiro classifique os projetos Vercel. Privado: `VITE_APP_MODE=private`, `VITE_PUBLIC_DEMO=false`, `VITE_AUTH_MODE=supabase`, URL/chave publishable Supabase e API privada. Demo: modo público, dados fictícios e nenhuma credencial/API financeira. A API pública de solicitação de acesso, se habilitada na demo, usa configuração própria e expõe apenas o formulário.

No Render:

```dotenv
AUTH_MODE=supabase
ENVIRONMENT=production
CORS_ORIGIN=https://DOMINIO-PRIVADO-CONFIRMADO
APP_PUBLIC_URL=https://DOMINIO-PRIVADO-CONFIRMADO
SUPABASE_URL=https://SEU-PROJETO.supabase.co
INVITATION_ADMIN_IDS=["UUID-ADMIN-CONFIRMADO"]
# DATABASE_URL: login runtime restrito; ADMIN_DATABASE_URL: login de acesso distinto.
# SUPABASE_SERVICE_ROLE_KEY: secret só no backend.
# MIGRATION_DATABASE_URL: só na sessão DDL isolada, nunca necessário no runtime.
```

No Supabase Dashboard → Authentication → URL Configuration:

- **Site URL:** origem privada confirmada, sem localhost.
- **Redirect URLs:** cadastrar a rota privada `/invite/accept`. Para um padrão explícito que inclua a query, usar `https://DOMINIO-PRIVADO-CONFIRMADO/invite/accept\?invitation_id=*`, com `?` literal escapado e sem wildcard no domínio/caminho. O [validador oficial do Auth](https://github.com/supabase/auth/blob/master/internal/utilities/request.go) também permite redirects com mesmo esquema/host/porta da Site URL; por isso corrigir a Site URL é essencial. Conferir o resultado com um convite sintético completo e preservar o ID.
- Manter signup público desabilitado e confirmação de e-mail ligada.
- Template **Invite user** e **Reset password**: usar `<a href="{{ .ConfirmationURL }}">Continuar no Investment Dashboard</a>`. Não substituir pelo `.SiteURL` isolado; ele perde a verificação e o vínculo do convite. Se customizar com TokenHash, preservar `.RedirectTo` e enviar `type=invite` no convite e `type=recovery` na recuperação.
- Verificar Auth Logs pelo horário e código, sem copiar tokens ou links ao chat. Conferir logs do SMTP separadamente. HTTP aceito não comprova caixa de entrada.
- Tokens/refresh tokens que já tenham sido compartilhados devem ser tratados como comprometidos: revogar sessões afetadas no Supabase e emitir novos links. Revogar o convite interno correspondente bloqueia a concessão antiga. Não reproduzir tokens antigos em comandos.

Referências oficiais: [redirecionamentos](https://supabase.com/docs/guides/auth/redirect-urls), [templates](https://supabase.com/docs/guides/auth/auth-email-templates), [verifyOtp](https://supabase.com/docs/reference/javascript/auth-verifyotp), [PKCE](https://supabase.com/docs/guides/auth/sessions/pkce-flow).

## E-mail e planos gratuitos

SMTP próprio é necessário para convidar destinatários externos à equipe usando Supabase hospedado. O serviço padrão é restrito a dois e-mails/hora e não oferece garantia de entrega. Configurar SMTP próprio no Supabase mantém identidade e envio nativos de Auth, sem gerar/enviar tokens manualmente. `generateLink` não envia e-mail por si só; não foi adotado porque exigiria outro transporte e tratamento de credenciais de link. [Documentação SMTP Supabase](https://supabase.com/docs/guides/auth/auth-smtp), [generateLink](https://supabase.com/docs/reference/javascript/auth-admin-generatelink).

Opções gratuitas publicadas na data da pesquisa, sujeitas a verificação na conta escolhida:

| Serviço | Cota divulgada | Condição operacional |
| --- | --- | --- |
| [Resend](https://resend.com/pricing) | 3.000/mês, 100/dia | Verificar domínio/remetente e usar credenciais SMTP próprias. |
| [Brevo](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan) | 300/dia | Ativar envio transacional, verificar remetente/domínio e observar aprovação da conta. |

Nenhum serviço foi contratado/configurado nesta tarefa. Escolher plano gratuito, desativar upgrade/overage automático quando disponível, configurar SPF/DKIM/DMARC e não habilitar tracking que reescreva links Auth. Guardar a senha SMTP somente no painel Supabase. O Supabase documenta limite inicial de 30/hora após configurar SMTP próprio; deve ser confirmado na conta antes de configurar o limite local.

Variáveis locais de proteção:

| Variável | Padrão | Regra |
| --- | --- | --- |
| `INVITATION_SMTP_MODE` | `builtin` | `custom` somente após SMTP próprio configurado. |
| `INVITATION_EMAILS_PER_HOUR` | 2 | Pode ser 30 com SMTP próprio e cota confirmada; builtin recusa valor acima de 2. |
| `INVITATION_MAX_SEND_ATTEMPTS` | 5 | Tentativas por convite, sem retry automático. |
| `INVITATION_SEND_COOLDOWN_SECONDS` | 60 | Não permite reduzir abaixo de 60. |
| `INVITATION_DAILY_LIMIT` | 50 | Concessões criadas por administrador/dia. |
| `INVITATION_PENDING_LIMIT` | 50 | Concessões simultâneas pendentes por administrador. |

Todos os limites são barreiras adicionais da aplicação e não aumentam quotas comerciais. Signup, recuperação e outras chamadas fora desse backend também consomem a quota Supabase. A Íris passa a 500/dia e 10/min para administrador, 100/dia e 5/min para usuários privados; veja [limites da Íris](assistant-limits.md). A demo mantém suas respostas locais e não consome Groq.

As concessões por administrador são limitadas transacionalmente pela configuração Python (padrão 50). A função PostgreSQL de reativação mantém um teto adicional de segurança de 500, alinhado ao maior valor permitido na configuração, sem impor o antigo limite oculto de dez.

## Operação e recuperação

Contas, Convites e Solicitações preservam paginação de cinco itens, busca e filtros. Cada listagem tolera falha nas demais. As ações têm trava de submissão duplicada e recarregam após sucesso ou erro, pois um envio pode falhar depois de a concessão ter sido gravada.

- `requested`: aguardar o destinatário e consultar logs SMTP; não afirmar entrega.
- `failed/email_address_not_authorized`: verificar SMTP padrão/equipe; trocar configuração antes de novo envio.
- `failed/over_email_send_rate_limit`: respeitar a quota do projeto; não contornar criando identidades.
- `uncertain`: verificar logs e destinatário antes do reenvio, após cooldown. O reenvio preserva a concessão interna; o provedor pode invalidar seu link anterior.
- `not_requested`: a concessão foi preparada mas o despacho não iniciou, por exemplo por quota ou interrupção; reenviar o mesmo convite quando permitido.
- `approved` sem entrega: localizar `invitation_id` na aba Convites. Não recusar/aprovar novamente para tentar disparar outro e-mail.
- `started` antigo: após cinco minutos aparece como incerto; um novo envio exige ação administrativa.
- Sem administradores visíveis: conferir login separado, membership PostgreSQL e registro protegido. Configuração inválida retorna 503, não uma listagem vazia enganosa.

Histórico de envio está em cada convite. Histórico administrativo paginado: `GET /api/admin/access-history`, com filtros opcionais `invitation_id`, `request_id`, `subject_user_id`. `GET /api/admin/access-configuration` mostra modo e limites sem segredos.

Para IPs no Render, configurar `FORWARDED_ALLOW_IPS` do Uvicorn com os proxies/redes confiáveis do ambiente e manter `--proxy-headers` habilitado; conferir o cliente normalizado com tráfego de teste. Não confiar em `cf-connecting-ip` arbitrário ou configurar `forwarded-allow-ips=*` sem uma fronteira de rede que impeça acesso direto. Se todos os visitantes aparecerem como o mesmo peer, a quota por IP será compartilhada; corrigir o proxy antes de abrir a solicitação pública. Fontes: [Uvicorn e proxies](https://uvicorn.dev/deployment/#proxies-and-forwarded-headers), [orientação Render](https://render.com/articles/fastapi-production-best-practices).

## Publicação manual futura

1. Confirmar domínio privado e projeto Supabase; consultar revisão real com conexão somente leitura. Não presumir 016. Capturar backup cifrado de **todo o schema public e dados**, funções/ACLs, e verificar restauração em PostgreSQL 17 descartável com roles sintéticas. Auth identities são geridas pelo Supabase e exigem seu procedimento próprio de recuperação.
2. Ensaiar upgrade da cópia da revisão real até 018 com role DDL proprietária sem bypass no runtime. Revisar 017/018. As migrations antigas permanecem intactas; downgrade de segurança é proibido. Não usar `stamp` para saltar revisões.
3. Fornecer `INVITATION_ADMIN_IDS` correto na sessão DDL da 017; conferir registro protegido. Provisionar login administrativo restrito e secret `ADMIN_DATABASE_URL`, mantendo `DATABASE_URL` runtime. Não trocar runtime por `postgres`.
4. Em janela aprovada, com backup/restauração já conferidos, executar manualmente pelo backend: `python -m alembic current`, `python -m alembic upgrade 018`, `python -m alembic current`. Resultado esperado 018. Uma migration aplicada antes do backend novo bloqueia temporariamente a administração antiga; coordenar ambos na mesma janela. A carteira continua submetida às mesmas memberships/RLS.
5. Publicar backend e frontend privado compatíveis; ajustar Site URL, redirects, templates, SMTP e variáveis. Conferir health, erros seguros e demo independente. Retirar credencial DDL do runtime.
6. Executar o checklist abaixo com identidades sintéticas autorizadas e e-mails controlados. Só depois declarar o fluxo real validado. Nada desta lista foi executado em produção por este trabalho.

Para backup do head 016 existe agora `backend/scripts/backup_supabase_016.py`; não usar o perfil 015 para um banco 016. Após a reconstrução, usar `backup_supabase_018.py`. Os perfis exigem revisão exata e cabeçalho autenticado correspondente (`IDBKP016`/`IDBKP018`). Os wrappers 014/015 também foram corrigidos e mantêm catálogos próprios. Use `--help` para os argumentos de saída e confirmação; o procedimento exige destino cifrado fora do repositório e credenciais de leitura na sessão administrativa segura.

## Checklist de validação real

- [ ] Revisão remota 018, RLS/FORCE RLS, funções e owners/grants conferidos.
- [ ] Runtime não assume o grupo admin, nem falsificando `app.admin_id`; login admin não lê finanças.
- [ ] Formulário público cria solicitação visível; duplicidade e abuso não criam acesso automático.
- [ ] Aprovar/recusar e repetir clique preserva decisão correta e não duplica envio.
- [ ] Usuário novo recebe link no domínio privado e define senha; entrada na carteira só após autorização.
- [ ] Identidade existente usa recuperação autorizada e mantém UUID/dados.
- [ ] Entrega comprovada no destinatário e logs, distinguida de solicitação aceita.
- [ ] Timeout/falha SMTP mantém aprovação/convite e histórico auditável, sem falso sucesso.
- [ ] Link expirado, usado, revogado ou de outra identidade é bloqueado.
- [ ] Trial começa na ativação, dura 168h e expiração bloqueia API sem apagar dados.
- [ ] Revogação bloqueia JWT ainda válido; reativação exige nova concessão administrativa.
- [ ] Administradores protegidos, dados entre contas isolados, demo sem consultas financeiras.
- [ ] Limites locais e do provedor conferidos, sem custos ou serviços pagos ativados.

## Comandos de validação local

Resultados finais: **493 testes backend aprovados, 1 opt-in ignorado na suíte comum; ensaio PostgreSQL 17 separado aprovado até 018; backup/restauração IDBKP018 aprovados; 274 testes frontend e builds público/privado aprovados**. Veja [evidências e limites da validação](validation.md#reconstrução-de-acesso--03112026-local-não-publicada). Entrega e configuração Supabase reais continuam pendentes do checklist operacional.

```powershell
Set-Location C:\Users\IAN\ProjetosVSCode\investment-dashboard\backend
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\check_access_configuration.py
# Opcional, somente metadados em transação read-only; não imprime credenciais:
.venv\Scripts\python.exe scripts\check_access_configuration.py --connect-read-only
New-Item -ItemType Directory -Force .tmp\access-validation | Out-Null
$env:INVESTMENT_TEMP_DIR = (Resolve-Path .tmp\access-validation).Path
.venv\Scripts\python.exe tests\run_postgres.py
Set-Location ..\frontend
npm test
npm run build
```

No Windows restrito, os testes assíncronos podem exigir execução fora da sandbox para criar o loop de eventos. Os testes usam apenas PostgreSQL descartável e respostas contratuais fictícias, sem destinatários reais.

## Arquivos principais da reconstrução

| Área | Arquivos |
| --- | --- |
| Autorização e concessões | `backend/app/accounts.py`, `auth.py`, `database.py`, novo `supabase_invitations.py` |
| Schema | novas `017_access_administration_boundary.py` e `018_assistant_request_quotas.py`; revisões antigas preservadas |
| Íris | `backend/app/assistant.py`, `tests/test_assistant.py`, novo `tests/assistant_quota_postgres.py` |
| Contratos e integração | novo `tests/test_access_reconstruction.py`, novo `tests/rebuilt_access_postgres.py`; `test_accounts.py`, `test_trial_access.py`, `test_postgres.py`, `conftest.py`, `run_postgres.py`, `verify_backup_restore.py` |
| Backups/diagnóstico | novos `scripts/backup_profiles.py`, `backup_supabase_016.py`, `backup_supabase_018.py`, `check_access_configuration.py`; `backup_archive.py`, wrappers 014/015, `tests/restore_supabase_backup.py`, novo `test_backup_supabase_018.py` |
| Callback e sessão | `frontend/src/App.tsx`, `api.ts`, `auth/supabase.ts`, `useAuth.ts`, `InvitePasswordPage.tsx`; novos `InviteAcceptPage.tsx` e `invitationCallback.ts`, com testes correspondentes e `auth.test.tsx`/`demo.test.tsx` |
| Administração e solicitação | `frontend/src/accounts/InvitationAdmin.tsx`, `auth/AccessRequestPage.tsx` e seus testes |
| Configuração/documentação | `.env.example`, `backend/.env.production.example`, `render.yaml`, este documento, `assistant-limits.md`, `validation.md`, `security-and-invitations.md`, `v3-launch-checklist.md` |

A lista exata, incluindo todos os testes, fica no commit local: `git show --stat HEAD`. Nenhuma publicação é acionada por esse commit.
