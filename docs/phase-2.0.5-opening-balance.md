# Fase 2.0.5 — saldo consolidado e conciliação manual

Implementação local para revisão em 28/10/2026. Sem commit, publicação, migration remota
ou homologação com contas reais. Todos os exemplos/testes/capturas são fictícios.

## Objetivo e decisões

Um CDB existente pode começar a ser acompanhado com uma posição informada pela instituição,
sem reconstruir suas aquisições. O snapshot **não é aplicação**, não cria lote ou movimento,
não altera eventos anteriores e não participa da capitalização CDI. Não há importação CSV.

O ledger de 2.0.1 permanece a fonte de verdade para aplicações/resgates de lotes conhecidos.
SGS, calendário e motor CDI/IOF/IR de 2.0.2/2.0.3 são reutilizados exclusivamente nesses lotes.
Não há segundo motor financeiro, fornecedor novo ou nova chamada externa para observações.

O contrato mantém seus campos. Ao começar sem histórico, a interface permite informar em
`application_date` a data inicial do acompanhamento, que funciona como limite inferior;
ela **não passa a representar uma aquisição histórica comprovada**. A data-base do snapshot
pode ser igual ou posterior. Para contratos com ledger, o significado anterior é preservado.

## Modelo e semântica financeira

Nova tabela `fixed_income_observations`, migration **004 → sucessora de 003**:

| Campo | Significado |
| --- | --- |
| `investment_id`, `owner_id` | Contrato e proprietário; owner vem da sessão do servidor |
| `kind` | `OPENING` único por contrato; `OBSERVATION` para conciliações posteriores |
| `as_of`, `created_at` | Data-base informada e instante UTC de gravação |
| `gross_value`, `net_value` | Patrimônio bruto e disponível líquido do CDB inteiro, obrigatórios |
| `ir_estimate`, `iof_estimate`, `taxes_combined` | Tributos informados, opcionais; combinados OU discriminados |
| `reported_gain` | Ganhos/perdas conforme a instituição; admite negativo, definição independente |
| `confirmed_principal` | Principal confirmado explicitamente; desconhecido continua `null` |
| `reason` | `POSITION` ou `AFTER_CONSOLIDATED_REDEMPTION` |
| `cash_received` | Caixa opcional da conciliação após resgate; não é amortização ou lucro |
| `source`, `notes` | Origem obrigatória (até 160 caracteres), observações opcionais (até 1000) |

Valores são Decimal/NUMERIC(14,2), representados por strings decimais na API, sem float.
Máximo absoluto: 999999999999,99; valores não finitos/excesso de casas são rejeitados,
não arredondados silenciosamente na entrada pela API. Operações intermediárias usam precisão 64;
apresentação BRL aceita vírgula decimal e preserva branco como desconhecido.

Regras na API e PostgreSQL:

- Patrimônio, tributos, principal e caixa não negativos; líquido não supera bruto.
- Tributos combinados conhecidos: `bruto - tributos = líquido`. Se IR e IOF forem ambos
  conhecidos: `bruto - IR - IOF = líquido`. Se apenas parte for conhecida, não pode superar
  a diferença; o restante fica desconhecido. A diferença **não é transformada em tributo oficial**.
- Ganho informado não determina principal, lucro tributável ou rentabilidade percentual.
- Uma abertura exige contrato sem lotes e sem abertura anterior. Contratos com lotes,
  inclusive encerrados, retornam 409: não há rebase silencioso de um histórico existente.
- Datas seguem America/Sao_Paulo, sem futuro e sem retroceder em relação à última observação
  ou movimento. Observações na mesma data são permitidas e ordenadas por id; anteriores
  permanecem acessíveis. Correção exige nova observação cronológica, nunca UPDATE/DELETE.
- Novas aplicações/movimentos devem ocorrer **depois** da abertura e não antes da última
  observação, respeitando também vencimento e regras anteriores do ledger.
- Advisory lock `(20001, investment_id)`, READ COMMITTED, índice único parcial, índices de
  proprietário/cronologia e triggers protegem concorrência e gravações SQL diretas.

Fixture exclusivamente fictícia: Banco Exemplo, CDB Pós-Fixado Exemplo, 100% CDI, início
15/10/2026, vencimento 15/10/2028; bruto R$ 5.000,00, líquido R$ 4.950,00, tributos combinados
R$ 50,00, ganhos informados R$ 250,00 e principal **não informado**. Não é seed nem valor
pré-preenchido na carteira privada. Confirmar principal exige informação independente.

### Novos lotes e resgates

Novas aplicações criam lotes reais separados. Resgates desses lotes mantêm o vínculo e a
amortização explícitos do ledger. Já o capital consolidado sem lotes não pode ser resgatado
por um lote inventado: usar **Conciliar posição manualmente**, motivo “após resgate”, nova
posição inteira e caixa recebido opcional. Isso não determina principal amortizado nem
impostos/resultados realizados. Não permite calcular automaticamente rendimento futuro
do capital antigo, mesmo quando seu principal tiver sido informado.

A última observação é uma fotografia na data-base; **não é atualizada automaticamente**
por aplicações/resgates posteriores. Uma nova conferência exige nova observação datada.
Não somar patrimônio observado com estimativas de novos lotes: a observação pode já
incluí-los. Não há gráfico histórico ou comparação de bases diferentes como rentabilidade.

`GET /api/fixed-income/investments/{id}/observed-history` retorna somente observações
manuais do contrato, dentro do intervalo solicitado. Aplicações e resgates do ledger não
criam snapshots automaticamente; por isso, principal registrado (por exemplo, R$ 150,00)
pode coexistir corretamente com um gráfico vazio. `coverage=unavailable` e `points=[]`
significam que não há observação no período, não que o principal seja zero ou que o banco
falhou. A interface pode explicar isso com: “O principal registrado vem das aplicações e
resgates. O gráfico mostra apenas posições conferidas manualmente; não há observações neste
período.” O filtro temporal pode excluir observações existentes fora da janela.

## API e segurança

Prefixo `/api/fixed-income/investments`; cliente HTTP e autenticação existentes:

| Método/caminho | Contrato |
| --- | --- |
| POST `/{id}/opening-balance` | `ObservationInput` → `ObservationOutput`, 201; abertura única |
| POST `/{id}/observations` | Mesmo input/output, 201; exige abertura existente |
| GET `/{id}/observations?offset=0&limit=100` | Histórico cronológico incluindo abertura; limite máximo 200 |
| GET `/` e `/{id}` | Acrescentam `tracking_mode` (`LEDGER`/`CONSOLIDATED`) e `latest_observation`; detalhe também `opening_balance` |
| GET `/{id}/returns` | Acrescenta `scope`: `ledger_only` ou `post_opening_lots_only`; premissas anteriores continuam obrigatórias |

Input monetário usa ponto decimal. Campos opcionais aceitam null; `reason` padrão POSITION;
`owner_id`/`kind`/ids não são aceitos no input. Respostas acrescentam id, investment_id, kind,
created_at; não expõem owner_id. Source/notes contêm informação privada apenas na API
autorizada, nunca em fixtures/logs. Campos financeiros indisponíveis não são convertidos em zero.

O `principal_balance` anterior do detalhe continua representando **somente o ledger**.
Não representa o capital consolidado; para este, consultar `latest_observation.confirmed_principal`.
Em returns consolidado sem novos lotes, principal/valores estimados são null, status incomplete,
avisos `manual_position_excluded`/`historical_returns_unavailable`. Com novos lotes, os números
referem-se exclusivamente a esses lotes, identificados por scope, sem somar a abertura.

401 sem sessão; 403 fora da allowlist existente; 404 para recurso alheio/inexistente;
409 para abertura duplicada/contrato com lotes/conciliação sem abertura; 422 para dados
inválidos. Novos erros 422 omitem input/ctx, preservando apenas localização/tipo/mensagem
sem valores pessoais. Falhas do banco mantêm mensagem genérica 503. Não repetir POST
automaticamente após timeout: consultar o histórico antes de reenviar.

RLS ENABLE/FORCE e api_owner usam o contexto existente `app.user_id`/`app.auth_mode`.
AUTH_MODE, JWT, ALLOWED_USER_IDS e a demo não foram alterados. Runtime sem ownership,
SUPERUSER ou BYPASSRLS, somente SELECT/INSERT na nova tabela e USAGE na sequência.
PUBLIC/anon/authenticated/service_role não recebem acesso à nova tabela/sequência;
grants default desses papéis são revogados na migration. Nenhum acesso direto via Supabase
no navegador; nenhum armazenamento financeiro privado em localStorage.

## Interface

- Cards com instituição/produto, remuneração, vencimento, bruto/líquido e data-base quando
  observados; ausência de posição é descrita, sem patrimônio fictício R$ 0,00.
- CDB sem lotes: “Registrar nova aplicação” ou “Iniciar com saldo atual”.
- Abertura/nova observação em modal acessível Radix: BRL, opcionais identificados, validação,
  revisão completa antes do POST, retorno ao formulário, loading/erro/sucesso e foco restaurado.
- Resumo da instituição separado da “Estimativa calculada pelo Investment Dashboard”.
  Principal não informado, histórico indisponível e tributos desconhecidos ficam explícitos.
- Origem/notas/instante de registro em seção secundária; histórico de observações imutável,
  paginado. Caixa de conciliação aparece com sua limitação, sem inferência de amortização.
- Novos lotes e seus saldos continuam separados; estimativas não consultam SGS quando só
  há saldo consolidado. O calendário do motor permanece limitado a 2024–2026.

## Implantação MANUAL: Supabase → Render → Vercel

**Nada desta seção foi executado remotamente.** Não alterar DATABASE_URL local nem usar
runtime para DDL. Confirmar manualmente cada etapa antes da próxima; parar em qualquer falha.

### 1. Diagnóstico e backup — antes de autorizar escrita

No projeto correto do Supabase, conferir Project Ref/host/usuário com o Dashboard → Connect.
Usar Session Pooler ou conexão administrativa já validada, com papel proprietário dos
objetos da migration 003 (incluindo `fi_validate_lot`), nunca `investment_runtime`.
Confirmar estes metadados no SQL Editor, sem consultar linhas financeiras:

```sql
SELECT current_database(), current_user;
SELECT version_num FROM public.alembic_version; -- exatamente 003 antes desta etapa
SELECT to_regclass('public.fixed_income_observations'); -- null antes da 004
SELECT p.oid::regprocedure, pg_get_userbyid(p.proowner) AS owner
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='public' AND p.proname IN ('fi_validate_lot','fi_reject_mutation');
SELECT rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb
FROM pg_roles WHERE rolname='investment_runtime'; -- todos flags false
```

Confirmar backup recuperável com data/escopo/retenção conhecidos e ensaio de restauração
em banco isolado. Não presumir que o plano gratuito inclui backups/PITR. Um arquivo existir
ou abrir com `pg_restore --list` não comprova restauração. Backup/dump deve permanecer fora
do repositório, com acesso restrito, incluindo dados da aplicação e plano de preservação das
identidades/roles. Nunca anexar dumps/logs a issue. Sem backup recuperável: **não migrar**.

Combinar uma janela sem gravações de renda fixa entre as contas autorizadas; se isso não
puder ser garantido, manter o backend em manutenção controlada até concluir 004 e GRANTs.
A função de lotes passa a ler a tabela nova: entre o commit da migration e os GRANTs,
o runtime antigo pode receber 503 ao movimentar CDB. Não existe feature flag nova de
manutenção nesta entrega; a janela deve ser coordenada manualmente, sem desativar proteções.

### 2. PowerShell — diagnóstico da conexão explícita, depois migration autorizada

Reutilizar CA/cadeia previamente validada; verify-full exige confiança e hostname corretos.
Não substituir por sslmode=require nem presumir que certifi sozinho configure libpq.
O certificado deve estar em arquivo local confiável (`PGSSLROOTCERT`), com hostname
correspondente ao pooler. Não copiar certificados privados ou credenciais para o Git.

```powershell
Set-Location C:\Users\IAN\ProjetosVSCode\investment-dashboard\backend
$fiPreviousCa = $env:PGSSLROOTCERT
$fiPreviousPgoptions = $env:PGOPTIONS
$fiPreviousMigrationUrl = $env:MIGRATION_DATABASE_URL
try {
  $env:PGSSLROOTCERT = Read-Host 'Caminho absoluto da CA confiável já validada'
  if (-not (Test-Path -LiteralPath $env:PGSSLROOTCERT -PathType Leaf)) { throw 'CA ausente' }
  # URL administrativa remota: postgresql+psycopg, senha URL-encoded,
  # host/porta/database do Dashboard e query sslmode=verify-full. Não colar em comando/histórico.
  $fiSecret = Read-Host 'URL administrativa REMOTA com sslmode=verify-full' -AsSecureString
  $env:MIGRATION_DATABASE_URL = [Net.NetworkCredential]::new('', $fiSecret).Password
  # MIGRATION_DATABASE_URL sobrepõe somente o engine Alembic; DATABASE_URL local é preservada.
  $env:PGOPTIONS = '-c default_transaction_read_only=on'
  .\.venv\Scripts\python.exe -m alembic current
  if ($LASTEXITCODE -ne 0) { throw 'Diagnóstico falhou; não prosseguir' }
  # PAUSA MANUAL: conferir destino, revisão 003, TLS, backup e permissões administrativas.
  $fiApproval = Read-Host 'Somente após conferir tudo, digite APLICAR 004; outro texto encerra'
  if ($fiApproval -cne 'APLICAR 004') { throw 'Migration não autorizada' }
  $env:PGOPTIONS = '-c default_transaction_read_only=off'
  .\.venv\Scripts\python.exe -m alembic upgrade 004
  if ($LASTEXITCODE -ne 0) { throw 'Migration falhou; parar e diagnosticar sem downgrade' }
  $env:PGOPTIONS = '-c default_transaction_read_only=on'
  .\.venv\Scripts\python.exe -m alembic current
  if ($LASTEXITCODE -ne 0) { throw 'Verificação falhou; não publicar' }
} finally {
  $env:MIGRATION_DATABASE_URL = $fiPreviousMigrationUrl
  $env:PGSSLROOTCERT = $fiPreviousCa
  $env:PGOPTIONS = $fiPreviousPgoptions
  Remove-Variable fiSecret,fiPreviousMigrationUrl,fiPreviousCa,fiPreviousPgoptions,fiApproval -ErrorAction SilentlyContinue
}
```

Esperado: 003 no diagnóstico, 004 depois. `upgrade 004` fixa o alvo, sem incluir migrations
futuras inadvertidamente. Não executar stamp, downgrade, DROP ou reescrever a 003.
`env.py` utiliza lock_timeout 5s e statement_timeout 30s; em falha, confirmar o estado
transacional/revisão antes de nova tentativa. Não ampliar timeout ou grants às cegas.

### 3. Supabase SQL Editor — GRANTs explícitos, após confirmação da 004

A migration não concede privilégios à role específica de cada instalação. O novo SELECT
é necessário também aos triggers/consultas de CDB antigos; aplicar grants antes do backend.
Não modificar permissões das tabelas antigas ou default privileges globais.

```sql
BEGIN;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='investment_runtime'
    AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb) THEN
    RAISE EXCEPTION 'Runtime ausente/insegura';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_class WHERE oid IN
    ('public.fixed_income_investments'::regclass,'public.fixed_income_lots'::regclass,
     'public.fixed_income_movements'::regclass,'public.fixed_income_observations'::regclass)
    AND pg_has_role('investment_runtime',relowner,'MEMBER')) THEN
    RAISE EXCEPTION 'Runtime possui ownership ou membership administrativa';
  END IF;
END; $$;
GRANT USAGE ON SCHEMA public TO investment_runtime;
REVOKE ALL ON TABLE public.fixed_income_observations FROM investment_runtime;
GRANT SELECT, INSERT ON TABLE public.fixed_income_observations TO investment_runtime;
REVOKE ALL ON SEQUENCE public.fixed_income_observations_id_seq FROM investment_runtime;
GRANT USAGE ON SEQUENCE public.fixed_income_observations_id_seq TO investment_runtime;
COMMIT;
```

### 4. Verificação pós-migration — somente leitura

```sql
SELECT version_num FROM public.alembic_version; -- 004
SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,
 pg_get_userbyid(c.relowner) AS owner,
 has_table_privilege('investment_runtime',c.oid,'SELECT') AS can_read,
 has_table_privilege('investment_runtime',c.oid,'INSERT') AS can_insert,
 has_table_privilege('investment_runtime',c.oid,'UPDATE') AS can_update,
 has_table_privilege('investment_runtime',c.oid,'DELETE') AS can_delete,
 has_table_privilege('investment_runtime',c.oid,'TRUNCATE') AS can_truncate
FROM pg_class c WHERE c.oid='public.fixed_income_observations'::regclass;
SELECT has_sequence_privilege('investment_runtime','public.fixed_income_observations_id_seq','USAGE');
SELECT policyname,qual,with_check FROM pg_policies
WHERE schemaname='public' AND tablename='fixed_income_observations';
SELECT tgname,pg_get_triggerdef(oid) FROM pg_trigger WHERE NOT tgisinternal
 AND tgrelid IN ('public.fixed_income_observations'::regclass,'public.fixed_income_movements'::regclass);
SELECT indexname,indexdef FROM pg_indexes
WHERE schemaname='public' AND tablename='fixed_income_observations';
SELECT grantee,privilege_type FROM information_schema.table_privileges
WHERE table_schema='public' AND table_name='fixed_income_observations';
```

Esperado: RLS/force true, owner administrativo, SELECT/INSERT/USAGE true; UPDATE/DELETE/
TRUNCATE false inclusive por herança; policy api_owner e triggers insert/append-only/no-truncate,
índice único parcial de abertura. PUBLIC/anon/authenticated/service_role sem privilégios de
tabela/sequência; investigar qualquer outro grant default inesperado antes de prosseguir.
O SQL Editor administrativo não prova RLS da conexão runtime: a homologação autenticada
abaixo continua obrigatória. `/health` 200 sozinho não comprova a 004 ou esses grants.

### 5. Render e Vercel — somente depois das verificações e aprovação

Publicar backend compatível com 004 primeiro, mantendo DATABASE_URL runtime/TLS/Auth/CORS
existentes e Pre-Deploy sem migration automática. Nenhuma variável nova nesta fase.
Verificar /health e GET privado de contratos. Publicar depois o projeto Vercel **privado**
com sua configuração/CSP atuais. Não modificar o projeto público/demo.

## Homologação na segunda conta privada

Executar manualmente, após implantação autorizada, com a conta secundária já existente.
Não registrar JWT, e-mail, UUID pessoal, senhas, telas reais ou payloads financeiros em logs/Git.
ALLOWED_USER_IDS deve continuar explícito no Render, contendo somente as contas autorizadas;
não abrir wildcard ou remover a verificação. Estes ambientes reais não foram acessados nesta fase.

1. Login da conta secundária, cadastrar o exemplo **fictício** acima (não a carteira principal).
2. Abrir detalhe vazio: duas alternativas e nenhum patrimônio presumido; escolher saldo atual.
3. Preencher fonte fictícia/valores da fixture e deixar principal vazio; revisar, voltar,
   conferir BRL e confirmar uma vez. Atualizar página: posição, data e origem preservadas,
   principal não informado e nenhuma aplicação/lote fictício.
4. Abertura repetida deve retornar 409. Dados inconsistentes retornam 422 sem reproduzir
   valores enviados no erro. Não logar requests/responses em ferramentas compartilhadas.
5. Criar aplicação fictícia posterior à abertura, resgatar parte de seu lote: ledger conserva
   histórico. Se estimar, confirmar premissas reais do contrato; números só dos novos lotes,
   sem somar ao saldo observado. Datas fora do calendário: indisponível, nunca CDI inventado.
6. Conciliar resgate consolidado por nova observação, motivo apropriado e caixa opcional.
   Original deve continuar no histórico, sem principal/IR/IOF deduzidos do caixa.
7. Com segunda sessão autorizada em perfil separado, tentar somente os ids **fictícios**
   dessa homologação: listagem não os revela; GET/POST cruzados retornam 404. Não sondar
   registros reais da conta principal. Sem sessão, 401; conta fora da allowlist, 403.
8. Logout/login/troca de conta não reutilizam query cache financeiro alheio; validar teclado,
   foco, fechamento do modal, carregamento/erro e largura móvel. Demo em perfil sem sessão
   deve continuar offline, sem Supabase/API/BCB e sem posições privadas.

Não apagar os registros de homologação pelo banco para “limpar”: são histórico imutável.
Usar ambiente/conta próprios e preservar sua identificação como dados fictícios.

## Falhas e rollback

Se diagnóstico, backup, migration, grants ou testes falharem, parar antes da próxima etapa,
examinar metadados/revisão sem divulgar payloads e corrigir para frente. Não desativar RLS,
triggers, TLS, auth ou conceder BYPASSRLS. Não repetir POST às cegas depois de timeout.

Downgrade 004 é bloqueado intencionalmente: excluir snapshots destruiria rastreabilidade.
A 004 também estende `fi_validate_lot` e adiciona guarda de movimentos; não restaurar a
função antiga isoladamente. Migrações 001–003 não foram editadas; nenhuma linha financeira
preexistente é reescrita pela 004. Reverter somente código exige verificar compatibilidade:
versões antigas desconhecem posições consolidadas e podem mostrar principal incompleto.
Não expor esse módulo por versões antigas a contratos consolidados; preferir correção
compatível, com manutenção controlada do módulo enquanto necessário. Restaurar backup só
com decisão explícita/ensaio separado e plano de reconciliação de todas as escritas posteriores.

## Testes, revisão e limites

- 264 testes backend, incluindo 22 novos casos de abertura/validações/conciliação,
  owner/auth, privacidade de erro e escopo do motor; SGS/brapi somente simulados.
- 1 integração PostgreSQL 17 descartável: cadeia até 004, regressões de ações/ledger,
  role sem bypass, RLS direta, grants/default Supabase, imutabilidade, dados inválidos por
  SQL e duas aberturas concorrentes (201/409). Nenhum volume/banco real foi utilizado.
- 125 frontend: oito novos testes abrangem abertura/revisão, null principal, tributos,
  BRL, erro, voltar/revisar, conciliação preservada e ausência de estimativa indevida.
  Novo fluxo também cobre 401/403/422, duplicação e bloqueio de fechamento pendente.
  Regressões existentes verificam troca de conta, foco e demo offline.
- Builds público e privado aprovados. Avisos conhecidos: bundle >500 kB, TestClient/httpx.
- Revisão visual com fixture offline em Chrome: 1440×1000 e 390×844; sem overflow horizontal,
  modal móvel ~366,6 px. Capturas fictícias locais ignoradas, sem sessão/valores reais.
- Revisão manual de arquivos novos/alterados: exemplos financeiros fictícios, sem seeds ou
  dados pessoais; erros não incluem input/ctx, nenhum novo log financeiro ou token. Auditoria
  de publicação e diff registrados em validation.md. Isso não substitui revisão humana futura.

Limites: não há histórico antigo reconstruído, estimativa do capital consolidado, impostos
realizados inferidos, sincronização bancária, CSV, comparação de rentabilidade entre bases
ou gráfico histórico novo. Posições são declaradas pelo usuário, não verificadas com banco.
Compatibilidade operacional remota, grants reais e homologação com contas reais pendentes.

## Arquivos desta entrega

- Backend novos: `app/fixed_income/observations.py`, `observation_routes.py`,
  `migrations/versions/004_opening_balances.py`, `tests/test_opening_balances.py`,
  `tests/opening_balance_postgres.py`.
- Backend modificados: `fixed_income/{schemas,router,returns_engine,returns_router,returns_schemas}.py`,
  `app/main.py`, `migrations/env.py`, `tests/{fixed_income_postgres,test_postgres}.py`.
- Frontend novos: `src/fixed-income/{ManualPositionDialog,ObservedPosition}.tsx`.
- Frontend modificados: `src/fixed-income/{FixedIncomePage,FixedIncomeDialog,FixedIncomeReturns}.tsx`,
  `FixedIncomePage.test.tsx`, `types.ts`, `fixed-income.css`, `src/api.ts`,
  `src/repositories/PrivateRepository.ts`.
- Documentos: este arquivo, `roadmap.md` e `validation.md`.

Após revisão, publicação continua exigindo autorização do responsável. Nenhuma etapa remota
ou comando Git de escrita foi executado automaticamente.
