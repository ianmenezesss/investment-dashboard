import { expect, test, vi } from 'vitest'
const http = vi.hoisted(() => vi.fn().mockResolvedValue([]))
vi.mock('../api', () => ({ request: http }))
import { PrivateRepository } from './PrivateRepository'

test('repositório privado usa HTTP autenticado e nunca lê ou grava localStorage', async () => {
  const read = vi.spyOn(Storage.prototype, 'getItem'), write = vi.spyOn(Storage.prototype, 'setItem')
  try {
    const repo = new PrivateRepository('test-private-token')
    await repo.list(); await repo.summary()
    await repo.create({ ticker: 'TEST4', kind: 'BUY', date: '2026-01-01', quantity: '1', price: '10', fees: '0' })
    await repo.delete(1); await repo.export()
    expect(http.mock.calls.every(call => call[1] === 'test-private-token')).toBe(true)
    expect(read).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled()
  } finally { vi.restoreAllMocks() }
})
