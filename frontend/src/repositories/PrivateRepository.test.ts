import { expect, test, vi } from 'vitest'
const http = vi.hoisted(() => vi.fn().mockResolvedValue([]))
vi.mock('../api', () => ({ request: http }))
import { PrivateRepository } from './PrivateRepository'

test('repositório privado usa HTTP autenticado e nunca lê ou grava localStorage', async () => {
  const read = vi.spyOn(Storage.prototype, 'getItem'), write = vi.spyOn(Storage.prototype, 'setItem')
  try {
    const repo = new PrivateRepository('test-private-token')
    await repo.list(); await repo.summary(); await repo.performance()
    expect(http).toHaveBeenCalledWith('dashboard/valuation', 'test-private-token', { signal: undefined })
    expect(http).toHaveBeenCalledWith('dashboard/performance', 'test-private-token', { signal: undefined })
    await repo.create({ ticker: 'TEST4', kind: 'BUY', date: '2026-01-01', quantity: '1', price: '10', fees: '0' })
    await repo.delete(1); await repo.export()
    expect(http.mock.calls.every(call => call[1] === 'test-private-token')).toBe(true)
    expect(read).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled()
  } finally { vi.restoreAllMocks() }
})

test('histórico individual usa o endpoint autenticado e codifica o ticker no caminho', async () => {
  const repo = new PrivateRepository('private-history-token')
  await repo.equityPriceHistory('ITUB4', 'MAX')
  expect(http).toHaveBeenCalledWith('dashboard/equities/ITUB4/price-history?period=MAX', 'private-history-token', { signal: undefined })
})

test('comparação privada envia tickers e período como parâmetros repetidos autenticados', async () => {
  const repo = new PrivateRepository('comparison-token')
  await repo.equityComparison(['ITUB4', 'BBAS3'], '6M')
  expect(http).toHaveBeenCalledWith('dashboard/equities/compare?tickers=ITUB4&tickers=BBAS3&period=6M', 'comparison-token', { signal: undefined })
})

test('registros financeiros usam endpoints privados e chave idempotente', async () => {
  http.mockResolvedValueOnce([]).mockResolvedValueOnce({ event_count: 1 }).mockResolvedValueOnce({ id: 4 }).mockResolvedValueOnce({ revision: 1 }).mockResolvedValueOnce([])
  const repo = new PrivateRepository('financial-events-token')
  const key = '0a99f00b-276f-49b4-9675-f0ccfa8439a1'
  const input = { kind: 'CONTRIBUTION' as const, event_date: '2025-01-01', cash_amount: '250.00', source: 'Extrato' }
  await repo.financialEvents()
  await repo.financialEventSummary('Tudo')
  await repo.createFinancialEvent(input, key)
  await repo.reviseFinancialEvent(4, { kind: 'REPLACE', expected_revision: 0, reason: 'Correção', replacement: input }, key)
  await repo.financialEventRevisions(4)
  expect(http.mock.calls.slice(-5)).toEqual([
    ['financial-events', 'financial-events-token', { signal: undefined }],
    ['dashboard/financial-events/summary?period=Tudo', 'financial-events-token', { signal: undefined }],
    ['financial-events', 'financial-events-token', expect.objectContaining({ method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(input) })],
    ['financial-events/4/revisions', 'financial-events-token', expect.objectContaining({ method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ kind: 'REPLACE', expected_revision: 0, reason: 'Correção', replacement: input }) })],
    ['financial-events/4/revisions', 'financial-events-token', { signal: undefined }],
  ])
})

test('API privada expõe preview, revisão e histórico com a chave idempotente no header', async () => {
  http.mockResolvedValueOnce({ kind: 'REPLACE' }).mockResolvedValueOnce({ id: 8 }).mockResolvedValueOnce([])
  const repo = new PrivateRepository('private-token')
  const intent = { kind: 'REPLACE' as const, expected_revision: 0, reason: 'Correção fictícia', replacement_date: '2025-01-01', replacement_amount: '250.00' }
  const key = 'f5277c12-8be4-4f3c-9134-e6b04046e09c'
  await repo.previewCdbApplicationRevision(4, 7, intent, key)
  await repo.createCdbApplicationRevision(4, 7, intent, key)
  await repo.cdbApplicationRevisions(4, 7, 0)
  expect(http.mock.calls.slice(-3)).toEqual([
    ['fixed-income/investments/4/applications/7/revisions/preview', 'private-token', expect.objectContaining({ method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(intent) })],
    ['fixed-income/investments/4/applications/7/revisions', 'private-token', expect.objectContaining({ method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(intent) })],
    ['fixed-income/investments/4/applications/7/revisions?offset=0&limit=100', 'private-token', { signal: undefined }],
  ])
})
