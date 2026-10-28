# Fase 2.0.8.2-A — base local de revisões

## Estado e limites

Base iniciada em `5def47d`, com árvore limpa confirmada. Migration 006 proposta,
sem aplicação em banco persistente, sem endpoints de escrita de revisões e sem UI de
correção/anulação. Nenhum grant de INSERT de revisões é concedido automaticamente ao
runtime. A primitive interna `append_revision` exige PostgreSQL; não faz commit pelo
chamador. A integração descartável foi aprovada conforme relato do usuário (1 passed,
1 warning em 2.95s); o agente não a reexecutou. A utilização pública depende de aprovação
e implementação da próxima entrega de API/UX.

## Arquitetura

`fixed_income_application_revisions` referencia a aplicação original por FK RESTRICT.
Cada raiz possui revisões consecutivas, validadas sob o lock `(20001, investment_id)`.
REPLACE contém valor e data completos; VOID é terminal e remove a aplicação da projeção.
Lotes, movimentos, caixa e posições originais permanecem preservados. A autoria é o
owner autenticado, conferido contra a aplicação. O timestamp é definido pelo trigger.

`fi_effective_movements()` é uma função SQL STABLE SECURITY INVOKER com search_path
fixo: conserva IDs originais, seleciona a última revisão por raiz e projeta data e principal.
A versão SQLite é exclusivamente para leitura/testes e tem SQL congelado comparado à
migration. Há teste PostgreSQL de paridade. Não existe persistência de saldo derivado.

A base mantém RLS/FORCE RLS, revoga grants herdados, exige motivo e payload coerente,
e bloqueia UPDATE/DELETE/TRUNCATE. O runtime futuro precisa SELECT na tabela de revisões
e EXECUTE na projeção para leitura. INSERT e USAGE da sequência são reservados à futura
escrita aprovada; no teste descartável são concedidos apenas ao papel de teste.
As migrations 001–005 não foram alteradas. A 006 contém SQL próprio congelado e bloqueia
downgrade destrutivo; não importa código mutável da aplicação.

## Inventário de leitores e validadores

| Consumidor | Fonte após esta entrega |
| --- | --- |
| router.history, saldos e detalhe de lotes | projeção efetiva; data de lote vem da aplicação efetiva |
| aplicação/resgate: cronologia e principal disponível | projeção efetiva sob advisory lock |
| snapshot de rendimentos | contrato, abertura, lotes e movimentos efetivos numa única instrução MVCC |
| returns_engine e ledger | recebem DTOs efetivos; fórmulas Decimal permanecem iguais |
| observações: última data financeira | máximo da projeção efetiva |
| frontend: histórico e total de aplicações | GET effective-movements, paginado |
| triggers de lote, resgate e observação | mesma função PostgreSQL da projeção |
| GET movements e movements/{id} | originais para auditoria; não usados para cálculos no frontend |
| arquivamento e abertura | dependências físicas, intencionalmente: VOID não apaga histórico |
| trigger de aplicação obrigatória por lote | original físico exigido na transação, preservado após revisão |
| trigger de tracking consolidado | observações originais, sem inferência de principal |

Não há leitor financeiro conhecido ainda consumindo movimentos brutos incompatíveis.
A função de projeção é a autoridade PostgreSQL; a integração deve comprovar a equivalência
com a leitura SQLite e o comportamento sem revisões. Novos leitores devem usar essa fonte.

## Validação e concorrência

Sob READ COMMITTED, revisão e resgate compartilham o lock do contrato. Após esperar,
o trigger relê a revisão atual. Revisão obsoleta, VOID terminal, aplicação alheia ou raiz
que não seja APPLICATION são recusados. O histórico efetivo é revalidado: primeira aplicação
na data inicial sem abertura, datas dentro do contrato/não futuras, depois da abertura,
resgates posteriores à aplicação e nenhum prefixo de saldo negativo. VOID com resgate
é recusado. Uma mudança de data não pode atravessar uma observação existente em nenhuma
direção. Valor observado nunca é recalculado ou somado ao principal.

A primitive interna serializa também a chave de idempotência por proprietário. Mesma chave
e conteúdo devolvem o evento existente, inclusive com revisão esperada antiga; conteúdo
diferente falha. Índices únicos distintos cobrem owner UUID e modo local com owner nulo.
Inserts SQL duplicados falham por unicidade; não oferecem replay automático. Qualquer falha
faz rollback pelo chamador, sem evento parcial. Não há cache de cálculos persistido; futuras
APIs de revisão precisarão invalidar caches e expor revisão/versão da projeção.

## Testes e execução Windows

Unidade: projeção sem revisão, REPLACE completo, VOID, preservação, valor e data efetivos
no detalhe/rendimentos, principal para resgate, payload inválido e ausência de endpoint.
PostgreSQL coberto pelo runner atual, com resultado informado pelo usuário: cadeia 001–006
e preservação dos registros existentes,
paridade SQL, RLS A/B/sem identidade, privilégios, SQL direto, imutabilidade, primeira
aplicação, abertura, resgates incompatíveis, idempotência e rollback; corridas de duas revisões,
mesma chave e correção versus resgate. O resultado informado nesta revisão refere-se à
entrega 2.0.8.2-A. A inspeção confirma a chamada dos quatro verificadores e head 006;
o agente não repetiu a execução PostgreSQL.

Executar uma vez no PowerShell, sem usar .env de produção:

```powershell
Set-Location 'C:\Users\IAN\ProjetosVSCode\investment-dashboard\backend'
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\run_postgres_diagnostic.ps1
```

O script registra hashes da 006 e dos verificadores, gera transcript completo em %TEMP%,
exige Docker Engine e imagem postgres:17-alpine já em cache, não faz pull, publica apenas
em 127.0.0.1 e usa container com nome aleatório, tmpfs e remoção após execução. O runner
substitui TEST_DATABASE_URL pela URL desse banco efêmero. O script restaura DOCKER_CONFIG.

## Pendências antes de habilitar escrita

- Preservar o log da integração informada pelo usuário. O sandbox não permitiu repetição
  independente pelo agente; futuras mudanças na migration/validadores exigem nova integração.
- Revisar custo da função e validação de histórico com carteiras maiores antes de definir
  limites operacionais. A consulta de rendimentos preserva o limite de 10.000 registros.
- Homologar contratos da futura API e UX, status de auditoria, mensagens de conflito e cache.
- Conferir grants do papel customizado no ambiente de implantação aprovado. A migration
  não conhece seu nome; backend depende da 006 e desses grants para leitura após implantação.
- Preparar rollout coordenado de banco/backend/frontend; não habilitar novos escritores
  enquanto algum componente antigo validar principal pelo ledger bruto.
