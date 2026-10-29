# Roadmap do Investment Dashboard

Atualizado em **29/10/2026** para registrar a auditoria de release da v3.0.4.
O plano não autoriza implementação automática de funcionalidades futuras.

O commit `f021ad8` está confirmado em `main` local e remoto. A publicação Vercel foi
reportada pelo responsável, mas seu SHA não foi inspecionado no painel. O health público
do Render respondeu `200`; isso valida conexão e controles básicos do papel runtime, mas
não informa a revisão Alembic. Confirme no Render que `alembic_version` está em `008` antes
de considerar a compatibilidade de produção totalmente verificada.

Revisão de prontidão 2.0.6 registrada em
[phase-2.0.6-production-readiness.md](phase-2.0.6-production-readiness.md): sem novas
funcionalidades; validação local/documental concluída, publicação e homologação remotas
pendentes de autorização.

Revisão final 2.0.7 de segurança e clareza da Renda Fixa registrada em
[phase-2.0.7-final-review.md](phase-2.0.7-final-review.md). Não inicia a Fase 3.0 nem
altera o schema. Os 118 testes aprovados foram registrados em `validation.md`; os testes
backend e a integração descartável foram executados pelo responsável no Windows. Homologação
secundária e verificação remota independente seguem pendentes. O responsável informou que
a 004 está em `head` no Supabase, com RLS e grants mínimos conferidos; esse estado não foi
acessado/verificado pelo agente.
Até a versão final serão usados exclusivamente dados fictícios, inclusive no desenvolvimento.

## Fase 2 — renda fixa

- **2.0.1:** contratos CDB, lotes e movimentações imutáveis de principal, validados em
  PostgreSQL descartável; sem rendimentos ou impostos.
- **2.0.2 (implementada para revisão):** consulta histórica privada de CDI diário (SGS 12)
  e Selic diária (SGS 11), com Decimal, cache e controle de chamadas. Sem migration,
  cálculo de rendimento ou UI. Ver [contrato e limites](phase-2.0.2-bcb-rates.md).
- **2.0.3 (implementada para revisão):** motor determinístico de estimativas CDI por lote,
  IOF/IR estimados para PF residente, premissas explícitas, principal separado de rendimento
  e estados de informação insuficiente. Sem migration ou UI. Ver [fórmulas e homologação](phase-2.0.3-fixed-income-returns.md).
- **2.0.4 (implementada para revisão):** interface privada CDB com listagem/cadastro,
  lotes, aplicações, resgates e histórico; estimativa explícita com premissas confirmadas,
  dados indisponíveis preservados e demo offline. Ver [fluxos e contratos](phase-2.0.4-fixed-income-ui.md).

- **2.0.5 (implementada para revisão):** saldo inicial consolidado como snapshot imutável,
  novas observações/conciliação manual sem presumir principal ou tributos, novos lotes
  separados e cards/formulários BRL. Migration 004; aplicação em produção reportada pelo
  responsável como concluída e head, ainda sem verificação remota independente.
  Ver [semântica, contratos e implantação](phase-2.0.5-opening-balance.md).
- **2.0.6 (prontidão):** revisão local e roteiro manual de publicação, sem funcionalidade.
- **2.0.7 (revisão final):** dicas acessíveis e distinção visual entre valores informados,
  calculados e estimados. Nenhum dado real é necessário para desenvolvimento/homologação.
  Testes backend focais e integração PostgreSQL descartável passaram segundo relato do
  responsável; conta secundária e verificação remota independente seguem pendentes.
  Ver [revisão final](phase-2.0.7-final-review.md).
- **2.0.8.1 (implementação local para revisão):** arquivamento por tombstone append-only
  apenas de contratos CDB sem lotes, movimentações ou observações. Contratos e histórico
  original permanecem preservados; listagem ativa os omite. Migration 005 foi exercitada
  somente pelo teste PostgreSQL descartável; não foi aplicada em ambiente persistente ou de
  produção. Ver [plano de arquivamento](phase-2.0.8.1-empty-cdb-archive.md).

- **2.0.8.2-A (base local revisada):** revisões append-only REPLACE/VOID,
  migration 006 e projeção efetiva compartilhada pelos leitores e validadores financeiros.
  Integração descartável aprovada conforme resultado informado pelo usuário; sem endpoints
  de escrita de revisão. Ver [arquitetura e inventário](phase-2.0.8.2-revision-foundation.md).

## Pós-lançamento — planejado, não implementado

- Importação de extratos CSV com validação e revisão antes de persistir.
- Integrações bancárias, respeitando consentimento, privacidade e fontes viáveis.
- Conciliação automatizada, sem sobrescrever ledger ou presumir impostos/principal.
- Reconstrução opcional de históricos a partir de documentos efetivamente disponíveis.

Snapshot não substitui histórico de aquisição. Essas funcionalidades exigirão escopo e
validação próprios; nenhuma está disponível como operação funcional nesta fase.

## Fase 3.0 — gráficos e evolução patrimonial

Objetivo: visualizações privadas com indicadores explicáveis e dados disponíveis de fato.
3.0.1 e 3.0.2 constam como publicadas segundo relato do responsável. A implementação
histórica de preços da 3.0.3 foi preservada, mas segue pendente de uma fonte adequada,
gratuita ou com uso permitido, com cobertura e campos suficientes. A 3.0.4 está concluída,
validada localmente e no commit `f021ad8`; a publicação é reportada pelo responsável, sem
confirmação independente do SHA implantado. O plano técnico,
endpoints, limites e decisões em aberto estão em [Fase 3.0 — plano técnico](phase-3.0-technical-plan.md)
e a validação final da 3.0.4 em [revisão final 3.0.4](phase-3.0.4-final-review.md).

| Subfase planejada | Escopo |
| --- | --- |
| 3.0.1 | Publicada conforme informado pelo responsável: indicadores, contratos e cobertura por ativo/carteira. |
| 3.0.2 | Publicada conforme informado pelo responsável: fluxos de aplicações/compras e resgates/vendas separados de patrimônio e rentabilidade. |
| 3.0.3 | Código local preservado: reconstrói quantidades pelo ledger e usa fechamento bruto/eventos societários da integração existente. A adequação da fonte, acesso a `rawClose`, cobertura e termos permanece pendente; não está concluída nem liberada para publicação. Ver [Fase 3.0.3](phase-3.0.3-equity-history.md). |
| 3.0.4 | Concluída e validada: histórico unificado de ações/CDB, capital movimentado e composição por bases abertas. Sem migration. Publicação reportada; SHA Vercel e revisão Alembic de produção pendentes de confirmação independente. Ver [revisão final](phase-3.0.4-final-review.md) e [notas](../CHANGELOG.md). |
| 3.0.5 | A proposta anterior de filtros, tooltips, estados de cobertura e layout foi incorporada às interfaces 3.0.3/3.0.4. Não há escopo adicional aprovado para esta subfase. |

## Proposta v4.0.0 — não aprovada

Esta proposta organiza opções para o próximo ciclo; não autoriza implementação, gasto,
integração externa ou alteração de schema.

1. **4.0.0 — confiabilidade operacional:** documentar versão/deployment SHA, verificar
   backups e restauração, e manter testes de autenticação, RLS e permissões de runtime.
2. **4.1 — importação revisável:** avaliar importação de CSV de corretora com prévia,
   validação, detecção de duplicatas e confirmação explícita antes de acrescentar ao ledger.
3. **4.2 — eventos de carteira:** definir suporte a proventos e eventos societários apenas
   com registros observáveis, regras documentadas e testes; sem presumir valores ausentes.
4. **4.3 — evolução patrimonial histórica:** considerar snapshots somente se houver fonte de
   preços gratuita e permitida com cobertura suficiente. Até lá, manter lacunas indisponíveis.

Critérios para qualquer escopo: preservar operações originais e REPLACE/VOID, isolamento por
proprietário, decimais exatos, demo pública offline e validação local antes de qualquer
publicação. Nenhuma API paga ou scraping está proposto.

### Preço e patrimônio são métricas diferentes

- **Histórico de preço** acompanha a cotação de um ativo ao longo do tempo; não representa
  o dinheiro ou o resultado de uma carteira individual.
- **Evolução do patrimônio** depende das quantidades efetivamente mantidas em cada data,
  das movimentações e dos preços correspondentes. Aportes e resgates alteram o patrimônio
  sem necessariamente representar rentabilidade. Caixa, proventos, custos, tributos e
  eventos corporativos precisarão de tratamento explícito conforme o escopo disponível.
- Um gráfico de preços não será apresentado como evolução patrimonial. A cotação atual
  não será aplicada retroativamente para inventar patrimônio histórico.

### Dependências e limites

A disponibilidade histórica dependerá de **fontes gratuitas e permitidas e dados realmente
existentes**, incluindo cobertura, limites, atraso, licença de uso e ajustes de preços. Antes
de adotar uma fonte futura, avaliar a viabilidade por ativo e período, sem assumir histórico
completo ou dados em tempo real. O orçamento do projeto não contempla API paga e esta decisão
não autoriza contratação.

O ledger de operações é a fonte principal da verdade para compras, vendas, aplicações e
resgates registrados. Cotações externas são estimativas e devem ser identificadas na
interface, com orientação para conferência na corretora. Não fabricar cotações nem aceitar
cálculos sabidamente incompatíveis com a base do preço e os eventos corporativos.

Períodos sem dados suficientes devem aparecer como indisponíveis/lacunas ou ter a seleção
limitada, sem preencher preços ou rendimentos fictícios. Resumos mensais/anuais devem
definir bases e datas antes de calcular percentuais; fluxo de caixa não é retorno.

Demo pública continuará offline, com séries explicitamente fictícias e separadas das
carteiras privadas. Credenciais de fornecedores continuarão exclusivas do backend.

## Fase 4.0 — gestão, análise e consolidação da carteira

Planejar integração entre Ações e Renda Fixa em uma visão geral, histórico consistente,
filtros e exportação, revisando responsividade e desempenho. Totais só serão apresentados
quando cobertura, data-base e sobreposição dos ativos estiverem resolvidas. Exportação não
deve ampliar dados ou permissões; isolamento por proprietário e demo offline continuam.

## Fase 5.0 — simulador e metas

Respeitar os placeholders atuais da navegação. “Planeje o que vem pela frente” poderá
simular aportes periódicos, taxas hipotéticas e reinvestimento em cenários comparativos.
“Seu próximo marco financeiro” poderá registrar patrimônio-alvo, prazo, progresso e
projeção de conclusão. Premissas escolhidas devem ficar visíveis; projeções são cenários,
nunca promessa ou garantia de retorno. Não pertence à Fase 2 ou 3.

## Fase 6.0 — melhorias opcionais do produto pessoal e da demonstração pública

Escopo exclusivamente opcional: polimento do produto pessoal e melhorias da demonstração
pública offline. Não inclui solicitação de acesso, convites, cadastro, multiusuário,
administração de contas ou autorização para ler dados privados. Os dados da demonstração
continuam fictícios e isolados.

## Versão 1.0 Final — lançamento do Investment Dashboard pessoal

Lançamento do produto para uso pessoal do proprietário, após homologação funcional e
financeira, privacidade, backup/restauração ensaiada, documentação, aprovação do responsável
e publicação controlada. A versão 1.0 não oferece onboarding para outros usuários.

## Nova versão 2.0 — expansão multiusuário por convite

Escopo posterior à 1.0: solicitação de acesso, aprovação manual do administrador, convite
individual com expiração, seguido da criação de uma carteira privada isolada.
RLS e autorização devem proteger cada conta. O administrador não recebe acesso automático
aos investimentos de outros usuários; convite e gestão de acesso não concedem leitura das
carteiras. Implementação depende de decisão e aprovação próprias; nenhum sistema de convite
é implementado ou autorizado por este roadmap.
