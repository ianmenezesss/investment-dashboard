import Decimal from 'decimal.js'
import type { Operation, Summary } from '../api'

// Mesmo contexto de decimal.Decimal do Python: 28 dígitos, ROUND_HALF_EVEN.
const D = Decimal.clone({ precision: 28, rounding: Decimal.ROUND_HALF_EVEN })
export type OperationInput = Omit<Operation, 'id'>

export function validateOperation(raw: unknown): Operation {
  if (!raw || typeof raw !== 'object') throw new Error('Operação inválida.')
  const value = raw as Record<string, unknown>
  if (!Number.isSafeInteger(value.id) || Number(value.id) <= 0) throw new Error('Identificador inválido.')
  if (typeof value.ticker !== 'string' || !/^[A-Z0-9]{4,20}$/.test(value.ticker)) throw new Error('Informe um ticker com 4 a 20 letras maiúsculas ou números.')
  if (value.kind !== 'BUY' && value.kind !== 'SELL') throw new Error('Operação deve ser compra ou venda.')
  if (typeof value.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value.date)) throw new Error('Informe uma data válida.')
  const parsed = new Date(`${value.date}T12:00:00Z`)
  const today = new Date().toLocaleDateString('en-CA')
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value.date || value.date > today) throw new Error('A data deve ser válida e não pode ser futura.')
  const amounts: Record<string, string> = {}
  for (const name of ['quantity', 'price', 'fees'] as const) {
    const input = value[name]
    if (typeof input !== 'string' || input.length > 40 || !/^\d+(\.\d+)?$/.test(input)) throw new Error('Valores devem ser números decimais positivos, sem separador de milhares.')
    const amount = new D(input)
    if (amount.decimalPlaces() > 8 || Math.max(0, amount.e + 1) > 12 || (name !== 'fees' && amount.lte(0))) throw new Error('Quantidade e preço devem ser positivos; use até 12 dígitos inteiros e 8 casas decimais.')
    amounts[name] = amount.toFixed()
  }
  return { id: Number(value.id), ticker: value.ticker, kind: value.kind, date: value.date, quantity: amounts.quantity, price: amounts.price, fees: amounts.fees }
}

export function summarizeDemo(operations: readonly Operation[]): Summary {
  const holdings = new Map<string, { ticker: string; quantity: Decimal; cost: Decimal }>()
  let purchases = new D(0), proceeds = new D(0), realized = new D(0)
  for (const op of [...operations].sort((a, b) => a.date.localeCompare(b.date) || a.id - b.id)) {
    let item = holdings.get(op.ticker)
    if (!item) { item = { ticker: op.ticker, quantity: new D(0), cost: new D(0) }; holdings.set(op.ticker, item) }
    const quantity = new D(op.quantity), price = new D(op.price), fees = new D(op.fees)
    if (op.kind === 'BUY') {
      const cost = quantity.times(price).plus(fees)
      item.cost = item.cost.plus(cost); item.quantity = item.quantity.plus(quantity); purchases = purchases.plus(cost)
    } else {
      if (quantity.gt(item.quantity)) throw new Error(`Venda de ${op.ticker} excede a posição disponível na data.`)
      const removed = item.cost.div(item.quantity).times(quantity)
      const net = quantity.times(price).minus(fees)
      realized = realized.plus(net.minus(removed)); proceeds = proceeds.plus(net)
      item.cost = item.cost.minus(removed); item.quantity = item.quantity.minus(quantity)
    }
  }
  const values = [...holdings.values()]
  return {
    acquisition_cost: values.reduce((sum, h) => sum.plus(h.cost), new D(0)).toFixed(), total_purchases: purchases.toFixed(), sale_proceeds: proceeds.toFixed(), realized_profit: realized.toFixed(), market_value: null,
    holdings: values.filter(h => !h.quantity.isZero()).map(h => ({ ticker: h.ticker, quantity: h.quantity.toFixed(), cost: h.cost.toFixed(), average_price: h.cost.div(h.quantity).toFixed() })),
  }
}
