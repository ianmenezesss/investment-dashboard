# Fase 5.2 — Importação CSV revisável

**Status local em 29/10/2026:** 5.2A implementada e validada na branch `feat/v5-development`. 5.2B (adaptadores bancários) permanece pendente até haver amostras anonimizadas ou contratos de layout verificados. Não há declaração de suporte a Nubank, Inter ou qualquer outra instituição.

## 5.2A — Importação genérica de eventos 5.1

O importador da página de movimentações lê o arquivo no navegador, em UTF-8 ou Windows-1252, detecta vírgula, ponto e vírgula ou tabulação e respeita aspas, escapes e quebras de linha dentro de campos. O arquivo não é enviado a serviço de terceiros nem armazenado pelo backend.

O usuário mapeia as colunas para data, tipo, valor recebido e ticker; a origem pode vir de uma coluna opcional ou de um rótulo obrigatório preenchido no formulário. O escopo são os eventos `CONTRIBUTION`, `WITHDRAWAL`, `DIVIDEND` e `JCP` da Fase 5.1. Datas aceitas: `AAAA-MM-DD` e `DD/MM/AAAA`. Valores aceitam ponto ou vírgula decimal, até oito casas, dentro dos limites `NUMERIC(20,8)`. Ticker é exigido para dividendos/JCP e proibido para aportes/retiradas. Taxas, bruto, imposto e descrição não são inferidos pelo layout genérico.

A prévia marca linhas inválidas, duplicatas no arquivo e possíveis duplicatas no histórico. O usuário confirma explicitamente antes do envio; cancelar descarta a prévia sem escrita. No servidor, `POST /api/financial-events/import` revalida todo o lote (máximo de 500 linhas), exige autenticação e `Idempotency-Key`, verifica datas futuras e persiste todas as linhas novas numa transação. Qualquer falha não tratada durante a inserção faz rollback do lote. Eventos idênticos por fatos financeiros são ignorados e contabilizados como duplicatas. A comparação não considera o rótulo de origem; duas ocorrências legítimas com mesmo tipo, data, ticker e caixa podem ser classificadas como possíveis duplicatas e devem ser revisadas manualmente antes da importação.

A idempotência usa IDs de requisição determinísticos derivados da chave do lote, proprietário e número da linha. A API não registra um objeto de lote separado; o próprio ledger 5.1 conserva os registros e as chaves idempotentes. Não há migration nesta fase. `owner_id`, `private_db`, autenticação Supabase e RLS/FORCE RLS existentes permanecem em vigor.

### Casos ainda fora do escopo genérico

- CSV de operações de compra/venda, aplicação/resgate de CDB, preço, quantidade, taxa, transferência entre contas ou moedas diferentes.
- Mapeamento de bruto, imposto e identificador estável da instituição; a origem documental pode ser mapeada como `source` ou preenchida no lote.
- Importação de eventos societários quantitativos ou construção de lotes fiscais.
- Resolução automática de conflitos ou alteração de eventos existentes; correções seguem o fluxo append-only da 5.1.

Os contratos e insumos necessários para a etapa 5.2B estão em [preparação para adaptadores bancários](phase-5.2b-adapter-readiness.md). Nenhum layout institucional é suportado ainda.

## Validação local

- Frontend: 182 testes aprovados; build de produção aprovado.
- Backend: 377 testes aprovados, 1 teste opt-in ignorado, 1 aviso de depreciação conhecido.
- PostgreSQL descartável: cadeia 001–009, autenticação/owner isolation/RLS, concorrência de lotes idênticos e ensaio de backup/restore aprovados.
- Sem migration nova, produção, push, merge ou deploy.
