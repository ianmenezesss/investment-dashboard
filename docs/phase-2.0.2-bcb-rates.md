# Fase 2.0.2 — consulta histórica CDI e Selic pelo BCB/SGS

## Escopo

Consulta autenticada de taxas oficiais publicadas pelo SGS, sem movimentar principal,
calcular rendimento, anualizar taxas, calcular IR/IOF ou implementar UI. Não altera ações,
FIIs, ETFs, brapi, autenticação, RLS, banco ou demo offline. Nenhuma dependência nova,
serviço pago, chave ou migration é necessária.

## Fonte e contrato

- **12 / CDI**: taxa diária, em **% ao dia**.
- **11 / SELIC**: taxa efetiva diária, em **% ao dia**, não a meta anual do Copom (432).
- Backend usa apenas HTTPS no endereço fixo
  `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados`, com códigos permitidos 11/12.
- Parâmetros externos: `formato=json`, `dataInicial=dd/MM/yyyy`, `dataFinal=dd/MM/yyyy`.
  URL, código arbitrário e headers de autenticação não são recebidos do visitante.
- Filtros de datas são obrigatórios nas séries diárias; a restrição oficial anunciada
  em 26/03/2025 limita cada período a **dez anos**. Esta implementação deliberadamente
  aceita no máximo **366 dias inclusivos**, sem dividir intervalos ou paginar automaticamente.
- A API não oferece, nas referências consultadas, uma cota numérica de chamadas/SLA que
  possamos garantir. Os limites abaixo são proteção local, não quotas oficiais do BCB.
- Manter atribuição BCB/SGS e revisar condições da fonte antes de redistribuir bases.
  O catálogo Selic informa licença ODbL.

Referências oficiais verificadas em 28/10/2026:

- [Catálogo Selic: unidade, série 11 e restrição de dez anos](https://dadosabertos.bcb.gov.br/dataset/11-taxa-de-juros---selic).
- [Recurso JSON oficial](https://dadosabertos.bcb.gov.br/dataset/11-taxa-de-juros---selic/resource/b73edc07-bbac-430c-a2cb-b1639e605fa8).
- [Metadados SGS da série 12](https://www3.bcb.gov.br/sgspub/consultarmetadados/consultarMetadadosSeries.do?method=consultarMetadadosSeriesInternet&hdOidSerieSelecionada=12).

## Endpoint privado

```text
GET /api/fixed-income/rates/12?start_date=2025-01-01&end_date=2025-01-05
GET /api/fixed-income/rates/11?start_date=2025-01-01&end_date=2025-01-05
```

`start_date` e `end_date` obrigatórios em ISO; datas inclusivas, em ordem, não futuras
segundo America/Sao_Paulo, até 366 dias. Outros códigos são rejeitados antes do HTTP.
Autenticação/allowlist Supabase e alternativa local de desenvolvimento são exatamente
as existentes, por `authenticate`. Não consulta banco: são séries macroeconômicas públicas,
não investimentos de um usuário. Cache de taxas é compartilhável entre contas autorizadas,
sem armazenar tokens, ids de usuário ou informações financeiras privadas.

Exemplo **fictício** de resposta tipada, com decimais como strings:

```json
{
  "series_code": 12, "name": "CDI", "unit": "% ao dia", "source": "BCB/SGS",
  "start_date": "2025-01-01", "end_date": "2025-01-05", "status": "ok",
  "observations": [
    {"date":"2025-01-02","value":"0.012345678901","series_code":12,"unit":"% ao dia"}
  ],
  "duplicates_removed": 0, "last_observation_date": "2025-01-02",
  "fetched_at": "2026-10-28T16:00:00Z", "expires_at": "2026-10-28T22:00:00Z",
  "from_cache": false
}
```

`0.05` significa 0,05% ao dia, não 5% nem taxa anual. Os valores são Decimal desde o
parsing JSON, limitados a 20 dígitos e 12 casas para conter payload malformado; não há
aritmética de rendimento nesta fase. Monotonic clock/tempos de rede não são valores financeiros.

Datas brasileiras são convertidas para `date` e ordenadas. Lacunas não são preenchidas
por zero, repetição, interpolação ou calendário presumido. Ausência pode indicar dia sem
publicação, período anterior à série ou atraso; não se classifica feriado automaticamente.
Nenhum indicador de cobertura completa é inferido. `last_observation_date` é referência
da última observação retornada, não horário de publicação. `fetched_at` é coleta do backend.

Lista JSON válida vazia gera `status=empty`, `observations=[]` e última data null.
404, HTML, erro HTTP ou corpo inválido **não** são tratados como lista vazia.
Duplicatas idênticas são removidas e contabilizadas; conflito entre valores na mesma
data rejeita a resposta inteira, sem selecionar arbitrariamente um deles.

## Falhas e limites

- HTTPX separado da brapi, TLS verificado por padrão, `trust_env=False`, sem redirects,
  credenciais, cookies compartilhados, polling, warm-up ou retries automáticos.
- Timeout HTTP connect 2 s/read 5 s/write 2 s/pool 1 s; prazo total de 8 s, incluindo espera
  no lock. Uma consulta externa por vez por processo, no mínimo 1 s entre novas chamadas
  e máximo 30 tentativas por janela móvel de 60 s. Cache hit não consome tentativa externa.
- Máximo 256 KiB descomprimidos e 732 registros recebidos; datas fora do período, formato
  inválido, constantes NaN/Infinity, JSON profundo, chaves JSON repetidas e valores não
  finitos/malformados são rejeitados. Ponto é o separador decimal esperado, não vírgula.
- Falha abre cooldown compartilhado de 30 s. HTTP 429 do fornecedor usa cooldown mínimo
  60 s e respeita `Retry-After` válido, incluindo valores maiores que uma hora e data HTTP.
- HTTP 401/403 permanecem os da autenticação existente. HTTP 422: série/parâmetros inválidos;
  429: limite local/fornecedor; 502: status HTTP/payload inesperado; 503: rede, timeout ou
  serviço indisponível. Falhas da integração retornam `detail.code` estável, sem corpo SGS,
  mensagens internas de transporte ou dados privados; há `Retry-After` nas falhas de serviço.
- Códigos: `unsupported_series`, `invalid_period`, `local_rate_limited`,
  `upstream_rate_limited`, `unexpected_http_status`, `invalid_content_type`,
  `invalid_payload`, `payload_too_large`, `upstream_timeout`, `upstream_network_error`,
  `request_deadline_exceeded`, `rates_service_unavailable`.
  Rejeições nativas de campos/path podem usar o formato padrão 422 do FastAPI.

## Cache e integridade

LRU em RAM de no máximo 64 períodos por processo, chave `(série, início, fim)`:

| Resposta válida | TTL |
| --- | --- |
| Lista vazia | 60 segundos |
| Período terminando nos últimos sete dias | 15 minutos |
| Período histórico anterior | 6 horas |

Só respostas HTTPS estruturalmente válidas entram no cache de dados. Isso não elimina
possibilidade de revisões pelo BCB: reconsultar após expiração. Não há persistência SQL,
arquivo, dado sintetizado ou fallback para cache vencido em falha. Retorna erro explícito.
`from_cache`, coleta e expiração mantêm o contexto da consulta; `Cache-Control: no-store`
continua aplicado pelo middleware às respostas privadas.

Locks, cooldown, limite e cache são por processo: reinícios os zeram e múltiplos workers
não compartilham orçamento. Reavaliar coordenação antes de escalar; não foi introduzido Redis
ou serviço pago. Um intervalo novo, mesmo sobreposto, pode causar outra consulta externa.

## Render e validação manual posterior

**Nenhuma variável/secreto adicional** é exigido: SGS não usa API key nesta integração.
Manter as configurações existentes de Supabase Auth/CORS/banco. O Render precisa resolver
e acessar `https://api.bcb.gov.br:443`, com cadeia TLS válida. Não desativar a verificação
de certificados para contornar problemas. A rede real do Render não foi validada nesta entrega.

Após publicação explicitamente autorizada, consultar um intervalo curto com sessão válida,
verificar unidade/data/coleta e repetir o mesmo período para observar `from_cache=true`.
Sem autenticação deve retornar 401; não usar tokens em URLs, screenshots ou logs.
Consultas de verificação real são manuais; nenhum teste automatizado chama a API SGS real.

## Testes

Resultado: **185 testes backend aprovados**, incluindo 46 novos, e **1 teste PostgreSQL
integrado aprovado**. Aviso conhecido de depreciação TestClient/httpx permanece.
Frontend/builds não foram reexecutados: não houve alteração frontend nesta fase.

```powershell
Set-Location C:\Users\IAN\ProjetosVSCode\investment-dashboard\backend
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_postgres.py --tb=short
$env:DOCKER_HOST='npipe:////./pipe/dockerDesktopLinuxEngine' # somente neste Windows, se necessário
.\.venv\Scripts\python.exe tests/run_postgres.py
```

HTTP simulado cobre séries 11/12, parâmetros brasileiros, Decimal exato, lacunas, lista vazia,
duplicatas idênticas/conflitantes, erro HTTP/rede, timeout, limites, expiração, LRU, cooldown,
períodos inválidos/futuros, endpoint autenticado, compartilhamento de taxas sem dados privados
e ausência de acesso ao banco. PostgreSQL é descartável, sem credenciais/volumes de produção.

Sem deploy, alteração de secrets, commit ou push. **Fase 2.0.2 para revisão**; commit/deploy
dependem de autorização do usuário.
