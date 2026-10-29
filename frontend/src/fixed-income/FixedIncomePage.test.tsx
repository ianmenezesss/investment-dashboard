import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, afterEach, expect, test, vi } from 'vitest'
import Decimal from 'decimal.js'
vi.mock('../runtime', () => ({ PUBLIC_DEMO: false, SUPABASE_AUTH: true, apiBase: () => '' }))
import { FixedIncomePage } from './FixedIncomePage'
import { PrivateRepository } from '../repositories/PrivateRepository'
import { fixedIncomeFixture } from '../test-fixtures/fixed-income'
import { totalApplications } from './format'
import { parseObservedBRL } from './ManualPositionDialog'
import type { ObservedPosition, CdbApplicationRevision, CdbMovement } from './types'

let host: HTMLDivElement, root: Root, queryClient: QueryClient
let fixture: ReturnType<typeof fixedIncomeFixture>
let listError: number, detailError: number, historyError: number, postError: number, returnError: number, archiveError: number, archived: boolean
let fetchMock: ReturnType<typeof vi.fn>
let observedRows: ObservedPosition[]
let originalMovements: CdbMovement[], revisionEvents: CdbApplicationRevision[], revisionFailures: number[], revisionPreviewFailures: number[]
let revisionRequests: { input: Record<string, unknown>; key: string; status: number; response: CdbApplicationRevision }[]
let loseRevisionResponse: boolean
const authError = vi.fn()
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
async function pause() { await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) }) }
beforeEach(() => {
  fixture = fixedIncomeFixture(); observedRows=[]; originalMovements = fixture.movements.map(row=>({...row})); revisionEvents=[]; revisionFailures=[]; revisionPreviewFailures=[]; revisionRequests=[]; loseRevisionResponse=false; listError = detailError = historyError = postError = returnError = archiveError = 0; archived = false; authError.mockClear()
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  fetchMock = vi.fn(async (path: string, init: RequestInit) => {
    expect((init.headers as Record<string, string>).Authorization).toMatch(/^Bearer token-/)
    expect(init.credentials).toBe('omit'); expect(init.cache).toBe('no-store')
    const url = new URL(path, 'https://test.invalid')
    if (url.pathname.endsWith('/observed-history')) return json({ investment_id: fixture.detail.id, coverage: 'unavailable', points: [], warning: 'Somente observações registradas.' })
    if (init.method === 'DELETE' && url.pathname.endsWith('/archive')) {
      if (archiveError) return json({ detail: 'Contrato não pode ser arquivado' }, archiveError)
      archived = true
      return new Response(null, { status: 204 })
    }
    if (init.method === 'POST') {
      const revisionId = Number(url.pathname.match(/\/applications\/(\d+)\/revisions/)?.[1])
      if (url.pathname.endsWith('/revisions/preview')) {
        if (revisionPreviewFailures.length) return json({ detail: 'A cronologia impede esta revisão fictícia.' }, revisionPreviewFailures.shift())
        const input = JSON.parse(String(init.body))
        const movement = fixture.movements.find(row=>row.id===revisionId) ?? originalMovements.find(row=>row.id===revisionId)!
        const lotBalance = fixture.detail.lots.find(lot=>lot.id===movement.lot_id)?.principal_balance ?? '0'
        const after = input.kind==='REPLACE' ? new Decimal(lotBalance).minus(movement.principal_amount).plus(input.replacement_amount).toFixed() : '0'
        return json({ kind:input.kind,lot_id:movement.lot_id,principal_before:lotBalance,principal_after:after,effective_date:input.replacement_date??null,amount:input.replacement_amount??null,reason:input.reason,will_create_event:true,idempotent_replay:false })
      }
      if (url.pathname.includes('/applications/') && url.pathname.endsWith('/revisions')) {
        const input = JSON.parse(String(init.body)), key = new Headers(init.headers).get('Idempotency-Key') ?? ''
        const prior = revisionRequests.find(item=>item.key===key)
        if (prior) return JSON.stringify(prior.input) === JSON.stringify(input) ? json(prior.response, 200) : json({detail:'Idempotency conflict'},409)
        if (revisionFailures.length) return json({detail:'Revisão recusada pelo teste'},revisionFailures.shift())
        const movement = fixture.movements.find(row=>row.id===revisionId)!
        const event:CdbApplicationRevision={id:revisionEvents.length+1,application_id:revisionId,revision:revisionEvents.filter(item=>item.application_id===revisionId).length+1,kind:input.kind as 'REPLACE'|'VOID',replacement_date:input.replacement_date as string??null,replacement_amount:input.replacement_amount?new Decimal(String(input.replacement_amount)).toFixed(8):null,reason:String(input.reason),created_at:'2026-10-28T12:00:00Z'}
        revisionEvents.push(event);revisionRequests.push({input,key,status:201,response:event})
        if (event.kind==='REPLACE') { const priorAmount=new Decimal(movement.principal_amount),nextAmount=new Decimal(event.replacement_amount!); const lot=fixture.detail.lots.find(item=>item.id===movement.lot_id)!; lot.principal_balance=new Decimal(lot.principal_balance).plus(nextAmount).minus(priorAmount).toFixed(); fixture.detail.principal_balance=new Decimal(fixture.detail.principal_balance).plus(nextAmount).minus(priorAmount).toFixed(); movement.principal_amount=event.replacement_amount!;movement.date=event.replacement_date! }
        else { fixture.movements=fixture.movements.filter(row=>row.id!==revisionId);fixture.detail.lots=fixture.detail.lots.filter(lot=>lot.id!==movement.lot_id);fixture.detail.principal_balance=new Decimal(fixture.detail.principal_balance).minus(movement.principal_amount).toFixed() }
        if(loseRevisionResponse){loseRevisionResponse=false;throw new TypeError('Network response lost after fictional commit')}
        return json(event,201)
      }
      if (postError) return json({ detail: 'Operação rejeitada: confira saldo e datas' }, postError)
      const input = JSON.parse(String(init.body))
      if(url.pathname.endsWith('/opening-balance')||url.pathname.endsWith('/observations')) {
        const row:ObservedPosition={...input,id:observedRows.length+1,investment_id:fixture.detail.id,kind:url.pathname.endsWith('/opening-balance')?'OPENING':'OBSERVATION',created_at:'2026-10-15T12:00:00Z'}
        observedRows.push(row);fixture.detail.tracking_mode='CONSOLIDATED';fixture.detail.latest_observation=row;if(row.kind==='OPENING')fixture.detail.opening_balance=row
        return json(row,201)
      }
      if (url.pathname.endsWith('/investments')) { fixture.detail = { ...fixture.detail, ...input, id: 2, principal_balance: '0', lots: [] }; fixture.movements = []; return json(fixture.detail, 201) }
      const kind = url.pathname.endsWith('/applications') ? 'APPLICATION' : 'REDEMPTION'
      const row = { ...fixture.movements[0], ...input, id: fixture.movements.length + 1, investment_id: fixture.detail.id, lot_id: input.lot_id ?? 2, kind, cash_received: input.cash_received ?? null }
      fixture.movements.push(row)
      originalMovements.push({...row})
      if (kind === 'APPLICATION') fixture.detail.lots.push({ id: row.lot_id, application_date: row.date, principal_balance: row.principal_amount })
      else { const lot = fixture.detail.lots.find(item => item.id === row.lot_id)!; lot.principal_balance = new Decimal(lot.principal_balance).minus(row.principal_amount).toFixed() }
      fixture.detail.principal_balance = new Decimal(fixture.detail.principal_balance)[kind === 'APPLICATION' ? 'plus' : 'minus'](row.principal_amount).toFixed()
      return json(row, 201)
    }
    if (url.pathname.endsWith('/returns')) return returnError ? json({ detail: 'Falha de consulta' }, returnError) : json(fixture.returns)
    if (url.pathname.includes('/applications/') && url.pathname.endsWith('/revisions')) { const id=Number(url.pathname.match(/\/applications\/(\d+)\/revisions/)?.[1]);const offset=Number(url.searchParams.get('offset')??0);return json(revisionEvents.filter(row=>row.application_id===id).slice(offset,offset+100)) }
    if (url.pathname.endsWith('/observations')) return json(observedRows)
    if (url.pathname.endsWith('/effective-movements')) return historyError ? json({ detail: 'Histórico indisponível' }, historyError) : json(fixture.movements.slice(Number(url.searchParams.get('offset')), Number(url.searchParams.get('offset')) + 100))
    if (url.pathname.endsWith('/movements')) return json(originalMovements.slice(Number(url.searchParams.get('offset')), Number(url.searchParams.get('offset')) + 100))
    if (url.pathname.endsWith('/investments')) return listError ? json({ detail: 'Lista indisponível' }, listError) : json(archived ? [] : [fixture.detail])
    return detailError ? json({ detail: 'Posição indisponível' }, detailError) : json(fixture.detail)
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(async () => { await act(async () => root.unmount()); queryClient.clear(); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks() })
async function render(selected = true, counter = 0, identity = 'owner-a') {
  await act(async () => root.render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[selected ? '/cdbs?investment=1' : '/cdbs']}><FixedIncomePage key={identity} repository={new PrivateRepository('token-' + identity)} identity={identity} newOperationRequest={counter} onAuthError={authError}/></MemoryRouter></QueryClientProvider>))
  await pause()
}
async function click(text: string) {
  const button = [...document.querySelectorAll('button')].find(button => button.textContent?.trim() === text)
  expect(button, text).toBeTruthy()
  await act(async () => button!.click()); await pause()
}
async function field(name: string, value: string) {
  const input = document.querySelector(`[role="dialog"] [name="${name}"]`) as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
  expect(input, name).toBeTruthy()
  await act(async () => {
    const prototype = input instanceof HTMLSelectElement ? HTMLSelectElement.prototype : input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event(input instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }))
  })
}
async function submitDialog() { await act(async () => document.querySelector('[role="dialog"] form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))); await pause() }
async function confirmRevisionCheckbox() { const input=document.querySelector<HTMLInputElement>('.fi-confirm input')!;expect(input).toBeTruthy();await act(async()=>input.click());await pause() }
const posts = () => fetchMock.mock.calls.filter(([, init]) => init.method === 'POST')

test('lista contratos e detalhe real, preserva principal e histórico sem consulta automática de rendimento', async () => {
  await render()
  expect(host.textContent).toContain('Banco fictício'); expect(host.textContent).toContain('100% do CDI')
  expect(host.textContent).toContain('Principal aplicado acumulado'); expect(host.textContent).toContain('R$ 1.000,00')
  expect(host.querySelector('[aria-label="Abrir CDB de teste"]')!.textContent).toBe('Ver lotes e histórico')
  expect(fetchMock.mock.calls.some(([path]) => path.includes('/returns'))).toBe(false)
  expect(fetchMock.mock.calls.every(([path]) => path.startsWith('/api/fixed-income/'))).toBe(true)
  expect(host.textContent).toContain('Caixa de resgate não é rendimento')
})

test('arquiva contrato somente após confirmação explícita e oculta a linha ativa sem apagar dados', async () => {
  fixture.detail.lots = []; fixture.detail.principal_balance = '0'; fixture.movements = []
  const confirmation = vi.spyOn(window, 'confirm').mockReturnValue(false)
  await render()
  await click('Arquivar contrato')
  expect(confirmation).toHaveBeenCalledWith(expect.stringContaining('CDB de teste'))
  expect(fetchMock.mock.calls.some(([, init]) => init.method === 'DELETE')).toBe(false)
  expect(host.textContent).toContain('Banco fictício')

  confirmation.mockReturnValue(true)
  await click('Arquivar contrato')
  expect(fetchMock.mock.calls.some(([path, init]) => path.endsWith('/investments/1/archive') && init.method === 'DELETE')).toBe(true)
  expect(host.textContent).toContain('Contrato vazio arquivado')
  expect(host.textContent).toContain('Seu primeiro CDB começa aqui')
  expect(fixture.movements).toHaveLength(0)
  confirmation.mockRestore()
})

test('conflito ao arquivar mantém o detalhe e informa que o servidor recusou', async () => {
  fixture.detail.lots = []; fixture.detail.principal_balance = '0'; fixture.movements = []; archiveError = 409
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  await render(); await click('Arquivar contrato')
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('Contrato não pode ser arquivado')
  expect(host.querySelector('[aria-label="Detalhes de CDB de teste"]')).not.toBeNull()
})

test('dicas financeiras são acessíveis por foco e distinguem cálculo do ledger', async () => {
  await render()
  const hint = document.querySelector<HTMLButtonElement>('[aria-label="Entender: principal aplicado acumulado"]')!
  expect(hint).toBeTruthy()
  await act(async () => hint.focus()); await pause()
  expect(document.querySelector('[role="tooltip"]')?.textContent).toContain('posição observada do CDB inteiro não é incluída')
  expect(host.textContent).toContain('Calculado do ledger')
  expect(host.textContent).toContain('Movimentações registradas')
})

test('cadastra CDI pelos campos reais, não cria aplicação implícita e confirma sucesso', async () => {
  await render(false); await click('Cadastrar CDB')
  for (const [name, value] of Object.entries({ issuer: 'Banco exemplo', product_name: 'Novo CDB', contracted_rate: '110.12345678', application_date: '2025-01-02', maturity_date: '2027-01-02' })) await field(name, value)
  await submitDialog()
  expect(JSON.parse(posts()[0][1].body)).toEqual({ issuer: 'Banco exemplo', product_name: 'Novo CDB', product_type: 'CDB', remuneration: 'CDI', indexer: 'CDI', contracted_rate: '110.12345678', application_date: '2025-01-02', maturity_date: '2027-01-02' })
  expect(posts()).toHaveLength(1); expect(host.textContent).toContain('CDB cadastrado')
  expect(host.textContent).toContain('Nenhuma aplicação registrada')
})

test('cadastro prefixado usa indexador NONE sem sugerir motor CDI', async () => {
  await render(false); await click('Cadastrar CDB'); await field('remuneration', 'FIXED')
  for (const [name, value] of Object.entries({ issuer: 'Banco exemplo', product_name: 'Prefixado', contracted_rate: '12.5', application_date: '2025-01-02', maturity_date: '2027-01-02' })) await field(name, value)
  await submitDialog()
  expect(JSON.parse(posts()[0][1].body).indexer).toBe('NONE')
  expect(host.textContent).toContain('não há cálculo prefixado disponível')
})

test('nova aplicação cria lote e atualiza posição e histórico após resposta da API', async () => {
  await render(); await click('Nova aplicação'); await field('date', '2025-01-03'); await field('principal_amount', '200.12345678'); await submitDialog()
  expect(posts()[0][0]).toBe('/api/fixed-income/investments/1/applications')
  expect(JSON.parse(posts()[0][1].body)).toEqual({ date: '2025-01-03', principal_amount: '200.12345678' })
  expect(host.textContent).toContain('Aplicação registrada em um novo lote')
  expect(host.textContent).toContain('R$ 1.200,12')
})

test('corrige aplicação só após preview e confirmação; envia a mesma intenção e preserva o lançamento original', async () => {
  await render(); await click('Corrigir aplicação')
  await field('replacement_amount','250.00'); await field('replacement_date','2025-01-02'); await field('reason','Valor fictício cadastrado incorretamente')
  await click('Ver impacto antes de confirmar')
  expect(posts().filter(([path])=>String(path).endsWith('/preview'))).toHaveLength(1)
  expect(posts().filter(([path])=>String(path).endsWith('/revisions'))).toHaveLength(0)
  expect(document.body.textContent).toContain('Impacto no principal registrado')
  await confirmRevisionCheckbox(); await click('Confirmar correção')
  const previewCall=posts().find(([path])=>String(path).endsWith('/preview'))!
  const writeCall=posts().find(([path])=>String(path).endsWith('/revisions'))!
  expect(JSON.parse(String(previewCall[1].body))).toEqual({kind:'REPLACE',expected_revision:0,reason:'Valor fictício cadastrado incorretamente',replacement_amount:'250.00',replacement_date:'2025-01-02'})
  expect(new Headers(previewCall[1].headers).get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/i)
  expect(new Headers(writeCall[1].headers).get('Idempotency-Key')).toBe(new Headers(previewCall[1].headers).get('Idempotency-Key'))
  expect(originalMovements[0].principal_amount).toBe('1000')
  expect(fixture.movements[0].principal_amount).toBe('250.00000000')
  expect(host.textContent).toContain('Aplicação corrigida na projeção efetiva')
})

test('anulação explica a natureza contábil e exige confirmação sem enviar valores substitutos ou criar resgate', async () => {
  await render(); await click('Anular aplicação')
  expect(document.body.textContent).toContain('anulação contábil: não registra caixa e não cria um resgate fictício')
  await field('reason','Lançamento fictício inexistente'); await click('Ver impacto antes de confirmar')
  expect(document.body.textContent).toContain('Esta ação é contábil')
  expect(document.querySelector('[name="replacement_amount"]')).toBeNull()
  await confirmRevisionCheckbox(); await click('Confirmar anulação')
  const write=posts().find(([path])=>String(path).endsWith('/revisions'))!
  expect(JSON.parse(String(write[1].body))).toEqual({kind:'VOID',expected_revision:0,reason:'Lançamento fictício inexistente'})
  expect(originalMovements).toHaveLength(1)
  expect(fixture.movements).toHaveLength(0)
  expect(posts().some(([path])=>String(path).includes('/redemptions'))).toBe(false)
  expect(host.textContent).toContain('Nenhum resgate ou caixa fictício foi criado')
  expect(host.textContent).toContain('Aplicação original #1')
})

test('replay após resposta de rede perdida reutiliza a mesma chave e aceita HTTP 200', async () => {
  loseRevisionResponse=true
  await render(); await click('Corrigir aplicação'); await field('replacement_amount','999.99'); await field('reason','Correção fictícia'); await click('Ver impacto antes de confirmar'); await confirmRevisionCheckbox(); await click('Confirmar correção')
  expect(document.body.textContent).toContain('mesma chave de idempotência será reutilizada')
  const writeButton=[...document.querySelectorAll('button')].find(button=>button.textContent?.trim()==='Confirmar correção')!
  expect(writeButton).toBeTruthy()
  await act(async()=>writeButton.click()); await pause()
  const writes=posts().filter(([path])=>String(path).endsWith('/revisions'))
  expect(writes).toHaveLength(2)
  expect(new Headers(writes[0][1].headers).get('Idempotency-Key')).toBe(new Headers(writes[1][1].headers).get('Idempotency-Key'))
  expect(host.textContent).toContain('Aplicação corrigida na projeção efetiva')
})

test.each([[409,'desatualizada'],[422,'inválida'],[404,'não foi encontrado']] as const)('apresenta erro HTTP %i claramente sem repetir gravação', async (status,message) => {
  if(status===422) revisionPreviewFailures=[status]; else revisionFailures=[status]
  await render(); await click('Corrigir aplicação'); await field('replacement_amount','500'); await field('reason','Teste fictício')
  await click('Ver impacto antes de confirmar')
  if(status!==422){await confirmRevisionCheckbox();await click('Confirmar correção')}
  expect(document.body.querySelector('[role="alert"]')?.textContent).toContain(message)
  expect(posts().filter(([path])=>String(path).endsWith('/revisions')&&!String(path).endsWith('/preview'))).toHaveLength(status===422?0:1)
})

test('histórico de revisões é paginado e mantém a sequência e valores de auditoria', async () => {
  revisionEvents=Array.from({length:101},(_,index)=>({id:index+1,application_id:1,revision:index+1,kind:index%2?'VOID':'REPLACE',replacement_date:index%2?null:'2025-01-02',replacement_amount:index%2?null:'250.00000000',reason:`Motivo fictício ${index+1}`,created_at:'2026-10-28T12:00:00Z'}))
  await render(); await click('Ver histórico de revisões')
  expect(host.textContent).toContain('Motivo fictício 100')
  expect(host.textContent).not.toContain('Motivo fictício 101')
  await click('Carregar mais revisões')
  expect(host.textContent).toContain('#101 · Correção')
  expect(host.textContent).toContain('R$')
})

test('resgate parcial separa caixa e principal, e total usa o saldo exato do lote', async () => {
  await render(); await click('Resgatar principal'); await field('date', '2025-01-03'); await field('principal_amount', '400'); await field('cash_received', '420'); await submitDialog()
  expect(JSON.parse(posts()[0][1].body)).toEqual({ date: '2025-01-03', principal_amount: '400', lot_id: 1, cash_received: '420' })
  expect(host.textContent).toContain('R$ 600,00'); expect(host.textContent).toContain('R$ 420,00')
  await click('Resgatar principal'); await click('Resgatar todo o principal do lote'); await submitDialog()
  expect(JSON.parse(posts()[1][1].body).principal_amount).toBe('600')
  expect(JSON.parse(posts()[1][1].body).cash_received).toBeNull()
  expect(host.textContent).toContain('Encerrado · histórico preservado')
})

test('venda superior ao principal é bloqueada por Decimal sem POST', async () => {
  await render(); await click('Resgatar principal'); await field('principal_amount', '1000.00000001'); await submitDialog()
  expect(document.querySelector('[role="dialog"] [role="alert"]')!.textContent).toContain('supera o saldo')
  expect(posts()).toHaveLength(0)
})

test('erros do backend não simulam persistência nem reenviam movimento', async () => {
  await render(); postError = 422; await click('Nova aplicação'); await field('principal_amount', '20'); await submitDialog()
  expect(document.querySelector('[role="dialog"] [role="alert"]')!.textContent).toContain('Operação rejeitada')
  expect(posts()).toHaveLength(1); expect(fixture.movements).toHaveLength(1)
})

test('loading e retry da listagem são explícitos', async () => {
  let resolve!: (response: Response) => void
  fetchMock.mockImplementationOnce(() => new Promise<Response>(r => { resolve = r }))
  await render(false)
  expect(host.textContent).toContain('Carregando CDBs')
  await act(async () => resolve(json({ detail: 'Falha temporária' }, 503))); await pause()
  expect(host.querySelector('[role="alert"]')).not.toBeNull()
  await click('Tentar listar novamente'); expect(host.textContent).toContain('CDB de teste')
})

test('carteira vazia oferece cadastro sem saldo fictício', async () => {
  fetchMock.mockImplementation(async () => json([])); await render(false)
  expect(host.textContent).toContain('Seu primeiro CDB começa aqui')
  expect(host.textContent).not.toContain('R$ 0,00')
})

test('histórico incompleto não vira principal aplicado total', async () => {
  fixture.movements = Array.from({ length: 101 }, (_, index) => ({ ...fixture.movements[0], id: index + 1 }))
  await render()
  const card = [...host.querySelectorAll('.fi-metrics article')].find(card => card.textContent!.includes('Principal aplicado acumulado'))!
  expect(card.textContent).toContain('Indisponível')
  await click('Carregar mais movimentações')
  expect(card.textContent).toContain('R$ 101.000,00')
})

async function consult() {
  const form = host.querySelector('.fi-premises')!
  await act(async () => {
    const input = form.querySelector<HTMLInputElement>('[name="as_of"]')!
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '2025-01-04')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => { for (const input of form.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')) input.click() })
  await act(async () => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))); await pause()
}

test('consulta estimativa com premissas explícitas e apresenta valores do snapshot sem recalcular', async () => {
  await render(); await consult()
  const call = fetchMock.mock.calls.find(([path]) => path.includes('/returns'))![0]
  expect(call).toContain('convention=daily_cdi_pro_rata_decimal_v1'); expect(call).toContain('calendar=anbima_2024_2026_v1'); expect(call).toContain('tax_profile=br_resident_individual')
  expect(host.textContent).toContain('R$ 20,10'); expect(host.textContent).toContain('R$ 18,69'); expect(host.textContent).toContain('R$ 0,32'); expect(host.textContent).toContain('R$ 1.001,09')
  expect(host.textContent).toContain('04/01/2025'); expect(host.textContent).toContain('BCB/SGS 12')
})

test('estimativa incompleta mantém null e explicita rendimentos realizados não apurados', async () => {
  fixture.returns.status = 'incomplete'
  for (const field of ['gross_income_estimate', 'gross_value_estimate', 'iof_estimate', 'ir_estimate', 'net_income_estimate', 'net_value_estimate'] as const) { fixture.returns[field] = null; fixture.returns.lots[0][field] = null }
  fixture.returns.lots[0].status = 'incomplete_history'; fixture.returns.lots[0].missing_rate_dates = ['2025-01-03']; fixture.returns.lots[0].realized_tax_status = 'insufficient_information'
  await render(); await consult()
  expect(host.textContent).toContain('Histórico CDI incompleto'); expect(host.textContent).toContain('Resultados realizados, IR e IOF de resgates: informação insuficiente')
  expect(host.querySelector('[aria-label="Estimativa de rentabilidade"]')!.textContent!.match(/Indisponível/g)!.length).toBeGreaterThanOrEqual(6)
})

test('falha na estimativa permite retry sem fabricar resultados', async () => {
  returnError = 503; await render(); await consult()
  expect(host.textContent).toContain('Falha de consulta'); expect(host.textContent).not.toContain('R$ 1.001,09')
  returnError = 0; await click('Tentar novamente'); expect(host.textContent).toContain('R$ 1.001,09')
})

test('401/403 não mostram dados financeiros em cache e notificam o guard existente', async () => {
  for (const status of [401, 403]) {
    listError = status; await render(false)
    expect(authError).toHaveBeenLastCalledWith(expect.objectContaining({ status }))
    expect(host.querySelector('table')).toBeNull()
    listError = 0; queryClient.clear()
  }
})

test('troca de identidade não compartilha estado financeiro entre contas', async () => {
  await render(); expect(host.textContent).toContain('Banco fictício')
  fetchMock.mockImplementation(async (path: string) => path.includes('/investments?') ? json([]) : json({ detail: 'Não encontrado' }, 404)); await render(false, 0, 'owner-b')
  expect(host.textContent).not.toContain('Banco fictício')
  expect(host.textContent).toContain('Seu primeiro CDB começa aqui')
})

test('Nova operação externa abre somente formulário de renda fixa', async () => {
  await render(); await render(true, 1)
  expect(document.querySelector('[role="dialog"]')!.textContent).toContain('Nova operação de renda fixa')
  expect(document.querySelector('input[name="ticker"]')).toBeNull()
})

test('soma de principal preserva oito casas sem interferir no Decimal da demo', () => {
  expect(totalApplications([{ ...fixture.movements[0], principal_amount: '999999999999.12345678' }, { ...fixture.movements[0], principal_amount: '0.00000001' }])).toBe('999999999999.12345679')
})

test('fechar formulário por Escape preserva ledger e devolve foco', async () => {
  await render()
  const origin = [...host.querySelectorAll<HTMLButtonElement>('button')].find(button => button.textContent === 'Nova aplicação')!
  await act(async () => origin.focus()); await click('Nova aplicação')
  await act(async () => document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
  await pause() // Radix restores focus after unmounting the focus scope.
  expect(document.querySelector('[role="dialog"]')).toBeNull()
  expect(document.activeElement).toBe(origin); expect(posts()).toHaveLength(0)
})

test('envio pendente bloqueia duplicação de movimento e mantém feedback de carregamento', async () => {
  await render(); await click('Nova aplicação'); await field('principal_amount', '20')
  let resolve!: (response: Response) => void
  fetchMock.mockImplementationOnce(() => new Promise<Response>(r => { resolve = r }))
  await submitDialog()
  expect(document.querySelector('[role="dialog"]')!.textContent).toContain('Registrando…')
  await submitDialog(); expect(posts()).toHaveLength(1)
  await act(async () => resolve(json({ ...fixture.movements[0], id: 2 }, 201))); await pause()
  expect(document.querySelector('[role="dialog"]')).toBeNull()
})

async function prepareManual() {
  fixture.detail.lots=[];fixture.detail.principal_balance='0';fixture.movements=[]
  await render();await click('Iniciar com saldo atual')
  for(const[name,value]of Object.entries({as_of:'2026-10-15',source:'Extrato fictício',gross_value:'5.000,00',net_value:'4.950,00',taxes_combined:'50,00',reported_gain:'250,00'}))await field(name,value)
}

test('saldo inicial exige revisão e preserva principal desconhecido sem aplicações fictícias', async()=>{
  await prepareManual()
  expect(host.textContent).not.toContain('R$ 0,00')
  await submitDialog();expect(posts()).toHaveLength(0)
  expect(document.querySelector('[role="dialog"]')!.textContent).toContain('Confirme antes de salvar')
  await click('Confirmar e salvar posição')
  const input=JSON.parse(posts()[0][1].body)
  expect(posts()[0][0]).toBe('/api/fixed-income/investments/1/opening-balance')
  expect(input).toMatchObject({gross_value:'5000.00',net_value:'4950.00',taxes_combined:'50.00',reported_gain:'250.00',confirmed_principal:null,ir_estimate:null,iof_estimate:null})
  expect(fixture.movements).toHaveLength(0);expect(fixture.detail.lots).toHaveLength(0)
  expect(host.textContent).toContain('Principal não informado');expect(host.textContent).toContain('Rentabilidade histórica indisponível')
  expect(host.textContent).toContain('R$ 5.000,00');expect(host.textContent).toContain('R$ 4.950,00')
  expect(fetchMock.mock.calls.some(([path])=>path.includes('/returns'))).toBe(false)
})

test('tributos inconsistentes são rejeitados antes de revisão e campos opcionais não viram zero',async()=>{
  await prepareManual();await field('taxes_combined','40,00');await submitDialog()
  expect(document.querySelector('[role="dialog"] [role="alert"]')!.textContent).toContain('deve corresponder')
  expect(posts()).toHaveLength(0)
  await field('tax_mode','unknown');await field('confirmed_principal','4.700,00');await submitDialog();await click('Confirmar e salvar posição')
  expect(JSON.parse(posts()[0][1].body)).toMatchObject({taxes_combined:null,ir_estimate:null,iof_estimate:null,confirmed_principal:'4700.00'})
})

test('IR IOF discriminados, valores preservados ao voltar e snapshot anterior mantido na conciliação',async()=>{
  await prepareManual();await field('tax_mode','separate');await field('ir_estimate','40,00');await field('iof_estimate','10,00');await submitDialog()
  await click('Voltar ao formulário')
  expect(document.querySelector<HTMLInputElement>('[name="gross_value"]')!.value).toBe('5.000,00')
  await submitDialog();await click('Confirmar e salvar posição')
  const first=JSON.stringify(observedRows[0])
  await click('Registrar nova posição')
  for(const[name,value]of Object.entries({as_of:'2026-10-16',source:'Aplicativo fictício',gross_value:'4.800,00',net_value:'4.750,00',taxes_combined:'50,00',reason:'AFTER_CONSOLIDATED_REDEMPTION'}))await field(name,value)
  await field('cash_received','300,00');await submitDialog();await click('Confirmar e salvar posição')
  expect(observedRows).toHaveLength(2);expect(JSON.stringify(observedRows[0])).toBe(first)
  expect(JSON.parse(posts()[1][1].body)).toMatchObject({reason:'AFTER_CONSOLIDATED_REDEMPTION',cash_received:'300.00',confirmed_principal:null})
  expect(fixture.movements).toHaveLength(0)
})

test('máscara monetária é exata, permite perdas independentes e não aceita casas fracionárias extras',()=>{
  expect(parseObservedBRL('5.000,00')).toBe('5000.00');expect(parseObservedBRL('-250,00')).toBe('-250.00');expect(parseObservedBRL('')).toBeNull()
  expect(()=>parseObservedBRL('1,001')).toThrow();expect(()=>parseObservedBRL('NaN')).toThrow()
})

test.each([422,401,403])('erro %i ao salvar posição não simula sucesso nem repete o POST',async(status)=>{
  await prepareManual();await submitDialog()
  fetchMock.mockImplementationOnce(()=>Promise.resolve(json({detail:[{loc:['body'],msg:'Tributos inconsistentes',type:'value_error'}]},status)))
  await click('Confirmar e salvar posição')
  expect(posts()).toHaveLength(1);expect(observedRows).toHaveLength(0)
  if(status===422){
    expect(document.querySelector('[role="dialog"] [role="alert"]')!.textContent).toContain('Tributos inconsistentes')
    expect(document.querySelector('[role="dialog"]')!.textContent).toContain('Confirme antes de salvar')
  }else{
    expect(authError).toHaveBeenCalledWith(expect.objectContaining({status}))
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  }
})

test('posição manual bloqueia envio duplicado e fechamento enquanto a confirmação está pendente',async()=>{
  await prepareManual();await submitDialog()
  let resolve!:(response:Response)=>void
  fetchMock.mockImplementationOnce(()=>new Promise<Response>(r=>{resolve=r}))
  await click('Confirmar e salvar posição')
  const button=[...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find(b=>b.textContent==='Salvando posição…')!
  expect(button.disabled).toBe(true)
  await act(async()=>{button.click();document.querySelector('[role="dialog"]')!.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))})
  expect(posts()).toHaveLength(1);expect(document.querySelector('[role="dialog"]')).not.toBeNull()
  const input=JSON.parse(posts()[0][1].body)
  await act(async()=>resolve(json({...input,id:1,investment_id:1,kind:'OPENING',created_at:'2026-10-15T12:00:00Z'},201)));await pause()
  expect(document.querySelector('[role="dialog"]')).toBeNull()
})
