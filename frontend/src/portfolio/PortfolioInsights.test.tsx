import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { PortfolioInsights, type CapitalFlows, type Composition } from './PortfolioInsights'
import { formatFlowAxisTick } from './format'

let host: HTMLDivElement
let root: Root
let client: QueryClient
const flow: CapitalFlows = { period_start: '2025-01-01', period_end: '2025-03-01', coverage_start: '2025-01-01', coverage_end: '2025-03-01', coverage: 'available',
  points: [{ date: '2025-02-01', contributions: '100.00', redemptions: '10.00', sales: '10.00', net_accumulated: '80.00' }], gross_contributions: '100.00', redemptions: '10.00', sales: '10.00', withdrawals: '20.00', net_accumulated: '80.00', market_value: null, return: null }
const composition: Composition = { as_of: '2025-03-01', equities: [{ asset: 'ABCD3', value: '40.00', basis: 'open_acquisition_cost' }], fixed_income: [{ asset: 'CDB fictício', value: '50.00', basis: 'effective_open_principal' }], declared_positions: [], missing_fixed_income: ['CDB sem posição'], market_values: null, coverage: 'partial', missing_components: ['cotações de mercado para ações', 'posições sem lote nem observação'], equity_basis: 'open_acquisition_cost', fixed_income_basis: 'effective_open_principal', declared_values_separate: true, class_totals: { equities_open_cost: '40.00', fixed_income_open_principal: '50.00', declared_positions: '0.00' } }
const pause = () => new Promise(resolve => setTimeout(resolve, 25))
async function render(repository: { capitalFlows: (...args: any[]) => Promise<CapitalFlows>; composition: (...args: any[]) => Promise<Composition> }) {
  await act(async () => root.render(<QueryClientProvider client={client}><PortfolioInsights repository={repository as never} identity="owner-a"/></QueryClientProvider>))
  await act(async () => { await pause() })
}
beforeEach(() => { host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host); client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }) })
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove() })

test('renders separated flows, open acquisition cost, effective principal and coverage notes', async () => {
  const repository = { capitalFlows: vi.fn(async (_period: string, _signal?: AbortSignal) => flow), composition: vi.fn(async (_signal?: AbortSignal) => composition) }
  await render(repository)
  expect(host.textContent).toContain('Aportes e compras no período')
  expect(host.textContent).toContain('Resgates de principal CDB no período')
  expect(host.textContent).toContain('Vendas de ações no período')
  expect(host.textContent).toContain('Fluxo líquido acumulado')
  const normalizedText = host.textContent?.replace(/[\s\u00a0]/g, '') ?? ''
  expect(normalizedText).toContain('R$100,00')
  expect(normalizedText.match(/R\$10,00/g)).toHaveLength(2)
  expect(normalizedText).toContain('R$80,00')
  expect(host.textContent).toContain('ABCD3')
  expect(host.textContent).toContain('CDB fictício')
  expect(host.textContent).toContain('Dados ausentes')
  expect(host.textContent).toContain('não representa patrimônio nem rentabilidade')
})

test('shows loading, error and empty states', async () => {
  let finish!: (value: CapitalFlows) => void
  const pending = new Promise<CapitalFlows>(resolve => { finish = resolve })
  const repository = { capitalFlows: () => pending, composition: async () => composition }
  await act(async () => root.render(<QueryClientProvider client={client}><PortfolioInsights repository={repository as never} identity="owner-a"/></QueryClientProvider>))
  expect(host.textContent).toContain('Carregando fluxos')
  await act(async () => finish({ ...flow, points: [] }))
  await act(async () => { await pause() })
  expect(host.textContent).toContain('Sem fluxos no período')
  client.clear()
  await act(async () => root.render(<QueryClientProvider client={client}><PortfolioInsights repository={{ capitalFlows: async () => { throw new Error('offline') }, composition: async () => { throw new Error('offline') }} as never} identity="owner-b"/></QueryClientProvider>))
  await act(async () => { await pause() })
  expect(host.querySelectorAll('[role="alert"]').length).toBe(2)
})

test('requests fresh filtered flows and marks selected temporal period', async () => {
  const repository = { capitalFlows: vi.fn(async (_period: string, _signal?: AbortSignal) => flow), composition: vi.fn(async (_signal?: AbortSignal) => composition) }
  await render(repository)
  await act(async () => { [...host.querySelectorAll('button')].find(button => button.textContent === '1M')!.click() })
  await act(async () => { await pause() })
  expect(repository.capitalFlows).toHaveBeenCalledTimes(2)
  expect(repository.capitalFlows.mock.calls.map(call => call[0])).toEqual(['Tudo', '1M'])
  expect(host.querySelector('button[aria-pressed="true"]')?.textContent).toBe('1M')
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
