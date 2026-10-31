# Plano mestre — v5.0.0

**Estado atualizado em 30/10/2026:** `main` e `origin/main` permanecem em `1a7e4d8`, com a Fase 5.5 integrada pela PR #11; esta branch de preparação deriva dessa base e não foi integrada remotamente. O proprietário relata a publicação das páginas recentes, mas a inspeção HTTP confirmou somente shells Vercel e health check Render, não o comportamento autenticado nem os SHAs implantados. 5.0A, 5.1, 5.3, 5.4 e 5.5A–C estão implementadas; 5.2A foi retirada e 5.2B está suspensa. A Fase 5.6 permanece fora da v1.0. O backup manual único foi gerado e seu hash/tamanho conferidos; restauração do arquivo real não foi executada. Esta atualização não acessou novamente nem alterou o banco de produção e não publica a release.

## Relação com o planejamento original

A arquitetura original reservava uma fase para planejamento: simulador com premissas explícitas, metas, projeções e relatórios. Importação CSV, eventos/proventos, contas/corretoras, snapshots e medição também aparecem em documentos anteriores, mas em fases numeradas diferentes. Este plano reorganiza dependências sem apagar os registros históricos.

## Princípios de v5

- Zero despesa obrigatória; open source e registros financeiros manuais.
- Simulações são cenários, não previsão ou promessa de retorno.
- Nenhuma taxa ou retorno é preenchido automaticamente sem origem e consentimento.
- Supabase Auth e isolamento por proprietário são preservados.
- Demo continua offline e não mostra carteira privada.
- Autenticação, isolamento por proprietário e RLS são preservados nos fluxos privados.
- Pagamento, API comercial ou Open Finance não é pré-requisito. Ideias permanecem opcionais.

## Fases propostas

### 5.0A — Navegação responsiva e identidade dinâmica

**Estado:** concluída na branch dedicada da v5.0A; registrada no handoff existente.

- Em desktop, menu expandido com rótulos e recolhido com ícones, tooltips e nomes acessíveis; preferência local opcional.
- Em mobile, drawer sobreposto com Escape, fechamento ao navegar, foco contido/devolvido e fundo inerte enquanto aberto.
- Identidade privada usa nome de exibição da sessão Supabase; sem nome, prefixo do e-mail; sem ambos, rótulo neutro. Avatar usa a inicial e identificadores longos não quebram o layout.
- Logout, expiração e troca de usuário limpam identidade e cache privados. Demo continua offline, sem ler sessão privada nem chamar API privada.
- Autorização continua usando `sub` validado no backend, allowlist quando aplicável, `owner_id` e RLS; e-mail/metadados são apenas apresentação.
- **Migration:** nenhuma prevista. Sem API paga, custo obrigatório ou dependência de preços.
- **Aceite e testes:** acessibilidade por teclado/leitor de tela, estados desktop/mobile/zoom, persistência opcional, identidade ausente/longa, logout e troca de sessão sem vazamento, e testes de demo offline. Detalhes em [plano 5.0A](phase-5.0A-responsive-navigation-user-identity.md).

### 5.1 — Caixa, proventos e eventos financeiros

**Prioridade:** alta para medição completa. **Estado:** implementada; especificação em [plano 5.1](phase-5.1-cash-flow-and-income-events.md). O proprietário informa que a migration 009 foi aplicada ao Supabase de produção e que as tabelas de eventos existem; esta alteração não modificou nem consultou o banco.

- Definir depósitos e saques externos, distinguindo compra/venda e aplicação/resgate.
- Proventos de ações (dividendos/JCP), reinvestimento e observações de eventos corporativos usam origem declarada e revisão auditável. Observações corporativas não alteram posição ou custo.
- Permitir lançamentos manuais observados; não criar eventos históricos retroativos.
- Evitar dupla contagem de transferências entre classes.
- Contrato append-only, idempotência, owner_id e RLS.
- **Visível:** histórico classificado e novos totais de caixa/proventos.
- **Migration:** 009 cria entidades append-only, RLS/FORCE RLS, triggers e grants mínimos; sem backfill de operações antigas.
- **Aceite validado:** valores `Decimal`, períodos, idempotência, REPLACE/VOID, isolamento de proprietário, histórico unificado e testes de PostgreSQL descartável. Tarifas de transferência e eventos societários quantitativos seguem fora do escopo.

### 5.2 — Importação CSV (retirada)

**Estado:** a importação 5.2A foi retirada da interface, do cliente e da API. Cadastro manual de operações e eventos, Histórico e dados persistidos permanecem. Não apagar tabelas nem dados existentes; migration 009 não é revertida. A preparação 5.2B para adaptadores está suspensa e não deve ser iniciada sem nova decisão do proprietário. O registro histórico está em [documentação arquivada da 5.2](phase-5.2-csv-import.md).

### 5.3 — Relatórios e exportação

**Estado:** implementada no frontend privado.
- 5.3A: aportes por mês/ano, período ajustável, gráfico e separação de ações (taxas incluídas) e principal aplicado em renda fixa.
- 5.3B: composição por classe/ativo e tabelas filtráveis de movimentos/eventos com compras, vendas, resgates, aportes e proventos discriminados.
- 5.3C: impressão do relatório filtrado com data de geração; o navegador permite salvar o diálogo de impressão como PDF.
- Reutiliza `/api/dashboard/movements` e `/api/dashboard/composition`, preservando a autenticação e o filtro por proprietário dos endpoints existentes.
- **Migration:** nenhuma. Sem persistência de relatórios, novos serviços ou bibliotecas.
- Valores movimentados/aportados não são apresentados como lucro, rentabilidade ou valor a mercado.

### 5.4 — Simulador

**Estado:** implementada como simulador local e não persistente.
- Três cenários editáveis (conservador, moderado e otimista), valor inicial, aporte mensal, prazo, aporte no início/fim e inflação opcional.
- Conversão de taxa anual efetiva em taxa mensal equivalente; precisão interna Decimal; apresentação nominal e real separadas.
- Fórmulas e premissas explícitas; não lê carteira, não consulta previsão ou fonte de mercado e não promete retornos.
- **Migration:** nenhuma. O estado da simulação existe apenas na tela e não é salvo.
- **Aceite validado por testes:** taxa zero/negativa, aporte zero, capital inicial zero, prazos, timing, inflação, cenários e entradas inválidas.

### 5.5 — Metas

**Estado:** integrada à `main` pela PR #11. O proprietário relata sua publicação na Vercel; a revisão HTTP desta preparação confirmou somente o shell SPA, não o fluxo autenticado. Detalhes e limites em [especificação da Fase 5.5](phase-5.5-goals.md).
- 5.5A: criar, editar, excluir e separar metas ativas/concluídas; valida nome, valor e prazo; mostra barra/percentual. A persistência fica no `localStorage` segregado por identidade Supabase no navegador atual; não sincroniza entre dispositivos e não é copiada para a demo pública.
- 5.5B: aceita progresso informado e confirmado manualmente ou capital investido da base privada `equity_open_acquisition_cost_plus_effective_cdb_principal`. O rótulo distingue patrimônio manual de custo/principal investido; o cálculo não inclui dinheiro externo, dividendos nem cotações de mercado. Dados incompletos são identificados, posições declaradas sem saldo ficam fora da base e o modo manual continua disponível.
- 5.5C: calcula aporte necessário, prazo aproximado e evolução hipotética com o mesmo conversor de taxa anual efetiva e motor do Simulador 5.4. Taxas padrão de 6%, 10% e 14% a.a. são editáveis e nunca apresentadas como promessa. Aportes modelados ocorrem no fim do mês; projeções aceitam até 600 meses. Prazo vencido ou ausente usa horizonte manual.
- **Migration:** nenhuma. Não adiciona API nem altera registros financeiros. A leitura da base investida usa o endpoint privado existente `GET /api/dashboard/performance`, com autenticação e isolamento atuais.
- **Aceite validado localmente:** CRUD e validações; isolamento local por identidade; demo sem metas; preservação de metas no formato anterior 5.5A; capital parcial/indisponível e fallback manual; cenários, zero/negativo, completo, vencido/sem prazo e limite de 600 meses. A suíte frontend completa e o build devem ser conferidos no registro de validação.

### 5.6 — Rentabilidade histórica e benchmarks

**Prioridade:** condicional.
- Depende da Fase 4.4, eventos e fluxos da 5.1, valuations completas, fonte gratuita e licença compatível.
- Mostrar método TWR/MWR, fonte, horário, cobertura e lacunas.
- Benchmark é série diferente da carteira; diferenças de moeda/período/base precisam de estado próprio.
- **Migration:** provável para snapshots append-only. Não aprovar antes do desenho de dados.
- **Aceite:** sem interpolação, sem cotação atual retroativa, resultados reproduzíveis e indisponíveis quando cobertura insuficiente.

O refinamento da demonstração pública offline, descrito historicamente como uma fase opcional própria, pode ser feito após as releases sem acessar a carteira privada. Não é pré-requisito de v5.

## Itens opcionais preservados

- Open Finance e agregadores: apenas se houver alternativa realmente gratuita e consentimento compatível; o fluxo manual permanece disponível. Não manter tokens bancários no frontend.
- API paga, premium ou comercial: não obrigatória; somente discutir se o proprietário rever a decisão de custo zero.
- Importação de novos layouts e conciliação automática estão suspensas e dependem de nova decisão; reconstrução documental exige dados de origem.
- Benchmark, PDF, metas compartilhadas ou recursos de colaboração: opcionais, não escopo automaticamente aprovado.

## Ordem e aceitação de release

Ordem recomendada a partir deste estado: revisar a branch 5.5 e seus commits/testes; decidir manualmente se será integrada/publicada; acompanhar eventuais lacunas de uso; planejar 5.6 sem iniciar implementação até existirem avaliações datadas, cobertura suficiente e uma fonte permitida. A importação 5.2 continua retirada/suspensa.

Release v5.0.0 só após as fases escolhidas para o release terem critérios aprovados, testes e documentação. Uma fase bloqueada por fonte não pode ser apresentada como implementada. A lista exata de escopo v5 permanece decisão do proprietário.

## Testes transversais

- Backend financial cases com Decimal, arredondamento e datas.
- API auth/owner_id/RLS; nenhum acesso cruzado.
- Cadastro manual, autorização, idempotência, isolamento por proprietário e comportamento vazio.
- Simulação determinística e cenários extremos.
- Metas sem patrimônio base e mudança de identidade; distinguir fonte manual/custo investido; preservar isolamento da demo; conferir taxas, projeções, prazos vencidos e sem prazo.
- Export sanitization, privacidade, filtros e encoding.
- Frontend responsivo, acessível, loading/error/empty/unavailable.
- Suite inteira, build, documentação e diff review.
