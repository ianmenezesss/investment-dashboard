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

export function aggregateIncomeReport(rows: readonly UnifiedMovement[]) {
  let totalDividend = new Decimal(0), totalJcp = new Decimal(0)
  const monthly = new Map<string, { key: string; dividends: Decimal; jcp: Decimal }>()
  const byAsset = new Map<string, { asset: string; dividends: Decimal; jcp: Decimal }>()
  let count = 0
  for (const row of rows) {
    if (row.operation !== 'DIVIDEND' && row.operation !== 'JCP') continue
    const amount = new Decimal(row.financial_value ?? '0').abs()
    if (!amount.isFinite()) continue
    count++
    const isDividend = row.operation === 'DIVIDEND'
    if (isDividend) totalDividend = totalDividend.plus(amount)
    else totalJcp = totalJcp.plus(amount)
    const key = row.date.slice(0, 7)
    const month = monthly.get(key) ?? { key, dividends: new Decimal(0), jcp: new Decimal(0) }
    if (isDividend) month.dividends = month.dividends.plus(amount)
    else month.jcp = month.jcp.plus(amount)
    monthly.set(key, month)
    const asset = byAsset.get(row.asset) ?? { asset: row.asset, dividends: new Decimal(0), jcp: new Decimal(0) }
    if (isDividend) asset.dividends = asset.dividends.plus(amount)
    else asset.jcp = asset.jcp.plus(amount)
    byAsset.set(row.asset, asset)
  }
  return {
    dividends: totalDividend,
    jcp: totalJcp,
    total: totalDividend.plus(totalJcp),
    count,
    monthly: [...monthly.values()].sort((a, b) => a.key.localeCompare(b.key)),
    byAsset: [...byAsset.values()].sort((a, b) => b.dividends.plus(b.jcp).comparedTo(a.dividends.plus(a.jcp))),
  }
}
