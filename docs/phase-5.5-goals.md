# Fase 5.5 — Metas financeiras

**Estado em 30/10/2026:** implementada localmente na branch `feat/v5.5-goals`, criada a partir de `main`/`origin/main` em `d80b69c`. Os commits 5.5A, 5.5B e 5.5C são separados. Nenhum merge, push, deploy, chamada ao Supabase de produção ou alteração de banco foi realizado.

## 5.5A — Cadastro local

- Cada meta contém nome, valor-alvo, prazo opcional, valor inicial de referência, progresso manual inicial e premissas locais para planejamento.
- O proprietário pode criar, editar e excluir metas. Metas são apresentadas como ativas, vencidas, sem prazo ou concluídas; a conclusão depende do valor da modalidade de progresso selecionada.
- A persistência usa `localStorage` por identidade Supabase autenticada, no navegador e perfil atuais. Não existe sincronização entre dispositivos, persistência em backend, exportação ou cópia para a demo pública.
- O formato tolera os campos acrescentados nas entregas 5.5B/C. Dados locais corrompidos ou incompatíveis não são sobrescritos automaticamente.

## 5.5B — Progresso e proveniência

- **Manual:** valor informado pelo proprietário e confirmado na meta. A confirmação fica registrada localmente com data/hora.
- **Capital investido:** leitura autenticada de `GET /api/dashboard/performance`; usa apenas `capital.open_positions_accounted`, cuja base deve ser `equity_open_acquisition_cost_plus_effective_cdb_principal`.
- O agregado é custo de aquisição das posições abertas em ações com taxas registradas mais principal efetivo aberto de renda fixa. Não é patrimônio a mercado. Não inclui depósitos/retiradas externos, dividendos/JCP, posições declaradas sem saldo de lotes ou observação, nem valores estimados por cotação.
- Posições de renda fixa sem saldo apurado, posições declaradas separadas e componentes desconhecidos geram aviso de cobertura parcial. Cotações de mercado ausentes não tornam incompleto o custo de aquisição, porque não são usadas nesse cálculo.
- Se o endpoint falhar ou a base for inválida, a meta mostra o último valor manual salvo e mantém a atualização manual disponível. Se houver cobertura parcial, a meta identifica a base e deixa o modo manual acessível.
- A fronteira privada continua sendo o `PrivateRepository` e o endpoint existente autenticado; a demo pública redireciona `/metas` e não busca nem persiste metas.

## 5.5C — Planejamento hipotético

- Usa `monthlyEffectiveRate` e `simulateScenario` do Simulador 5.4. A taxa efetiva mensal é `(1 + taxa anual efetiva)^(1/12) − 1`; os aportes planejados entram no fim do mês.
- As taxas anuais padrão são 6%, 10% e 14%, editáveis por meta e salvas apenas localmente. Aceita hipóteses maiores que −100% e até 500% a.a., como o Simulador.
- Mostra a diferença até o alvo, o aporte mensal necessário para o horizonte escolhido, o tempo matemático para alcançar o objetivo com o aporte informado e a evolução nominal dos três cenários.
- Se o prazo futuro da meta for usado, o horizonte é calculado em meses-calendário. Sem prazo, com prazo no dia atual ou vencido, usa-se horizonte manual. O cálculo é limitado a 600 meses.
- A fórmula do aporte no fim do mês é: `PMT = max(0, [alvo − base × (1+r)^n] / [((1+r)^n − 1)/r])`; com taxa zero, `PMT = max(0, alvo − base)/n`.
- Quando a base selecionada é capital investido, a simulação parte do custo/principal registrado como hipótese matemática. Isso não estima nem declara o patrimônio atual a mercado. As projeções são nominais; não incluem inflação, tributos, custos, risco, volatilidade ou garantias e não calculam rentabilidade real.

## Dados e operações

- Nenhuma migration foi criada ou alterada. A 009 e os registros financeiros existentes ficam intocados. O proprietário informa que a 009 foi aplicada ao Supabase de produção; esta etapa não fez verificação independente.
- Não foram adicionados endpoints, modelos, dependências pagas ou integrações externas. O endpoint de performance já existente é apenas consultado, e somente na área privada.
- A branch não deve avançar para a Fase 5.6 automaticamente. A decisão de merge e publicação continua manual.

## Validação e limitações

- Casos cobertos por testes: CRUD/validação, separação local por identidade, proteção da demo, migração não destrutiva do formato local 5.5A, progresso manual/capital investido, cobertura parcial e indisponível, valores extremos, cenários zero/negativo, prazos completos/vencidos/ausentes e limite de 600 meses.
- Suite frontend completa: ver [registro de validação](validation.md). O backend não mudou; nesta execução o teste backend não pôde iniciar porque o `.venv` aponta para um executável Python da Microsoft Store inacessível. A integração PostgreSQL não foi executada.
- A verificação automática do CSS e do build confirma as regras responsivas empacotadas; a revisão visual em navegador real deve ocorrer antes de publicar.
- Os dados locais dependem da retenção do armazenamento do navegador. Limpar os dados do site ou usar outro perfil/dispositivo não transfere as metas.
