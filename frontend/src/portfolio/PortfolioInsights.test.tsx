import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { PortfolioInsights, type CapitalFlows, type Composition } from './PortfolioInsights'
import type { FinancialPerformance } from '../api'
import { formatFlowAxisTick } from './format'

let host: HTMLDivElement
let root: Root
let client: QueryClient
const flow: CapitalFlows = { period_start: '2025-01-01', period_end: '2025-03-01', coverage_start: '2025-01-01', coverage_end: '2025-03-01', coverage: 'available',
  points: [{ date: '2025-02-01', contributions: '100.00', redemptions: '10.00', sales: '10.00', cumulative_contributions: '100.00', cumulative_withdrawals: '20.00', net_accumulated: '80.00' }], gross_contributions: '100.00', equity_purchases: '100.00', cdb_applications: '0.00', redemptions: '10.00', cdb_redemptions: '10.00', sales: '10.00', equity_sale_proceeds: '10.00', cumulative_contributions: '100.00', cumulative_withdrawals: '20.00', withdrawals: '20.00', net_accumulated: '80.00', market_value: null, return: null }
const composition: Composition = { as_of: '2025-03-01', equities: [{ asset: 'ABCD3', value: '40.00', basis: 'open_acquisition_cost' }], fixed_income: [{ asset: 'CDB fictício', value: '50.00', basis: 'effective_open_principal' }], declared_positions: [], missing_fixed_income: ['CDB sem posição'], market_values: null, coverage: 'partial', missing_components: ['cotações de mercado para ações', 'posições sem lote nem observação'], equity_basis: 'open_acquisition_cost', fixed_income_basis: 'effective_open_principal', declared_values_separate: true, class_totals: { equities_open_cost: '40.00', fixed_income_open_principal: '50.00', declared_positions: '0.00' } }
const performance: FinancialPerformance = {
  as_of: '2025-03-01', ledger_as_of: '2025-03-01T12:00:00Z', currency: 'BRL',
  flows: { coverage_start: '2025-01-01', coverage_end: '2025-03-01', coverage: 'available', equity_purchases_with_fees: '100.00', cdb_applications_principal: '0.00', equity_sales_after_fees: '10.00', cdb_principal_redemptions: '10.00', recorded_contributions: '100.00', recorded_withdrawals: '20.00', net_recorded_flow: '80.00' },
  capital: { equities_open_cost: '40.00', fixed_income_open_principal: '50.00', open_positions_accounted: '90.00', equity_open_share_percent: '44.4', fixed_income_open_share_percent: '55.6', basis: 'equity_open_acquisition_cost_plus_effective_cdb_principal' },
  equities: { ledger_as_of: '2025-03-01T12:00:00Z', acquisition_cost: '40.00', total_purchases: '100.00', sale_proceeds: '10.00', realized_profit: '5.00', market_value: '50.00', holdings: [], valuation: { status: 'complete', calculated_at: '2025-03-01T12:00:00Z', is_complete: true, open_cost: '40.00', unrealized_profit: '10.00', return_percent: '25.00', partial_market_value: '50.00', covered_cost: '40.00', covered_positions: 1, total_positions: 1, missing_tickers: [], quoted_at_min: null, quoted_at_max: null }, combined_result_before_tax: '15.00', combined_result_status: 'complete', partial_unrealized_result_estimate: '10.00', result_scope: 'realized_plus_open_unrealized_before_tax' },
  fixed_income: { effective_open_principal: '50.00', declared_positions: [], missing_positions: ['CDB sem posição'], returns_scope: 'per_contract_only' },
  composition,
  portfolio: { consolidated_market_value_estimate: null, return_percent: null, status: 'not_comparable' },
}
const pause = () => new Promise(resolve => setTimeout(resolve, 25))
async function render(repository: { capitalFlows: (...args: any[]) => Promise<CapitalFlows>; performance: (...args: any[]) => Promise<FinancialPerformance> }) {
  await act(async () => root.render(<QueryClientProvider client={client}><PortfolioInsights repository={repository as never} identity="owner-a"/></QueryClientProvider>))
  await act(async () => { await pause() })
}
beforeEach(() => { host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host); client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }) })
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove() })

test('renders historical flows, period breakdown, open acquisition cost and effective principal', async () => {
  const repository = { capitalFlows: vi.fn(async (_period: string, _signal?: AbortSignal) => flow), performance: vi.fn(async (_signal?: AbortSignal) => performance) }
  await render(repository)
  expect(host.textContent).toContain('Resultado acumulado em ações')
  expect(host.textContent).toContain('R$\u00a015,00')
  expect(host.textContent).toContain('Compras de ações + aplicações acumuladas')
  expect(host.textContent).toContain('Vendas após taxas + resgates de principal')
  expect(host.textContent).toContain('Compras de ações no período · inclui taxas')
  expect(host.textContent).toContain('Resgates CDB · principal')
  expect(host.textContent).toContain('Capital aplicado contabilizado em posições abertas')
  expect(host.textContent).toContain('Ações · custo aberto com taxas')
  const normalizedText = host.textContent?.replace(/[\s\u00a0]/g, '') ?? ''
  expect(normalizedText).toContain('R$100,00')
  expect(normalizedText.match(/R\$10,00/g)).toHaveLength(2)
  expect(normalizedText).toContain('R$80,00')
  expect(normalizedText).toContain('R$90,00')
  expect(host.textContent).toContain('ABCD3')
  expect(host.textContent).toContain('CDB fictício')
  expect(host.textContent).toContain('Dados ausentes')
  expect(host.textContent).toContain('não representa patrimônio nem rentabilidade')
  expect(host.textContent).toContain('não é lucro ou rentabilidade')
})

test('preserves all-time totals when period filter changes and formats large decimals exactly', async () => {
  const repository = { capitalFlows: vi.fn(async (period: string, _signal?: AbortSignal) => ({ ...flow,
    gross_contributions: period === 'Tudo' ? '1234567890.125' : '12.345',
    cumulative_contributions: period === 'Tudo' ? '1234567890.125' : '12.345',
    net_accumulated: period === 'Tudo' ? '1234567890.125' : '12.345',
    points: [{ ...flow.points[0], cumulative_contributions: '1234567890.125' }],
  })), performance: vi.fn(async (_signal?: AbortSignal) => ({ ...performance, flows: { ...performance.flows,
    recorded_contributions: '1234567890.125', recorded_withdrawals: '0', net_recorded_flow: '1234567890.125' } })) }
  await render(repository)
  await act(async () => { [...host.querySelectorAll('button')].find(button => button.textContent === '1M')!.click() })
  await act(async () => { await pause() })
  expect(host.textContent).toContain('R$\u00a01.234.567.890,13')
  expect(repository.capitalFlows.mock.calls.map(call => call[0])).toEqual(['Tudo', '1M'])
})

test('shows loading, error and empty states', async () => {
  let finish!: (value: CapitalFlows) => void
  const pending = new Promise<CapitalFlows>(resolve => { finish = resolve })
  const repository = { capitalFlows: () => pending, performance: async () => performance }
  await act(async () => root.render(<QueryClientProvider client={client}><PortfolioInsights repository={repository as never} identity="owner-a"/></QueryClientProvider>))
  expect(host.textContent).toContain('Carregando fluxos')
  await act(async () => finish({ ...flow, points: [] }))
  await act(async () => { await pause() })
  expect(host.textContent).toContain('Sem fluxos no período')
  client.clear()
  await act(async () => root.render(<QueryClientProvider client={client}><PortfolioInsights repository={{ capitalFlows: async () => { throw new Error('offline') }, performance: async () => { throw new Error('offline') }} as never} identity="owner-b"/></QueryClientProvider>))
  await act(async () => { await pause() })
  expect(host.querySelectorAll('[role="alert"]').length).toBe(4)
})

test('does not present a combined equity result when quote coverage is partial', async () => {
  const partial = { ...performance, equities: { ...performance.equities, combined_result_before_tax: null,
    combined_result_status: 'partial' as const, market_value: null,
    valuation: { ...performance.equities.valuation, status: 'partial' as const,
      is_complete: false, missing_tickers: ['BBAS3'] } } }
  await render({ capitalFlows: async () => flow, performance: async () => partial })
  expect(host.textContent).toContain('Resultado combinado indisponível')
  expect(host.textContent).toContain('BBAS3')
  expect(host.textContent).not.toContain('R$\u00a015,00')
})

test('labels a covered combined result that includes stale market quotes as an estimate', async () => {
  const stale = { ...performance, equities: { ...performance.equities,
    combined_result_status: 'stale' as const,
    valuation: { ...performance.equities.valuation, status: 'stale' as const,
      quoted_at_max: '2025-03-01T12:00:00Z' } } }
  await render({ capitalFlows: async () => flow, performance: async () => stale })
  expect(host.textContent).toContain('R$\u00a015,00')
  expect(host.textContent).toContain('A estimativa inclui cotações desatualizadas')
  expect(host.textContent).toContain('Confira os valores atuais diretamente na corretora')
})

test('requests fresh filtered flows and marks selected temporal period', async () => {
  const repository = { capitalFlows: vi.fn(async (_period: string, _signal?: AbortSignal) => flow), performance: vi.fn(async (_signal?: AbortSignal) => performance) }
  await render(repository)
  await act(async () => { [...host.querySelectorAll('button')].find(button => button.textContent === '1M')!.click() })
  await act(async () => { await pause() })
  expect(repository.capitalFlows).toHaveBeenCalledTimes(2)
  expect(repository.capitalFlows.mock.calls.map(call => call[0])).toEqual(['Tudo', '1M'])
  expect(host.querySelector('button[aria-pressed="true"]')?.textContent).toBe('1M')
})

test('separates external cash flows from received dividends and JCP', async () => {
  const repository = {
    capitalFlows: async () => flow,
    performance: async () => performance,
    financialEventSummary: vi.fn(async () => ({ period_start: null, period_end: '2025-03-01', coverage: 'available' as const,
      contributions: '100.00', withdrawals: '25.00', net_external_cash_flow: '75.00', dividends_received: '8.00',
      jcp_received: '2.50', income_total_received: '10.50', event_count: 4 })),
  }
  await render(repository)
  expect(repository.financialEventSummary).toHaveBeenCalledWith('Tudo', expect.anything())
  expect(host.textContent).toContain('Caixa externo e proventos registrados')
  expect(host.textContent).toContain('Aportes externos')
  expect(host.textContent).toContain('Retiradas externas')
  expect(host.textContent).toContain('Fluxo líquido externo')
  expect(host.textContent).toContain('Dividendos recebidos informados')
  expect(host.textContent).toContain('Proventos são separados de aportes')
  expect((host.textContent ?? '').replace(/\u00a0/g, ' ')).toContain('R$ 75,00')
  expect((host.textContent ?? '').replace(/\u00a0/g, ' ')).toContain('R$ 8,00')
})

test('formats small flow ticks in BRL and keeps compact tick labels distinct', () => {
  const normalize = (value: string) => value.replace(/\u00a0/g, ' ')
  expect(normalize(formatFlowAxisTick(50))).toBe('R$ 50')
  expect(normalize(formatFlowAxisTick(100))).toBe('R$ 100')
  expect(normalize(formatFlowAxisTick(200))).toBe('R$ 200')
  expect(normalize(formatFlowAxisTick(1000))).toBe('R$ 1 mil')
  const compact = [1000, 1001, 2000, 2001].map(formatFlowAxisTick)
  expect(new Set(compact).size).toBe(compact.length)
})
