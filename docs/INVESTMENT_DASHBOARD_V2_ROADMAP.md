# Investment Dashboard — versões públicas e fechamento da v3.0

Atualizado em 01/11/2026. A v2.0.0 é a última versão publicada, segundo o proprietário. A v3.0.0 está implementada e validada localmente, mas ainda não publicada; nenhuma migration ou configuração de produção foi executada nesta validação.

## Versões

| Versão | Conteúdo | Estado |
|---|---|---|
| v1.2.1 | Estabilização da cobertura histórica, clareza da exportação, aviso de envio à Groq e orientação para registros de CDB. | Incluída na v2.0.0. |
| v1.3.0 | Histórico individual Brapi Free, comparação de ativos com cobertura efetiva e histórico de observações CDB. | Incluída na v2.0.0; Brapi é opcional e limitado pelo plano Free. |
| v2.0.0 | Evolução patrimonial por observações datadas, métricas com cobertura explícita e Íris com contexto público da tela. | Publicada segundo o proprietário. |
| v3.0.0 | Acesso por convite, carteiras isoladas, quotas persistentes da Íris, exclusão retomável e loader administrativo fictício. | Código final validado localmente; publicação ainda não executada. |

## Escopo implementado na v3.0

- Supabase Auth mantém a identidade; não há rota de cadastro público. Convites são enviados pelo Admin Auth API usando chave somente no backend. UUID, e-mail confirmado e membership ativo são verificados no servidor.
- Memberships e dados financeiros permanecem separados por proprietário com RLS/FORCE RLS. A administração pode gerir acesso, sem acesso privilegiado às carteiras. Limites persistentes da Íris são 5 mensagens/minuto e 50/dia por conta ativa; a IA não recebe carteira, operações, saldos ou token.
- Migration 012 adiciona jobs/auditoria de exclusão e proveniência de fixture. A exclusão exige confirmação textual e autenticação recente, não aceita UUID de outra conta, apaga dados por fases retomáveis e só remove a identidade pelo Supabase Admin API após o purge financeiro. Ledgers mantêm triggers append-only; uma role NOLOGIN sem BYPASSRLS, sem memberships e sem DELETE/TRUNCATE de runtime é dona das funções restritas.
- `backend/scripts/load_demo_fixture.py` é a única entrada do loader, sem endpoint público. Exige UUIDs do admin e destino, allowlist, confirmação, projeto Supabase/DB coincidente, usuário existente e carteira vazia. Valida valores, datas, ordem e consistência; insere ações, CDB, proventos e observações patrimoniais suficientes em transação única. Marca a origem fictícia, grava marker de idempotência e a interface privada avisa quando a fixture está carregada.
- A demonstração pública permanece offline e sem Íris, gestão de convites, loader ou chamadas à API privada. Comparador de CDI/Ibovespa/IPCA foi removido; a série BCB necessária à renda fixa permanece.

## Validação local

- Backend completo: 439 aprovados, 1 ignorado; o ignorado é a integração PostgreSQL opt-in executada separadamente.
- PostgreSQL 17 descartável: migration 001–012, isolamento entre proprietários, exclusão e falha parcial, loader com conta vazia/não vazia e backup/restauração `IDBKP012` aprovados.
- Frontend: 232 testes aprovados em 33 arquivos; build TypeScript/Vite aprovado, 2.387 módulos transformados; `git diff --check` aprovado.
- Nenhum serviço externo, banco ou conta real foi acessado. A interface autenticada ainda não foi inspecionada em navegador com sessão Supabase real.

## Condições operacionais para publicação

1. Confirmar a revisão real do banco, criar backup protegido correspondente e ensaiar restore em PostgreSQL descartável.
2. Confirmar que a role DDL do Supabase pode criar `investment_deletion_executor` e transferir ownership das funções; manter `DATABASE_URL` no papel runtime restrito.
3. Aplicar apenas as migrations ausentes até 012 e verificar RLS/FORCE RLS, owners das funções e grants antes de publicar os três serviços.
4. Conferir manualmente Render, Supabase e Vercel, incluindo cadastro público desabilitado, redirects de convite, secrets e CORS.
5. Após publicar, testar login/convite, demonstração pública e área privada com uma conta de teste autorizada. Não usar dados financeiros reais na homologação da Íris.

## Fora do escopo da v3.0

Cadastro público irrestrito, importação CSV, Open Finance, sincronização bancária, negociação automática, recomendação de compra/venda, RAG, memória persistente da Íris e APIs pagas não fazem parte do produto aprovado. A v3.0 encerra o desenvolvimento funcional planejado; não há backlog de funcionalidades posteriores neste roadmap.
