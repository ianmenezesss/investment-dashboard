# Fase 2.0.1 — modelo contábil de renda fixa

## Escopo e decisões

Backend persistente para principal de CDB, sem cálculo de rendimentos, cotação,
capitalização, IR, IOF, liquidez bancária ou integração com instituições. Não há interface
nova ou alteração do dashboard de ações/demo. Nenhum serviço/dependência foi acrescentado.

Três tabelas novas, sem alterar `operations`:

| Tabela | Conteúdo |
| --- | --- |
| `fixed_income_investments` | Contrato: emissor, produto, tipo, remuneração, indexador, taxa, aplicação, vencimento e proprietário |
| `fixed_income_lots` | Um lote para cada aplicação, vinculado a um contrato/proprietário e sua data |
| `fixed_income_movements` | Eventos APPLICATION/REDEMPTION, com lote explícito, data, principal e caixa recebido opcional |

- CDB prefixado: `product_type=CDB`, `remuneration=FIXED`, `indexer=NONE`;
  `contracted_rate=12.5` significa **12,5% ao ano**, não 0,125.
- CDB pós-fixado: `remuneration=CDI`, `indexer=CDI`; `contracted_rate=110` significa
  **110% do CDI**, não CDI +110 pontos. Nenhuma taxa CDI é buscada nesta fase.
- Taxa positiva, menor que 10.000, até oito casas. Modalidade/indexador devem concordar.
- O contrato pode ser cadastrado sem saldo. Sua primeira aplicação deve ter exatamente
  `application_date`; cadastrar o contrato, por si só, não movimenta dinheiro.
- Novas aplicações criam **novos lotes**, com os mesmos termos/vencimento do contrato.
  Termos ou vencimentos distintos exigem outro contrato. Não existe escolha FIFO implícita.
- Um resgate parcial/total referencia exatamente um lote. Resgatar vários lotes exige
  registros explícitos separados; não há resgate agregado automático.
- Campos separados para tipo/remuneração/indexador permitem ampliar o modelo em futuras
  migrations para IPCA+, LCI/LCA e Tesouro. Esses valores ainda são rejeitados; não há
  semântica antecipada de spread, isenção, custódia ou marcação a mercado.

### Principal e caixa

`principal_balance = soma(APPLICATION.principal_amount) − soma(REDEMPTION.principal_amount)`.
É saldo do **principal**, nunca patrimônio atualizado ou rendimento acumulado.

Valores são `NUMERIC(20,8)`/Decimal, estritamente positivos e finitos, até
999.999.999.999,99999999 por movimentação. Acumulação usa contexto Decimal de 64 dígitos.
Principal e caixa são em BRL; não há suporte a moedas estrangeiras.
Taxa contratada usa `NUMERIC(12,8)`. JSON devolve decimais como strings; recomenda-se
também enviá-los como strings.

Em um resgate, `principal_amount` é o principal efetivamente amortizado. `cash_received`
é opcional e registra **o caixa líquido efetivamente recebido**, se conhecido de fonte
confiável (ex.: extrato). Pode diferir do principal ou permanecer null, inclusive em resgate
total. Ex.: amortizar 400 com caixa 430 reduz o principal em 400, não em 430.
Não se calcula rendimento/tributo pela diferença: seriam necessários os componentes
brutos, taxas, impostos e ajustes do extrato. O modelo permite acrescentá-los futuramente
sem reinterpretar o principal ou assumir que caixa null seja zero. Aplicações não têm
`cash_received`; custos acessórios não são modelados nesta fase.

### Datas, cronologia e imutabilidade

- Datas financeiras são DATE; “hoje” usa America/Sao_Paulo no Python e no PostgreSQL.
  Registro técnico `created_at` usa timestamp UTC. Vencimento deve ser posterior à aplicação.
- Não se aceitam aplicações/movimentações futuras. Aplicações devem estar entre a data
  inicial e o vencimento, inclusive. Resgates podem ser registrados após o vencimento,
  pois o principal não desaparece automaticamente e a liquidação pode ocorrer depois.
- Movimentações são append-only e não decrescem em data **por investimento**, mesmo entre
  lotes. No mesmo dia, a ordem é o id de inserção. É preciso cadastrar o histórico em ordem.
- Não há PUT/PATCH/DELETE para contratos, lotes ou movimentos. Triggers PostgreSQL bloqueiam
  UPDATE, DELETE e TRUNCATE das novas tabelas. Também os termos do contrato são imutáveis.
- Não existe correção retroativa ou estorno nesta fase. Um erro não deve ser “corrigido”
  com rendimento inventado ou lançamento inverso informal. Uma fase futura deverá definir
  eventos compensatórios auditáveis e regras financeiras antes de permitir correções.
- Cada lote possui exatamente uma aplicação: índice parcial único e trigger de integridade
  diferido exigem sua aplicação na mesma transação. Lote + aplicação são gravados atomicamente.
- FKs, checks e triggers validam vínculo/proprietário, datas e saldo, além da validação Python.
- Escritas usam READ COMMITTED e advisory lock transacional `(20001, investment_id)`;
  aplicação e trigger usam a mesma chave. Resgates concorrentes não podem consumir o mesmo
  saldo. Outros níveis de isolamento são rejeitados no trigger para não validar saldo em
  snapshot antigo. API limita espera pelo lock a cinco segundos; falha do banco mantém
  resposta genérica 503, sem SQL/parâmetros.

As funções são SECURITY INVOKER, VOLATILE (padrão), com search_path fixo e objetos
qualificados. A escolha de snapshots segue a [documentação de volatilidade PostgreSQL](https://www.postgresql.org/docs/17/xfunc-volatility.html)
e de [visibilidade em triggers](https://www.postgresql.org/docs/17/trigger-datachanges.html).

## API autenticada

Usa `private_db`, Supabase Auth e tratamento de erros existentes, sem modificá-los.
`owner_id` é definido pela identidade autenticada; inputs com owner_id são rejeitados.

| Método / caminho (prefixo `/api/fixed-income`) | Efeito |
| --- | --- |
| POST `/investments` | Cadastra contrato sem principal; retorna 201 |
| GET `/investments?offset=0&limit=100` | Lista contratos da identidade atual; máximo 200 por página |
| GET `/investments/{id}` | Contrato, principal total e lotes com saldo, inclusive encerrados |
| POST `/investments/{id}/applications` | Cria lote + aplicação imutável; retorna movimento 201 |
| POST `/investments/{id}/redemptions` | Amortiza principal de lote explícito; retorna movimento 201 |
| GET `/investments/{id}/movements?offset=0&limit=100` | Histórico cronológico paginado |
| GET `/investments/{id}/movements/{movement_id}` | Consulta um movimento original |

Contrato de exemplo fictício:

```json
{"issuer":"Banco fictício","product_name":"CDB exemplo","product_type":"CDB",
 "remuneration":"FIXED","indexer":"NONE","contracted_rate":"12.5",
 "application_date":"2025-01-01","maturity_date":"2027-01-01"}
```

Aplicação: `{"date":"2025-01-01","principal_amount":"1000"}`.
Resgate: `{"lot_id":1,"date":"2025-02-01","principal_amount":"400","cash_received":"430"}`.
Os ids são ilustrativos; usar ids retornados pela própria API em ambiente de teste.

Sem sessão: 401; conta não autorizada: 403, conforme autenticação existente;
recurso/lote alheio ou inexistente: 404; datas, valores, saldo ou termos inválidos: 422.
Respostas privadas mantêm `Cache-Control: no-store`. Não há chamadas brapi neste módulo.
Não há idempotência de POST nesta fase: não repetir automaticamente uma requisição de
escrita após timeout sem consultar o histórico e verificar se já foi gravada.
Detalhe do investimento inclui todos os lotes; para históricos extensos usar movimentos paginados.

## RLS e permissões

Migration `003`, sucessora de `002`, cria somente as três tabelas e seus índices,
sequências, políticas e funções/triggers. Habilita **ENABLE + FORCE RLS** e `api_owner`
em todas. Usa o mesmo contexto transacional `app.user_id`/`app.auth_mode` das ações.
Local autenticado de desenvolvimento admite owner null somente em `app.auth_mode=local`;
produção continua exigindo Supabase. Nenhuma identidade é atribuída a registros existentes.

A migration revoga privilégios de PUBLIC e, quando existentes, anon/authenticated/service_role
**somente nos objetos novos**. Não cria roles, não altera auth.users, políticas ou dados de ações.
O runtime deve continuar sem SUPERUSER/BYPASSRLS/ownership, com USAGE no schema,
SELECT/INSERT nas tabelas novas e USAGE nas sequências. Não precisa UPDATE/DELETE/TRUNCATE.
Executar GRANTs manualmente após a migration. Conexão SQL é exclusiva do backend;
as configurações app.* não são credenciais e não devem ser controláveis pelo navegador.
`/health` existente valida a tabela de ações, não comprova a revisão/permissões de renda fixa.

## Aplicação segura no Supabase — procedimento MANUAL

Nada abaixo foi executado contra produção. Não alterar `.env`, DATABASE_URL local, volumes
Docker ou arquivos da Vercel/Render. Validar primeiro em PostgreSQL descartável/staging,
confirmar backup recuperável e a revisão/commit auditados. Publicar o backend é etapa
posterior, fora desta entrega. Downgrade destrutivo de 003 é bloqueado: usar correção aditiva.

### 1. PowerShell: conexão administrativa remota explícita e diagnóstico

Usar conexão direta ou Session Pooler do projeto correto (não Transaction Pooler).
URL com `postgresql+psycopg://` e `sslmode=verify-full`; CA oficial já validada conforme
[procedimento Render/Supabase](render-supabase-setup.md). Papel DDL distinto do runtime.
Não usar chaves Supabase como senha SQL nem colocar URL no histórico do terminal.

```powershell
Set-Location C:\Users\IAN\ProjetosVSCode\investment-dashboard\backend
$fiPreviousPgoptions = $env:PGOPTIONS
$fiPreviousCa = $env:PGSSLROOTCERT
$env:PGOPTIONS = '-c search_path=public'
$env:PGSSLROOTCERT = (Resolve-Path (Read-Host 'Caminho da CA oficial do Supabase')).Path
$fiSecret = Read-Host 'URL administrativa REMOTA com psycopg e verify-full' -AsSecureString
$env:MIGRATION_DATABASE_URL = [System.Net.NetworkCredential]::new('', $fiSecret).Password
.\.venv\Scripts\python.exe -m alembic heads
# Esperado: 003 (head). Esse comando apenas lê a cadeia de arquivos.
```

Diagnóstico a seguir não importa configurações privadas da aplicação, não imprime a URL
e usa transação READ ONLY. O host deve pertencer ao projeto esperado; confirmar isso
privadamente no painel Supabase antes de preencher a conexão. Exigir resultado `READY`:

```powershell
@'
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
engine = None
try:
    url = make_url(os.environ["MIGRATION_DATABASE_URL"])
    assert url.drivername == "postgresql+psycopg"
    assert url.host and url.host not in ("localhost", "127.0.0.1", "::1")
    assert url.query.get("sslmode") == "verify-full"
    assert Path(url.query.get("sslrootcert") or os.environ["PGSSLROOTCERT"]).is_file()
    engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5})
    with engine.connect() as c, c.begin():
        c.execute(text("SET TRANSACTION READ ONLY"))
        assert c.scalar(text("SELECT current_schema()")) == "public"
        assert c.scalar(text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")) is True
        assert c.scalar(text("SELECT has_schema_privilege(current_user,'public','CREATE')"))
        assert c.scalar(text("SELECT version_num FROM public.alembic_version")) == "002"
        for name in ("fixed_income_investments", "fixed_income_lots", "fixed_income_movements"):
            assert c.scalar(text("SELECT to_regclass(:name)"), {"name":"public."+name}) is None
        for name in ("fi_reject_mutation", "fi_validate_contract", "fi_validate_lot", "fi_require_application", "fi_validate_movement"):
            assert c.scalar(text("SELECT to_regprocedure(:name)"), {"name":"public."+name+"()"}) is None
    print("READY: revisão 002, schema public, TLS e nomes novos livres. Confirmar backup/projeto antes do upgrade.")
except Exception:
    print("STOP: diagnóstico falhou; revisar TLS, projeto, revisão, permissões ou colisões sem expor a URL.")
    raise SystemExit(1)
finally:
    if engine is not None: engine.dispose()
'@ | .\.venv\Scripts\python.exe -
if ($LASTEXITCODE -ne 0) { throw 'Não executar migration' }
```

Se revisão já for 003, não repetir upgrade/grants sem verificar os objetos existentes.
Se houver colisões com revisão 002, não usar IF NOT EXISTS/stamp para esconder divergência.

### 2. PowerShell: escrita administrativa, somente após revisão e backup

```powershell
# EXECUTA DDL REMOTO. Confirmar conscientemente a conexão e o backup antes desta linha.
.\.venv\Scripts\python.exe -m alembic upgrade 003
if ($LASTEXITCODE -ne 0) { throw 'Upgrade falhou; investigar sem stamp/downgrade' }
.\.venv\Scripts\python.exe -m alembic current
# Esperado: 003 (head)
```

`env.py` exige Settings locais válidos e usa MIGRATION_DATABASE_URL explicitamente quando
preenchida; DATABASE_URL local não é modificada nem usada para DDL nessa execução.
Se Settings falhar, interromper e corrigir legitimamente a configuração local, preservando
DATABASE_URL. O env mantém lock_timeout 5 s/statement_timeout 30 s; falha de DDL transacional
deve ser diagnosticada, sem aumentar limites automaticamente. Não usar `--sql` como dry run:
o env atual não oferece modo offline. Não usar autogenerate ou stamp em produção.

### 3. Supabase SQL Editor: GRANTs somente nos objetos novos

Este bloco escreve permissões. Substituir o nome da role apenas se o runtime real usar
outro nome revisado; não alterar a senha/ownership nem usar postgres no runtime.

```sql
BEGIN;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='investment_runtime'
      AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb) THEN
    RAISE EXCEPTION 'Role runtime ausente ou insegura';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_class WHERE oid IN
      ('public.fixed_income_investments'::regclass,'public.fixed_income_lots'::regclass,
       'public.fixed_income_movements'::regclass)
      AND pg_has_role('investment_runtime',relowner,'USAGE')) THEN
    RAISE EXCEPTION 'Runtime tem ownership direto ou efetivo';
  END IF;
END; $$;
GRANT USAGE ON SCHEMA public TO investment_runtime;
REVOKE ALL ON TABLE public.fixed_income_investments, public.fixed_income_lots,
  public.fixed_income_movements FROM investment_runtime;
GRANT SELECT, INSERT ON TABLE public.fixed_income_investments, public.fixed_income_lots,
  public.fixed_income_movements TO investment_runtime;
REVOKE ALL ON SEQUENCE public.fixed_income_investments_id_seq, public.fixed_income_lots_id_seq,
  public.fixed_income_movements_id_seq FROM investment_runtime;
GRANT USAGE ON SEQUENCE public.fixed_income_investments_id_seq, public.fixed_income_lots_id_seq,
  public.fixed_income_movements_id_seq TO investment_runtime;
COMMIT;
```

### 4. Diagnóstico posterior — SQL Editor (somente leitura)

```sql
SELECT version_num FROM public.alembic_version;
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
       pg_get_userbyid(c.relowner) AS owner,
       has_table_privilege('investment_runtime',c.oid,'SELECT') AS can_read,
       has_table_privilege('investment_runtime',c.oid,'INSERT') AS can_insert,
       has_table_privilege('investment_runtime',c.oid,'UPDATE') AS can_update,
       has_table_privilege('investment_runtime',c.oid,'DELETE') AS can_delete,
       has_table_privilege('investment_runtime',c.oid,'TRUNCATE') AS can_truncate
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname IN
 ('fixed_income_investments','fixed_income_lots','fixed_income_movements');
SELECT tablename, policyname, qual, with_check FROM pg_policies
WHERE schemaname='public' AND tablename LIKE 'fixed_income_%';
SELECT event_object_table,trigger_name,event_manipulation FROM information_schema.triggers
WHERE event_object_schema='public' AND event_object_table LIKE 'fixed_income_%';
SELECT has_sequence_privilege('investment_runtime','public.fixed_income_investments_id_seq','USAGE'),
       has_sequence_privilege('investment_runtime','public.fixed_income_lots_id_seq','USAGE'),
       has_sequence_privilege('investment_runtime','public.fixed_income_movements_id_seq','USAGE');
```

Esperado: 003; três tabelas com RLS/force true, proprietário administrativo;
SELECT/INSERT true e UPDATE/DELETE/TRUNCATE false; três políticas api_owner; triggers
de validação/imutabilidade; USAGE nas três sequências. Revisar também privilégios
herdados: REVOKE direto não remove privilégios de memberships/PUBLIC. Não ampliar grants
nem desativar RLS para “resolver” erro. O SQL Editor administrativo não prova o isolamento
da URL runtime: validar com a conexão runtime e contas de teste em staging.

Após a operação, limpar somente as variáveis deste procedimento:

```powershell
Remove-Item Env:MIGRATION_DATABASE_URL -ErrorAction SilentlyContinue
$env:PGOPTIONS = $fiPreviousPgoptions
$env:PGSSLROOTCERT = $fiPreviousCa
Remove-Variable fiSecret,fiPreviousPgoptions,fiPreviousCa -ErrorAction SilentlyContinue
```

## Testes e limites da validação

Na implementação inicial: **139 testes backend** (31 novos), **96 frontend**, builds público
e privado aprovados; DDL inicialmente renderizado em memória. A rodada complementar abaixo
executou PostgreSQL real e reexecutou backend; frontend/builds não foram repetidos, pois
não houve mudanças nesses arquivos. Permanecem avisos conhecidos de TestClient/httpx e bundle acima de 500 kB.

```powershell
Set-Location C:\Users\IAN\ProjetosVSCode\investment-dashboard\backend
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_postgres.py
# Integração real: somente Docker ativo, imagem disponível e container efêmero dedicado:
.\.venv\Scripts\python.exe tests/run_postgres.py
```

A suíte PostgreSQL existente foi ampliada para aplicar 002, inserir ação fictícia, aplicar
003 e comprovar preservação; verifica RLS diretamente com role sem bypass, vínculos entre
usuários, imutabilidade, lote sem aplicação, cronologia e dois resgates concorrentes.
Usa somente container próprio com tmpfs, sem volumes pessoais nem Supabase. Não apontar
TEST_DATABASE_URL para banco real: o teste exige banco vazio e cria objetos/fixtures.

Validação PostgreSQL concluída em **28/10/2026**: 1 teste de integração aprovado em container
descartável PostgreSQL 17-alpine, além de 139 regressões backend reexecutadas e aprovadas.
Foram confirmados RLS, isolamento por usuário, privilégios mínimos e revogação de grants
default simulados do Supabase, imutabilidade, precisão de oito casas, cronologia, resgates
parciais/totais e concorrência. A cadeia 001→002→003 preservou ação fictícia preexistente.
Nenhuma correção de aplicação ou migration foi necessária.

O `compose.yaml` não contém serviço de testes: `db` usa o volume persistente `postgres_data`.
Ele não foi iniciado/usado. O executor criou somente container próprio com tmpfs, porta e
credencial temporárias, removido ao terminar. No Windows desta máquina foi necessário
selecionar o endpoint Docker Desktop Linux, apenas no processo:

```powershell
$env:DOCKER_HOST = 'npipe:////./pipe/dockerDesktopLinuxEngine'
.\.venv\Scripts\python.exe tests/run_postgres.py
```

Pronta para homologação controlada, mantendo as etapas de diagnóstico, backup e GRANTs
do procedimento acima. O teste local não comprova as permissões/revisão/TLS reais do
Supabase; isso exige verificação manual do ambiente alvo. Migrations foram aplicadas
somente no banco descartável, sem dados reais ou mudanças de autenticação/infraestrutura.
Não foram feitos deploy, commit, push ou tag. Versionamento mantido em Fase 2.0.1.

Commit sugerido: `feat(phase-2.0.1): model fixed income investments and transactions`.
