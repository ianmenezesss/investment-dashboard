# Fase 2.0.8.2-B — API de revisões de aplicações CDB

## Escopo

Entrega local da API, sem interface, commit ou deploy. A migration 007 depende do papel
de runtime `investment_runtime` documentado em `render-supabase-setup.md`, provisionado
fora do Alembic e separado do papel DDL. A migration falha antes de conceder qualquer
privilégio se esse papel não existir, não tiver LOGIN, for SUPERUSER/BYPASSRLS, tiver
INHERIT, atributos administrativos ou memberships. Para suportar leituras e validações
por trigger, concede SELECT nas tabelas de contratos, lotes, movimentos, observações e
arquivamento. Para escrita, concede SELECT/INSERT apenas na tabela de revisões e USAGE da
sua sequence; também concede EXECUTE na projeção efetiva. Antes remove grants excessivos
do runtime nos objetos de revisão/sequence/função. Não concede UPDATE, DELETE ou TRUNCATE
na tabela de revisões. Não se validou a configuração de nenhuma instância externa.

## Endpoints

- `POST /api/fixed-income/investments/{investment_id}/applications/{movement_id}/revisions`
- `POST` no mesmo caminho terminado em `/preview` (não persiste a revisão; usa savepoint,
  triggers e rollback local para compartilhar as validações PostgreSQL).
- `GET` no caminho de revisões, com `offset` e `limit` (máximo 200), filtrado pelo dono.

Escrita exige `Idempotency-Key` UUID, `expected_revision`, `reason` não vazio e `kind`.
REPLACE exige o principal total e data; VOID não aceita substitutos e é terminal. Mesmo
conteúdo/chave reexecuta a resposta (200); chave com conteúdo diferente gera 409; nova
revisão gera 201. Ausente/alheio retorna 404 sem revelar propriedade. Entrada inválida
retorna 422. Cronologia/conflitos retornam 409 ou 422 com mensagem sem detalhe SQL.

Exemplo fictício:

```http
POST /api/fixed-income/investments/41/applications/88/revisions
Idempotency-Key: 6ca12dfc-63fa-4a01-baf0-746c8d1ae200
Content-Type: application/json

{"kind":"REPLACE","expected_revision":0,"reason":"Valor de cadastro incorreto",
 "replacement_date":"2025-01-03","replacement_amount":"100.00"}
```

## Validação e proteção

O helper adquire lock transacional por contrato, relê a aplicação e então serializa a
chave de idempotência. Trigger SECURITY INVOKER da migration 007 aplica os limites de
cronologia por ID global: data não pode preceder evento anterior nem ultrapassar evento
posterior; igualdade é permitida. Em seguida o trigger 006 preserva verificações de
abertura, primeira aplicação, observações, datas e saldos intermediários, contando
resgates existentes. Projeção continua como fonte dos cálculos; movimentos, lotes e
observações originais não são atualizados nem apagados. Nenhum resgate é sintetizado.

Preview usa savepoint e rollback dentro da transação, portanto não deixa evento, mas pode
consumir valor de sequence; também serializa sob lock e aplica as mesmas triggers. Como
resultado é só uma simulação momentânea, uma escrita posterior deve reenviar revisão e
esperado atuais. Integração descartável de 001–007 precisa ser executada antes de qualquer
publicação; Docker indisponível no ambiente atual.

## Execução PostgreSQL descartável no Windows

No PowerShell, na raiz do repositório:

```powershell
& .\backend\tests\run_postgres_diagnostic.ps1
```

O runner usa somente a imagem PostgreSQL já em cache, sem pull, banco efêmero e log em
`%TEMP%`. O teste cria um papel `investment_runtime` fictício e verifica seus privilégios;
nenhuma credencial de ambiente é necessária.
