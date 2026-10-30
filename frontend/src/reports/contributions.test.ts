import { describe, expect, it } from 'vitest'
import type { UnifiedMovement } from '../repositories/PrivateRepository'
import { aggregateContributions, contributionRows, decimalMoney } from './contributions'

const row = (date: string, operation: UnifiedMovement['operation'], investment_class: UnifiedMovement['investment_class'], financial_value: string, fees: string | null = null): UnifiedMovement => ({
  id: `${date}:${operation}`, date, operation, investment_class, asset: 'ATIVO', quantity: null, unit_price: null, financial_value, fees, cash_received: null,
})

describe('report contributions', () => {
  const movements = [row('2026-01-10', 'BUY', 'AÇÕES', '100.01', '0.99'), row('2026-01-20', 'APPLICATION', 'CDB', '250.10'), row('2026-02-03', 'SELL', 'AÇÕES', '500', '2'), row('2025-12-30', 'BUY', 'AÇÕES', '50', '0')]

  it('filters only recorded purchases and applications in the selected dates', () => {
    expect(contributionRows(movements, '2026-01-01', '2026-01-31').map(item => item.operation)).toEqual(['BUY', 'APPLICATION'])
  })

  it('aggregates equity fees and fixed-income principal with exact decimals by month/year', () => {
    const rows = contributionRows(movements, '2025-01-01', '2026-12-31')
    const months = aggregateContributions(rows, 'month')
    expect(months.map(item => [item.key, item.equities.toFixed(2), item.fixedIncome.toFixed(2), item.total.toFixed(2)])).toEqual([
      ['2025-12', '50.00', '0.00', '50.00'], ['2026-01', '101.00', '250.10', '351.10'],
    ])
    expect(aggregateContributions(rows, 'year').map(item => [item.key, item.total.toFixed(2)])).toEqual([['2025', '50.00'], ['2026', '351.10']])
    expect(decimalMoney(months[1].total)).toBe('R$ 351,10')
  })

  it('returns an empty report for a period without aporte records', () => {
    expect(aggregateContributions([], 'month')).toEqual([])
  })
})
