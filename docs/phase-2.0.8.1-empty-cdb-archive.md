# Fase 2.0.8.1 — arquivamento de contratos CDB vazios

## Escopo

Arquivar somente um contrato pertencente à identidade autenticada quando não houver lote,
movimentação ou observação associado. O arquivamento grava um tombstone append-only; não
remove nem altera o contrato e não apaga ou cria lançamentos financeiros. Contratos
arquivados deixam a listagem ativa e os endpoints operacionais passam a responder 404.
Repetir o arquivamento pelo próprio proprietário retorna 409; IDs alheios retornam 404.
O frontend exige confirmação explícita do navegador e só oferece a ação quando o detalhe
carregado aparenta estar vazio. O servidor e as garantias PostgreSQL são a autoridade final.

## Migration 005

`backend/migrations/versions/005_archive_empty_fixed_income.py` sucede a 004 e cria
`fixed_income_investment_archives`, com FK `ON DELETE RESTRICT` para o contrato, `owner_id`,
`archived_at` e unicidade por `investment_id`. O registro é um tombstone de lifecycle, não
uma movimentação financeira. O downgrade é bloqueado para preservar tombstones.

A tabela aplica RLS e `FORCE ROW LEVEL SECURITY` com a mesma regra de proprietário/modo local
das tabelas da renda fixa. A migration revoga privilégios de PUBLIC, `anon`, `authenticated`
e `service_role`; não concede `UPDATE`, `DELETE` ou `TRUNCATE`. O papel de runtime precisa
receber somente `SELECT` e `INSERT` na tabela e `USAGE` na sequência, além dos privilégios
de leitura já necessários nas dependências. Isso deve ser conferido na configuração local
de cada ambiente antes de qualquer aplicação futura; não foi feita alteração remota.

Um trigger invoker valida proprietário e ausência de lotes, movimentações e observações.
Ele adquire o advisory lock transacional `20001, investment_id`, compartilhado pelas
gravações atuais de lotes, movimentações e observações. O endpoint adquire o mesmo lock
antes de consultar a elegibilidade e o mantém até o commit. Assim, sob `READ COMMITTED`,
uma aplicação/observação concorrente confirma primeiro e torna o arquivamento inelegível,
ou o tombstone confirma primeiro e a gravação posterior é rejeitada.

Os triggers de lote, movimentação e observação também rejeitam novas dependências após o
arquivamento, inclusive em inserções SQL feitas pelo papel de runtime. Toda futura tabela
dependente de contrato precisará participar do mesmo lock e ser incluída na verificação de
elegibilidade, trigger e testes. As FKs existentes e o tombstone não usam cascata.

## API e interface

- `DELETE /api/fixed-income/investments/{id}/archive`: 204 ao arquivar, 409 se o próprio
  contrato já estiver arquivado ou tiver dependências, 404 para proprietário diferente.
- Listagem, detalhe, movimentos, observações e estimativas não expõem contratos arquivados.
- O cliente pergunta explicitamente antes de enviar; em sucesso fecha o detalhe, atualiza a
  lista ativa e informa que o contrato vazio foi arquivado. Erros de conflito preservam o
  detalhe e mostram a resposta da API.
- Nenhum cálculo de principal/rendimento foi alterado. Os valores originais do contrato,
  ledger e observações permanecem intocados.

## Validação local

Os testes de unidade cobrem proprietário, contrato vazio, lote, observação, repetição e
ocultação sem remoção. A integração PostgreSQL descartável percorre 001–005, verifica
RLS/FORCE RLS, grants, imutabilidade, bloqueio de novas dependências, preservação do contrato
original e corrida entre aplicação e arquivamento. Os testes de frontend cobrem confirmação,
cancelamento, sucesso, ocultação e conflito. Resultados executados estão registrados em
`docs/validation.md`, com a execução PostgreSQL identificada como relato do usuário quando
não repetida pelo agente.

## Riscos e pendências

- A serialização depende dos triggers e escritores de dependências usarem o advisory lock
  compartilhado. Novos caminhos de escrita devem seguir esse contrato.
- Um banco cujo papel de runtime não tenha `SELECT`/`INSERT` mínimos na nova tabela retornará
  erro de banco; a migration não adivinha o nome de um papel customizado.
- A checagem cobre as dependências conhecidas no schema atual. Uma futura FK/tabela que
  referencie contratos exige atualização desta regra antes de ser habilitada.
- Arquivamento não é reversível pela API. Correção operacional deve ser uma migration ou
  processo auditado separado; não reativar alterando/excluindo o tombstone.
- A migration é local. Foi aplicada somente ao banco efêmero de integração; aplicação em
  ambiente persistente, grants remotos, homologação e publicação continuam fora do escopo desta
  entrega.
