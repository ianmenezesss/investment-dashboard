# Plano mestre — v5.0.0

**Status em 29/10/2026:** desenvolvimento na branch `feat/v5-development`. A 5.0A e 5.1 estão implementadas. A importação CSV 5.2A foi retirada por decisão do proprietário; 5.2B está suspensa. O proprietário informa que a migration 009 foi aplicada ao Supabase de produção. Este status não autoriza publicação.

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

**Prioridade:** média; placeholder atual e escopo original.
- Meta de patrimônio, prazo, data-base, progresso e cenário hipotético.
- Se patrimônio atual não puder ser consolidado, permitir valor manual confirmado ou mostrar progresso indisponível; nunca estimar silenciosamente.
- **Migration:** necessária para sincronizar metas persistentes entre dispositivos; não necessária para fluxo não persistido aprovado.
- **Aceite:** atingir/ultrapassar meta, ausência de base, ajustes, precisão, acessibilidade, owner_id e remoção/edição auditável.

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

Ordem recomendada a partir deste estado: revisar e aprovar as entregas locais 5.3/5.4; depois planejar 5.5 Metas, definindo a base de patrimônio atual antes de prometer progresso. A importação 5.2 está retirada. A 5.6 segue condicional aos dados/fontes previstos em 4.4.

Release v5.0.0 só após as fases escolhidas para o release terem critérios aprovados, testes e documentação. Uma fase bloqueada por fonte não pode ser apresentada como implementada. A lista exata de escopo v5 permanece decisão do proprietário.

## Testes transversais

- Backend financial cases com Decimal, arredondamento e datas.
- API auth/owner_id/RLS; nenhum acesso cruzado.
- Cadastro manual, autorização, idempotência, isolamento por proprietário e comportamento vazio.
- Simulação determinística e cenários extremos.
- Metas sem patrimônio base e mudança de identidade.
- Export sanitization, privacidade, filtros e encoding.
- Frontend responsivo, acessível, loading/error/empty/unavailable.
- Suite inteira, build, documentação e diff review.
