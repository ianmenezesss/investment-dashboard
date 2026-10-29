# Fase 3.0.4 — revisão final do histórico e dos indicadores

**Estado: implementação concluída e validada localmente para revisão em 29/10/2026.**
Esta rodada não publicou a aplicação, não executou migrations nem alterou dados de
produção. A Fase 3.0.3 permanece pendente de uma fonte histórica adequada e validada.

## Escopo concluído

- Histórico privado `/historico`, carregado de `GET /api/dashboard/movements`, reúne
  compras/vendas de ações e aplicações/resgates efetivos de CDB. Filtra por datas, classe
  e ativo, ordena do mais recente para o mais antigo e identifica movimentações por classe
  e ID. A projeção CDB respeita REPLACE/VOID; consulta e composição são limitadas ao
  `owner_id` autenticado.
- `GET /api/dashboard/capital-flows` alimenta o gráfico de compras/aplicações acumuladas,
  vendas líquidas/resgates de principal acumulados e fluxo líquido acumulado. Filtros de
  período alteram a janela do gráfico e do detalhamento; os indicadores históricos continuam
  representando o histórico inteiro até a data-base.
- `GET /api/dashboard/composition` alimenta a composição atual por custo aberto de ações e
  principal efetivo de CDB. Observações declaradas sem base confiável de reconciliação ficam
  apresentadas em série separada e excluídas do total e dos percentuais agregados.
- O dashboard e Ações mantêm os indicadores de ações e o painel compartilhado de fluxos e
  composição. A área CDB permanece na rota `/cdbs`; `/historico` contém somente a tabela
  unificada. A navegação privada compartilha a identidade do usuário nas consultas.

## Semântica financeira

- **Compras de ações:** quantidade × preço + taxas registradas. **Aplicações CDB:** principal
  registrado. O total acumulado soma esses dois fluxos, não depósitos externos confirmados.
- **Vendas:** quantidade × preço − taxas registradas. **Resgates:** principal amortizado,
  sem tratar `cash_received` como rendimento ou lucro. A série de saídas soma venda líquida
  e principal resgatado.
- **Fluxo líquido acumulado:** compras + aplicações − vendas líquidas − principal resgatado.
  Não equivale a lucro, patrimônio, saldo em caixa ou retorno da carteira.
- **Capital aplicado em posições abertas:** custo restante de ações com taxas conforme o
  custo médio do ledger + principal efetivo de CDB. Posições declaradas manualmente não
  entram neste subtotal. Nenhum valor de mercado é somado a ele.
- **Resultado realizado de ações:** segue o cálculo existente em `backend/app/finance.py`:
  valor de venda líquido das taxas menos custo médio atribuível à quantidade vendida; a
  base de aquisição inclui taxas de compra. Tributos não são calculados e as taxas não são
  deduzidas duas vezes.

Todos os cálculos agregados usam os registros do proprietário e movimentos efetivos. Os
valores decimais são preservados no backend. Os gráficos convertem valores para coordenadas
visuais, mas exibem valores de origem no tooltip monetário.

## Preços e estimativas — 3.0.3 pendente

O histórico de operações é a fonte principal da verdade para atividades registradas. Uma
cotação de mercado externa, pontual ou histórica, é uma **estimativa** e não corrige nem
substitui o ledger. A interface identifica valuations/fechamentos externos como estimativas
e orienta conferência dos valores na corretora. O histórico de preços da 3.0.3 foi preservado
sem scraping e sem nova integração nesta rodada.

Para evitar que a pendência histórica bloqueie a 3.0.4, o backend agora possui a variável
opt-in `EQUITY_HISTORY_ENABLED`, desligada por padrão e no modelo Render. O histórico de
preços só faz chamadas ao provedor quando `MARKET_DATA_ENABLED=true`,
`EQUITY_HISTORY_ENABLED=true` e o token está configurado. Assim, cotações pontuais podem
continuar habilitadas com `MARKET_DATA_ENABLED=true` e `EQUITY_HISTORY_ENABLED=false`; a
implementação histórica permanece disponível, mas a interface mostra indisponibilidade
explícita e nenhuma chamada de histórico é feita. Não há variável obrigatória nova para
publicar a 3.0.4.

A 3.0.3 não deve ser considerada resolvida enquanto não houver uma fonte com uso permitido,
cobertura e campos compatíveis com o cálculo (incluindo preço bruto e eventos corporativos).
Futuramente podem ser avaliadas fontes gratuitas permitidas, mesmo que tenham atualização
atrasada, limites de chamadas ou cobertura parcial. Preço ausente deve continuar indisponível;
não se fabricam cotações nem se usam cálculos conhecidos como incompatíveis com a base do
preço. Não há verba aprovada para API paga.

## Autenticação, schema e dados

Endpoints continuam privados com autenticação existente, `private_db` e isolamento por
`owner_id`. A demonstração pública continua offline e não recebe carteira privada. Não houve
mudança de schema, necessidade de migration ou leitura/escrita de banco de produção. A
configuração remota do banco não foi consultada nesta rodada; antes da publicação, confirme
que o banco está na revisão Alembic atual do repositório (008) e que o papel de runtime tem
os privilégios provisionados pelas migrações existentes.

## Validação automatizada

Execute na raiz do checkout no PowerShell:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_finance.py tests/test_price_basis.py tests/test_security.py tests/test_supabase_auth.py tests/test_fixed_income.py tests/test_application_revisions.py tests/test_equity_history.py tests/test_portfolio.py tests/test_unified_movements_api.py tests/test_fixed_income_returns.py tests/test_fixed_income_returns_api.py tests/test_observed_history_api.py tests/test_bcb_rates.py tests/test_bcb_rates_api.py tests/test_valuation.py tests/test_valuation_api.py -q
Set-Location ..\frontend
npm test
npm run build
Set-Location ..
git diff --check
```

Os resultados desta revisão ficam registrados em [validation.md](validation.md). Uma
integração PostgreSQL descartável não foi necessária para esta revisão: não há migration ou
alteração de schema.

## Checklist de conferência manual

Use dados fictícios ou uma base local descartável; não crie operações de teste na conta real.

1. Inicie API e frontend conforme [Supabase Auth — testes locais](supabase-auth.md). Entre
   com a conta autorizada ou use o modo local configurado para o banco local.
2. Na **Visão geral**, confira os indicadores de ações, valuation marcado como estimativa,
   composição, três séries de fluxo e movimentos recentes.
3. Em **Ações**, confira quantidade/custo aberto e histórico de preço com origem, cobertura,
   datas e aviso de conferência na corretora. Se `rawClose` não estiver disponível, confirme
   o estado indisponível e a ausência de preenchimento de lacunas.
4. Em **Renda fixa**, confira aplicações/resgates, principal, histórico original e projeção
   efetiva. Um REPLACE deve aparecer uma vez com os valores corrigidos; um VOID não aparece
   como efetivo. Caixa recebido não deve ser confundido com rendimento.
5. Em **Histórico**, filtre por início/fim, Ações/CDB e texto do ativo; confira ordem
   cronológica, datas `pt-BR`, valores, taxas e colunas com rolagem horizontal em viewport
   estreito. Teste também estado vazio, falha de API e tentativa de recarregar.
6. Na evolução dos fluxos, alterne 1M, 3M, 6M, 1A e Tudo; leia valores exatos nos tooltips e
   confirme que compras/aplicações, vendas líquidas/resgates e fluxo líquido têm rótulos
   separados. Verifique a coluna no celular.
7. Confirme a navegação entre as quatro áreas e retorne à Visão geral sem perda de sessão.

## Recomendação de publicação

A funcionalidade 3.0.4 é independente da fonte histórica e pode integrar uma publicação
controlada com `EQUITY_HISTORY_ENABLED=false`. A implementação 3.0.3 permanece preservada e
indisponível até validação de fonte, cobertura e termos; isso não desliga cotações pontuais
que usem a configuração geral existente. **Decisão desta revisão: NO-GO para executar a
publicação agora**, pois não foram inspecionadas a configuração real do Render/Vercel/Supabase,
a revisão do banco remoto nem o fluxo visual no navegador. A decisão técnica do código é
**GO condicionado** à conferência manual abaixo e à confirmação do schema/roles de produção.
Nenhuma ação remota foi executada.
