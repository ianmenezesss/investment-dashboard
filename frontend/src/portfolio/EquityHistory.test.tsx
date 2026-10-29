import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { EquityHistory as EquityHistoryData } from '../api'
import { EquityHistory, equityHistoryTooltip, formatEquityMoney, prepareEquityChartData } from './EquityHistory'

let host: HTMLDivElement
let root: Root
let client: QueryClient
const response: EquityHistoryData = {
  period_start: '2025-01-01', period_end: '2025-03-01', coverage_start: '2025-01-02', coverage_end: '2025-03-01',
  coverage: 'partial', source: 'brapi', price_basis: 'raw_close',
  convention: 'Operações na data são refletidas no fechamento.', missing_tickers: ['PETR4'], provider_errors: {},
  points: [
    { date: '2025-02-27', market_value: '110.25', partial_market_value: '110.25', net_invested: '100.00', difference_over_net_flows: '10.25', coverage: 'complete', missing_tickers: [], held_positions: 1,
      holdings: [{ ticker: 'ITUB4', quantity: '2', price: '55.125', market_value: '110.25' }] },
    { date: '2025-03-01', market_value: null, partial_market_value: '80.00', net_invested: '120.00', difference_over_net_flows: null, coverage: 'partial', missing_tickers: ['PETR4'], held_positions: 2,
      holdings: [{ ticker: 'ITUB4', quantity: '2', price: '40', market_value: '80' }, { ticker: 'PETR4', quantity: '1', price: null, market_value: null }] },
  ],
}
const pause = () => new Promise(resolve => setTimeout(resolve, 25))
async function render(repository: { equityHistory: (...args: any[]) => Promise<EquityHistoryData> }) {
  await act(async () => root.render(<QueryClientProvider client={client}><EquityHistory repository={repository as never} identity="owner-a"/></QueryClientProvider>))
  await act(async () => { await pause() })
}
beforeEach(() => { host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host); client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }) })
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove() })

test('renders market value, net flow, dated difference, source, tooltip values and partial coverage', async () => {
  expect(prepareEquityChartData(response.points).map(point => [point.market_value_plot, point.net_invested_plot])).toEqual([[110.25, 100], [null, 120]])
  const repository = { equityHistory: vi.fn(async (_period: string, _signal?: AbortSignal) => response) }
  await render(repository)
  expect(host.textContent).toContain('Evolução histórica das ações')
  expect(host.textContent).toContain('estimativa externa')
  expect(host.textContent).toContain('confira os valores na corretora')
  expect(host.textContent).toContain('R$ 120,00')
  expect(host.textContent).toContain('R$ 10,25')
  expect(host.textContent).toContain('PETR4')
  expect(host.textContent).toContain('Cobertura parcial')
  expect(host.textContent).toContain('Fonte: brapi')
  expect(host.textContent).toContain('não é rentabilidade nem lucro realizado')
  expect(equityHistoryTooltip('110.25', 'market_value')).toEqual(['R$ 110,25', 'Valor de mercado das ações'])
  expect(equityHistoryTooltip(null, 'net_invested')).toEqual(['Indisponível', 'Fluxo líquido em ações'])
  expect(formatEquityMoney('1000000000000000000.23')).toBe('R$ 1.000.000.000.000.000.000,23')
  await act(async () => { host.querySelector<HTMLButtonElement>('button')!.click() })
  await act(async () => { await pause() })
  expect(repository.equityHistory.mock.calls.map(call => call[0])).toEqual(['Tudo', '1M'])
  expect(host.querySelector('button[aria-pressed="true"]')?.textContent).toBe('1M')
})

test('shows loading, error and empty/no-raw-price states', async () => {
  let finish!: (value: EquityHistoryData) => void
  const pending = new Promise<EquityHistoryData>(resolve => { finish = resolve })
  await act(async () => root.render(<QueryClientProvider client={client}><EquityHistory repository={{ equityHistory: () => pending } as never} identity="owner-a"/></QueryClientProvider>))
  expect(host.textContent).toContain('Carregando histórico')
  await act(async () => finish({ ...response, points: [], coverage: 'empty', provider_errors: {} }))
  await act(async () => { await pause() })
  expect(host.textContent).toContain('Sem operações de ações registradas')
  expect(host.textContent).toContain('Nenhuma cotação é consultada sem operações')
  expect(host.textContent).not.toContain('Não há preços históricos originais')
  client.clear()
  await render({ equityHistory: async () => { throw new Error('offline') } })
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('Não foi possível carregar')
  client.clear()
  await render({ equityHistory: async () => ({ ...response, points: [], coverage: 'unavailable', provider_errors: { ITUB4: 'raw_price_unavailable' } }) })
  expect(host.textContent).toContain('rawClose')
  client.clear()
  await render({ equityHistory: async () => ({ ...response, points: [], coverage: 'unavailable', provider_errors: { ITUB4: 'raw_history_not_available' } }) })
  expect(host.textContent).toContain('O acesso configurado não permite')
  expect(host.textContent).toContain('rawClose')
  client.clear()
  await render({ equityHistory: async () => ({ ...response, points: [], coverage: 'unavailable', provider_errors: { ITUB4: 'disabled' } }) })
  expect(host.textContent).toContain('A consulta ao histórico agregado de preços está desabilitada na configuração do backend')
})
