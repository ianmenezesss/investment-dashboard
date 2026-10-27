import { expect, test, vi } from 'vitest'
import { DemoRepository, DEMO_STORAGE_KEY } from './DemoRepository'
import { initialOperations } from '../demo/fixtures'
import { summarizeDemo, validateOperation } from '../demo/finance'
import Decimal from 'decimal.js'

function storage() {
  const values = new Map<string, string>()
  return { values, getItem: vi.fn((key: string) => values.get(key) ?? null), setItem: vi.fn((key: string, value: string) => { values.set(key, value) }) }
}
const buy = { ticker: 'TEST4', kind: 'BUY' as const, date: '2026-01-01', quantity: '10', price: '20', fees: '2' }

test('compra, venda parcial, taxas e atualização imediata dos indicadores', () => {
  const repo = new DemoRepository(storage())
  const initialProfit = repo.getSnapshot().summary.realized_profit
  const listener = vi.fn(); repo.subscribe(listener)
  repo.create(buy)
  repo.create({ ...buy, date: '2026-01-02', price: '30', fees: '0' })
  repo.create({ ...buy, kind: 'SELL', date: '2026-01-03', quantity: '5', price: '40', fees: '1' })
  const { summary } = repo.getSnapshot()
  expect(summary.holdings.find(h => h.ticker === 'TEST4')).toMatchObject({ quantity: '15', cost: '376.5', average_price: '25.1' })
  expect(new Decimal(summary.realized_profit).minus(initialProfit).toFixed(8)).toBe('73.50000000')
  expect(listener).toHaveBeenCalledTimes(3)
})

test('venda superior à posição e venda anterior à compra não alteram estado ou storage', () => {
  const store = storage(), repo = new DemoRepository(store)
  repo.create(buy)
  const before = repo.getSnapshot(), persisted = store.values.get(DEMO_STORAGE_KEY)
  expect(() => repo.create({ ...buy, kind: 'SELL', quantity: '11', date: '2026-01-02' })).toThrow('excede a posição')
  expect(() => repo.create({ ...buy, kind: 'SELL', quantity: '1', date: '2025-12-31' })).toThrow('excede a posição')
  expect(repo.getSnapshot()).toBe(before)
  expect(store.values.get(DEMO_STORAGE_KEY)).toBe(persisted)
})

test('persistência após recarga e restauração ficam restritas à chave demonstrativa', () => {
  const store = storage()
  store.values.set('private-sentinel', 'do-not-touch')
  const repo = new DemoRepository(store), created = repo.create(buy)
  const reloaded = new DemoRepository(store)
  expect(reloaded.getSnapshot().operations).toContainEqual(created)
  reloaded.reset()
  expect(new DemoRepository(store).getSnapshot().operations).toEqual(initialOperations.map(validateOperation))
  expect(store.values.get('private-sentinel')).toBe('do-not-touch')
  expect(store.getItem.mock.calls.every(([key]) => key === DEMO_STORAGE_KEY)).toBe(true)
  expect(store.setItem.mock.calls.every(([key]) => key === DEMO_STORAGE_KEY)).toBe(true)
})

test('carteira da versão 1 é preservada sem escrita e migra somente ao salvar', () => {
  const store = storage()
  const old = { kind: 'investment-demo', version: 1, operations: [{ ...buy, id: 99 }] }
  const raw = JSON.stringify(old); store.values.set(DEMO_STORAGE_KEY, raw)
  const repo = new DemoRepository(store)
  expect(repo.getSnapshot().operations).toEqual(old.operations)
  expect(repo.getSnapshot().seedVersion).toBe(1)
  expect(store.values.get(DEMO_STORAGE_KEY)).toBe(raw)
  expect(store.setItem).not.toHaveBeenCalled()
  repo.create({ ...buy, date: '2026-01-02' })
  const saved = JSON.parse(store.values.get(DEMO_STORAGE_KEY)!)
  expect(saved).toMatchObject({ version: 2, seedVersion: 1 })
  expect(saved.operations).toContainEqual(old.operations[0])
  expect(new DemoRepository(store).getSnapshot().operations).toHaveLength(2)
  repo.reset()
  expect(JSON.parse(store.values.get(DEMO_STORAGE_KEY)!)).toMatchObject({ version: 2, seedVersion: 2 })
  expect(repo.getSnapshot().operations).toHaveLength(26)
})

test('novo conjunto fictício possui seis posições, taxas e vendas positivas e negativas', () => {
  expect(initialOperations).toHaveLength(26)
  const complete = summarizeDemo(initialOperations)
  expect(complete.holdings).toHaveLength(6)
  expect(complete.market_value).toBeNull()
  expect(initialOperations.filter(op => op.kind === 'SELL')).toHaveLength(6)
  const deltas = initialOperations.map((op, i) => op.kind === 'SELL' ? new Decimal(summarizeDemo(initialOperations.slice(0, i + 1)).realized_profit).minus(summarizeDemo(initialOperations.slice(0, i)).realized_profit) : new Decimal(0))
  expect(deltas.some(delta => delta.gt(0))).toBe(true)
  expect(deltas.some(delta => delta.lt(0))).toBe(true)
})

test('exclusão recalcula carteira e bloqueia remoção que invalidaria venda posterior', () => {
  const repo = new DemoRepository(storage())
  const purchase = repo.create(buy)
  const sale = repo.create({ ...buy, kind: 'SELL', quantity: '5', date: '2026-01-02', fees: '0' })
  expect(() => repo.delete(purchase.id)).toThrow('excede a posição')
  repo.delete(sale.id); repo.delete(purchase.id)
  expect(repo.getSnapshot().summary.holdings.some(h => h.ticker === 'TEST4')).toBe(false)
})

test.each(['invalid-json', JSON.stringify({ kind: 'investment-demo', version: 999, operations: [] }), JSON.stringify({ kind: 'investment-demo', version: 1, operations: [{ ...buy, id: 1, quantity: '-1' }] })])('conteúdo corrompido ou incompatível recupera fixtures com aviso', raw => {
  const store = storage(); store.values.set(DEMO_STORAGE_KEY, raw)
  const repo = new DemoRepository(store)
  expect(repo.getSnapshot().operations).toHaveLength(initialOperations.length)
  expect(repo.getSnapshot().notice).toContain('inválidos ou incompatíveis')
  repo.reset()
  expect(new DemoRepository(store).getSnapshot().notice).toBe('')
})

test('quota indisponível preserva operação em memória e informa ausência de persistência', () => {
  const repo = new DemoRepository({ getItem: () => null, setItem: () => { throw new Error('Quota') } })
  repo.create(buy)
  expect(repo.getSnapshot().summary.holdings.some(h => h.ticker === 'TEST4')).toBe(true)
  expect(repo.getSnapshot().notice).toContain('apenas nesta sessão')
})
