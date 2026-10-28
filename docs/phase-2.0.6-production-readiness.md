# Fase 2.0.6 — prontidão de produção

Revisão local em 28/10/2026 para preparar a publicação da Fase 2.0.5. Esta fase não
adiciona funcionalidades. O commit `385120723a183f0964652682a99a7e64ab281ab9`
está presente em `main`; checkout limpo e um commit à frente de `origin/main`.

## Resultado da revisão local

- Migration `004` declara dependência de `003`; cria snapshots separados do ledger,
  constraints de valores/taxas, índices por proprietário e cronologia, e índice único
  parcial para uma abertura por investimento.
- RLS e FORCE RLS usam `app.user_id` (com exceção local já existente). Triggers validam
  proprietário, contrato, datas, abertura sem histórico, cronologia, concorrência e
  append-only. A migration também estende a validação de lotes e protege movimentos
  posteriores à posição observada. Downgrade destrutivo é bloqueado.
- Endpoints usam autenticação e `owned_investment`; escrita valida o contrato, serializa
  por advisory lock no PostgreSQL e converte duplicidade em conflito. Valores monetários
  usam Decimal/Pydantic e constraints SQL. Listagem é limitada/paginada.
- Não foram encontrados problemas que justificassem correção de código nesta revisão.
- A integração PostgreSQL e as regressões específicas já constam como aprovadas no
  registro da Fase 2.0.5 em `docs/validation.md`. Tentativa de reexecução nesta sessão
  não iniciou: o Python da `.venv` aponta para uma instalação indisponível e o Python
  empacotado pelo Codex não inclui pytest. Portanto, sem nova execução nesta revisão.
- Nenhum build foi executado: nenhum arquivo de aplicação foi alterado. As aprovações
  anteriores de testes/builds permanecem registros da Fase 2.0.5, não uma validação nova.
- Não foram feitas conexões a Supabase, Render ou Vercel. Aplicação da 004, grants
  remotos, allowlist efetiva e homologação das duas contas continuam pendentes.

## Publicação manual — ordem e comandos

Executar somente após autorização explícita, backup recuperável ensaiado e confirmação
do destino. O procedimento detalhado de diagnóstico, TLS, grants e verificações SQL está
em [Fase 2.0.5 — implantação manual](phase-2.0.5-opening-balance.md#implantação-manual-supabase--render--vercel).
Não use a URL administrativa em argumentos de processo, histórico ou logs.

1. No Supabase, confirmar projeto/host/usuário, backup e restauração ensaiada. Em conexão
   somente leitura, confirmar `alembic_version = 003`, ausência da tabela de observações,
   ownership das funções e papel runtime sem privilégios administrativos.
2. Em PowerShell, no diretório `backend`, preencher a CA já validada e a URL administrativa
   remota com `sslmode=verify-full` conforme o runbook vinculado. O runbook salva/restaura
   variáveis de ambiente e pede confirmação textual antes de gravar. Comandos centrais:

   ```powershell
   .\.venv\Scripts\python.exe -m alembic current
   # Somente após autorização explícita e checagem independente do backup/destino:
   .\.venv\Scripts\python.exe -m alembic upgrade 004
   .\.venv\Scripts\python.exe -m alembic current
   ```

   Esperado: `003` antes e `004` depois. Se o Python da `.venv` não iniciar, pare e
   restabeleça o ambiente aprovado; não use outro interpretador sem dependências fixadas.
3. No SQL Editor Supabase, aplicar somente os `GRANT USAGE ON SCHEMA`, `SELECT, INSERT`
   na tabela nova e `USAGE` na sequência descritos no runbook. Não conceder UPDATE,
   DELETE, TRUNCATE, ownership ou BYPASSRLS. Confirmar RLS/Force RLS, policy, triggers,
   índices, grants e privilégios herdados usando as consultas somente leitura do runbook.
4. Publicar backend no Render sem migration automática; verificar health e endpoints
   privados autenticados. Manter `ALLOWED_USER_IDS` explícito apenas com os dois usuários
   autorizados, TLS `verify-full`, auth e CORS restritos. Publicar depois o frontend
   privado na Vercel. Não alterar o projeto da demo.
5. Executar homologação secundária abaixo. Confirmar isolamento da conta principal e
   operação offline da demo antes de considerar a fase pronta para iniciar 3.0.

Não repetir migration após timeout sem verificar `alembic_version` e transação. Não usar
`stamp`, downgrade, DROP ou grants amplos. A tabela de snapshots é append-only; recuperação
de falha é correção para frente. Se for necessário restaurar backup, fazê-lo somente com
decisão explícita, ensaio isolado e plano que considere todas as escritas posteriores.

## Homologação manual — conta secundária

- [ ] Entrar na conta secundária autorizada.
- [ ] Cadastrar contrato CDB inteiramente fictício.
- [ ] Registrar saldo inicial fictício; confirmar bruto/líquido e principal não informado.
- [ ] Tentar segunda abertura e confirmar bloqueio `409`.
- [ ] Registrar nova aplicação posterior à abertura.
- [ ] Registrar observação posterior e verificar histórico append-only.
- [ ] Atualizar página e sair/entrar; confirmar persistência.
- [ ] Em sessão secundária, confirmar que ids fictícios da conta principal não são acessíveis
      (404), sem sondar registros reais; ausência de sessão deve retornar 401.
- [ ] Confirmar que a conta principal segue isolada e que a demo pública não chama backend,
      Supabase ou dados privados.

Usar somente valores fictícios. Não apagar registros de homologação, pois são imutáveis.

## Pendências antes da Fase 3.0

- [ ] Backup de produção recuperável e ensaio de restauração confirmados.
- [ ] Migration 003 confirmada em produção; migration 004 aplicada manualmente após autorização.
- [ ] Grants mínimos e RLS conferidos na instalação real.
- [ ] Backend e frontend publicados manualmente e endpoints autenticados verificados.
- [ ] Homologação secundária aprovada; isolamento da conta principal e demo offline confirmados.
- [ ] Revisão final de privacidade e configuração efetiva de `ALLOWED_USER_IDS`.

Até concluir essas verificações, a 004 está **validada localmente/documentalmente**, mas
**não homologada nem aplicada em produção**; a publicação não está autorizada nem executada.
