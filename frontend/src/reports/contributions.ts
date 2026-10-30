import Decimal from 'decimal.js'
import type { UnifiedMovement } from '../repositories/PrivateRepository'

export type ContributionPeriod = { key: string; equities: Decimal; fixedIncome: Decimal; total: Decimal }

export function contributionRows(movements: readonly UnifiedMovement[], start: string, end: string) {
  return movements.filter(row => row.date >= start && row.date <= end && (row.operation === 'BUY' || row.operation === 'APPLICATION'))
}

export function aggregateContributions(rows: readonly UnifiedMovement[], bucket: 'month' | 'year'): ContributionPeriod[] {
  const values = new Map<string, { equities: Decimal; fixedIncome: Decimal }>()
  for (const row of rows) {
    const key = bucket === 'month' ? row.date.slice(0, 7) : row.date.slice(0, 4)
    if (!/^\d{4}(?:-\d{2})?$/.test(key)) continue
    const amount = new Decimal(row.financial_value ?? '0').plus(row.operation === 'BUY' ? row.fees ?? '0' : '0')
    const current = values.get(key) ?? { equities: new Decimal(0), fixedIncome: new Decimal(0) }
    if (row.operation === 'BUY') current.equities = current.equities.plus(amount)
    else current.fixedIncome = current.fixedIncome.plus(amount)
    values.set(key, current)
  }
  return [...values].sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => ({
    key, ...value, total: value.equities.plus(value.fixedIncome),
  }))
}

export function decimalMoney(value: Decimal) {
  return `R$ ${value.toFixed(2).replace('.', ',')}`
}
