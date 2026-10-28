# Fase 2.0.8.4 — preparação de publicação

Estado em `f6a865d`: produção informada em 2.0.7 / Alembic 004; migrations locais até 008. O usuário confirmou integração 001–008 e ensaio descartável de backup/restore aprovados no Windows. Nenhum serviço de produção foi acessado nesta preparação.

## Parecer e gates

**NO-GO para publicar agora.** Restam gates operacionais: confirmar a role SQL efetiva da API, obter evidência de backup recuperável do banco de produção e seu restore em clone, e concluir homologação autenticada com duas contas. O runner SQL descartável aprovado usa identidades simuladas e não comprova login Supabase.

Não usar dados pessoais na homologação. Registrar somente resultados, versão Alembic e identificadores não sensíveis; não registrar URL, senha, token, extrato ou valores reais.

## 1. Migrations e compatibilidade

| Etapa | Mudança aditiva e dependência | Atenção operacional |
| --- | --- | --- |
| 004 → 005 | Tombstone de contrato vazio; FK RESTRICT, unicidade, RLS/FORCE RLS, triggers para vazio, propriedade e imutabilidade | `005` revoga acesso público, sem conceder grants ao runtime. |
| 005 → 006 | Tabela append-only de revisões, índices de sequência/idempotência, projeção efetiva e validadores de lotes, movimentos e observações | Novas consultas e triggers leem tabelas com RLS. Conferir privilégios do papel realmente conectado e equivalência de saldo sem revisões. |
| 006 → 007 | Grants mínimos para `investment_runtime` na revisão e sua sequência; substitui o corpo da função `fi_revision_after` já ligada ao trigger 006, acrescentando cronologia global | Falha deliberadamente se a role não existir ou tiver atributos/memberships indevidos. Não altera movimentos ou lotes existentes. |
| 007 → 008 | Verifica role restrita e concede SELECT/INSERT no tombstone e USAGE na sequência de arquivamento | Depende da role externa `investment_runtime` estar provisionada corretamente. |

`down_revision` é 004→005→006→007→008, com um único head 008. As migrations são transacionais no PostgreSQL; se o upgrade falhar, confirmar `alembic_version` e objetos antes de repetir. Os downgrades 005–008 são bloqueados para preservar histórico append-only. Não usar `stamp`, downgrade destrutivo ou restauração sobre operações posteriores. A compatibilidade com 004 depende de executar a cadeia inteira no mesmo banco, sob papel DDL separado. O runtime não deve ser dono de tabelas nem ter privilégios de criação, UPDATE/DELETE/TRUNCATE em arquivos/revisões ou BYPASSRLS.

### Pré-condições SQL, somente leitura, executadas futuramente por operador autorizado

Em conexão administrativa já identificada, confirmar a versão e a role prevista sem revelar credenciais:

```sql
SELECT version_num FROM public.alembic_version;
SELECT rolname, rolcanlogin, rolinherit, rolsuper, rolbypassrls,
       rolcreatedb, rolcreaterole, rolreplication
FROM pg_roles WHERE rolname = 'investment_runtime';
SELECT count(*) AS memberships FROM pg_auth_members
WHERE member = (SELECT oid FROM pg_roles WHERE rolname = 'investment_runtime');
```

Antes da migration, exigir versão única 004, role presente com LOGIN, NOINHERIT e demais flags administrativas falsas, sem memberships. Na **conexão efetiva do backend**, executar leitura controlada `SELECT current_user, session_user, current_database(), current_schema()` e comparar com a role aprovada e o banco esperado. Não imprimir a URL. A checagem atual `ensure_production_role` impede superuser/BYPASSRLS/ownership de `operations` e exige RLS nessa tabela, mas não confirma, sozinha, que `current_user = investment_runtime` nem os grants novos; por isso esta verificação separada é obrigatória.

Após 008, consultar RLS/FORCE RLS e grants efetivos:

```sql
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
       pg_get_userbyid(c.relowner) AS owner
FROM pg_class c WHERE c.oid IN
 ('public.fixed_income_investment_archives'::regclass,
  'public.fixed_income_application_revisions'::regclass);
SELECT has_table_privilege('investment_runtime','public.fixed_income_investment_archives','SELECT') AS archive_read,
       has_table_privilege('investment_runtime','public.fixed_income_investment_archives','INSERT') AS archive_insert,
       has_sequence_privilege('investment_runtime','public.fixed_income_investment_archives_id_seq','USAGE') AS archive_seq,
       has_table_privilege('investment_runtime','public.fixed_income_application_revisions','SELECT') AS revision_read,
       has_table_privilege('investment_runtime','public.fixed_income_application_revisions','INSERT') AS revision_insert,
       has_sequence_privilege('investment_runtime','public.fixed_income_application_revisions_id_seq','USAGE') AS revision_seq,
       has_function_privilege('investment_runtime','public.fi_effective_movements()','EXECUTE') AS projection_exec;
SELECT c.relname, has_table_privilege('investment_runtime',c.oid,'UPDATE') AS can_update,
       has_table_privilege('investment_runtime',c.oid,'DELETE') AS can_delete,
       has_table_privilege('investment_runtime',c.oid,'TRUNCATE') AS can_truncate
FROM pg_class c WHERE c.oid IN
 ('public.fixed_income_investment_archives'::regclass,
  'public.fixed_income_application_revisions'::regclass);
```

Todas as permissões positivas acima devem ser verdadeiras; UPDATE/DELETE/TRUNCATE devem ser falsas. Conferir políticas `api_owner`, triggers `fi_archive_*`, `fi_revision_*`, índices de unicidade, e que as funções operam como invocador, sem bypass de RLS. A migration 008 provisiona grants mínimos para `investment_runtime`, mas a role conectada pela API deve ser identificada antes de aceitar que esses grants se aplicam.

## 2. Preparação e sequência de publicação futura

1. **Congelar escritas financeiras** na janela de publicação e registrar início, versão 004 e contagens agregadas sem dados pessoais. Bloquear jobs concorrentes de migrations. Manter leitura disponível apenas se houver garantia de compatibilidade e consistência; caso contrário, usar manutenção temporária.
2. **Backup verificável**: capturar snapshot/backup consistente do banco e guardar identificador, hora, escopo, hash/manifesto e prazo de retenção definido pelo operador. Confirmar que a retenção cobre a janela de publicação e observação. Ensaiar restore em PostgreSQL descartável isolado, verificar versão 004, objetos, RLS e contagens agregadas. Nunca restaurar no banco ativo como teste.
3. **Go/no-go pré-migration**: backup e restore aprovados, destino confirmado, role DDL distinta do runtime, papel efetivo da API identificado, role `investment_runtime` apta à 007/008, janela sem escritas e cadeia Alembic única. Caso contrário, NO-GO.
4. **Migrations**: com credencial DDL temporária, executar futuramente da raiz `cd backend; python -m alembic -c alembic.ini current; python -m alembic -c alembic.ini heads; python -m alembic -c alembic.ini upgrade head`. `MIGRATION_DATABASE_URL` pertence apenas ao processo DDL; não deve existir no runtime. Nunca executar estas linhas antes da aprovação de publicação. Após upgrade, conferir versão única 008, RLS, triggers, ACLs, sequências e projeção sem revisão. Falha ou drift: parar; não repetir às cegas.
5. **Grants de arquivamento**: migration 008 concede ao `investment_runtime` somente SELECT/INSERT no tombstone e USAGE na sequência, preservando RLS/FORCE RLS e negando UPDATE/DELETE/TRUNCATE. A migration aborta se role ausente ou insegura. Confirmar role efetiva e privilégios por conexão runtime após upgrade.
6. **Backend Render**: publicar versão 2.0.8 após schema 008 e ACLs aprovadas. Conferir `/health`, autenticação, leitura privada e prévia sem persistência. Não ativar frontend de revisão antes da API. Manter escrita congelada até validar endpoints e RLS.
7. **Frontend Vercel privado**: publicar build correspondente após backend aprovado; verificar CSP/CORS, login, prévia, revisão e refetch. A demonstração pública é projeto separado e deve continuar offline, sem API financeira privada.
8. **Smoke e liberação**: executar roteiro fictício abaixo em ambiente de homologação separado; em produção limitar smoke a health, autenticação e leituras não sensíveis autorizadas, sem criar lançamentos de teste. Liberar escritas somente após todos os gates. Registrar versão backend/frontend, hora e resultados sem payloads financeiros.

Nomes de configuração a conferir sem ler valores: Render `ENVIRONMENT`, `AUTH_MODE`, `DATABASE_URL`, `PGSSLROOTCERT`, `SUPABASE_URL`, `ALLOWED_USER_IDS`, `CORS_ORIGIN`; processo DDL `MIGRATION_DATABASE_URL`; Vercel privado `VITE_PUBLIC_DEMO`, `VITE_APP_MODE`, `VITE_AUTH_MODE`, `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`; Vercel público `VITE_PUBLIC_DEMO`. Conferir raiz/build/output/CSP e ausência de migration automática no deploy. Variáveis `VITE_*` são incorporadas ao bundle: nunca inserir segredo nelas.

## 3. Homologação com dados fictícios

Em banco e contas descartáveis, executar: contrato vazio e arquivamento; contrato com aplicação e bloqueio de arquivo; aplicação inicial na data do contrato; resgate parcial e integral; REPLACE de valor/data com prévia; VOID sem resgate, com evento terminal; bloqueio de VOID com resgate dependente; correção retroativa que cruzaria resgate ou observação; aplicações/resgates intercalados e datas iguais; múltiplas revisões e sequência desatualizada; replay com mesma chave/payload e conflito 409 com chave reutilizada em payload distinto; falha de rede após gravação e retry; consulta paginada do histórico; abertura/observações imutáveis; duas contas, com 404/nenhuma linha para recurso alheio. Conferir saldos, principal efetivo, rendimentos e dashboard após cada alteração, sem somar posição observada aos lotes. Confirmar que registros originais não mudam e que VOID não cria caixa ou resgate.

**Aprovação objetiva:** migrations 001–008 e runner descartável aprovados no código candidato; backup/restore comparado por conteúdo e contagens; role/ACL/RLS/trigger checks aprovados; nenhuma leitura ou escrita cruzada; resposta idempotente idêntica; nenhum saldo intermediário negativo ou cronologia inválida aceitos; UI exige motivo, prévia e confirmação e atualiza consultas; smoke de API/frontend aprovado. Qualquer falha nesses pontos, migration parcial, role não identificada, backup não restaurável ou privilégio amplo implica **NO-GO**. Os testes SQL usam proprietários fictícios e não substituem login autenticado real.

## 4. Falha e recuperação

- **Antes de migration:** cancelar publicação e reabrir a versão 2.0.7 após confirmar que não houve DDL nem escrita pendente.
- **Migration falha:** manter congelamento de escritas, consultar `alembic_version`, catálogo de objetos e logs sem segredos; PostgreSQL normalmente reverte a transação falha. Corrigir causa e ensaiar novamente em clone descartável antes de qualquer repetição. Não usar `stamp` para mascarar drift.
- **Backend/frontend falha após schema 008:** voltar os artefatos de aplicação para a versão anterior apenas se a compatibilidade com schema 008 tiver sido verificada em ensaio. Manter novas rotas desabilitadas e escritas congeladas até decisão. Preferir correção aditiva para defeitos de schema.
- **Banco após escritas 2.0.8:** não fazer downgrade 005–008 nem restaurar snapshot 004 sobre operações novas. Preservar eventos append-only. Plano de recuperação exige reconciliação de operações pós-backup e aprovação explícita do proprietário antes de qualquer restauração isolada ou corte de tráfego. Guardar backup conforme retenção definida; validar restore em ambiente separado antes de usá-lo.

## 5. Riscos e decisões pendentes

1. Confirmar a identidade SQL efetiva usada pelo backend implantado e o provisionamento da role `investment_runtime`; a documentação histórica não substitui essa evidência.
2. Confirmar que a role `investment_runtime` existe e que a migration 008 foi aplicada pela role DDL correta; confirmar os grants pela conexão efetiva do backend.
3. Definir janela de congelamento de escritas, método de backup, retenção e local de restore ensaiado.
4. Confirmar compatibilidade de rollback da aplicação 2.0.7 contra schema 008 em clone antes de confiar nessa opção.
5. Homologar duas contas e configurações de rede/CSP/TLS em ambiente separado antes da decisão final de publicação.

## 6. Ensaio local automatizado de backup/restore

Script único: `backend/tests/run_postgres_backup_restore.ps1`. Executar no PowerShell a partir da raiz do repositório. Logs, dump e temporários do host ficam em `E:\InvestmentDashboard\temp`; a pasta é criada se necessário e conteúdo existente não é limpo:

```powershell
& .\backend\tests\run_postgres_backup_restore.ps1
```

O script exige digitar `DESCARTAVEL`, rejeita contexto Docker que não seja `npipe:`/`unix:`, isola `DOCKER_CONFIG`, rejeita `DOCKER_HOST`/`DOCKER_CONTEXT` herdados, usa somente `postgres:17-alpine` já presente (sem pull), cria uma bridge Docker exclusiva com binding padrão `127.0.0.1` e nomes UUID exclusivos, publica cada porta explicitamente em `127.0.0.1` e usa `tmpfs` sem volumes nomeados. O container PostgreSQL fica em uma bridge que permite saída de rede; portanto o ensaio não promete isolamento total de rede. A aplicação de testes recebe somente URL de banco local, auth local, mercado desabilitado, sem proxies herdados e `NO_PROXY=*`; nenhum endereço de produção é utilizado. O runner desativa bytecode/cache do pytest e aponta `TEMP`, `TMP` e `TMPDIR` para E:. Ele executa `tests/test_postgres.py` no banco fonte vazio, produz `pg_dump` custom em E:, precria somente roles fictícias necessárias e restaura em outro container/banco. Ambos os containers e a rede criada pela execução são removidos; nenhum container ou volume preexistente é removido. O PowerShell está salvo em UTF-8 com BOM, força stdout/stderr Python em UTF-8, captura cada fluxo em arquivo temporário separado em E:, registra o exit code e acrescenta traceback/exceção completos após sanitização; os arquivos intermediários da execução são apagados somente depois da captura.

**Armazenamento interno do Docker:** os arquivos do host (backup, log, Docker config temporário) usam E:. O PostgreSQL fica em `tmpfs`; nenhum volume persistente é montado. A bridge exclusiva publica somente em loopback e permite saída de rede, portanto o ensaio não promete isolamento total de rede. O armazenamento de imagens/VM continua sob configuração do Docker Desktop e pode ocupar C:; `DockerRootDir` não identifica necessariamente o disco virtual no host.

O verificador compara versão 008, contagens e SHA-256 de linhas das tabelas de operações/ledger, constraints validadas, RLS/FORCE RLS, triggers append-only, atributos e memberships da role, grants/negações e visibilidade sob `investment_test_runtime` para os dois proprietários fictícios. O log consolidado fica em `E:\InvestmentDashboard\temp` e contém tamanho/hash do backup, sem URL ou credenciais. O dump temporário é removido após o ensaio; seu hash permanece no log. Este exercício valida backup/restore do schema candidato fictício em head 008; não substitui um restore autorizado de backup operacional legado em clone, que não será obtido de produção nesta fase.

**Evidência atual:** o usuário confirmou no Windows Docker 29.5.3, migrations 001–008 e backup/restore descartável aprovados. A validação de produção permanece pendente e deve ocorrer somente na janela autorizada; o resultado local não substitui backup real, identidade efetiva da API nem login autenticado.
