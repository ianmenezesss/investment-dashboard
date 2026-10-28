# Render + Supabase: sequência manual de preparação

Este é o procedimento operacional para o estado informado: banco sem tabelas da aplicação,
migrações 001/002 pendentes, runtime administrativo e Pre-Deploy vazio. Não executar deploy
até concluir todas as etapas. Nenhum comando remoto deste documento foi executado pelo Codex.
Não alterar o `.env` local, não usar o Docker e não usar credenciais SQL no frontend.

## 1. Preparar certificado e ferramentas — Windows

Na pasta `backend`, usar Python do ambiente virtual com `requirements.lock.txt` instalado.
Para a definição segura de senha, também é necessário o cliente `psql` no PATH; não é necessário
instalar/iniciar um servidor PostgreSQL. Obter ferramentas de uma distribuição oficial PostgreSQL.

No Supabase, baixar o certificado CA oficial nas configurações de banco/SSL do próprio projeto.
Guardar fora do repositório, por exemplo em uma pasta privada de configuração. O arquivo deve
conter o certificado PEM (`BEGIN CERTIFICATE`), nunca uma chave privada. Usar o hostname do
Session Pooler fornecido em Connect, não um IP e não o hostname da API HTTPS.

O formato SQLAlchemy é:

```text
postgresql+psycopg://investment_runtime.PROJECT_REF:SENHA_URL_ENCODED@HOST_SESSION_POOLER:5432/postgres?sslmode=verify-full
```

São marcadores, não configuração funcional. Para a conexão administrativa, usar o usuário
administrativo mostrado em Connect. Senhas com caracteres reservados precisam de percent-encoding.
Não colocar aspas literais no valor salvo no Render. Se já houver query string, acrescentar
`&sslmode=verify-full`, sem duplicar `sslmode`. Usar apenas Session Pooler/5432 neste procedimento.

`sslmode=verify-full` valida cadeia e hostname. `PGSSLROOTCERT` aponta para a CA; também é possível
usar `sslrootcert` na URL, mas esse parâmetro tem precedência sobre a variável de ambiente.
Remover caminhos de certificado antigos da URL. O caminho Windows não pode ser reutilizado no Render.
Não presumir que a trust store do Render ou `certifi` contenha a CA necessária.

Abrir uma nova janela PowerShell, sem transcrição de terminal:

```powershell
Set-Location 'C:\Users\IAN\ProjetosVSCode\investment-dashboard\backend'
$taskPython = (Resolve-Path '.\.venv\Scripts\python.exe').Path
Get-Command psql -ErrorAction Stop
$env:PGSSLROOTCERT = (Resolve-Path (Read-Host 'Caminho do certificado CA oficial baixado')).Path
$env:PGSSLMODE = 'verify-full'
$taskSecret = Read-Host 'URL administrativa Session Pooler, psycopg e verify-full' -AsSecureString
$env:MIGRATION_DATABASE_URL = [System.Net.NetworkCredential]::new('', $taskSecret).Password
Remove-Variable taskSecret
& $taskPython -m alembic -c alembic.ini heads
& $taskPython -m alembic -c alembic.ini history --verbose
```

Sucesso: somente head `002`, histórico `001 -> 002`, CA existente e cliente psql disponível.
A URL permanece apenas no ambiente desta sessão/filhos. `DATABASE_URL` não é alterada.

## 2. Testar TLS administrativo antes de escrever — Windows

Definir o script abaixo uma única vez na mesma janela. O modo `check` faz somente consultas
e configurações transacionais. O modo `migrate` é explicitamente separado na etapa 3.
O modo `runtime` verifica a conexão restrita e não aplica migrações.

```powershell
$taskDbScript = @'
import os
from pathlib import Path
from sqlalchemy import create_engine, text, event
from sqlalchemy.engine import make_url, Engine

engine = None
stage = "configuration"
try:
    action = os.environ["PRODUCTION_DB_ACTION"]
    if action not in ("check", "migrate", "runtime"):
        raise ValueError()
    variable = "PRODUCTION_RUNTIME_URL" if action == "runtime" else "MIGRATION_DATABASE_URL"
    url = make_url(os.environ[variable])
    if (url.drivername != "postgresql+psycopg" or not url.host
        or url.host.lower() in ("localhost", "127.0.0.1", "::1")
        or url.port != 5432 or url.query.get("sslmode") != "verify-full"):
        raise ValueError()
    ca = url.query.get("sslrootcert") or os.environ.get("PGSSLROOTCERT", "")
    if not ca or not Path(ca).is_file():
        raise ValueError()
    if action != "runtime":
        options = str(url.query.get("options", "")).strip()
        url = url.update_query_dict({"options": (options + " -csearch_path=public").strip()})
    stage = "TLS/connection"
    engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 10})
    with engine.connect() as c, c.begin():
        c.execute(text("SET TRANSACTION READ ONLY"))
        c.execute(text("SET LOCAL statement_timeout = '15s'"))
        if not c.connection.driver_connection.pgconn.ssl_in_use:
            raise ValueError()
        if c.scalar(text("SELECT current_schema()")) != "public":
            raise ValueError()
        role = c.execute(text("""
            SELECT current_user AS name, r.rolsuper, r.rolbypassrls,
                   r.rolcreaterole, r.rolcreatedb, r.rolreplication
            FROM pg_roles r WHERE r.rolname=current_user
        """)).mappings().one()
        objects = dict(c.execute(text("""
            SELECT name, to_regclass('public.' || name)::text
            FROM (VALUES ('operations'),('alembic_version')) AS names(name)
        """)).tuples().all())
        print("TLS verify-full: OK; schema public: OK")
        print("role", dict(role))
        print("objects", objects)
        stage = "schema/permissions"
        if action == "runtime":
            if role["name"] != "investment_runtime" or any(
                role[key] for key in ("rolsuper", "rolbypassrls", "rolcreaterole", "rolcreatedb", "rolreplication")
            ):
                raise ValueError()
            if not objects["operations"]:
                raise ValueError()
            safe = c.scalar(text("""
                SELECT relrowsecurity AND relforcerowsecurity
                   AND NOT pg_has_role(current_user,relowner,'USAGE')
                FROM pg_class WHERE oid='public.operations'::regclass
            """))
            memberships = c.scalar(text("""
                SELECT count(*) FROM pg_auth_members
                WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)
            """))
            if not safe or memberships:
                raise ValueError()
            if c.scalar(text("SELECT has_schema_privilege(current_user,'public','CREATE')")):
                raise ValueError()
            if c.scalar(text("SELECT has_database_privilege(current_user,current_database(),'CREATE')")):
                raise ValueError()
            for privilege in ("SELECT", "INSERT", "DELETE"):
                if not c.scalar(text("SELECT has_table_privilege(current_user,'public.operations',:p)"), {"p": privilege}):
                    raise ValueError()
            for privilege in ("UPDATE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                if c.scalar(text("SELECT has_table_privilege(current_user,'public.operations',:p)"), {"p": privilege}):
                    raise ValueError()
            if not c.scalar(text("SELECT has_sequence_privilege(current_user,'public.operations_id_seq','USAGE')")):
                raise ValueError()
            if c.scalar(text("SELECT has_sequence_privilege(current_user,'public.operations_id_seq','SELECT')")):
                raise ValueError()
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                if c.scalar(text("SELECT has_table_privilege(current_user,'public.alembic_version',:p)"), {"p": privilege}):
                    raise ValueError()
            c.execute(text("SELECT set_config('app.user_id','',true), set_config('app.auth_mode','supabase',true)"))
            if c.execute(text("SELECT id FROM public.operations LIMIT 1")).first() is not None:
                raise ValueError()
            print("Runtime restrito e RLS sem identidade: OK")
        elif action == "migrate":
            # Este procedimento é especificamente para o banco inicialmente vazio.
            if any(objects.values()):
                raise ValueError()
            if not c.scalar(text("SELECT has_schema_privilege(current_user,'public','CREATE')")):
                raise ValueError()
        elif objects["alembic_version"]:
            print("revision", list(c.execute(text("SELECT version_num FROM public.alembic_version")).scalars()))
    engine.dispose()
    engine = None
    if action == "migrate":
        stage = "migration"
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        cfg = Config("alembic.ini")
        if ScriptDirectory.from_config(cfg).get_current_head() != "002":
            raise ValueError()
        os.environ["MIGRATION_DATABASE_URL"] = url.render_as_string(hide_password=False)
        def guard(connection):
            schema = connection.scalar(text("SELECT current_schema()"))
            connection.rollback()
            if schema != "public":
                raise ValueError()
        event.listen(Engine, "engine_connect", guard)
        command.upgrade(cfg, "head")
        print("Upgrade 001 -> 002 concluido; conferir no SQL Editor.")
except Exception as error:
    code = getattr(getattr(error, "orig", None), "sqlstate", None)
    print("FALHA na etapa", stage, "; SQLSTATE:", code or "indisponivel")
    print("Detalhes privados omitidos. Parar; nao repetir escrita sem conferir o estado.")
    raise SystemExit(1)
finally:
    if engine is not None:
        engine.dispose()
'@
$env:PRODUCTION_DB_ACTION = 'check'
$taskDbScript | & $taskPython -
if ($LASTEXITCODE -ne 0) { throw 'Diagnóstico falhou. Não prosseguir.' }
```

Sucesso: handshake real com `verify-full`, schema public e ambos os objetos ausentes.
Se certificado falhar, corrigir CA/hostname/caminho; não trocar para `require`.
O resultado local valida a cadeia desse endpoint com a CA explícita, não prova a rede do Render.

## 3. Aplicar 001/002 — Windows, ESCRITA REMOTA MANUAL

Antes: confirmar projeto/host/banco no painel, backup recuperável e nenhuma execução concorrente.
Se a etapa 2 mostrou objetos existentes, PARAR e consultar a revisão; este fluxo não tenta reparar drift.
O `.env` local deve continuar válido para importar Settings; o env.py usa a URL administrativa explícita
para a conexão efetiva, sem conectar ao engine local. Não executar `stamp`, `downgrade`, `--sql`
ou `--autogenerate`. Os timeouts do env.py são lock 5s e statement 30s.

```powershell
$env:PRODUCTION_DB_ACTION = 'migrate'
$taskDbScript | & $taskPython -
if ($LASTEXITCODE -ne 0) { throw 'Migração não confirmada. Conferir banco antes de repetir.' }
```

No **Supabase SQL Editor**, executar somente este diagnóstico:

```sql
SELECT version_num FROM public.alembic_version;
SELECT c.relname, pg_get_userbyid(c.relowner) AS owner,
       c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c
WHERE c.oid = 'public.operations'::regclass;
SELECT indexname, indexdef FROM pg_indexes
WHERE schemaname='public' AND tablename='operations';
SELECT policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies WHERE schemaname='public' AND tablename='operations';
SELECT rolname FROM pg_roles WHERE rolname='investment_runtime';
```

Sucesso: versão única 002, owner administrativo, RLS true/true, índice ix_operations_owner_id,
política api_owner com USING e WITH CHECK corretos; role investment_runtime ainda ausente.
Se a role já existe ou surgem políticas inesperadas, revisar antes da próxima etapa, sem excluir objetos.

## 4. Criar role e privilégios — Supabase SQL Editor, ESCRITA

Revisar primeiro as concessões padrão; as revogações seguintes atingem somente objetos da aplicação:

```sql
SELECT current_database();
SELECT pg_get_userbyid(defaclrole) AS owner, defaclnamespace::regnamespace,
       defaclobjtype, defaclacl FROM pg_default_acl;
SELECT c.relname, c.relacl FROM pg_class c
WHERE c.oid IN ('public.operations'::regclass,
               'public.alembic_version'::regclass,
               'public.operations_id_seq'::regclass);
```

Se o banco confirmado for postgres, aplicar como administrador/proprietário:

```sql
BEGIN;
CREATE ROLE investment_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS
  NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT;
GRANT CONNECT ON DATABASE postgres TO investment_runtime;
GRANT USAGE ON SCHEMA public TO investment_runtime;
REVOKE ALL ON TABLE public.operations, public.alembic_version
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SEQUENCE public.operations_id_seq
  FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, DELETE ON TABLE public.operations TO investment_runtime;
GRANT USAGE ON SEQUENCE public.operations_id_seq TO investment_runtime;
COMMIT;
```

Não conceder ownership, UPDATE, TRUNCATE, CREATE ou associação administrativa.
DELETE já permite o LOCK TABLE EXCLUSIVE utilizado pela API. USAGE permite nextval na sequência.
Não revogar globalmente USAGE/CREATE de public ou privilégios do banco: isso pode atingir outros
serviços Supabase. Se o runtime herdar CREATE de PUBLIC, o teste da etapa 6 para e exige um ajuste
específico revisado; não prosseguir nem aplicar REVOKE global automaticamente.
Não alterar default privileges globalmente neste procedimento; reavaliar ACLs após futuras migrações.

## 5. Definir senha da nova role — psql iniciado no Windows, ESCRITA

Na mesma janela PowerShell, com a CA e PGSSLMODE já definidos:

```powershell
$taskPoolerHost = Read-Host 'Host Session Pooler confirmado em Connect'
$taskAdminUser = Read-Host 'Usuário administrativo do pooler confirmado em Connect'
psql -h $taskPoolerHost -p 5432 -U $taskAdminUser -d postgres -W
```

Digitar a senha administrativa somente no prompt oculto do psql. Dentro do psql:

```text
\password investment_runtime
ALTER ROLE investment_runtime LOGIN;
\q
```

O comando `\password` solicita e confirma a nova senha sem colocá-la em comando literal/histórico.
Não usar ALTER ROLE PASSWORD com senha literal no SQL Editor. Não reutilizar a senha administrativa.

## 6. Testar runtime antes de configurar Render — Windows, leitura

Montar a URL com usuário `investment_runtime.PROJECT_REF`, mesmo projeto/banco e Session Pooler.
A role SQL é investment_runtime; o sufixo PROJECT_REF pertence ao roteamento do pooler.

```powershell
$taskSecret = Read-Host 'URL remota da nova role, psycopg e verify-full' -AsSecureString
$env:PRODUCTION_RUNTIME_URL = [System.Net.NetworkCredential]::new('', $taskSecret).Password
Remove-Variable taskSecret
$env:PRODUCTION_DB_ACTION = 'runtime'
$taskDbScript | & $taskPython -
if ($LASTEXITCODE -ne 0) { throw 'Runtime reprovado. Não configurar nem publicar.' }
```

Sucesso: TLS OK, papel investment_runtime sem atributos administrativos, sem memberships,
sem CREATE e ownership, RLS forçada, privilégios mínimos e nenhuma linha sem contexto de identidade.
Tabela vazia não comprova isolamento entre dois usuários; testes com fixtures devem ser feitos em
PostgreSQL separado de homologação, nunca criando operações de teste na carteira pessoal.

## 7. Configurar tudo junto — painel Render, sem deploy durante a preparação

Environment -> Secret Files: criar `supabase-ca.crt` contendo o PEM oficial baixado na etapa 1.
No serviço Python nativo o arquivo estará em `/etc/secrets/supabase-ca.crt`.

Salvar as variáveis com **Save only**:

| Variável | Valor necessário |
| --- | --- |
| DATABASE_URL | URL da role investment_runtime testada, com postgresql+psycopg e sslmode=verify-full |
| PGSSLROOTCERT | /etc/secrets/supabase-ca.crt |
| ENVIRONMENT | production |
| AUTH_MODE | supabase |
| SUPABASE_URL | URL HTTPS raiz do mesmo projeto Auth, sem barra final ou /auth/v1 |
| ALLOWED_USER_IDS | Lista JSON de UUIDs reais autorizados, ex.: ["UUID-REAL"] |
| CORS_ORIGIN | Origem HTTPS exata do frontend privado, sem caminho/barra final |

Retirar MIGRATION_DATABASE_URL do runtime, se existir, sem alterar o .env local.
Não precisa de API_TOKEN, senha SQL do usuário final, service_role ou segredo JWT simétrico.
Settings: Root Directory backend; Build `pip install -r requirements.lock.txt && pip install --no-deps .`;
Start `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log`;
Health Check `/health`; Pre-Deploy **vazio**. O render.yaml foi ajustado para não aplicar migrations.
Alterações no YAML local não mudam automaticamente um serviço configurado manualmente.

Se Shell estiver disponível no serviço, após a configuração entrar efetivamente em vigor,
validar a conexão com o ambiente real (não imprimir a URL):

```bash
python - <<'PY'
from app.database import SessionLocal, ensure_production_role
from sqlalchemy import text
with SessionLocal() as db:
    assert db.scalar(text('SELECT 1')) == 1
    assert db.connection().connection.driver_connection.pgconn.ssl_in_use
    ensure_production_role(db)
print('TLS e role de producao: OK')
PY
```

Este teste é Bash no Shell do Render, não PowerShell. Sem Shell, o primeiro /health da execução
futura será a confirmação de rede/arquivo CA dentro do Render. Não foi possível confirmar isso
remotamente nesta sessão. Save only ainda não altera o ambiente de um processo já em execução.
Uma publicação manual futura é a última etapa do operador; nenhuma foi executada ou agendada.

## 8. Aceitação após a publicação manual futura

- /health: HTTP 200; sem token em /api/operations: 401.
- Login Supabase real autorizado: leitura privada 200; carteira vazia é válida.
- Token expirado/inválido: 401; conta fora da allowlist: 403.
- JWT ES256/RS256 e kid válido; JWKS acessível. HS256 não é aceito por este backend.
- Frontend usa o domínio correto da API e envia Authorization Bearer; CORS não autoriza previews automaticamente.
- Demonstração continua independente da API privada.

| Sintoma | Causa a resolver antes de tentar novamente |
| --- | --- |
| Erro atual de produção/TLS ao importar Settings | sslmode ausente ou diferente de verify-full na URL efetiva |
| Erro de PostgreSQL/psycopg em Settings | Prefixo postgres:// ou postgresql:// em vez de postgresql+psycopg:// |
| Settings falha por Supabase/CORS | URL com caminho/barra final, UUID inválido/lista vazia, modo ou origem incorretos |
| CA não encontrada/certificate verify failed/hostname mismatch | Secret File/caminho/CA incorretos ou host diferente do certificado |
| Timeout/DNS/autenticação SQL | Host/porta/rede/senha codificada/usuário pooler incorretos, role sem LOGIN ou conexão excedida |
| /health 503, operations ausente | Migrações pendentes, banco errado ou schema errado |
| /health 503, acesso requer revisão | Runtime owner/superuser/BYPASSRLS ou RLS não habilitada/forçada |
| /health 200 mas operação falha | /health não confere todos os GRANTs, sequência ou JWT; executar etapa 6 e leitura autenticada |
| JWT 401/403/503 | Sessão/issuer/audience/assinatura/allowlist incorretos ou JWKS indisponível |
| Alembic falha antes da conexão remota | Settings local inválido; corrigir a configuração local legitimamente, sem trocar sua DATABASE_URL |
| Upgrade interrompido por lock/statement timeout | Conferir versão/objetos/concorrência antes de repetir; nunca apagar objetos ou usar stamp |

Ao terminar, fechar a janela ou limpar variáveis temporárias:

```powershell
Remove-Item Env:MIGRATION_DATABASE_URL,Env:PRODUCTION_RUNTIME_URL,Env:PRODUCTION_DB_ACTION,Env:PGSSLROOTCERT,Env:PGSSLMODE -ErrorAction SilentlyContinue
Remove-Variable taskDbScript -ErrorAction SilentlyContinue
```

## Referências oficiais

- https://supabase.com/docs/guides/database/psql
- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://supabase.com/kb/troubleshooting/disabling-prepared-statements-qL8lEL
- https://www.postgresql.org/docs/current/libpq-ssl.html
- https://www.postgresql.org/docs/current/sql-lock.html
- https://render.com/docs/configure-environment-variables
