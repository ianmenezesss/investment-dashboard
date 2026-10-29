import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { IndividualEquityPriceHistory as HistoryData } from '../api'
import { IndividualEquityHistory, formatDailyPrice, isPriceHistoryContract, preparePriceChartData } from './IndividualEquityHistory'

let host: HTMLDivElement
let root: Root
let client: QueryClient
const data: HistoryData = {
  ticker: 'ITUB4', period: '1M', currency: 'BRL', source: 'provider-test-double', price_basis: 'raw_close',
  period_start: '2026-09-29', period_end: '2026-10-29', coverage_start: '2026-10-01', coverage_end: '2026-10-28',
  points: [{ date: '2026-10-28', close: '1234.5678' }, { date: '2026-10-01', close: '10.12000001' }],
  availability: 'available', reason: null,
}
const pause = () => new Promise(resolve => setTimeout(resolve, 30))
async function render(repository: { equityPriceHistory: (...args: any[]) => Promise<HistoryData> }, tickers = ['ITUB4', 'PETR4']) {
  await act(async () => root.render(<QueryClientProvider client={client}><IndividualEquityHistory repository={repository as never} identity="owner-a" tickers={tickers}/></QueryClientProvider>))
  await act(async () => { await pause() })
}
beforeEach(() => {
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
})
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove() })

test('selects a portfolio ticker, queries the selected period and displays localized exact prices', async () => {
  const repository = { equityPriceHistory: vi.fn(async (ticker: string, period: HistoryData['period']) => ({ ...data, ticker, period })) }
  await render(repository)
  expect(repository.equityPriceHistory).toHaveBeenCalledWith('ITUB4', '1M', expect.any(AbortSignal))
  expect(host.textContent).toContain('Histórico de preço por ação')
  expect(host.textContent).toContain('Fonte: provider-test-double')
  expect(host.textContent).toContain('fechamento sem ajustes')
  expect(host.textContent).toContain('01/10/2026')
  expect(formatDailyPrice('1234.5678')).toBe('R$\u00a01.234,5678')
  expect(preparePriceChartData(data.points).map(point => point.date)).toEqual(['2026-10-01', '2026-10-28'])
  expect(data.points[0].date).toBe('2026-10-28')

  await act(async () => {
    const select = host.querySelector<HTMLSelectElement>('[aria-label="Selecionar ativo para histórico"]')!
    select.value = 'PETR4'
    select.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await act(async () => { await pause() })
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent === 'Máximo')!.click())
  await act(async () => { await pause() })
  expect(repository.equityPriceHistory.mock.calls.map(call => call.slice(0, 2))).toContainEqual(['PETR4', 'MAX'])
  expect(host.querySelector('button[aria-pressed="true"]')?.textContent).toBe('Máximo')
})

test('shows loading, disabled, provider-unavailable, empty and transport-error states', async () => {
  let resolve!: (value: HistoryData) => void
  const pending = new Promise<HistoryData>(done => { resolve = done })
  await act(async () => root.render(<QueryClientProvider client={client}><IndividualEquityHistory repository={{ equityPriceHistory: () => pending } as never} identity="owner-a" tickers={['ITUB4']}/></QueryClientProvider>))
  expect(host.textContent).toContain('Carregando histórico de ITUB4')
  await act(async () => resolve({ ...data, availability: 'disabled', points: [], coverage_start: null, coverage_end: null, source: null, reason: 'feature_disabled' }))
  await act(async () => { await pause() })
  expect(host.textContent).toContain('O histórico individual está desativado')

  client.clear()
  await render({ equityPriceHistory: async () => ({ ...data, availability: 'unavailable', points: [], coverage_start: null, coverage_end: null, source: null, reason: 'provider_not_configured' }) }, ['ITUB4'])
  expect(host.textContent).toContain('fonte de dados e sua licença não forem validadas')

  client.clear()
  await render({ equityPriceHistory: async () => ({ ...data, availability: 'empty', points: [], coverage_start: null, coverage_end: null }) }, ['ITUB4'])
  expect(host.textContent).toContain('Sem preços para o período')

  client.clear()
  await render({ equityPriceHistory: async () => { throw new Error('API offline') } }, ['ITUB4'])
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('API offline')
  expect(host.textContent).toContain('Tentar novamente')
})

test('empty portfolio never queries provider history', async () => {
  const repository = { equityPriceHistory: vi.fn() }
  await render(repository, [])
  expect(host.textContent).toContain('Nenhuma ação em carteira')
  expect(repository.equityPriceHistory).not.toHaveBeenCalled()
})

test('malformed API payload renders a safe error state', async () => {
  await render({ equityPriceHistory: async () => [] as never }, ['ITUB4'])
  expect(isPriceHistoryContract([])).toBe(false)
  expect(isPriceHistoryContract({ ...data, points: [{ date: '2026-10-01', close: 'NaN' }] })).toBe(false)
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('Resposta de histórico inválida')
})
