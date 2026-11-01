# Investment Dashboard — v2.0 e v3.0

**Atualizado em 01/11/2026.** Este documento descreve o estado do checkout local, não o estado de serviços externos. A última versão publicada continua sendo a v1.2.0. A candidata v2.0.0 ainda requer validação local completa e aprovação do proprietário; não houve commit, push, release, deploy ou acesso a banco de produção.

## Estado das versões

| Versão | Conteúdo | Estado neste checkout |
|---|---|---|
| v1.2.1 | Correções de cobertura histórica, rótulos de exportação, aviso de privacidade da Íris e orientação para observações de CDB. | Incluída na candidata; ainda não publicada. |
| v1.3.0 | Histórico individual Brapi Free, comparação de preços ajustados, cobertura parcial explícita e relatório manual de dividendos/JCP. | Incluída na candidata; recursos Brapi continuam opt-in. |
| v2.0.0 | Observações patrimoniais datadas, evolução com cobertura, comparação de benchmarks e explicação contextual da Íris. | Implementada localmente; migration 010 ainda não aplicada em produção. |
| v3.0 | Acesso por convite, carteiras separadas por proprietário e ciclo seguro de entrada/saída. | Não implementada. Depende dos critérios de segurança abaixo. |

## v2.0.0 implementada localmente

### Patrimônio e desempenho

- Observações financeiras são anexadas com data, classe, valor, moeda, origem e nota; correções são novas observações, não edições do histórico.
- Ações exigem valor de mercado informado e fonte identificada. CDBs entram somente quando existe uma observação de saldo para a mesma data. Caixa e outros ativos sem observação não são inferidos.
- A evolução retorna observações disponíveis e estados `complete`, `partial`, `unavailable` ou `empty`. Um total é omitido quando falta cobertura de uma classe habilitada; a interface não interpola nem inventa pontos.
- O endpoint de desempenho existente mantém resultados realizados e não realizados cobertos separados. Não calcula retorno total da carteira, TWR ou XIRR sem valuations e fluxos completos e comparáveis.
- `/api/dashboard/benchmarks` compara CDI, Ibovespa e IPCA somente em meses comuns efetivamente cobertos, com base 100 e aviso de cobertura. Isso não representa rentabilidade da carteira. A série depende da disponibilidade das fontes públicas BCB SGS e Brapi; não houve chamada externa nesta validação.
- Relatórios de dividendos/JCP somam apenas eventos manuais registrados e ativos no ledger, com filtros por data, ativo e tipo. Não há feed automático de proventos.

### Íris

A Íris pode explicar indicadores e gráficos com conhecimento estático e um rótulo da tela atual escolhido de uma lista fechada. Nenhuma posição, operação, saldo, filtro, token ou carteira é enviado à Groq. A chamada depende de configuração externa e da cota Free; indisponibilidade da IA não bloqueia o dashboard. Não há RAG, memória persistente ou recomendação de compra e venda.

### Persistência e API

- Migration `010_portfolio_valuation_observations` cria a tabela append-only com UUID do proprietário, RLS/FORCE RLS, policy de proprietário e privilégios mínimos.
- `GET` e `POST /api/dashboard/wealth-observations` exigem autenticação. A gravação aceita chave de idempotência e não expõe acesso entre proprietários.
- `GET /api/dashboard/benchmarks` exige autenticação e não consulta o banco financeiro.
- O formato manual de backup `IDBKP010` inclui a nova tabela; o leitor continua aceitando arquivos `IDBKP009` legados. O backup continua manual e não inclui Supabase Auth, Storage nem configurações externas.
- `docs/fixtures/v2-demo-scenario.json` contém somente dados fictícios para reconciliação local.

## Limites e critérios de interpretação

- A Brapi Free fornece histórico ajustado limitado e não oferece, nessa configuração, os preços crus e eventos societários necessários para reconstruir o valor histórico agregado da carteira. A cotação ajustada individual não é tratada como valuation nem como retorno total. Confira os [limites por plano](https://brapi.dev/faq/quais-as-limitacoes) e o [contrato do histórico](https://brapi.dev/docs/acoes/historico) antes de habilitar em um ambiente.
- O provider usa `adjustedClose` como enviado, sem preenchimento, suavização ou substituição por `rawClose`. Uma queda acentuada pode decorrer de ajuste societário legítimo, mas a resposta Free sem preço cru/evento não permite confirmar a causa. A interface mantém a base e a fonte visíveis; não classifica a queda automaticamente.
- CDI e IPCA têm fontes, periodicidades e unidades diferentes do Ibovespa. A API compara somente pontos mensais com janela comum e não preenche dados ausentes. Fonte: [BCB SGS 12 — CDI](https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados/ultimos/12?formato=json), [BCB SGS 433 — IPCA](https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/12?formato=json) e [Brapi](https://brapi.dev/faq/buscar-ibov). A validação usa mocks e não confirma disponibilidade atual dos provedores.
- Observações prospectivas não reconstruem anos anteriores à primeira coleta. Dados privados reais não foram usados nos testes.
- Demonstração pública, autenticação e repositório privado permanecem separados. Os testes automatizados cobrem a ausência de chat na demo; isso não equivale a uma inspeção visual autenticada em produção.

## Critérios ainda necessários para v3.0

A v3.0 não está implementada e não deve ser declarada concluída até que todos estes pontos sejam testados em ambiente descartável e em um piloto autorizado:

1. Convites de uso limitado, expirados e revogáveis; cadastro público irrestrito permanece desabilitado.
2. Cada recurso financeiro é vinculado ao UUID do proprietário autenticado no servidor; não confiar em `owner_id` recebido do cliente.
3. RLS/FORCE RLS e grants mínimos em todas as tabelas financeiras, incluindo novas tabelas; testes negativos com ao menos dois usuários comprovam que leitura e escrita cruzadas falham.
4. Limites de uso da Íris são aplicados no backend e não permitem consumo descontrolado nem envio automático de dados da carteira.
5. Exportação e exclusão de conta têm escopo, confirmação, tratamento de dependências e testes de restauração/remoção; exclusão não deixa dados financeiros órfãos.
6. Testes de autenticação, convite, revogação, isolamento, backup/restore e regressão da demonstração pública passam antes de qualquer publicação.

Não se iniciou implementação de multiusuário nem se aplicou migration 010 em produção. A publicação da v2.0 exige primeiro concluir os testes locais, revisar o backup/restore sintético e autorizar separadamente a operação de deploy/migration.

## Fora do escopo aprovado

CSV genérico, Open Finance, scraping, integração automática com corretoras, negociação, recomendações de compra/venda, API de mercado paga, cadastro público irrestrito, monetização, RAG, memória persistente da Íris, sincronização de metas e rentabilidade TWR/XIRR sem dados suficientes não fazem parte das versões v1.2.1, v1.3, v2.0 ou v3.0 aqui definidas. Esta lista delimita o escopo; não é backlog pendente.

## Validação local

Backend: 419 aprovados e 1 ignorado; frontend: 230 aprovados em 32 arquivos; build TypeScript/Vite aprovado com 2.384 módulos. A integração PostgreSQL 17 local passou com migrations 001–010, role restrita, duas identidades fictícias e round-trip de backup/restore IDBKP010. Foram corrigidos a serialização sob RLS, timestamps UTC e o contexto limitado da Íris; os gráficos diários usam rótulos dia/mês. Não houve chamada Groq/Brapi/BCB, acesso a carteira real, conexão/migration remota, commit, push ou deploy. A inspeção visual Supabase autenticada permanece manual. Evidência detalhada em [`validation.md`](validation.md).
