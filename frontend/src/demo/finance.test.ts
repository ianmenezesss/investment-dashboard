import { expect, test } from 'vitest'
import cases from '../../../shared/finance-cases.json'
import { summarizeDemo, validateOperation } from './finance'

for (const item of cases.cases) {
  test(`contrato compartilhado com Python: ${item.name}`, () => {
    const ops = item.operations.map(validateOperation)
    if (item.invalid) expect(() => summarizeDemo(ops)).toThrow('excede a posição')
    else expect(summarizeDemo(ops)).toMatchObject(item.expected!)
  })
}

test.each([
  { quantity: '-1' }, { quantity: '0' }, { price: 'NaN' }, { fees: '-1' },
  { quantity: '0.000000001' }, { price: '1000000000000' },
  { date: '2026-02-30' }, { date: '2099-01-01' }, { ticker: '<script>' },
])('rejeita entrada inválida %j', change => {
  expect(() => validateOperation({ id: 1, ticker: 'TEST4', kind: 'BUY', date: '2026-01-01', quantity: '1', price: '10', fees: '0', ...change })).toThrow()
})
