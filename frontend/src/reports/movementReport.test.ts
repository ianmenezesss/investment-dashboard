import { describe, expect, it } from 'vitest'
import type { UnifiedMovement } from '../repositories/PrivateRepository'
import { aggregateIncomeReport, filterReportMovements, movementTotals, sharePercent } from './movementReport'

const make = (id: string, date: string, operation: UnifiedMovement['operation'], investment_class: UnifiedMovement['investment_class'], asset: string, financial_value: string | null, fees: string | null = null, cash_received: string | null = null): UnifiedMovement => ({ id, date, operation, investment_class, asset, financial_value, fees, cash_received, quantity: null, unit_price: null })

describe('filtered movement reports', () => {
  const rows = [
    make('a', '2026-01-01', 'BUY', 'AÇÕES', 'ITUB4', '100.00', '1.25'),
    make('b', '2026-01-03', 'SELL', 'AÇÕES', 'ITUB4', '80.00', '1.00'),
    make('c', '2026-01-05', 'APPLICATION', 'CDB', 'CDB DI', '200.00'),
    make('d', '2026-01-06', 'REDEMPTION', 'CDB', 'CDB DI', '50.00', null, '51.00'),
    make('e', '2026-01-07', 'CONTRIBUTION', 'FLUXO DE CAIXA', 'Carteira', '75.00'),
    make('f', '2026-01-08', 'DIVIDEND', 'PROVENTOS', 'ITUB4', '3.00'),
  ]
  it('filters by date, category and asset and sorts newest first', () => {
    expect(filterReportMovements(rows, '2026-01-02', '2026-01-08', 'PROVENTOS', 'itu').map(row => row.id)).toEqual(['f'])
  })
  it('separates purchases, disposals, external cash and income', () => {
    const totals = movementTotals(rows)
    expect(totals.purchases.toFixed(2)).toBe('301.25')
    expect(totals.disposals.toFixed(2)).toBe('130.00')
    expect(totals.external.toFixed(2)).toBe('75.00')
    expect(totals.income.toFixed(2)).toBe('3.00')
    expect(totals.transactionVolume.toFixed(2)).toBe('431.25')
    expect(totals.count).toBe(6)
  })
  it('calculates category percentages without dividing by zero', () => {
    expect(sharePercent('1', '3')).toBe('33.3')
    expect(sharePercent('0', '0')).toBe('0.0')
  })
  it('groups manually recorded dividends and JCP by month and asset without mixing them', () => {
    const income = aggregateIncomeReport([
      make('d1', '2026-01-08', 'DIVIDEND', 'PROVENTOS', 'ITUB4', '3.10'),
      make('j1', '2026-01-09', 'JCP', 'PROVENTOS', 'ITUB4', '1.50'),
      make('d2', '2026-02-08', 'DIVIDEND', 'PROVENTOS', 'BBAS3', '2.25'),
      make('buy', '2026-02-09', 'BUY', 'AÇÕES', 'ITUB4', '100'),
    ])
    expect(income.dividends.toFixed(2)).toBe('5.35')
    expect(income.jcp.toFixed(2)).toBe('1.50')
    expect(income.total.toFixed(2)).toBe('6.85')
    expect(income.count).toBe(3)
    expect(income.monthly.map(row => [row.key, row.dividends.toFixed(2), row.jcp.toFixed(2)])).toEqual([
      ['2026-01', '3.10', '1.50'], ['2026-02', '2.25', '0.00'],
    ])
    expect(income.byAsset.map(row => row.asset)).toEqual(['ITUB4', 'BBAS3'])
  })
})
