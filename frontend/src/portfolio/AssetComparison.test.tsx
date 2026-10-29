import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { EquityComparison } from '../api'
import { AssetComparison, isEquityComparisonContract, prepareComparisonChartData } from './AssetComparison'

let host: HTMLDivElement
let root: Root
let client: QueryClient
const data: EquityComparison = {
  tickers: ['BBAS3', 'ITUB4'], period: '1M', currency: 'BRL', source: 'provider-test-double', price_basis: 'raw_close',
  period_start: '2026-09-29', period_end: '2026-10-29', common_start_date: '2026-10-01',
  coverage: [
    { ticker: 'BBAS3', coverage_start: '2026-10-01', coverage_end: '2026-10-02', base_price: '20' },
    { ticker: 'ITUB4', coverage_start: '2026-10-01', coverage_end: '2026-10-03', base_price: '10' },
  ],
  points: [
    { date: '2026-10-01', values: { BBAS3: '100', ITUB4: '100' } },
    { date: '2026-10-02', values: { BBAS3: '110', ITUB4: null } },
    { date: '2026-10-03', values: { BBAS3: null, ITUB4: '120' } },
  ], availability: 'available', reason: null,
}
const pause = () => new Promise(resolve => setTimeout(resolve, 30))

async function render(repository: { equityComparison: (...args: any[]) => Promise<EquityComparison> }, tickers = ['ITUB4', 'BBAS3', 'VALE3']) {
  await act(async () => root.render(<QueryClientProvider client={client}>
    <AssetComparison repository={repository as never} identity="owner-a" tickers={tickers}/>
  </QueryClientProvider>))
  await act(async () => { await pause() })
}

beforeEach(() => {
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
})
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove() })

test('loads two selected assets and shows a responsive base-100 comparison with explicit gaps', async () => {
  const repository = { equityComparison: vi.fn(async () => data) }
  await render(repository)
  expect(repository.equityComparison).toHaveBeenCalledWith(['BBAS3', 'ITUB4'], '1M', expect.any(AbortSignal))
  expect(host.textContent).toContain('Comparar ativos')
  expect(host.textContent).toContain('Base comum: 01/10/2026')
  expect(host.textContent).toContain('Fonte: provider-test-double')
  expect(host.textContent).toContain('fechamento sem ajustes')
  const chartData = prepareComparisonChartData(data)
  expect(chartData[1]).toEqual({ date: '2026-10-02', BBAS3: 110, ITUB4: null })
  expect(data.points[1].values.ITUB4).toBeNull()

  await act(async () => {
    const period = [...host.querySelectorAll('button')].find(button => button.textContent === '1A')!
    period.click()
  })
  await act(async () => { await pause() })
  expect(repository.equityComparison).toHaveBeenCalledWith(['BBAS3', 'ITUB4'], '1A', expect.any(AbortSignal))

  await act(async () => {
    const vale = [...host.querySelectorAll('label')].find(label => label.textContent?.includes('VALE3'))!.querySelector('input')!
    vale.click()
  })
  await act(async () => { await pause() })
  expect(repository.equityComparison).toHaveBeenCalledWith(['BBAS3', 'ITUB4', 'VALE3'], '1A', expect.any(AbortSignal))
})

test('renders feature-disabled and no-common-date states without any chart values', async () => {
  await render({ equityComparison: async () => ({ ...data, currency: null, source: null, price_basis: null,
    common_start_date: null, coverage: [], points: [], availability: 'disabled', reason: 'feature_disabled' }) })
  expect(host.textContent).toContain('Nenhuma fonte externa foi habilitada')
  expect(host.querySelector('.recharts-wrapper')).toBeNull()

  client.clear()
  await render({ equityComparison: async () => ({ ...data, currency: null, source: null, price_basis: null,
    common_start_date: null, coverage: [], points: [], availability: 'empty', reason: 'no_common_date' }) })
  expect(host.textContent).toContain('Não há uma data com fechamento válido')
  expect(host.querySelector('.recharts-wrapper')).toBeNull()
})

test('shows loading, transport-error and malformed-contract states', async () => {
  let reject!: (cause: Error) => void
  const pending = new Promise<EquityComparison>((_resolve, fail) => { reject = fail })
  await act(async () => root.render(<QueryClientProvider client={client}>
    <AssetComparison repository={{ equityComparison: () => pending } as never} identity="owner-a" tickers={['BBAS3', 'ITUB4']}/>
  </QueryClientProvider>))
  expect(host.textContent).toContain('Carregando comparação')
  await act(async () => reject(new Error('API offline')))
  await act(async () => { await pause() })
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('API offline')

  client.clear()
  await render({ equityComparison: async () => [] as never })
  expect(isEquityComparisonContract([])).toBe(false)
  expect(host.textContent).toContain('Resposta de comparação inválida')
  expect(host.querySelector('.recharts-wrapper')).toBeNull()
})

test('does not request comparison until two assets are selected', async () => {
  const repository = { equityComparison: vi.fn() }
  await render(repository, ['ITUB4'])
  expect(host.textContent).toContain('Selecione pelo menos duas ações')
  expect(repository.equityComparison).not.toHaveBeenCalled()
})

test('selection cannot exceed four assets', async () => {
  const repository = { equityComparison: vi.fn((_tickers: string[]) => new Promise<EquityComparison>(() => {})) }
  await render(repository, ['BBAS3', 'ITUB4', 'VALE3', 'B3SA3', 'PETR4'])
  const labels = [...host.querySelectorAll('label')]
  for (const ticker of ['ITUB4', 'VALE3']) {
    const checkbox = labels.find(label => label.textContent?.includes(ticker))!.querySelector('input')!
    await act(async () => checkbox.click())
  }
  expect(repository.equityComparison.mock.calls.some(call => call[0].length === 4)).toBe(true)
  expect(labels.find(label => label.textContent?.includes('PETR4'))!.querySelector('input')!.disabled).toBe(true)
})
