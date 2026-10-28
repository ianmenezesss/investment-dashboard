# Fase 1.9.2 — infraestrutura gratuita de cotações

## Escopo entregue

Adaptador HTTPX para brapi v2, serviço de cache e endpoint privado `GET /api/quotes`.
Não há cálculo de patrimônio, resultado não realizado ou rentabilidade nesta fase.
`GET /api/dashboard` mantém o contrato anterior e `market_value=null`. O frontend não passou
a solicitar cotações; a demonstração pública, seus dados fictícios e sua CSP permanecem intactos.
O plano 1.9.1 e a correção de sessão 1.8.4 foram preservados.

Nenhuma API exclusiva da B3, serviço pago, Redis, tabela, migration, autenticação ou RLS foi
introduzida/alterada. Não houve chamada real à brapi, alteração de painel, deploy, push ou tag.

## Configuração — exclusivamente backend

| Variável no Render | Valor/efeito |
| --- | --- |
| MARKET_DATA_ENABLED | `false` por padrão; `true` permite consulta sob demanda |
| BRAPI_TOKEN | Token da conta brapi gratuita, armazenado como segredo no backend |

Não usar `VITE_BRAPI_TOKEN`, não enviar o token ao navegador, não colocá-lo em URL, repositório,
mensagens ou screenshots. O nome BRAPI_TOKEN segue a instrução desta fase; BRAPI_API_KEY,
citada pela documentação externa, não é lida por esta implementação.
Não alterar DATABASE_URL, credenciais SQL, JWT, Supabase ou configurações Vercel para esta fase.

Flag desligada ou token vazio: o serviço retorna `disabled`, com reason `disabled` ou
`missing_token`, sem qualquer chamada externa. A falta do token não impede startup, login ou
o livro financeiro. Os exemplos versionados têm flag desligada e token vazio; `.env` real não
foi editado. A habilitação no Render será manual, somente depois da publicação autorizada.

## Fluxo e privacidade

1. O endpoint usa as dependências existentes de autenticação, autorização e RLS.
2. Calcula somente a lista de tickers de posições abertas do usuário, pelo livro contábil existente.
3. Finaliza a transação de leitura com rollback antes de aguardar a rede; nenhum registro é modificado.
4. Consulta o cache/fornecedor e devolve objetos normalizados. Não aceita tickers arbitrários por
   query string: parâmetros como symbols não ampliam o universo além das posições autorizadas.

Não é um proxy público da brapi. São enviados ao fornecedor apenas o ticker e o token próprio
do backend, nunca JWT Supabase, proprietário, operações ou quantidades. O cache guarda somente
preços públicos, não carteiras ou identidades. Cache-Control da resposta privada continua no-store.

O HTTPX AsyncClient é criado no lifespan e fechado no shutdown, sem consulta no startup. Usa
TLS verificado, trust_env=false, uma conexão e URL fixa. Redirects não são seguidos, inclusive
para evitar encaminhar o segredo a outro host. Não há chamada em health, operações, dashboard,
exportação, login ou demo; a rede externa só é utilizada pelo novo serviço sob demanda.

## Contrato externo e validação

O adaptador usa `GET https://brapi.dev/api/v2/stocks/quote?symbols=TICKER`, com segredo no header
Authorization Bearer. Interpreta `results[].data`, regularMarketPrice, currency e regularMarketTime,
conferindo requestedSymbol e symbol. Não pressupõe contrato v1 idêntico.
[Documentação brapi v2](https://brapi.dev/docs).

Tickers aceitos para consulta têm quatro caracteres alfanuméricos maiúsculos e um/dois dígitos
finais: ITUB4, BBAS3, B3SA3, PETR4, por exemplo. Essa regra é validação sintática, não confirmação
de que um instrumento existe ou pertence à classe ações. Não aceita .SA, sufixo F, minúsculas,
listas, URLs ou caminhos; não converte símbolos silenciosamente. Ticker inválido não consome API.

Preço deve ser finito, positivo, até 1e12 e com até oito casas decimais; JSON numérico é lido com
Decimal e serializado como string, sem float intermediário. Moeda BRL e timestamp com timezone
são exigidos para preço utilizável. Timestamp mais de 60 s no futuro é rejeitado. Respostas
limitadas a 64 KiB; JSON/HTML inválido, identidade divergente ou campo incompatível viram erro
controlado. `changed=true` retorna ausência utilizável por mudança de símbolo, sem alterar a operação.

## Cache, limites e falhas

- TTL de sucesso: **1.800 segundos**. Cache LRU em RAM, máximo de 256 tickers.
  A instância fixa o contexto brapi/B3/BRL/v2, e o ticker completa a chave.
- Cache negativo/falhas: 60 s; um retorno ruim nunca destrói o último preço válido.
- Lock único por processo: uma chamada externa por vez e deduplicação de misses simultâneos.
  No plano gratuito, cada ativo é solicitado individualmente.
- Sem retry automático, cron, polling ou opção de bypass/force-refresh.
- HTTPX: connect 1 s, read/write 2 s, pool 0,5 s. Deadline global de 8 s por lote, incluindo fila;
  ativos pendentes ficam sem preço ao esgotá-lo. Cancelamento libera o lock. Não inventa resultados.
- 429 respeita Retry-After numérico/data, com mínimo de 60 s e máximo de 24 h; valor inválido
  usa 60 s. 401/403 externos aplicam cooldown global de 15 min para revisão do token/plano.
- Orçamento conservador de 12.000 tentativas HTTP por vida do processo. Atingido esse teto,
  novas consultas são bloqueadas até reinício do serviço, sem contornar bloqueio do fornecedor.
- Counters internos: hits, misses, requests e errors, sem logs de credenciais ou dados financeiros.

O orçamento não reinicia automaticamente no calendário e não substitui o consumo da conta:
RAM é perdida em reinícios e não coordena instâncias. Usar **um worker e uma instância**; outros
projetos que compartilhem a mesma conta também consomem quota. Antes de escalar, planejar
coordenação distribuída. Não prometer quota global/mensal garantida pelo contador local.
Monitorar o painel da brapi. Quatro ativos continuamente consultados a cada 30 minutos podem
consumir aproximadamente 5.760 chamadas em 30 dias, além de falhas e reinícios.

O plano gratuito consultado informa 15.000 requisições por ciclo, um ativo por chamada,
uma chamada simultânea e atraso aproximado de 30 min. Isso não significa tempo real.
[Limites oficiais](https://brapi.dev/faq/quais-as-limitacoes).

## Resposta e estado da cotação

`GET /api/quotes` retorna `{"quotes": [...]}`; carteira sem posições abertas retorna lista vazia,
sem consultar o provedor. Campos de cada item:

- ticker, price (string ou null), currency e provider (`brapi`);
- status e reason (códigos controlados, sem payload/erro bruto);
- quoted_at e fetched_at, em UTC quando disponíveis;
- from_cache, is_stale, expected_delay_seconds (1800) e retry_after_seconds quando aplicável.

| status | Interpretação |
| --- | --- |
| ok | Preço válido dentro da política de idade; continua sendo cotação com atraso do plano |
| stale | Cotação com mais de 75 min, ou último preço válido reutilizado após falha |
| no_data | Ticker sem resultado, 404, preço ausente ou símbolo alterado; sem preço anterior aproveitável |
| provider_error | Falha HTTP/rede/limite/contrato ou deadline; sem preço anterior aproveitável |
| unavailable | Ticker sintaticamente inválido ou cotação recebida antiga demais |
| disabled | Serviço desligado ou token não configurado |

Ao aproveitar último preço bom, reason informa a causa atual (network_error, rate_limited,
missing_price etc.), from_cache=true e is_stale=true; quoted_at/fetched_at continuam os originais.
Buscar novamente um dado antigo não o torna atual. Preço com mais de 96 h deixa de ser utilizável.
Essas janelas são políticas conservadoras, não um calendário B3: em feriados/fins de semana
mostrar a data do último negócio, sem afirmar pregão aberto/fechado. O campo is_stale não
representa ausência do atraso esperado de 30 min.

Erros do fornecedor devolvem HTTP **200 com metadados**, não HTTP 401/403 do aplicativo.
Isso evita encerrar a sessão privada por problema no token da brapi. Acesso não autenticado
ao endpoint continua recebendo 401; o backend mantém as regras de autorização existentes.
Não há preço de compra, zero ou fonte alternativa como substituição para cotação ausente.

## Como validar

### Testes locais, sem gastar a API

Na pasta backend:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_postgres.py
```

Na pasta frontend:

```powershell
npm test
npm run build
```

Testes backend usam HTTPX MockTransport, relógio controlado e SQLite em memória. Nenhum dado
real foi criado. A suíte PostgreSQL opcional foi excluída para não acessar bancos.
Conftest agora desativa a fonte dotenv apenas dentro dos testes: durante a primeira execução
foi encontrado JSON inválido em ALLOWED_USER_IDS do arquivo local. O arquivo e a validação
de produção não foram alterados; os testes não devem depender de credenciais/configuração local.
HTTPX 0.28.1 e httpcore já constam do lock; HTTPX foi promovido de extra de testes a dependência
direta de runtime no pyproject, sem atualização desnecessária do lock.

### Homologação manual futura

Antes de ativar em produção, conferir acesso/termos vigentes do fornecedor e cadastrar o token
gratuito no backend. A ressalva de licença/SLA da Fase 1.9.1 permanece; esta implementação não
comprova direito de redistribuição nem cobertura real da conta. Não houve homologação ao vivo.

Após publicação **futura e autorizada** do código, configurar MARKET_DATA_ENABLED=true e
BRAPI_TOKEN no Render. O código atual publicado pode ainda não possuir /api/quotes.
Usar uma conta já autorizada e posições já existentes; não criar registros financeiros para testar.
O token abaixo é o JWT de sessão Supabase do usuário, **não** BRAPI_TOKEN:

```powershell
$taskJwt = Read-Host 'JWT da sessão privada (entrada oculta)' -AsSecureString
$taskHeaders = @{ Authorization = 'Bearer ' + [System.Net.NetworkCredential]::new('', $taskJwt).Password }
try {
    Invoke-RestMethod -Uri 'https://investment-dashboard-3ogz.onrender.com/api/quotes' -Headers $taskHeaders
} finally {
    Remove-Variable taskJwt,taskHeaders -ErrorAction SilentlyContinue
}
```

Sem sessão, esperar 401. Desligado, esperar disabled. Sem posições, esperar lista vazia.
Com posições, conferir os símbolos, fonte, moeda e timestamps; repetir dentro de 30 min
deve indicar cache sem novas chamadas upstream. Observar consumo no painel do fornecedor,
sem mostrar tokens ou cabeçalhos em screenshots. BBAS3/B3SA3 precisam de acesso validado
na conta; não assumir que o sandbox sem token cobre toda a carteira.
Conferir /health 200 e dashboard contábil inalterado mesmo se o fornecedor estiver fora.
O frontend não mostrará patrimônio a mercado até as próximas subfases.

## Resultado e versionamento

- **73 testes backend aprovados**, com falhas e cotações inteiramente simuladas.
- **78 testes frontend aprovados**; nenhuma alteração de código frontend.
- **Builds público e privado aprovados**, sem chaves reais. Avisos já existentes de bundle
  acima de 500 kB e depreciação Starlette/httpx não bloquearam as verificações.
- Nenhum deploy/push/tag/commit foi executado. Sugestão:

```text
feat(phase-1.9.2): integrate free market data provider
```
