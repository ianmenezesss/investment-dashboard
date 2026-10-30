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

**Prioridade:** média; relatórios constam no planejamento original. Exportação JSON de operações já existe, mas não equivale a relatórios.
- Filtros temporais, operações, posições e fluxos com rótulos e bases explicitadas.
- CSV de saída e resumo imprimível podem ser avaliados; PDF não é obrigatório.
- Seguir mesmo escopo owner_id, sem revelar registros de outra carteira.
- **Migration:** não necessariamente para exportar dados existentes; snapshots/relatórios persistidos não são propostos.
- **Aceite:** comparar saídas às consultas, moeda/data-base/coverage claras, privacidade e escaping seguro de CSV.

### 5.4 — Simulador

**Prioridade:** média; placeholder de navegação atual e escopo original.
- Cenários com aportes periódicos, prazo, taxa hipotética e reinvestimento.
- Mostrar premissas, frequência, convenção e resultados em cenários alternativos.
- Não puxar estimativa histórica para inferir retorno futuro; entrada manual deve ser identificada.
- **Migration:** nenhuma se temporário/local; necessária se cenários forem salvos no servidor por usuário.
- **Aceite:** valores extremos, Decimal, intervalos, aporte inicial/periódico, interrupção e ausência de promessas. UI deve chamar simulação de hipótese.

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

Ordem recomendada: estabilizar 5.1 e a interface atual; depois planejar relatórios 5.3, simulador 5.4 ou metas 5.5, escolhendo uma etapa para aprovação. A importação 5.2 está retirada. A 5.6 segue condicional aos dados/fontes previstos em 4.4.

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
