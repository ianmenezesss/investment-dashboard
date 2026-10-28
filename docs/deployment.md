# Preparação para GitHub, Vercel, Render e Supabase

Não executar deploy como parte da Fase 1.5. Os arquivos são modelos revisáveis; não há serviços remotos criados ou credenciais externas configuradas.

Atualização 1.6: login Supabase no frontend foi implementado. A configuração e os testes manuais locais estão em [supabase-auth.md](supabase-auth.md). O projeto Supabase foi criado pelo proprietário, mas não foi configurado automaticamente no checkout. Nenhum deploy ou push foi executado nesta etapa.

## GitHub público

Na raiz, depois de revisar os arquivos:

```powershell
backend\.venv\Scripts\python.exe scripts/audit_publication.py
git init -b main
git add .
git status --short
git diff --cached --stat
git diff --cached --name-only
backend\.venv\Scripts\python.exe scripts/audit_publication.py
```

Confira que `.env`, backups, logs, exportações, bancos e diretórios privados não aparecem na lista. Revise o conteúdo staged localmente sem compartilhá-lo no chat. O `.gitignore` não protege arquivos já rastreados. Se houver um segredo rastreado ou no histórico, interrompa a publicação e planeje a remoção e rotação; não reescreva o histórico automaticamente.

Após a revisão, crie um repositório vazio no GitHub e substitua os marcadores abaixo:

```powershell
git commit -m "Prepare public demo and private investment API"
git remote add origin https://github.com/SEU_USUARIO/investment-dashboard.git
git push -u origin main
```

Esses comandos não foram executados automaticamente. Ative secret scanning e push protection disponíveis para o repositório público. A CI usa somente fixtures e um container PostgreSQL efêmero; não cadastre seus segredos pessoais como necessários aos testes.

## Vercel: somente a demonstração pública

- Root Directory: `frontend`.
- Framework: Vite; instalação: `npm ci`; build: `npm run build`; saída: `dist`.
- Variáveis: `VITE_PUBLIC_DEMO=true` para clareza operacional. Nenhum token, senha, URL privada ou chave Supabase é necessário.
- `frontend/vercel.ts` seleciona a configuração por projeto. O modelo `frontend/vercel.public.json` preserva o rewrite React Router e os headers públicos, incluindo CSP sem conexões de rede. Veja [publicação privada](private-frontend-production.md).
- O código usa demonstração por padrão em produção. Desde a Fase 1.6, um projeto privado separado pode habilitar explicitamente `VITE_APP_MODE=private` e configurar Supabase; `VITE_PUBLIC_DEMO=true` continua forçando demonstração. A CSP privada deve ser revisada pelo modelo separado, sem alterar a configuração pública.
- Preview deployments também devem usar apenas demonstração. Não cadastrar segredos em variáveis `VITE_*`: são incorporadas ao JavaScript público.

Verificar rotas `/`, `/acoes` e `/historico` em refresh, identificação visual de demonstração, exportação fictícia e zero chamadas à API. Não apontar um rewrite da demonstração para o backend pessoal.

## Supabase: configuração externa pendente

1. Criar um projeto separado do banco local. Não importar os investimentos reais nesta preparação.
2. Configurar assinatura assimétrica (ES256 ou RS256). O backend usa o JWKS do projeto em `/auth/v1/.well-known/jwks.json`, valida issuer `/auth/v1`, audience `authenticated`, expiração e role. Tokens legados HS256 não são aceitos.
3. Desativar novas inscrições públicas em Auth. Criar manualmente somente as contas autorizadas, usando login por e-mail/senha. Não disponibilizar formulário público de cadastro.
4. Preencher `ALLOWED_USER_IDS` como uma lista JSON de UUIDs dessas contas, não e-mails enviados pelo cliente. Nenhuma conta fora da lista é autorizada mesmo com JWT válido.
5. Escolher conexão direta ou session pooler compatível com IPv4 do host e configurar TLS com `sslmode=verify-full` e certificado raiz apropriado (`PGSSLROOTCERT` quando exigido). Testar certificado e hostname; não reduzir a verificação para contornar erros.
6. Separar o papel de migrations (DDL) do papel de runtime (DML). O runtime não pode ser proprietário de `operations`, superusuário ou BYPASSRLS. Não usar credenciais administrativas como runtime.
7. Aplicar migrations num banco de homologação e verificar a RLS antes de qualquer dado real. A tabela deve ter RLS habilitada e forçada. O contexto de proprietário é definido somente pela API; não há acesso financeiro direto do navegador via PostgREST.

Concessões mínimas ao papel de runtime, substituindo o nome por um papel criado e protegido pelo administrador:

```sql
GRANT USAGE ON SCHEMA public TO investment_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.operations TO investment_runtime;
GRANT USAGE, SELECT ON SEQUENCE public.operations_id_seq TO investment_runtime;
```

Não usar `GRANT ALL`, não conceder DDL ao runtime e não expor credenciais SQL. Os UUIDs legados permanecem nulos, e não são acessíveis por identidades Supabase. A atribuição de registros reais a uma identidade deve ser uma operação separada, explicitamente autorizada e conferida com backup.

## Render: backend privado preparado, ainda não ativado

`render.yaml` declara build Python, comando Uvicorn, health check e ausência de deploy automático. Revise o schema e a disponibilidade de pre-deploy no plano escolhido antes de importar o Blueprint. `preDeployCommand` pode exigir plano compatível; se indisponível, executar a migração como etapa controlada separada antes de iniciar o serviço.

Variáveis do backend:

| Variável | Uso |
| --- | --- |
| `ENVIRONMENT=production` | Restrições de produção e documentação HTTP desativada |
| `AUTH_MODE=supabase` | JWT obrigatório; token local não aceito |
| `DATABASE_URL` | Conexão TLS do papel restrito, segredo exclusivo do backend |
| `MIGRATION_DATABASE_URL` | Conexão TLS do papel de DDL, somente para migração |
| `SUPABASE_URL` | Origem HTTPS do projeto, sem caminho ou barra final |
| `ALLOWED_USER_IDS` | Lista JSON das contas previamente autorizadas |
| `CORS_ORIGIN` | Uma origem HTTPS exata da futura interface privada, sem barra final |
| `PGSSLROOTCERT` | Caminho do certificado raiz quando necessário |

Não configurar `API_TOKEN` no modo de produção. Não são necessárias service role keys nem segredos de assinatura JWT: a API consulta apenas chaves públicas JWKS. As senhas de banco devem ficar no gerenciador de ambiente do provedor.

Idealmente executar migrations em pipeline/processo separado para não manter a credencial de DDL no processo de runtime. O Blueprint apresenta o pre-deploy como alternativa operacional; revise a disponibilidade e o escopo de segredos antes de ativá-lo.

Comandos previstos:

```text
pip install -r requirements.lock.txt
pip install --no-deps .
python -m alembic upgrade head
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log
```

O proxy do provedor deve terminar TLS; não expor HTTP direto publicamente. A API envia HSTS em produção. CORS não substitui autenticação: todas as rotas financeiras continuam protegidas. O health check não divulga registros nem credenciais e falha se a conexão, o papel de runtime ou a RLS estiverem incorretos.

## Condições para ativação futura

Homologar o login por e-mail/senha implementado na Fase 1.6, testar o fluxo real de JWKS e rotação de chaves, validar SSL e rede entre Render/Supabase, verificar inscrições bloqueadas, testar dois usuários e negações, preparar backup/restauração, revisar limites de requisição e confirmar as configurações de logs. O seletor `frontend/vercel.ts` preenche as origens do modelo privado a partir das variáveis do projeto, conforme [publicação privada](private-frontend-production.md).

A Fase 2 deve começar com regressão da persistência local, concluir o fluxo privado de autenticação em homologação e só então evoluir ações/cotações/proventos. Não acrescentar CDBs antes de validar essa fronteira de segurança.

Fontes oficiais consultadas para os modelos: [JWT Supabase](https://supabase.com/docs/guides/auth/jwts), [chaves de assinatura](https://supabase.com/docs/guides/auth/signing-keys), [Blueprint Render](https://render.com/docs/blueprint-spec), [health checks](https://render.com/docs/health-checks), [configuração Vercel](https://vercel.com/docs/project-configuration) e [rewrites](https://vercel.com/docs/routing/rewrites). As opções externas devem ser reconferidas antes da ativação.
