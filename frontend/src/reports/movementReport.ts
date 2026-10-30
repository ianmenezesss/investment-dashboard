import Decimal from 'decimal.js'
import type { UnifiedMovement } from '../repositories/PrivateRepository'

export function filterReportMovements(rows: readonly UnifiedMovement[], start: string, end: string, category: string, asset: string) {
  const search = asset.trim().toLocaleLowerCase('pt-BR')
  return rows.filter(row => row.date >= start && row.date <= end && (category === 'all' || row.investment_class === category) && row.asset.toLocaleLowerCase('pt-BR').includes(search))
    .slice().sort((a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id))
}

export function movementTotals(rows: readonly UnifiedMovement[]) {
  const groups = { purchases: new Decimal(0), disposals: new Decimal(0), external: new Decimal(0), income: new Decimal(0), other: new Decimal(0) }
  for (const row of rows) {
    const amount = new Decimal(row.financial_value ?? '0').abs()
    if (row.operation === 'BUY') groups.purchases = groups.purchases.plus(amount).plus(row.fees ?? '0')
    else if (row.operation === 'APPLICATION') groups.purchases = groups.purchases.plus(amount)
    else if (row.operation === 'SELL') groups.disposals = groups.disposals.plus(amount.minus(row.fees ?? '0'))
    else if (row.operation === 'REDEMPTION') groups.disposals = groups.disposals.plus(row.cash_received ?? amount)
    else if (row.operation === 'CONTRIBUTION' || row.operation === 'WITHDRAWAL') groups.external = groups.external.plus(amount)
    else if (row.operation === 'DIVIDEND' || row.operation === 'JCP') groups.income = groups.income.plus(amount)
    else groups.other = groups.other.plus(amount)
  }
  return { ...groups, count: rows.length, transactionVolume: groups.purchases.plus(groups.disposals) }
}

export function sharePercent(value: string, total: string) {
  const base = new Decimal(total)
  return base.isZero() ? '0.0' : new Decimal(value).div(base).mul(100).toDecimalPlaces(1).toFixed(1)
}
