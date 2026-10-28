# Fase 2.0.8.2-C — Interface privada de revisão de aplicações

## Escopo

A tela privada de renda fixa oferece ações para corrigir ou anular uma aplicação CDB. A interface usa os contratos da API 2.0.8.2-B: `POST .../revisions/preview`, `POST .../revisions` e `GET .../revisions?offset=&limit=`. Ela envia `expected_revision` e uma chave UUID em `Idempotency-Key`; a mesma chave é mantida enquanto o conteúdo da intenção não muda e em retries de resultado incerto.

Antes da gravação, a tela exibe a variação do principal do lote calculada pela prévia do servidor, esclarece que não está estimando rendimentos, impostos nem caixa, e exige confirmação explícita. Anular é descrito como evento contábil que não cria resgate nem caixa. O servidor revalida a operação na gravação.

## Histórico e atualização

O histórico paginado apresenta a sequência, tipo, motivo, data efetiva e principal substituto. A listagem auditável de aplicações lê os movimentos originais preservados; os cálculos da tela continuam consumindo somente os movimentos efetivos já usados pelo ledger. Após sucesso, são invalidados os dados privados de renda fixa e o resumo do dashboard, e a projeção de rendimentos é recarregada. Não há controles para editar ou excluir registros históricos.

Conflitos 409 orientam recarregar a sequência; operações inválidas 422 exibem a justificativa da API; 404 informa que o recurso não está disponível. Em falha de rede ou erro 5xx após envio, a interface recomenda retry sem mudar o formulário e conserva a chave para que a API resolva a repetição idempotente.

## Limites

A tela só aparece no fluxo autenticado e usa `PrivateRepository`; a demonstração pública não envia chamadas para a API financeira privada. A integração PostgreSQL 001–007 reportada pelo usuário foi executada em banco descartável Windows: 1 aprovado, 1 aviso, em 3,31 s (log local do usuário `investment-dashboard-postgres-20261028-191753.log`). Essa evidência não representa execução neste ambiente. Sem homologação visual em navegador, sessão Supabase real ou deploy.

## Verificações desta implementação

- Backend: 278 aprovados, 1 ignorado e 1 aviso. A integração PostgreSQL é o teste ignorado; a evidência de integração fornecida pelo usuário está descrita acima.
- TypeScript `tsc -b`: aprovado.
- Vitest frontend completo (`npm test -- --configLoader runner`): **136 testes passaram** em 10 arquivos. O `--configLoader runner` evita o bloqueio do esbuild ao percorrer o diretório pai neste sandbox.
- Build (`npm run build -- --configLoader runner`): aprovado; Vite transformou 2.351 módulos. Permanece o aviso existente de bundle principal acima de 500 kB.
- `git diff --check`: sem erros de whitespace nos arquivos rastreados. Git emitiu apenas avisos de normalização LF/CRLF.
- Não houve commit da interface C.
