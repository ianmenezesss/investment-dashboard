# Investment Dashboard — planejamento v2.0 e v3.0

**Atualizado em 31/10/2026.** Este é o roadmap funcional atual para as próximas versões principais. Ele descreve o código e a documentação locais; não afirma que recursos opcionais estão ligados em produção nem consulta dados financeiros da carteira.

## Decisão de versão

As etiquetas internas de fase (1.9.x, 2.0.x, 3.x, 4.x e 5.x) registram entregas técnicas anteriores e **não são versões major públicas do produto**. As versões públicas seguem `CHANGELOG.md` e as tags de release. A v1.2.0 — Íris foi publicada conforme informado pelo proprietário. Este plano organiza a evolução do produto em v1.2.1, v1.3, v2.0 e v3.0; os documentos de fases antigas permanecem como registro histórico.

**Direção aprovada:** estabilizar a v1.2.0 na v1.2.1; recuperar históricos individuais/comparativos compatíveis com a Brapi Free na v1.3; construir análise patrimonial com dados observados na v2.0; e habilitar acesso multiusuário apenas por convite na v3.0. A v1.2.1/v1.3 foi implementada e validada localmente; ainda não foi publicada e nenhuma alteração de produção é declarada neste documento.

## Resumo do estado verificado no código

| Área | Estado atual | Impedimento ou limite comprovado | Próxima ação |
|---|---|---|---|
| Cotação pontual de ações | Adaptador Brapi e cache já existem; integração é opcional. | Dados podem estar atrasados ou indisponíveis, conforme plano e ticker. | Manter o estado explícito, timestamp/cache e nenhum acesso direto pelo navegador. |
| Histórico de valor da carteira de ações | Endpoint, reconstrução por operações, UI e testes existem; desativado por padrão. | O provedor pede `includeRaw=true`, lê `rawClose` e consulta eventos societários. Brapi Free não libera preços raw, não inclui dados de dividendos/eventos e limita a 1 ticker por chamada. O código, por outro lado, agrupa até 20 tickers. Não basta ligar as flags. | Não habilitar com a chave Free atual. Preservar indisponibilidade até existir fonte sem custo que cubra preço original e eventos, ou metodologia segura aprovada. |
| Histórico individual por ativo | Adaptador Brapi Free local usa uma chamada por ticker, `adjustedClose`, cache e limite serial compartilhado por processo; períodos 6M/1A/MAX mostram o trecho disponível como parcial. | A Brapi Free limita o histórico a até 3 meses; o recurso continua opt-in e depende de `MARKET_DATA_ENABLED`, `INDIVIDUAL_EQUITY_HISTORY_ENABLED` e token backend. O limite local de 12.000 chamadas é por processo e não acompanha consumo externo nem reinicializações. | Validar configuração externa manualmente antes de habilitar; nunca usar campo raw ou plano pago. |
| Comparação de ativos | Rota/UI preservam estado parcial, base ajustada, datas efetivas em comum e lacunas sem interpolação; chamadas serializadas para 2–4 ativos da própria carteira. | O índice base 100 compara preços ajustados; não representa retorno líquido nem rentabilidade da carteira. Meses anteriores ao trecho Free não são incluídos. | Habilitar junto do histórico individual e sempre mostrar o estado de cobertura. |
| Cobertura de séries históricas | Históricos individuais propagam as datas retornadas; o agregador não declara cobertura completa quando a primeira data recebida fica dentro do intervalo solicitado. | Histórico agregado continua dependente de `includeRaw=true`, `rawClose` e eventos societários que o Free não fornece. Seu bloqueio segue ativo; `adjustedClose` não é usado para reconstruir o valor da carteira. | Manter valuation histórico agregado indisponível até haver fonte e metodologia adequadas sem custo obrigatório. |
| Histórico de CDB | Endpoint privado e gráfico mostram observações datadas; estado vazio orienta como registrar nova observação consolidada. | Aplicações/resgates não criam snapshots retroativos. Sem observações, não há dados suficientes. Nenhum banco de produção foi consultado. | Registrar somente valor informado pela instituição e data real; não estimar pontos intermediários. |
| Eventos, dividendos e JCP | Cadastro manual, revisão/anulação e movimentos financeiros existem. | A fonte Brapi Free não inclui dados de proventos; exportação JSON cobre somente operações de ações, não é backup integral. | Relatórios filtráveis baseados no ledger manual pertencem à v2.0; esta etapa não importa nem infere proventos. |
| CDI e Selic | Fonte pública SGS/BCB e rotas de taxas existem; os códigos aceitos no código são CDI (12) e Selic (11). | IPCA não está no contrato atual dessas duas séries. Não há benchmark de Ibovespa pronto como comparação uniforme para a carteira. | Acrescentar séries e unidades somente após documentar fonte, calendário, janela e método de comparação. |
| Rentabilidade total da carteira | O endpoint de desempenho atual mostra resultados/fluxos cobertos, mas não declara retorno total. | Faltam série completa de valuations e classificação consistente de fluxos externos, além de dados históricos adequados para todas as classes. Compras/vendas/aplicações não são, por si, aportes externos. | Criar captura prospectiva auditável de valores por classe e fluxos; calcular TWR/MWR/XIRR somente quando os requisitos forem satisfeitos. |
| Íris | Chat privado autenticado, conhecimento estático, stateless, Groq/Qwen opcional; sem acesso à carteira ou persistência. A interface avisa que perguntas são enviadas à Groq e orienta a não incluir dados pessoais/financeiros. | O contexto enviado é a pergunta e o conhecimento estático; cota Free pode indisponibilizar respostas sem bloquear o dashboard. | Na v2.0, explicar gráficos usando somente conhecimento estático e contexto público da interface; nenhum dado privado é enviado automaticamente. |
| Demonstração pública | Build e repositório demonstrativo são isolados do fluxo privado. | É uma fronteira de segurança que deve ser testada em cada release. | Preservar demo offline/fictícia e incluir prova automatizada de que não monta Íris nem chama endpoint privado. |

## Brapi Free: adequação por funcionalidade

Na documentação oficial consultada em 31/10/2026, o plano Gratuito informa 15.000 chamadas por ciclo, 1 ticker por chamada, 1 chamada simultânea, até 3 meses de histórico, atraso de aproximadamente 30 minutos e sem dados de dividendos. `adjustedClose` inclui ajustes por desdobramentos e proventos; `includeRaw=true` e os campos `raw*` estão disponíveis no Pro. Uma resposta a período maior pode retornar `usedRange` menor sem erro HTTP. A Brapi também informa que não é distribuidora/redistribuidora licenciada da B3 e não oferece SLA. Os limites e termos podem mudar e devem ser conferidos novamente antes de integrar ou redistribuir dados: [limites por plano](https://brapi.dev/faq/quais-as-limitacoes), [FAQ do plano gratuito](https://brapi.dev/faq/api-e-gratis-mesmo), [limites simultâneos](https://brapi.dev/docs/mcp), [histórico e base de preços](https://brapi.dev/docs/acoes/historico), [origem/licença e SLA](https://brapi.dev/faq).

| Uso pretendido | Compatível com Free? | Regra segura proposta |
|---|---|---|
| Cotação pontual | Em princípio, sim, sujeita a ticker/cota e atraso do plano. | Requisição backend por ticker conforme limite; cache, timestamp, timeout e falha visível. |
| Histórico individual | Possível para gráfico de preço ajustado até a janela Free documentada, sujeito a cobertura do ticker. | Exibir claramente “preço ajustado”; no máximo 3 meses de dados efetivamente recebidos. Mostrar que 6M/1A/MAX não estão integralmente cobertos. |
| Comparação de ativos | Possível com série ajustada equivalente e datas comuns, sujeito às mesmas limitações. | Uma consulta por ticker; limitar a janela à interseção coberta. Não chamar índice base 100 de retorno da carteira. |
| Valoração histórica da carteira | Não compatível com a implementação atual. | Não multiplicar `adjustedClose` por quantidades históricas reconstruídas sem reconciliar os ajustes/eventos. Não usar `close` como “cru” sem comprovação do contrato e tratamento de eventos. |
| Histórico de dividendos/JCP e eventos societários | Não pelo plano Free documentado. | Manter cadastro manual e estados indisponíveis; não alegar histórico completo de proventos. |

**Resultado prático:** a Brapi Free pode destravar uma etapa de gráficos individuais e comparação em preço ajustado, mas não destrava corretamente a reconstrução histórica do valor da carteira nem dados de dividendos. A cota de 15.000 chamadas não elimina a restrição de 1 ticker por chamada, o limite de simultaneidade nem as lacunas de cobertura. Não há recomendação para upgrade pago.

O backend aplica orçamento local de 12.000 chamadas e uma chamada concorrente por processo. Não é um contador da conta: reinicializações, múltiplas instâncias e outros serviços que usem o mesmo token não são contabilizados. A configuração também fica desabilitada até o operador habilitar o provider e fornecer `BRAPI_TOKEN`.

## Arquitetura, finanças e segurança

- **Base existente:** React/TypeScript/Vite, FastAPI, SQLAlchemy/Alembic, PostgreSQL, Supabase Auth, `owner_id`, autorização no servidor, RLS/FORCE RLS e modo demo segregado. O backend usa `Decimal` para cálculos monetários e há serviços/endpoints por domínio; não é necessário reescrever a aplicação para as melhorias incrementais.
- **Experiência e qualidade:** navegação responsiva, componentes Radix/Tailwind, gráficos Recharts, relatórios imprimíveis e lazy loading estão no projeto; uma medição registrada em 29/10/2026 reduziu o chunk inicial para 443,68 kB. Isso é evidência de uma otimização, não um perfil de performance atual. As suítes locais foram executadas para este candidato; não substituem E2E visual, revisão WCAG, pentest ou validação de sessão Supabase em produção.
- **Higiene de versão:** os metadados do frontend, pacote backend e FastAPI/OpenAPI foram alinhados a `1.3.0`, versão local que incorpora a estabilização 1.2.1 e os históricos v1.3. A versão publicada mais recente continua sendo v1.2.0 até release formal.
- **Novos dados:** gráficos de preço individual podem reutilizar contratos existentes. Comparar eventos por ativo pode reutilizar o ledger. Patrimônio histórico confiável exige snapshots prospectivos de cada componente com data, fonte, base, moeda, método e cobertura, provavelmente nova tabela append-only, migration, políticas/grants e endpoint autenticado. Snapshot não deve ser inventado retroativamente.
- **Cálculo de desempenho:** classificar depósitos/retiradas externas separadamente de compras/vendas, aplicações/resgates, proventos e transferências internas. TWR exige valuations nas fronteiras de fluxo; XIRR exige fluxos datados e valuation terminal comparável. Resultado indisponível é preferível a uma fórmula com dados incompletos.
- **Íris:** não precisa de RAG para explicar conceitos básicos ou o funcionamento documentado. Para explicar um indicador, oferecer ação explícita (“explicar este indicador”), mostrar os campos enviados e transmitir somente o mínimo agregado (nome do indicador, valor/unidade, período e aviso de cobertura). Nunca enviar JWT, nome, ticker/posição individual, operações ou carteira completa por padrão. Sem memória persistente, ferramentas de escrita ou recomendação de investimento.
- **Custos:** preservar custo obrigatório zero. Cache e limites locais devem minimizar chamadas; exceder cota deve produzir indisponibilidade clara. Nunca usar proxy/conta para contornar limite. Verificar termos de distribuição da fonte antes de expor cotações a convidados.
- **Validação de produção:** testes automatizados não substituem conferência legítima de login, isolamento entre proprietários, CSP/Network da demo, restore de backup e SHAs dos deploys. Nenhuma carteira ou banco remoto foi consultado nesta análise.

## Dez melhorias prioritárias

Complexidade: **B** baixa, **M** média, **A** alta. Custos potenciais descrevem a opção proposta, não uma cobrança já configurada.

| # | Melhoria e benefício | Complexidade | Impacto usuário / portfólio | Dependências | Custo potencial | Versão |
|---:|---|---|---|---|---|---|
| 1 | Corrigir documentação/metadados, semântica de cobertura e rótulo de exportação; avisar que perguntas da Íris são processadas pela Groq. | B | Médio / médio | README/CHANGELOG, versão dos pacotes/OpenAPI e testes frontend existentes. | R$ 0. | v1.2.1 |
| 2 | Orientar o registro de observações CDB, sem inventar pontos nem alterar saldo. | B | Médio / médio | Formulário de observação consolidada e endpoint já existentes. | R$ 0. | v1.2.1 |
| 3 | Implementar histórico individual Brapi Free com `adjustedClose`, um ticker por chamada, janela até 3M, cache e cobertura parcial explícita. | M | Alto / alto | Token backend, opt-in de mercado, limite local e testes MockTransport. | R$ 0 na cota Free; pode atingir cota e ficar indisponível. | v1.3 |
| 4 | Comparar 2–4 ações apenas na janela de cobertura simultânea, sem preencher lacunas ou chamar preço de retorno total. | M | Médio/alto / alto | Item 3, fonte/moeda/base compatíveis e datas comuns. | R$ 0, consome cota Free por ticker. | v1.3 |
| 5 | Corrigir comparação temporal para expor início/fim comum e só incluir datas observadas nesse intervalo. | B/M | Médio / alto | Extensão do contrato existente e regressões unitárias. | R$ 0. | v1.3 |
| 6 | Relatórios de dividendos/JCP com filtros e totais sobre eventos do ledger, sem feed Free de proventos. | M | Médio / alto | Eventos `REPLACE`/`VOID`, filtros e totais reconciliados. | R$ 0; sem feed externo. | v2.0 |
| 7 | Evolução patrimonial prospectiva com snapshots auditáveis e estados de cobertura por classe. | A | Alto / alto | Modelo de snapshot, nova migration append-only, endpoint, RLS, backup/restore e UI. | DB/hospedagem existente; confirmar limites gratuitos/armazenamento. | v2.0 |
| 8 | Rentabilidade com fluxo externo e escolha justificada de TWR/MWR; separar estimativa, preço, provento, imposto e taxa. | A | Alto / muito alto | Item 7, fluxos completos, valuations comparáveis, testes Decimal e dados suficientes. | R$ 0 se fonte gratuita validada; sem API paga. | v2.0 |
| 9 | “Explicar este indicador” na Íris com contexto agregado explicitamente selecionado e minimizado. | M/A | Médio / alto | Consentimento na UI, allowlist de campos, exclusão de tokens/PII, testes do prompt/log e cota Groq Free. | R$ 0 enquanto a cota Groq Free suportar; indisponibilidade sem upgrade pago. | v2.0 |
| 10 | Onboarding por convite, revogação e isolamento entre carteiras, sem cadastro público. | A | Alto / muito alto | Convite de uso único, Auth Supabase, owner/RLS, testes com duas identidades, exportação e exclusão. | Infraestrutura existente, sujeita aos limites gratuitos. | v3.0 |

## Roadmap proposto

### v1.2.1 — correções e estabilização

**Estado: implementada localmente; ainda não publicada.** A documentação e os metadados acompanham o código candidato v1.3.0.

- Corrigida a semântica de séries históricas cujo primeiro ou último ponto não cobre o intervalo solicitado; cobertura incompleta não é marcada como completa.
- Exportação nomeada como operações de ações (JSON), com exclusões explícitas; não é backup integral.
- Interface da Íris avisa que as mensagens são enviadas à Groq e recomenda não incluir informações pessoais ou financeiras.
- Histórico CDB sem pontos orienta registrar observação datada, sem criar dados presumidos.
- Testes locais e builds estão registrados abaixo; não foram usados dados de produção.

**Aceite:** cobertura parcial explícita, dados ausentes não inferidos, exportação descrita corretamente, consentimento informado sobre Groq e interface pública sem chat/API privada.

### v1.3 — dados históricos gratuitos

**Estado: implementada localmente; ainda não publicada.** O recurso permanece opt-in pelas variáveis backend e não foi exercitado contra a conta real nesta etapa.

- Adaptador Brapi Free usa uma chamada por ticker, `adjustedClose` e autenticação somente no backend; não solicita campos `raw*`.
- Cache de 30 minutos para sucesso, cache curto para falhas, concorrência serial por processo e orçamento local de 12.000 chamadas por processo.
- Janela efetiva máxima de três meses. 6M/1A/MAX retornam apenas o trecho realmente coberto com estado parcial. Uma resposta 403/429 não gera retries automáticos.
- Comparação 2–4 ações exige fonte, moeda e base compatíveis, escolhe início/fim do trecho comum, deixa lacunas nulas e não interpola.
- Relatório de dividendos/JCP não está nesta entrega; permanece incluído no escopo v2.0 somente com eventos já registrados no ledger.

**Bloqueio mantido:** não habilitar `EQUITY_HISTORY_ENABLED` para valuation agregado com a implementação atual. Brapi Free não entrega `rawClose`, dados de eventos nem agregação acima de um ticker por chamada. A decisão exige uma fonte realmente gratuita/adequada ou outra metodologia validada, nunca upgrade automático.

**Aceite:** testes simulam provedor limitado, 403/429, janela encurtada, ticker ausente e lacunas; UI nomeia preço ajustado e cobertura; nenhum endpoint afirma total da carteira ou retorno por essa série; chave fica no backend; nenhuma chamada do build público.

### v2.0 — patrimônio e desempenho com dados auditáveis

**Objetivo:** evoluir do registro e resumo atual para uma visão temporal honesta da carteira, começando prospectivamente.

1. Definir dicionário e proveniência de valores por classe: ações, CDB observado/estimado, caixa quando houver, moeda, método, fonte, data/hora e cobertura.
2. Classificar fluxos externos e internos sem reinterpretar operações antigas. Valores históricos ausentes ficam ausentes; sem backfill de preço ou principal inventado.
3. Verificar se avaliações e observações datadas já bastam; criar snapshots prospectivos append-only apenas se necessários, com endpoint autenticado, owner/RLS, restrições/grants, índices, retenção e migration testada em PostgreSQL descartável.
4. Construir patrimônio no tempo apenas nos pontos e intervalos comparáveis, com avisos por classe; não interpolar lacunas sem metodologia visível.
5. Adicionar benchmarks CDI/Selic/IPCA e, se cobertura/licença gratuita for adequada, Ibovespa. Comparar mesma janela, unidade, moeda e calendário; mostrar premissas e exclusões.
6. Implementar TWR ou MWR/XIRR somente após teste de fluxos externos e valuations terminais suficientes. Resultado ambíguo ou sem raiz deve ser declarado.
7. Adicionar filtros/relatórios/exportação da série com data, fonte, base, cobertura e metodologia; manter PDF via impressão, a menos que haja necessidade concreta de outra solução.
8. Evoluir a Íris para explicação contextual opcional de métricas apenas com consentimento e payload agregado mínimo; sem RAG no primeiro corte.

**Aceite:** reconciliação em casos fictícios; vetores de fluxos, eventos, resgates, proventos, divisões de ações e faltas de preço; `Decimal` e regras de arredondamento; cálculos recusados quando incompletos; duas identidades negativas/RLS; teste de restore; fonte e custo aprovados; demo pública permanece offline; validação visual autenticada legítima.

**Novos componentes prováveis:** uma tabela de snapshots financeiros e migration; endpoints de captura/consulta autenticados; possivelmente uma tabela de definição de fonte/metodologia se o modelo exigir. Benchmark pode reutilizar serviços BCB/Brapi somente depois de cobrir unidade, calendário e limites. Não é necessário novo serviço pago.

### v3.0 — acesso multiusuário limitado por convite

**Objetivo:** expandir de uso pessoal para pequeno grupo sem permitir cadastro público livre nem cruzamento de carteiras.

- Começar por threat model, papeis, convite único/expirável/revogável, signup fechado, suspensão/remoção e política de retenção/exportação.
- Validar cada rota, relatório, export, cache, snapshots e IA sob usuários A/B, com `owner_id` obtido do JWT verificado, filtros de servidor e RLS/FORCE RLS.
- Prover carteira vazia ao convidado; não copiar nem expor dados do proprietário. Administração de convite separada de acesso ao conteúdo financeiro.
- Definir limites por usuário/IP para recursos de mercado e Groq; logs mínimos sem payload financeiro, backup/restore, incidentes, exclusão e custos de hosting.
- Piloto pequeno somente após testes negativos, restore ensaiado e revisão de privacidade/termos. Sem monetização ou cobrança como requisito.

**Aceite:** testes de acesso cruzado em todas as classes de recursos, concorrência/replay/expiração de convite, restore em ambiente descartável, processo de remoção/portabilidade e limites gratuitos confirmados. Signup público permanece desligado.

## Fora do escopo aprovado

CSV, Open Finance, scraping, conexão/sincronização automática com corretoras, negociação/ordens, recomendações de compra/venda, API de mercado paga, cadastro público irrestrito, monetização, RAG e memória persistente da Íris não fazem parte das versões v1.2.1, v1.3, v2.0 ou v3.0 planejadas. Esta lista encerra o escopo dessas ideias; não representa backlog pendente.

## Validação local da v1.2.1/v1.3

- Backend completo: 404 testes aprovados, 1 ignorado; aviso de depreciação existente do `TestClient` com HTTPX.
- Frontend completo: 224 testes aprovados em 29 arquivos.
- Build de produção aprovado com 2.382 módulos; `git diff --check` aprovado após a última alteração documental.
- Testes do provider Brapi usam `httpx.MockTransport`; não foram feitas chamadas reais à Brapi ou Groq, acessos ao PostgreSQL remoto, nem leituras ou escritas da carteira real.
- A demonstração pública tem teste automatizado sem Íris e sem chamadas ao endpoint privado. Inspeção visual autenticada exige sessão Supabase legítima e não foi realizada nesta etapa.

## Referências do repositório

- [Master plan](INVESTMENT_DASHBOARD_MASTER_PLAN.md) — histórico e decisões de continuidade.
- [CHANGELOG](../CHANGELOG.md) — versões públicas.
- [Roadmap histórico](roadmap.md) — etapas técnicas antigas; não sobrescreve este plano.
- [Histórico agregado de ações](phase-3.0.3-equity-history.md), [histórico individual](phase-4.1-individual-equity-history.md) e [comparação](phase-4.2-asset-comparison.md).
- [Rentabilidade temporal](phase-4.4-historical-performance-plan.md), [arquitetura gratuita](free-tier-architecture.md) e [expansão por convite](multiuser-expansion-plan.md).
