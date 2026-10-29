# Plano mestre — v5.0.0

**Status:** Planejado. Os placeholders de Simulador e Metas no app apontam para a Fase 5; as propostas neste documento não significam que o código exista ou que a implementação esteja autorizada.

## Relação com o planejamento original

A arquitetura original reservava uma fase para planejamento: simulador com premissas explícitas, metas, projeções e relatórios. Importação CSV, eventos/proventos, contas/corretoras, snapshots e medição também aparecem em documentos anteriores, mas em fases numeradas diferentes. Este plano reorganiza dependências sem apagar os registros históricos.

## Princípios de v5

- Zero despesa obrigatória; open source, registros manuais e CSV primeiro.
- Simulações são cenários, não previsão ou promessa de retorno.
- Nenhuma taxa ou retorno é preenchido automaticamente sem origem e consentimento.
- Supabase Auth e isolamento por proprietário são preservados.
- Demo continua offline e não mostra carteira privada.
- Importação sempre tem preview, validação, duplicate detection e confirmação.
- Pagamento, API comercial ou Open Finance não é pré-requisito. Ideias permanecem opcionais.

## Fases propostas

### 5.0A — Navegação responsiva e identidade dinâmica

**Prioridade:** etapa inicial de experiência de uso; planejada e não autorizada para implementação.

- Em desktop, menu expandido com rótulos e recolhido com ícones, tooltips e nomes acessíveis; preferência local opcional.
- Em mobile, drawer sobreposto com Escape, fechamento ao navegar, foco contido/devolvido e fundo inerte enquanto aberto.
- Identidade privada usa nome de exibição da sessão Supabase; sem nome, prefixo do e-mail; sem ambos, rótulo neutro. Avatar usa a inicial e identificadores longos não quebram o layout.
- Logout, expiração e troca de usuário limpam identidade e cache privados. Demo continua offline, sem ler sessão privada nem chamar API privada.
- Autorização continua usando `sub` validado no backend, allowlist quando aplicável, `owner_id` e RLS; e-mail/metadados são apenas apresentação.
- **Migration:** nenhuma prevista. Sem API paga, custo obrigatório ou dependência de preços.
- **Aceite e testes:** acessibilidade por teclado/leitor de tela, estados desktop/mobile/zoom, persistência opcional, identidade ausente/longa, logout e troca de sessão sem vazamento, e testes de demo offline. Detalhes em [plano 5.0A](phase-5.0A-responsive-navigation-user-identity.md).

### 5.1 — Caixa, proventos e eventos financeiros

**Prioridade:** alta para medição completa; proposta nova no detalhe de implementação, alinhada às lacunas antigas.

- Definir depósitos e saques externos, distinguindo compra/venda e aplicação/resgate.
- Estudar proventos de ações (dividendos/JCP), reinvestimento e eventos corporativos com fonte declarada e correção auditável.
- Permitir lançamentos manuais observados; não criar eventos históricos retroativos.
- Evitar dupla contagem de transferências entre classes.
- Contrato append-only, idempotência, owner_id e RLS.
- **Visível:** histórico classificado e novos totais de caixa/proventos.
- **Migration:** provável para novas entidades/tipos; não alterar o ledger atual sem compatibilidade de leitura/revisões.
- **Aceite:** reconciliação financeira conhecida, períodos e taxas, REPLACE/VOID compatíveis, isolamento por usuário, importação não executa sem confirmação.

### 5.2 — Importação CSV revisável

**Prioridade:** alta para preservar histórico sem digitação repetida; item já planejado em roadmap anterior.

- Começar com um layout de instituição/corretora por vez.
- Upload local e processamento seguro; não enviar CSV a terceiros.
- Prévia antes de persistir, validação de data/ticker/quantidade/preço/taxa, regras de moeda, detecção de duplicatas e relatório de rejeições.
- Permitir mapear para eventos de 5.1; não interpretar campos desconhecidos como preço ou rendimento.
- **Migration:** talvez para batches/idempotência/auditoria de importação; decidir por arquitetura. Evitar guardar arquivo bruto após processar sem necessidade.
- **Aceite:** fixture anonimizada, reexecução idempotente, validação manual, cancelamento sem gravação, segurança de upload e testes por formato.

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

- Open Finance e agregadores: apenas se houver alternativa realmente gratuita e consentimento compatível; fluxo manual/CSV é fallback. Não manter tokens bancários no frontend.
- API paga, premium ou comercial: não obrigatória; somente discutir se o proprietário rever a decisão de custo zero.
- Importação de novos layouts, conciliação automática e reconstrução documental: por etapas e com dados de origem.
- Benchmark, PDF, metas compartilhadas ou recursos de colaboração: opcionais, não escopo automaticamente aprovado.

## Ordem e aceitação de release

Ordem proposta: 5.0A → 5.1 → primeiro CSV de 5.2 → relatórios 5.3 → simulador 5.4 → metas 5.5 → 5.6 quando dados/fonte existirem. Simulador pode ser antecipado em protótipo sem persistência porque depende apenas de premissas explícitas, não de 5.6.

Release v5.0.0 só após as fases escolhidas para o release terem critérios aprovados, testes e documentação. Uma fase bloqueada por fonte não pode ser apresentada como implementada. A lista exata de escopo v5 permanece decisão do proprietário.

## Testes transversais

- Backend financial cases com Decimal, arredondamento e datas.
- API auth/owner_id/RLS; nenhum acesso cruzado.
- CSV valid/invalid/duplicate, preview/cancel, no unexpected writes.
- Simulação determinística e cenários extremos.
- Metas sem patrimônio base e mudança de identidade.
- Export sanitization, privacidade, filtros e encoding.
- Frontend responsivo, acessível, loading/error/empty/unavailable.
- Suite inteira, build, documentação e diff review.
