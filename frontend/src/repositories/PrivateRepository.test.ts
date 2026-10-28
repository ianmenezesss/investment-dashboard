import { expect, test, vi } from 'vitest'
const http = vi.hoisted(() => vi.fn().mockResolvedValue([]))
vi.mock('../api', () => ({ request: http }))
import { PrivateRepository } from './PrivateRepository'

test('repositório privado usa HTTP autenticado e nunca lê ou grava localStorage', async () => {
  const read = vi.spyOn(Storage.prototype, 'getItem'), write = vi.spyOn(Storage.prototype, 'setItem')
  try {
    const repo = new PrivateRepository('test-private-token')
    await repo.list(); await repo.summary()
    expect(http).toHaveBeenCalledWith('dashboard/valuation', 'test-private-token', { signal: undefined })
    await repo.create({ ticker: 'TEST4', kind: 'BUY', date: '2026-01-01', quantity: '1', price: '10', fees: '0' })
    await repo.delete(1); await repo.export()
    expect(http.mock.calls.every(call => call[1] === 'test-private-token')).toBe(true)
    expect(read).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled()
  } finally { vi.restoreAllMocks() }
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
