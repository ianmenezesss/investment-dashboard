# Fase 2.0.3 — estimativas de rentabilidade de CDB/CDI

## Base inspecionada e escopo

Base local confirmada: commit `1baf46743211c6ee3b4026b2d7932d65b12c8b4b`, Fase 2.0.2.
O ledger 2.0.1 contém principal, lote, data e caixa líquido opcional; não contém convenção
de capitalização, cupons, rendimento bruto liquidado, IR/IOF efetivos ou perfil tributário.
Não se pode recuperar esses componentes pela diferença caixa menos principal.

A entrega acrescenta um **motor puro de estimativas** e uma consulta privada. Mantém todos
os modelos, migrations e contratos existentes; não altera movimentos, taxas SGS, autenticação,
RLS, ações, FIIs/ETFs, frontend ou demo offline. Não há dependências/serviços pagos novos.

## Convenção explícita, não universal

A consulta deve escolher `convention=daily_cdi_pro_rata_decimal_v1`. Esse nome confirma:

- Remuneração percentual de CDI diário, usando a série SGS **12**, em % ao dia.
- Aplicação inclusiva e data de avaliação/vencimento exclusiva na capitalização.
- Sem spread anual, taxa anualizada, cupons, custos ou pagamentos de juros intermediários.
- Resgate amortiza proporcionalmente principal e rendimento do lote; a parte retirada
  não continua rendendo na posição aberta. O caixa líquido registrado não é reinterpretado.
- Calendário financeiro escolhido explicitamente, compatível com o contrato do usuário.

`contracted_rate=110` significa 110% do CDI. Para cada data publicada válida `d`:

```text
f_d = 1 + (CDI_d / 100) × (percentual_contratado / 100)
F_lote = produto(f_d), aplicação ≤ d < min(as_of, vencimento)
P_remanescente = aplicações − amortizações de principal até as_of
Rendimento_bruto_aberto = P_remanescente × (F_lote − 1)
```

Não é `CDI + 10% a.a.` nem `F_CDI elevado a 1,10`. Prefixados, spread, cupons ou outros
produtos não são calculados. O endpoint devolve `unsupported_product` ou
`convention_required` em vez de adotar uma regra silenciosamente.

A [metodologia DI da B3](https://www.b3.com.br/data/files/E9/24/20/40/0D331610D1820216790D8AA8/Manual-do-Produto-Certificado-de-Deposito-Bancario-CDB.pdf)
descreve produtos com truncamento intermediário e arredondamento de fator. **Este modelo
Decimal não replica a liquidação B3**, não reconstrói taxa anual DI e não aplica truncamento
diário de 16 casas/fator final de 8. Mesmo em produto economicamente semelhante, arredondamento,
calendário ou condições do emissor podem produzir diferenças. Só usar a convenção selecionada
quando adequada ao contrato; extrato da instituição prevalece para liquidação real.

Nenhuma migration é necessária: premissas são parâmetros da nova consulta e são ecoadas
na resposta com versão `2.0.3`; não são gravadas retroativamente em contratos imutáveis.
Persistência de convenções por contrato exigirá desenho próprio em uma entrega futura.

## Precisão e arredondamento

- Valores/taxas são Decimal, com contexto local de **64 dígitos**, ROUND_HALF_EVEN.
- Nenhum arredondamento monetário ocorre na capitalização ou no cálculo da base dos impostos.
- Valores de apresentação são arredondados a centavos **por lote**, ao final. O principal
  contábil continua com suas oito casas; a valorização utiliza sua apresentação em centavos.
- `bruto = principal_em_centavos + rendimento_bruto_em_centavos`;
  `rendimento_líquido = rendimento_bruto − IOF − IR` e `líquido = bruto − IOF − IR`.
  Componentes exibidos reconciliam; totais somam os componentes arredondados dos lotes.
- Não há float financeiro. Fatores não positivos ou excessivos (ordem acima de 10³²)
  tornam as taxas inválidas para o motor, sem overflow ou resultado inventado.

## Datas e cobertura

- `as_of` obrigatório, não futuro e não anterior à aplicação contratual, usando hoje em
  America/Sao_Paulo. Movimentos posteriores são ignorados na posição histórica.
- Um SELECT com joins e filtros owner_id captura contrato, lotes e movimentos no mesmo
  snapshot MVCC. A conexão/transação é liberada antes do HTTP SGS. Até 10.000 registros
  por consulta; exceder resulta em 422, nunca em soma truncada.
- A posição considera os movimentos registrados em `date <= as_of`. Como o ledger contém
  datas, não horários financeiros, não se tenta reconstruir ordem intradiária de liquidação.
- Cada lote mantém sua aplicação original para juros e idade tributária; resgates parciais
  não reiniciam a contagem de dias. Lotes posteriores a as_of não integram a posição.
- Crescimento para no vencimento. Se houver principal sem resgate registrado **após o
  vencimento**, `matured_unsettled`: bruto pode ser estimado até o vencimento, mas líquido
  e impostos ficam null. Não se presume quando houve retenção/liquidação automática.
- Resgate total deixa zero na **posição aberta**, sem afirmar lucro ou tributos passados.

`calendar=anbima_2024_2026_v1` deve ser confirmado explicitamente: segunda a sexta menos
as datas das listas nacionais ANBIMA para [2024](https://www.anbima.com.br/feriados/fer_nacionais/2024.asp),
[2025](https://www.anbima.com.br/feriados/fer_nacionais/2025.asp) e
[2026](https://www.anbima.com.br/feriados/fer_nacionais/2026.asp), verificadas em 28/10/2026.
O calendário é estático/versionado, não um serviço remoto, e não cobre calendários locais,
condições especiais de emissor ou anos fora desse intervalo. Fora da cobertura retorna
`unsupported_calendar`. Antes de usar anos novos, é necessária revisão e nova versão.

As taxas são aplicadas **somente** se publicadas para datas esperadas. Não se fabrica
taxa para sábado, domingo, feriado, atraso ou lacuna. Cada dia útil esperado ausente aparece
em `missing_rate_dates`; o lote fica `incomplete_history` e não recebe valores de rendimento,
impostos ou líquido. Uma publicação incompatível com o calendário escolhido é `invalid_rates`.
Isso também evita tratar como zero uma taxa ainda não divulgada, inclusive da véspera.

## Hipóteses tributárias

Somente `tax_profile=br_resident_individual`: hipótese de pessoa física residente no Brasil,
CDB tributável comum, sem regime especial/isencão. Ausência dessa confirmação mantém bruto,
mas retorna `tax_profile_required`, com impostos e líquido null.

Estimativa de resgate hipotético em as_of, enquanto não ultrapassado o vencimento:

| Dias corridos desde aplicação do lote | IR sobre rendimento positivo, após IOF |
| --- | --- |
| Até 180 | 22,5% |
| 181 a 360 | 20% |
| 361 a 720 | 17,5% |
| A partir de 721 | 15% |

IOF sobre rendimento positivo, por dia corrido 1 a 30:

```text
dia:  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15
IOF: 96 93 90 86 83 80 76 73 70 66 63 60 56 53 50
dia: 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30
IOF: 46 43 40 36 33 30 26 23 20 16 13 10  6  3  0
```

Do dia 30 em diante, IOF zero. Dia da própria aplicação não tem dias capitalizados nem
rendimento estimado; IOF sobre rendimento positivo em dia zero não é modelado.

```text
ganho_tributável = max(rendimento_bruto_aberto, 0)
IOF = ganho_tributável × alíquota_IOF(dias)
IR = (ganho_tributável − IOF) × alíquota_IR(dias)
```

Perdas não geram imposto estimado nem crédito tributário inferido. `tax_basis_date` é a
data de referência da estimativa, **não** uma declaração de fato gerador realizado.
As regras não são aplicadas a rendimentos de resgates já ocorridos: qualquer resgate no
lote produz `realized_tax_status=insufficient_information` e `realized_ir`, `realized_iof`,
`realized_income` null, mesmo quando cash_received esteja registrado.

Fontes consultadas em 28/10/2026: [IN RFB 1.585/2015, art. 46](https://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=67494),
[regras oficiais Tesouro Direto sobre tributação de renda fixa](https://www.tesourodireto.com.br/sobre-o-tesouro/regras-e-regulamento),
[tabela IOF publicada pelo Banco do Brasil](https://www.bb.com.br/site/investimentos/iof/)
e [Decreto 6.306/2007, texto na Câmara](https://www2.camara.leg.br/legin/fed/decret/2007/decreto-6306-14-dezembro-2007-566561-normaatualizada-pe.html).
Não é motor fiscal completo nem promessa de liquidação. Mudança legislativa, perfil
diferente ou condição contratual exige revisão; sem extrapolação para outros produtos.

## Exemplos fictícios auditáveis

Aplicação R$ 1.000 em 02/01/2025, avaliação 04/01/2025, taxas fictícias de **1% ao dia**
em 02 e 03/01 (nenhuma taxa no sábado), sem amortizações:

| Percentual CDI | Fator de dois dias | Rendimento bruto exibido |
| --- | --- | --- |
| 100% | 1,0201 | R$ 20,10 |
| 110% | 1,022121 | R$ 22,12 |
| 120% | 1,024144 | R$ 24,14 |

No caso 100%, idade dois dias: IOF bruto 20,10 × 93% = 18,693 → R$ 18,69;
IR bruto (20,10 − 18,693) × 22,5% = 0,316575 → R$ 0,32.
Rendimento líquido estimado exibido = 20,10 − 18,69 − 0,32 = **R$ 1,09**.

Se 400 do principal do primeiro lote forem amortizados em 03/01, restam 600:
rendimento aberto = 600 × 0,0201 = **R$ 12,06**, não 20,10. A remuneração da parte
resgatada não é somada novamente. Se outro lote aplicado em 03/01 tiver principal 200,
rende 200 × 0,01 = R$ 2,00. Total bruto aberto R$ 14,06. Nenhum desses valores é
inferido a partir do caixa recebido no resgate.

## API nova, contratos existentes preservados

```text
GET /api/fixed-income/investments/{id}/returns
  ?as_of=2025-01-04
  &convention=daily_cdi_pro_rata_decimal_v1
  &calendar=anbima_2024_2026_v1
  &tax_profile=br_resident_individual
```

Usa private_db/owner_id/RLS existentes. 401 sem sessão, 403 pela allowlist existente,
404 para investimento alheio/inexistente, 422 para datas/parâmetros inválidos. Resposta
privada no-store contém principal, lotes, valores estimados, fatores, bases de data,
razões de indisponibilidade, versão, premissas e referências SGS (coleta/expiração/cache).

Totais de cada métrica só existem se **todos** os lotes ativos tiverem essa métrica;
caso contrário são null. Principal conhecido continua disponível. Status global:
`estimated`, `incomplete` ou `empty`. Campos realizados nunca são confundidos com abertos.
Indisponibilidade SGS preserva principal e retorna `rates_error`/`rates_unavailable`
com métricas null no corpo 200; não mascara falhas como rendimento zero.

Reutiliza o RateService da 2.0.2, exclusivamente série 12 (Selic 11 não substitui CDI).
Divide apenas o histórico coberto (2024–2026) em janelas de até 366 dias inclusivos,
sem sobreposição. Máximo três janelas, orçamento total 30 s. Há uma única espera curta
(até dois segundos) por janela para espaçamento local; não repete erros do fornecedor
ou contorna cooldown/limite móvel. Falha em qualquer janela torna a avaliação indisponível.
Nenhuma cache financeira de usuário é criada; permanece o cache público limitado de taxas.

## Homologação segura CDI/Selic no Render — manual e pendente

**Não executada nesta entrega. Nenhuma sessão/JWT de produção foi fornecida ou utilizada.**
Leitura do código/MockTransport/PostgreSQL local não prova rede, JWT, versão publicada
ou disponibilidade real do SGS no Render. Não se buscou token em arquivos ou no navegador.

Com a versão já publicada da 2.0.2, confirmar no painel Render o commit esperado e usar
JWT real de uma sessão Supabase autorizada. Abrir PowerShell sem transcrição, não salvar
token em arquivo/URL/.env, não compartilhar screenshots. Este teste faz somente GET:

```powershell
$fiApi = 'https://investment-dashboard-3ogz.onrender.com'
$fiSecret = Read-Host 'Access token da sua sessão Supabase autorizada (entrada oculta)' -AsSecureString
$fiJwt = [System.Net.NetworkCredential]::new('', $fiSecret).Password
$fiHeaders = @{ Authorization = "Bearer $fiJwt" }
try {
    foreach ($fiRound in 1..2) {
        foreach ($fiSeries in 12,11) {
            try {
                $fiResult = Invoke-RestMethod -Method Get -Headers $fiHeaders -TimeoutSec 40 `
                  -Uri "$fiApi/api/fixed-income/rates/${fiSeries}?start_date=2025-01-02&end_date=2025-01-03"
                if ($fiResult.series_code -ne $fiSeries -or $fiResult.unit -ne '% ao dia') {
                    throw 'Contrato de resposta divergente'
                }
                [pscustomobject]@{ serie=$fiResult.series_code; unidade=$fiResult.unit;
                  estado=$fiResult.status; registros=$fiResult.observations.Count; cache=$fiResult.from_cache }
            } catch { throw 'Homologação não confirmada; revisar status/rede/JWT sem registrar headers ou resposta de erro completa.' }
            Start-Sleep -Seconds 2
        }
    }
} finally {
    Remove-Variable fiSecret,fiJwt,fiHeaders,fiResult -ErrorAction SilentlyContinue
}
```

Esperado: série/unidade corretas, datas dentro do período, strings Decimal válidas, nenhuma
taxa inventada; repetir pode usar cache, cujo estado é por processo (não garantia entre workers).
Separadamente, GET sem Authorization deve retornar 401. Se 401/403 autenticado, revisar
expiração/allowlist/projeto; se 429, respeitar Retry-After; 502/503 exige revisar disponibilidade
e saída HTTPS do Render para api.bcb.gov.br. Não registrar tokens ou desativar TLS.

Após **futura autorização de publicação da 2.0.3**, testar o novo GET com investimento
próprio existente e premissas realmente compatíveis. Comparar principal com o ledger e
valores com o extrato, sem criar operações fictícias na carteira real. Outro usuário
autorizado não deve conseguir consultar esse id. Não alegar validação tributária definitiva.

## Validação local e arquivos

Resultados: **242 testes backend aprovados** (57 novos), mais **1 teste integrado
PostgreSQL aprovado**, incluindo o novo endpoint sob RLS. Aviso conhecido de depreciação
TestClient/httpx permanece; não houve falhas nos checks finais.

Novos módulos: returns_calendar.py, returns_schemas.py, returns_engine.py e returns_router.py
em backend/app/fixed_income. main.py apenas registra o novo router. Modelos, schemas
anteriores, ledger, BCB/SGS e migrations permanecem iguais. Testes novos de motor/API e
ampliação de fixed_income_postgres.py exercitam o endpoint sob a role sem BYPASSRLS.

```powershell
Set-Location C:\Users\IAN\ProjetosVSCode\investment-dashboard\backend
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_postgres.py --tb=short
$env:DOCKER_HOST='npipe:////./pipe/dockerDesktopLinuxEngine' # se necessário neste Windows
.\.venv\Scripts\python.exe tests/run_postgres.py
```

Todos os testes usam taxas fictícias/HTTP simulado, sem consumir SGS real. PostgreSQL
é container descartável com tmpfs, sem volumes pessoais/credenciais de produção.
Frontend e builds não precisam ser alterados para esta entrega backend; UI permanece na 2.0.4.
Nenhuma migration, commit, push ou deploy de produção foi executado. Publicação depende
de autorização do usuário.
