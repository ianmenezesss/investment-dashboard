# Fase 5.1 — Fluxos externos, proventos e eventos observados

**Estado:** implementada e validada localmente em `feat/v5-development`. A migration 009 foi aplicada somente aos bancos PostgreSQL descartáveis de teste; nenhum banco persistente ou de produção foi alterado.

## Escopo entregue

- Registro manual e privado de aportes e retiradas externos, dividendos, JCP e observações societárias.
- Consulta de eventos efetivos e resumo por período.
- Inclusão dos eventos efetivos no histórico unificado existente e dos totais de caixa/proventos na área de indicadores.
- Correções append-only por `REPLACE` e `VOID`, com justificativa, revisão esperada e chave de idempotência.
- Interface na página de histórico para registro, correção e anulação; revisão exige confirmação explícita antes de um `VOID`.

## Regras financeiras

- `CONTRIBUTION` e `WITHDRAWAL` são transferências entre o titular e a carteira. A direção vem do tipo; o valor registrado é positivo. Compras/vendas de ações e aplicações/resgates de CDB continuam nos ledgers existentes e não são convertidos em aporte/retirada.
- `DIVIDEND` e `JCP` registram o caixa recebido. Valor bruto e imposto retido são opcionais e permanecem `null` quando desconhecidos. Se ambos forem fornecidos, o backend valida `bruto - imposto = recebido`. Não são estimados rendimentos nem valores fiscais.
- Reinvestimento de provento é registrado como provento recebido e como compra/aplicação já pertencente ao ledger existente. O mesmo provento não deve ser lançado como aporte externo.
- `CORPORATE_ACTION` é uma observação textual associada ao ativo e a uma fonte declarada. Não ajusta quantidade, custo, posição, caixa ou preço; desdobramentos, bonificações e outros eventos ainda exigem tratamento sustentado por dados e metodologia específicos.
- Os totais apresentados são `aportes - retiradas` e valores de caixa de dividendos/JCP. Eles não representam patrimônio, lucro ou rentabilidade. O sistema ainda não registra tarifa de transferência como campo separado; lançar somente o valor observado do fluxo e não inferir uma tarifa.
- Os valores monetários persistidos são `NUMERIC(20,8)` e processados com `Decimal`. A interface apresenta BRL, conforme a moeda suportada pelo dashboard.

## API e persistência

- `GET /api/financial-events` — lista apenas eventos efetivos do proprietário autenticado.
- `POST /api/financial-events` — registro manual, exige `Idempotency-Key` UUID.
- `GET /api/financial-events/{event_id}/revisions` — trilha de correções, visível somente ao proprietário.
- `POST /api/financial-events/{event_id}/revisions` — adiciona substituição ou anulação; exige revisão esperada, motivo e chave de idempotência.
- `GET /api/dashboard/financial-events/summary?period=1M|3M|6M|1A|Tudo` — totais por intervalo.

Todos os endpoints são privados. `private_db` instala o proprietário validado pelo Supabase; consultas filtram `owner_id`, e a migration aplica RLS e FORCE RLS. O e-mail e os metadados de apresentação não participam da autorização. As tabelas e revisões são append-only; runtime recebe somente `SELECT`/`INSERT` e uso das sequências. Downgrade é intencionalmente bloqueado.

A migration 009 cria `financial_events` e `financial_event_revisions`, índices, constraints, RLS/policies, triggers de imutabilidade, guarda de sequência das revisões e grants mínimos. Não há backfill: operações anteriores não são reinterpretadas como depósitos, retiradas ou proventos.

`REPLACE` insere uma revisão com payload substituto e motivo; `VOID` insere uma revisão terminal sem payload. A projeção efetiva usa a revisão mais recente e exclui anulados. O histórico preserva o original e mostra a revisão efetiva; a interface permite consultar o motivo e a sequência de revisões.

## Testes e validação

- Backend: testes de aportes/retiradas/proventos/JCP/evento observado, `Decimal`, idempotência, payloads inválidos, resumo, proprietário, histórico unificado, `REPLACE`/`VOID` e autenticação.
- PostgreSQL descartável: cadeia 001–009, persistência, RLS/FORCE RLS, isolamento entre dois proprietários, grants restritos, constraints financeiras e backup/restore independente.
- Frontend: inclusão, correção/alteração de tipo, justificativa, confirmação de anulação, consulta das revisões, filtros do histórico e resumo sem confundir fluxo com rentabilidade.
- Backend completo: **373 aprovados, 1 ignorado**, 1 aviso conhecido de depreciação do `TestClient`/httpx.
- Frontend completo: **180 aprovados** em 19 arquivos.
- PostgreSQL descartável: **1 aprovado**; migrações 001–009, RLS/isolamento, constraints, e backup/restore com contagens, grants e acesso por proprietário iguais.
- Build: `npm run build` aprovado. `npm audit --audit-level=low` e `pip-audit -r backend/requirements.lock.txt`: **0 vulnerabilidades conhecidas** nas bases consultadas.
- `git diff --check`: aprovado; avisos de conversão LF/CRLF permanecem apenas como comportamento de checkout Windows.

## Limitações e dependências seguintes

- Não há saldo de caixa conciliado, registro de tarifas de transferência, eventos societários quantitativos nem fonte de preço histórico aprovada.
- Nenhum evento antigo é fabricado ou importado automaticamente.
- A Fase 5.2 precisa começar por um único formato autorizado e uma fixture CSV anonimizada. Não processar um extrato real até definir mapeamento e regras de deduplicação.
- A Fase 5.6 permanece condicional às avaliações patrimoniais datadas, fluxos completos e fonte gratuita/licenciada; esta fase não calcula TWR, MWR, lucro total ou benchmark.
