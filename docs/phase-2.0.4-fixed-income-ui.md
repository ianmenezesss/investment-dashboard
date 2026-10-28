# Fase 2.0.4 — interface privada de renda fixa

## Entrega

`/cdbs` substitui o placeholder privado por listagem, cadastro de contratos, detalhe com
lotes/histórico, aplicações e resgates de principal, e consulta explícita de estimativas.
O CDB individual pode ser aberto diretamente em `/cdbs?investment=ID`, sempre sob o guard
de sessão existente e a autorização/RLS da API. Nenhum dado financeiro privado é persistido
em localStorage/sessionStorage; queries ficam em memória e são identificadas pelo usuário.

Sem alterações no backend, banco, migrations, autenticação, RLS, cálculo financeiro ou
infraestrutura. Os endpoints necessários já existem; **nenhuma extensão backend foi necessária**.
Nenhuma dependência nova, chave, serviço pago, commit, push ou deploy.

## Contratos utilizados

Todos usam o cliente HTTP autenticado `request` e o `PrivateRepository` existentes,
incluindo Authorization Bearer, AbortSignal em consultas, cache HTTP no-store e sem cookies.

| Método / caminho (prefixo `/api/fixed-income`) | Uso |
| --- | --- |
| GET `/investments?offset=N&limit=20` | Lista paginada de contratos |
| POST `/investments` | Cadastro com os campos reais 2.0.1 |
| GET `/investments/{id}` | Principal remanescente e lotes atuais |
| GET `/investments/{id}/movements?offset=N&limit=100` | Histórico original, com carregar mais |
| POST `/investments/{id}/applications` | Nova aplicação e lote |
| POST `/investments/{id}/redemptions` | Amortização parcial ou total de um lote explícito |
| GET `/investments/{id}/returns?...` | Snapshot de rentabilidade da Fase 2.0.3 |

Listagem retorna metadados, não saldos agregados. O detalhe é carregado apenas para o
CDB escolhido, evitando uma consulta de posição para cada linha. Não há total geral da
carteira de renda fixa inventado. Contrato, posição e histórico são consultas distintas;
não se alega que compartilhem um snapshot transacional. As métricas da estimativa usam
somente o snapshot retornado pelo endpoint returns.

**Principal aplicado acumulado** é soma Decimal das APPLICATION do histórico completo,
com contexto isolado de 64 dígitos, sem alterar a configuração Decimal da demo. Enquanto
existir próxima página ou erro de histórico, mostra Indisponível. Ao atingir página cheia,
pode ser necessária consulta adicional vazia para comprovar o fim da paginação.
**Principal remanescente atual** vem exclusivamente do detalhe da API, sem somar páginas
parciais ou subtrair caixa. Exibição em centavos; backend e payload mantêm até oito casas.

## Fluxos e imutabilidade

- Cadastro: emissor, nome do produto, remuneração CDI ou FIXED, taxa contratada, aplicação
  inicial e vencimento. Envia product_type=CDB e indexer correspondente CDI/NONE; não cria
  uma aplicação implícita. Taxa CDI é percentual do CDI; prefixada é percentual ao ano.
- Aplicação: data e principal, sempre com valores decimais em strings. A primeira usa a
  data contratual; as seguintes criam lotes. Backend valida cronologia por investimento.
- Resgate: lote com saldo, data, principal amortizado e caixa líquido recebido opcional.
  O botão de total preenche **o saldo exato do lote**, sem arredondar para centavos.
  Valor acima do saldo é barrado também com Decimal no frontend; API continua autoridade.
- Caixa vazio envia null, nunca zero ou principal presumido. Zero informado continua zero.
  Aplicações exibem caixa “Não se aplica”; resgate sem caixa exibe “Não informado”.
- Não há edição/exclusão de contrato, lote ou movimento. Mensagens explicam que o ledger
  é imutável. Uma operação registrada tem confirmação visual e invalida posição/histórico;
  estimativa anterior é descartada e precisa de nova confirmação das premissas.
- Nova operação do cabeçalho em `/cdbs` abre seletor próprio de renda fixa. Em Ações,
  mantém o modal original de ações. CDBs não carregam ticker/compra/venda de ações.
- Exportação de renda fixa não existe no contrato atual. O botão Exportar de ações é
  ocultado nesta página para não exportar um domínio diferente sob rótulo enganoso.

Nenhum POST é repetido automaticamente. Envio pendente bloqueia duplicação, fechamento
do modal e Escape. Em falha de rede/5xx, a UI informa resultado possivelmente não confirmado
e manda conferir histórico antes de reenviar. Abortar ao desmontar não prova rollback;
cache financeiro é marcado inválido para releitura na próxima visita. Sem idempotência no
backend, não há garantia de evitar duplicação se o usuário reenviar manualmente sem conferir.
Erro de GET após um POST bem-sucedido é separado da confirmação de gravação.

## Estimativa: ação explícita, nenhum rendimento fictício

O usuário informa `as_of` e confirma três premissas, inicialmente **desmarcadas**:

1. `daily_cdi_pro_rata_decimal_v1`: percentual diário CDI, amortização proporcional,
   sem spread, cupons ou custos intermediários.
2. `anbima_2024_2026_v1`: calendário compatível com o contrato.
3. `br_resident_individual`: PF residente no Brasil e CDB tributável comum.

Somente após Consultar estimativa o frontend chama returns. Não consulta SGS, BCB ou
brapi diretamente. Queries de estimativa têm staleTime 15 min, retry false, sem polling
ou refetch por foco de janela. Alterar premissas/data oculta o snapshot anterior até nova
consulta; movimentos novos também o invalidam. Não são executados cálculos de juros ou
impostos no React.

Mostra principal na data consultada, rendimento bruto/líquido, valor bruto/líquido, IOF,
IR estimados, status por lote, datas sem CDI e horários de coleta/expiração. Valores null
continuam Indisponível, sem virar zero. O principal atual do detalhe não é apresentado
como principal histórico da estimativa.

Estados tratados: estimated/closed, convenção/calendário/perfil não confirmado,
calendário fora da cobertura, histórico incompleto, taxas inválidas/indisponíveis e
vencimento sem liquidação registrada. Resultados realizados e tributos de resgates são
explicitamente não apurados; caixa recebido não é rendimento. Não se apresenta estimativa
como saldo confirmado de liquidação.

## Segurança, UX e demo

- Reutiliza useAuth, guards do App, ApiError e QueryClient existentes. 401/403 nas consultas
  ou gravações são encaminhados ao guard; telas com erro de autorização não exibem tabelas
  anteriores. Chaves de query incluem identidade; troca de usuário remonta o módulo, e
  logout limpa o cache privado existente. Não há armazenamento financeiro local privado.
- Modais Radix reutilizam foco preso, Escape quando ociosos, foco devolvido ao acionador,
  labels, fieldsets, status/alert e estados disabled. Erros têm nova tentativa de leitura;
  estado vazio oferece cadastro, sem patrimônio fictício. Sucesso de gravação é anunciado.
- CSS restrito ao módulo, tema escuro/menta, grids responsivos e tabelas com rolagem própria.
- Demo não oferece o módulo. Acesso forçado a `/cdbs` público ou `/demo/cdbs` mostra aviso
  de disponibilidade privada, sem renderizar queries de CDB, sem Supabase/SGS e sem simular
  persistência fictícia de renda fixa. A demo de ações continua offline e independente.

## Limitações e lacunas conhecidas

- Motor somente CDI; contrato prefixado pode ser cadastrado/movimentado, mas sua seção
  informa que não existe cálculo prefixado. Nada é substituído por CDI ou Selic.
- Calendário backend 2024–2026; demais anos ficam indisponíveis conforme 2.0.3.
- Sem edição, exclusão, compensação de erros, idempotência, exportação CDB ou cálculo de
  tributos realizados no backend atual. Esses recursos não são apresentados como disponíveis.
- Não há endpoint de patrimônio histórico, então nenhum gráfico de valorização foi criado.
  Evolução histórica permanece no planejamento da Fase 3, condicionada aos dados reais.
- Carga de principal aplicado depende do histórico completo. Listas são paginadas; não há
  agregados globais nem carga automática de todos os contratos/movimentos de uma vez.
- Acesso autenticado real aos deploys e comparação com extratos continuam pendentes de
  homologação manual. Testes com fixtures não comprovam publicação ou configuração remota.

## Validação local

Resultado: **117 testes frontend** (21 novos), **242 backend**, **1 integração PostgreSQL**
e **builds público/privado aprovados**.

Testes frontend novos usam contratos fiéis e respostas HTTP simuladas, nunca persistência
fictícia na aplicação privada: listagem, cadastro CDI/prefixado, aplicação, resgate parcial/
total, saldo exato, rejeição, loading/erro/retry, paginação, null, estimativas, autorização,
troca de identidade, botão contextual, Escape/foco, envio duplicado e soma Decimal.
Testes integrados do App cobrem navegação Ações/CDBs e demo offline sem Supabase/HTTP.

Backend existente e teste PostgreSQL descartável foram executados sem alteração de código
backend. Builds público e privado executados com variáveis apenas no processo, sem chaves
reais. Permanecem os avisos conhecidos de bundle >500 kB e TestClient/httpx.

Chrome headless com fixture isolado e offline: desktop 1440×1000 e celular 390×844.
No celular, documento 390 px, tabela 650 px em região 340 px; modal ~366,6 px, sem overflow
da página. Capturas/helpers ficam apenas em frontend/.tmp ignorado pelo Git. Não é teste
de conta real nem certificação completa de acessibilidade.

## Homologação manual após publicação autorizada

1. Confirmar backend com fases 2.0.1–2.0.3 e migration 003 já aplicada por procedimento
   separado; esta entrega não aplica migrations nem altera Render/Vercel.
2. Login real: abrir Renda fixa, conferir contratos da conta e abrir detalhe por URL.
3. Em ambiente de homologação com dados de teste, cadastrar CDB, aplicar e resgatar parcial/
   total; conferir payload, histórico imutável, principal e caixa distintos. Não inserir
   operações de teste na carteira real.
4. Confirmar premissas compatíveis e consultar estimativa; testar lacuna, null, prefixado,
   ausência de histórico e conta não autorizada. Verificar que não há polling SGS.
5. Testar logout/troca de conta, acesso por id alheio, teclado, celular e navegação para Ações.
6. Conferir demo pública offline e ausência de rede privada/Supabase/BCB ao forçar rota CDB.

Nenhum commit/push/deploy realizado. Publicação depende de autorização do usuário.
