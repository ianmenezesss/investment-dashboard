import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ObservedHistory, type ObservedSeries } from './ObservedHistory'

let host: HTMLDivElement
let root: Root
let client: QueryClient
const points: ObservedSeries = {
  coverage: 'observed_points_only', warning: 'Pontos observados',
  points: [
    { as_of: '2026-01-10', gross_value: '1000.00', net_value: '980.00', source: 'Extrato fictício A' },
    { as_of: '2026-02-10', gross_value: '1100.00', net_value: '1078.00', source: 'Extrato fictício B' },
  ],
}

async function render(load: (id: number, start: string, end: string, signal: AbortSignal) => Promise<ObservedSeries>) {
  await act(async () => root.render(<QueryClientProvider client={client}><ObservedHistory id={7} identity="owner-a" load={load}/></QueryClientProvider>))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 25)) })
}

beforeEach(() => {
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
})
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove() })

test('renders observed values, sources and chart points', async () => {
  const load = vi.fn(async (_id: number, _start: string, _end: string, _signal: AbortSignal) => points)
  await render(load)
  expect(await host.querySelector('details')?.textContent).toContain('Extrato fictício A')
  expect(host.textContent).toContain('R$ 1.000,00')
  expect(host.querySelector('.recharts-responsive-container')).toBeTruthy()
  const details = host.querySelector('details')!
  expect(details.querySelectorAll('li')).toHaveLength(2)
  expect(details.textContent).toContain('2026-02-10')
  expect(load).toHaveBeenCalledWith(7, expect.any(String), expect.any(String), expect.any(AbortSignal))
})

test('shows loading, error and empty states', async () => {
  let finish!: (value: ObservedSeries) => void
  const pending = new Promise<ObservedSeries>(resolve => { finish = resolve })
  await render(() => pending)
  expect(host.querySelector('[role="status"]')?.textContent).toContain('Carregando')
  await act(async () => finish({ ...points, points: [] }))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 25)) })
  expect(await host.textContent).toContain('Histórico patrimonial indisponível')

  client.clear()
  await act(async () => root.render(<QueryClientProvider client={client}><ObservedHistory id={7} identity="owner-b" load={async () => { throw new Error('offline') }}/></QueryClientProvider>))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 25)) })
  expect(await host.querySelector('[role="alert"]')?.textContent).toContain('Não foi possível carregar')
})

test('reports a malformed response as an error instead of dereferencing a missing points array', async () => {
  await render(async () => ({ coverage: 'unavailable', warning: 'bad mock payload' } as unknown as ObservedSeries))
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('Não foi possível carregar as posições')
  expect(host.textContent).not.toContain('Nenhuma posição observada neste período')
})

test('changes the requested dates when a temporal filter is selected', async () => {
  const load = vi.fn(async (_id: number, _start: string, _end: string, _signal: AbortSignal) => points)
  await render(load)
  await act(async () => { [...host.querySelectorAll('button')].find(button => button.textContent === '1M')!.click() })
  expect(load).toHaveBeenCalledTimes(2)
  const [, start1, end1] = load.mock.calls[0]
  const [, start2, end2] = load.mock.calls[1]
  expect(end2).toBe(end1)
  expect(new Date(start2).getTime()).toBeGreaterThan(new Date(start1).getTime())
  expect(host.querySelector('button[aria-pressed="true"]')?.textContent).toBe('1M')
})


