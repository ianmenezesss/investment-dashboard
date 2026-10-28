# Fase 1.7.3 — migrações de produção, execução manual

> Para a preparação atual do Render com CA explícita, role restrita e comandos PowerShell,
> siga a sequência única em [render-supabase-setup.md](render-supabase-setup.md).
> Este documento preserva a análise anterior. O `preDeployCommand` citado adiante foi
> removido do `render.yaml`; migrações são manuais. Os GRANTs mínimos atuais são
> SELECT/INSERT/DELETE na tabela e USAGE na sequência, conforme o novo procedimento.

## Estado confirmado e limite da inspeção

O checkout possui a cadeia `base -> 001 -> 002 (head)`, confirmada com `alembic heads` e `history --verbose`. A conexão do `.env` local continua local e não existe MIGRATION_DATABASE_URL disponível neste checkout. Nenhuma credencial de produção foi solicitada, impressa ou alterada. Não foi possível consultar o PostgreSQL remoto a partir desta sessão: tabelas, revisão e permissões reais em produção continuam **pendentes do diagnóstico abaixo**.

Não foram executadas migrações, grants, alterações de políticas, deploy ou push. Somente este procedimento foi acrescentado à documentação; nenhum código de aplicação/migração foi alterado.

Um `/health` HTTP 200 não comprova a revisão Alembic. Neste checkout, com `ENVIRONMENT=production`, o health também consulta `public.operations`, exige RLS habilitada/forçada e rejeita conexão que seja proprietária da tabela, superusuário ou BYPASSRLS. Portanto, se esse código/configuração forem os mesmos do Render, 200 sugere que a tabela já existe e essas verificações passaram. Se a tabela não existir, investigar versão publicada ou ENVIRONMENT: não assumir banco vazio.

## Compatibilidade das revisões

| Arquivo | Efeito de upgrade | Pré-requisitos |
| --- | --- | --- |
| `001_operations.py` | Cria operations, PK e sequência de ID; NUMERIC(20,8), datas e timestamp com timezone | USAGE/CREATE no schema de destino; nome operations livre |
| `002_ownership.py` | Acrescenta owner_id UUID nulo e índice; habilita e força RLS; cria política api_owner | Revisão 001 íntegra; conexão proprietária da tabela ou com privilégios efetivos de proprietário; nomes da coluna/índice/política ainda livres |

Esses recursos são compatíveis com PostgreSQL do Supabase e não exigem superusuário nem extensão UUID (o UUID é recebido da autenticação). A 002 não atribui registros a usuários, não muda valores financeiros e não apaga políticas. Não cria roles ou GRANTs. `GRANT ALL` não substitui a propriedade exigida por ALTER TABLE/CREATE POLICY.

As instruções de criação são não qualificadas por schema. O schema efetivo deve ser **public**, pois o backend verifica `public.operations`. O procedimento abaixo fixa search_path na conexão de migração, sem alterar configurações globais ou DATABASE_URL.

`env.py` usa MIGRATION_DATABASE_URL quando preenchida e, se ausente, cai em DATABASE_URL. Define lock_timeout=5s e statement_timeout=30s. PostgreSQL usa DDL transacional, e esse env abre uma transação para a execução da cadeia. Em banco novo, aplicar direto até head; não parar em 001, que ainda não habilita RLS. Timeouts podem interromper índice/ALTER em tabela grande: não aumentar limites automaticamente nem executar processos concorrentes.

O env atual não implementa um ramo offline específico. Não tratar `upgrade --sql` como dry run seguro. Não usar `stamp head` para ocultar divergências. Não usar `revision --autogenerate` contra produção: o metadata contém somente operations e não deve dirigir alterações em tabelas do Supabase ou de outros aplicativos. `alembic check` global também pode reportar tabelas alheias como divergências.

## 1. Escolher conexão e ambiente

Preferir conexão direta do painel **Connect** do Supabase para migrations. Se a máquina só tiver IPv4 e a conexão direta não estiver disponível, usar o **Session pooler**, com host e usuário exatamente como fornecidos pelo projeto. Não usar Transaction pooler/porta 6543 neste procedimento: os SET de sessão do env.py são feitos antes da transação da migração e precisam permanecer na mesma sessão.

Usar `postgresql+psycopg://` e TLS `sslmode=verify-full`, com certificado raiz validável e PGSSLROOTCERT quando necessário. Não trocar por require para contornar erro de certificado. O usuário/host do pooler pode diferir da conexão direta; não deduzir esses valores nem usar service_role/publishable key como senha SQL. Comparar privadamente que as conexões DDL e runtime pertencem ao mesmo projeto/banco.

Executar no mesmo commit de aplicação publicado, dentro da pasta **backend**, onde estão alembic.ini e migrations/. No Shell do Render, conferir:

```bash
pwd
test -f alembic.ini && test -f migrations/env.py
python -m alembic -c alembic.ini heads
python -m alembic -c alembic.ini history --verbose
```

Head esperado: somente `002`. Se o shell abrir na raiz do repositório, executar `cd backend` primeiro. Conferir a versão publicada no painel Render, especialmente se diferir do checkout local. Não iniciar deploy para realizar essa conferência.

Shell/SSH e pre-deploy têm restrições de plano no Render. Se não houver Shell, usar a cópia local auditada no ambiente virtual, conectando **somente MIGRATION_DATABASE_URL** ao remoto. Não executar SQL de upgrade manualmente pelo SQL Editor para depois usar stamp.

Para informar conexão DDL apenas à sessão Bash, sem colocá-la no histórico:

```bash
read -r -s -p "URL SQL DDL do banco de produção (entrada oculta): " MIGRATION_DATABASE_URL
printf '\n'
export MIGRATION_DATABASE_URL
```

No Render, DATABASE_URL já representa o runtime remoto. No diagnóstico local, se também quiser verificar o papel real de runtime, fornecer uma variável separada, sem substituir DATABASE_URL:

```bash
read -r -s -p "URL SQL de runtime de produção (entrada oculta): " PRODUCTION_RUNTIME_URL
printf '\n'
export PRODUCTION_RUNTIME_URL
```

No PowerShell local, dentro de backend, usar o executável `.\.venv\Scripts\python.exe` no lugar de `python`. Para fornecer as URLs somente ao processo/filhos:

```powershell
$taskDdlSecret = Read-Host 'URL SQL DDL de produção' -AsSecureString
$env:MIGRATION_DATABASE_URL = [System.Net.NetworkCredential]::new('', $taskDdlSecret).Password
$taskRuntimeSecret = Read-Host 'URL SQL de runtime de produção' -AsSecureString
$env:PRODUCTION_RUNTIME_URL = [System.Net.NetworkCredential]::new('', $taskRuntimeSecret).Password
```

Os blocos Python seguintes usam heredoc Bash. No PowerShell, usar o mesmo conteúdo entre `@'` e `'@ | .\.venv\Scripts\python.exe -`. Não editar `.env` local, não imprimir env e não colocar URLs em comandos versionados, prints, screenshots ou no chat.

## 2. Diagnóstico exclusivamente de leitura

Executar no ambiente com as URLs de produção disponíveis. Não importa settings da aplicação, não executa env.py e usa transações READ ONLY. Exibe somente metadados e permissões, sem linhas financeiras ou credenciais.

```bash
python - <<'PY'
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

targets = {
    'migration': os.environ.get('MIGRATION_DATABASE_URL'),
    'runtime': os.environ.get('PRODUCTION_RUNTIME_URL') or os.environ.get('DATABASE_URL'),
}
for label, value in targets.items():
    print(f'--- {label} ---')
    if not value:
        print('PENDENTE: conexão não fornecida; papel não verificado')
        continue
    engine = None
    try:
        url = make_url(value)
        if url.drivername != 'postgresql+psycopg' or not url.host or url.host in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('Conexão remota explícita exigida')
        if url.query.get('sslmode') != 'verify-full':
            raise ValueError('TLS com verificação completa exigido')
        engine = create_engine(url, hide_parameters=True, connect_args={'connect_timeout': 5})
        with engine.connect() as c, c.begin():
            c.execute(text('SET TRANSACTION READ ONLY'))
            c.execute(text("SET LOCAL statement_timeout = '15s'"))
            queries = {
                'connection_role': """SELECT current_database() AS database, current_user AS role,
                    current_setting('search_path') AS search_path, current_schema() AS active_schema,
                    has_database_privilege(current_user,current_database(),'CONNECT') AS can_connect,
                    has_schema_privilege(current_user,'public','USAGE') AS schema_usage,
                    has_schema_privilege(current_user,'public','CREATE') AS schema_create,
                    r.rolsuper, r.rolbypassrls, r.rolcreaterole, r.rolcreatedb
                    FROM pg_roles r WHERE r.rolname=current_user""",
                'public_tables': """SELECT c.relname, c.relkind, pg_get_userbyid(c.relowner) AS owner
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m') ORDER BY c.relname""",
                'application_objects': """SELECT c.relname, c.relkind,
                    pg_get_userbyid(c.relowner) AS owner, c.relrowsecurity, c.relforcerowsecurity,
                    c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) AS direct_owner,
                    pg_has_role(current_user,c.relowner,'USAGE') AS effective_owner_membership
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='public' AND c.relname IN
                    ('operations','alembic_version','operations_id_seq','ix_operations_owner_id')
                    ORDER BY c.relname""",
                'columns': """SELECT c.relname, a.attname,
                    format_type(a.atttypid,a.atttypmod) AS type, a.attnotnull,
                    pg_get_expr(d.adbin,d.adrelid) AS default_expression
                    FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
                    WHERE n.nspname='public' AND c.relname IN ('operations','alembic_version')
                    AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum""",
                'indexes': """SELECT indexname,indexdef FROM pg_indexes
                    WHERE schemaname='public' AND tablename='operations'""",
                'policies': """SELECT policyname,permissive,roles,cmd,qual,with_check
                    FROM pg_policies WHERE schemaname='public' AND tablename='operations'""",
                'grants': """SELECT grantee,table_name,privilege_type FROM information_schema.table_privileges
                    WHERE table_schema='public' AND table_name IN ('operations','alembic_version')
                    ORDER BY table_name,grantee,privilege_type""",
            }
            for name, sql in queries.items():
                print(name, [dict(row) for row in c.execute(text(sql)).mappings()])
            if c.scalar(text("SELECT to_regclass('public.alembic_version')")):
                if c.scalar(text("SELECT has_table_privilege(current_user,'public.alembic_version','SELECT')")):
                    print('revision', list(c.execute(text('SELECT version_num FROM public.alembic_version')).scalars()))
                else:
                    print('revision: tabela existe, sem SELECT para este papel')
            else:
                print('revision: tabela alembic_version ausente')
            for table in ('operations', 'alembic_version'):
                exists = c.scalar(text('SELECT to_regclass(:name)'), {'name': 'public.' + table})
                if exists:
                    for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE'):
                        allowed = c.scalar(text('SELECT has_table_privilege(current_user,:name,:privilege)'),
                            {'name': 'public.' + table, 'privilege': privilege})
                        print(f'{table}.{privilege}', allowed)
            sequence = c.scalar(text("SELECT to_regclass('public.operations_id_seq')"))
            if sequence:
                for privilege in ('USAGE','SELECT'):
                    print('sequence.' + privilege, c.scalar(text("SELECT has_sequence_privilege(current_user,'public.operations_id_seq',:p)"), {'p': privilege}))
    except Exception as error:
        # Não imprimir repr/str do erro: podem conter DSN ou detalhes privados.
        code = getattr(getattr(error, 'orig', None), 'sqlstate', None)
        print('FALHA: diagnóstico não concluído; SQLSTATE:', code or 'não disponível')
        print('Não aplicar migrações até revisar conexão, TLS, schema e permissões.')
    finally:
        if engine is not None:
            engine.dispose()
PY
```

O SQL Editor do Supabase pode consultar os catálogos acima, mas seu current_user normalmente é administrativo. Isso **não comprova** os privilégios da conexão usada no Render: verificar com a URL real de runtime e a URL DDL.

## 3. Decidir se é seguro prosseguir

| Estado observado | Decisão |
| --- | --- |
| operations e alembic_version ausentes | Banco da aplicação ainda não inicializado; pode planejar 001+002 juntas após validar roles/schema/backup |
| alembic_version vazia e operations ausente | Tratar como base, verificando a estrutura da tabela de versão |
| Revisão única 001 e operations exatamente com colunas da 001, sem owner_id/índice/política api_owner | Planejar somente a evolução 002; revisar qualquer política já existente antes |
| Revisão única 002, coluna/índice/política e RLS corretos | Não há migração pendente; não recriar tabelas nem políticas |
| operations existe sem revisão, revisão desconhecida/múltipla, versão incompatível com estrutura, objeto em outro schema ou nomes conflitantes | PARAR. Diagnosticar drift; não apagar, não usar stamp e não aplicar scripts cegamente |

Outras tabelas legítimas do Supabase não significam conflito. Não tocá-las. É a existência/estrutura dos objetos da aplicação que decide o caminho.

Para o papel DDL: CONNECT no banco e USAGE em public; CREATE em public se precisar criar operations ou alembic_version; se houver operations, ser seu proprietário efetivo para a 002; se houver alembic_version, poder lê-la e inserir/atualizar/excluir seu marcador. Se o papel não for proprietário direto, confirmar com o administrador a herança/SET ROLE necessária antes de continuar; não conceder privilégios automaticamente.

Para o runtime: USAGE em public, SELECT/INSERT/UPDATE/DELETE em operations e USAGE/SELECT na sequência; não ser proprietário direto, superusuário ou BYPASSRLS. Evitar também herança de papéis administrativos, CREATE/DDL e TRUNCATE desnecessários. RLS deve estar habilitada e forçada. A política api_owner deve comparar owner_id com app.user_id, permitindo nulos apenas quando app.auth_mode=local; a API em produção usa supabase e define essas variáveis com escopo transacional.

Políticas permissivas adicionais combinam-se com OR e podem ampliar acesso; políticas restritivas podem bloquear acesso. Se houver políticas inesperadas, não removê-las: revisar antes da aplicação. As migrações não fazem deduplicação automática de coluna, índice ou política já existentes.

Se o runtime ainda não tiver os GRANTs e o papel restrito **já existir**, o proprietário pode aplicar, em etapa manual separada e aprovada, substituindo investment_runtime pelo papel real:

```sql
GRANT USAGE ON SCHEMA public TO investment_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.operations TO investment_runtime;
GRANT USAGE, SELECT ON SEQUENCE public.operations_id_seq TO investment_runtime;
```

Esses comandos só fazem sentido após as tabelas existirem; não foram executados. Não conceder ALL nem privilégios financeiros novos a anon/authenticated/PUBLIC. Auditar os privilégios efetivos e os padrões existentes do projeto, sem presumir o que o Supabase concede por padrão. Não conceder acesso à alembic_version ao runtime sem necessidade.

## 4. Antes da execução manual

- Confirmar projeto, banco, commit e somente head 002. Confirmar que a conta DDL e o runtime são distintos.
- Garantir backup/snapshot recuperável e restauração conhecida. Confirmar a cobertura real do plano Supabase; não presumir backup habilitado. Se for necessário pg_dump, executar em ambiente privado com conexão direta e armazenar o arquivo fora do repositório; não despejar conteúdo no terminal.
- Escolher janela de baixa atividade e impedir duas execuções Alembic simultâneas. DDL/índices podem bloquear escrita. Não desabilitar RLS ou matar conexões de terceiros para contornar timeout.
- Revisar políticas e schema existentes. Se estiver em 002, encerrar a aplicação de migrações e fazer apenas a conferência pós-execução.
- O render.yaml local contém `preDeployCommand: python -m alembic upgrade head`. Conferir se isso está ativo no painel, sem iniciar deploy ou mudar configurações agora. Esta etapa usa execução manual única; não disparar um deploy que execute outra migração em paralelo.

## 5. Fixar destino da sessão e conferir revisão (não aplica upgrade)

Este wrapper exige MIGRATION_DATABASE_URL explícita e não altera DATABASE_URL nem arquivos. Ajusta apenas search_path dessa conexão pelo parâmetro libpq options e chama current, que consulta a revisão sem criar schema/tabelas. Também confere current_schema() em cada conexão real antes de qualquer migração. Se o pooler recusar ou ignorar options e o schema efetivo não for public, interromper e usar conexão direta compatível, ou revisar separadamente o env.py; não improvisar fallback silencioso:

```bash
python - <<'PY'
import os
from sqlalchemy import event, text
from sqlalchemy.engine import Engine, make_url
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
try:
    value = os.environ.get('MIGRATION_DATABASE_URL')
    if not value:
        raise ValueError('Conexão DDL explícita ausente')
    url = make_url(value)
    if url.drivername != 'postgresql+psycopg' or not url.host or url.host in ('localhost','127.0.0.1','::1') or url.query.get('sslmode') != 'verify-full':
        raise ValueError('Destino remoto/TLS inválido')
    options = str(url.query.get('options', '')).strip()
    url = url.update_query_dict({'options': (options + ' -csearch_path=public').strip()})
    os.environ['MIGRATION_DATABASE_URL'] = url.render_as_string(hide_password=False)
    cfg = Config('alembic.ini')
    if ScriptDirectory.from_config(cfg).get_current_head() != '002':
        raise ValueError('Head diferente do auditado')
    def guard_schema(connection):
        actual = connection.scalar(text('SELECT current_schema()'))
        connection.rollback()
        if actual != 'public':
            raise ValueError('Schema efetivo diferente de public')
    event.listen(Engine, 'engine_connect', guard_schema)
    command.current(cfg, verbose=True)
except Exception:
    print('Conferência interrompida. Revise destino, TLS, settings e permissões; detalhes privados omitidos.')
    raise SystemExit(1)
PY
```

A validação de Settings continua sendo executada pelo env.py. No Render, conferir ENVIRONMENT=production, AUTH_MODE=supabase e demais valores públicos obrigatórios. Localmente, preservar o .env atual; o único destino remoto usado para o Alembic é a variável MIGRATION_DATABASE_URL da sessão.

## 6. Comando de alteração — executar somente depois de aprovar as verificações

**Não executado pelo assistente.** O destino é reaplicado no mesmo processo do upgrade para não cair acidentalmente no banco local. A chamada final é o equivalente programático de `python -m alembic -c alembic.ini upgrade head`. A variável de aprovação abaixo não é uma credencial e vale somente para esse comando Bash:

```bash
MIGRATION_APPROVAL='APLICAR 002 PRODUCAO' python - <<'PY'
import os
from sqlalchemy import event, text
from sqlalchemy.engine import Engine, make_url
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
try:
    value = os.environ.get('MIGRATION_DATABASE_URL')
    if not value:
        raise ValueError('Conexão DDL explícita ausente')
    url = make_url(value)
    if url.drivername != 'postgresql+psycopg' or not url.host or url.host in ('localhost','127.0.0.1','::1') or url.query.get('sslmode') != 'verify-full':
        raise ValueError('Destino remoto/TLS inválido')
    options = str(url.query.get('options', '')).strip()
    url = url.update_query_dict({'options': (options + ' -csearch_path=public').strip()})
    os.environ['MIGRATION_DATABASE_URL'] = url.render_as_string(hide_password=False)
    cfg = Config('alembic.ini')
    if ScriptDirectory.from_config(cfg).get_current_head() != '002':
        raise ValueError('Head diferente do auditado')
    approval = os.environ.get('MIGRATION_APPROVAL')
    if approval != 'APLICAR 002 PRODUCAO':
        raise ValueError('Execução não confirmada')
    def guard_schema(connection):
        actual = connection.scalar(text('SELECT current_schema()'))
        connection.rollback()
        if actual != 'public':
            raise ValueError('Schema efetivo diferente de public')
    event.listen(Engine, 'engine_connect', guard_schema)
    command.upgrade(cfg, 'head')
    print('Upgrade concluído; execute a conferência independente de revisão, RLS e runtime.')
except Exception:
    print('Upgrade não concluído. Não apagar objetos nem usar stamp; reinspecione revisão e schema. Detalhes privados omitidos.')
    raise SystemExit(1)
PY
```

No PowerShell, definir `$env:MIGRATION_APPROVAL='APLICAR 002 PRODUCAO'` antes de enviar o conteúdo Python pelo here-string e remover a variável depois. Não usar input() com heredoc, pois stdin já contém o script. Essa confirmação é uma barreira humana adicional, não um controle de acesso.

## 7. Conferência posterior, sem escritas financeiras

Repetir os blocos de diagnóstico e current após o comando. Esperado:

- public.alembic_version com uma única revisão 002.
- operations com PK/id e sequência, campos da 001 e owner_id UUID nullable.
- Índice ix_operations_owner_id sobre owner_id.
- relrowsecurity=true e relforcerowsecurity=true.
- Política api_owner com a expressão auditada; nenhuma política antiga removida por este procedimento.
- Role runtime sem ownership/superuser/bypass e com os privilégios DML/seq necessários.

Com a conexão de runtime, confirmar os privilégios e RLS pelo diagnóstico. Somente depois, verificar `/health` HTTP 200 com ENVIRONMENT=production e executar uma leitura autenticada no aplicativo com conta autorizada. Não criar registros de teste no banco pessoal e não publicar tokens no terminal/chat. Testar isolamento com duas identidades deve ocorrer em homologação/dados de teste controlados, não por manipulação de registros privados existentes.

Em erro: a transação PostgreSQL tende a desfazer DDL e marcador juntos, mas uma queda de conexão pode deixar o resultado do commit incerto. Sempre reinspecionar versão e objetos antes de tentar novamente. Não usar downgrade: 001 apagaria operations e o downgrade de 002 está deliberadamente bloqueado. Tratar inconsistência com investigação/migração corretiva revisada, nunca exclusão automática.

Ao terminar, retirar as variáveis temporárias da sessão (`unset MIGRATION_DATABASE_URL PRODUCTION_RUNTIME_URL MIGRATION_APPROVAL` no Bash; `Remove-Item Env:MIGRATION_DATABASE_URL,Env:PRODUCTION_RUNTIME_URL,Env:MIGRATION_APPROVAL -ErrorAction SilentlyContinue` no PowerShell). Não alterar o .env local. Não manter a credencial DDL no runtime quando a execução puder ser isolada.

## Fontes oficiais consultadas

- [Conexões Supabase: direta/session/transaction](https://supabase.com/docs/guides/database/connecting-to-postgres).
- [Row Level Security Supabase](https://supabase.com/docs/guides/database/postgres/row-level-security).
- [RLS PostgreSQL](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) e [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html).
- [Comandos Alembic](https://alembic.sqlalchemy.org/en/latest/api/commands.html).
- [Shell/SSH Render](https://render.com/docs/ssh) e [pre-deploy](https://render.com/docs/deploys).
