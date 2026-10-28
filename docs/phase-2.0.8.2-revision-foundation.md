# Fase 2.0.8.2-A — base local de revisões

## Estado e limites

Base iniciou em `5def47d`. A camada A (migration 006 e projeção) permanece como fundação.
A camada B adiciona migration 007 e endpoints de API sem interface gráfica. A migração foi
escrita localmente; não foi aplicada a banco persistente ou remoto. A integração 001–007
precisa ser executada no runner descartável antes de publicar; Docker não está acessível
neste ambiente. Consulte `phase-2.0.8.2-B-application-revision-api.md` para contratos e
grants/runtime role.

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

Unidade cobre projeção, REPLACE/VOID, preservação, leituras financeiras e validação do
payload público. O verificador PostgreSQL foi estendido para 001–007, grants do papel
runtime, preview sem persistência, replay/conflito idempotente, cronologia global com datas
iguais, autorização cruzada, rollback, imutabilidade e concorrência. Essa integração ainda
não foi executada nesta entrega. O resultado anterior do usuário (1 passed, 1 warning)
corresponde exclusivamente às migrations 001–006 e não valida 007/API.

Executar uma vez no PowerShell, sem usar .env de produção:

```powershell
Set-Location 'C:\Users\IAN\ProjetosVSCode\investment-dashboard\backend'
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\run_postgres_diagnostic.ps1
```

O script registra hashes das migrations 006/007 e dos verificadores, gera transcript completo em %TEMP%,
exige Docker Engine e imagem postgres:17-alpine já em cache, não faz pull, publica apenas
em 127.0.0.1 e usa container com nome aleatório, tmpfs e remoção após execução. O runner
substitui TEST_DATABASE_URL pela URL desse banco efêmero. O script restaura DOCKER_CONFIG.

## Pendências antes de habilitar escrita

- Executar a integração descartável 001–007 pelo runner e preservar o log. Docker Engine
  não estava acessível nesta execução; nenhuma aprovação PostgreSQL é declarada.
- Revisar custo da função e validação de histórico com carteiras maiores antes de definir
  limites operacionais. A consulta de rendimentos preserva o limite de 10.000 registros.
- Confirmar, sem revelar connection strings ou dados, que a conexão do ambiente aprovado
  efetivamente usa a role SQL `investment_runtime`; a configuração externa não foi lida.
- Homologar os três endpoints e revisar privilégios após aplicar 007 somente em banco
  descartável; não aplicar produção antes da integração e aprovação.
- Preparar rollout coordenado de banco/backend/frontend; não habilitar novos escritores
  enquanto algum componente antigo validar principal pelo ledger bruto.
