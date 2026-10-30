import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { FinancialEventEntry } from './FinancialEventEntry'

let host: HTMLDivElement, root: Root, client: QueryClient
const pause = () => new Promise(resolve => setTimeout(resolve, 0))

beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  client = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { retry: false, gcTime: 0 } } })
  vi.stubGlobal('crypto', { randomUUID: () => '9a5d3a0d-f918-4b42-bc1a-8271e65b1514' })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  host.remove()
  vi.unstubAllGlobals()
})

test('records explicit gross cash income and source using an idempotency key', async () => {
  const createFinancialEvent = vi.fn(async () => ({ id: 12 }))
  await act(async () => root.render(<QueryClientProvider client={client}><FinancialEventEntry repository={{ createFinancialEvent }}/></QueryClientProvider>))
  const details = host.querySelector('details')!
  details.open = true
  const set = (name: string, value: string) => {
    const input = host.querySelector(`[name="${name}"]`) as HTMLInputElement
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
    input.dispatchEvent(new Event('change', { bubbles: true }))
  }
  await act(async () => {
    const select = host.querySelector('[aria-label="Tipo de registro financeiro"]') as HTMLSelectElement
    select.value = 'DIVIDEND'
    select.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await act(async () => {
    set('event_date', '2025-01-05')
    set('ticker', 'itub4')
    set('cash_amount', '7.10')
    set('gross_amount', '8.00')
    set('tax_withheld', '0.90')
    set('source', 'Informe consultado')
    host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await pause()
  })
  expect(createFinancialEvent).toHaveBeenCalledWith({
    kind: 'DIVIDEND', event_date: '2025-01-05', ticker: 'ITUB4', cash_amount: '7.10',
    gross_amount: '8.00', tax_withheld: '0.90', source: 'Informe consultado', description: null,
  }, '9a5d3a0d-f918-4b42-bc1a-8271e65b1514')
  expect(host.textContent).toContain('Registro incluído no histórico')
})

test('does not send an event if secure idempotency generation is unavailable', async () => {
  vi.stubGlobal('crypto', {})
  const createFinancialEvent = vi.fn()
  await act(async () => root.render(<QueryClientProvider client={client}><FinancialEventEntry repository={{ createFinancialEvent }}/></QueryClientProvider>))
  host.querySelector('details')!.open = true
  await act(async () => {
    host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await pause()
  })
  expect(createFinancialEvent).not.toHaveBeenCalled()
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('geração segura')
})

test('reuses the idempotency key when retrying the same event after a network error', async () => {
  const createFinancialEvent = vi.fn().mockRejectedValueOnce(new Error('Conexão interrompida')).mockResolvedValueOnce({ id: 13 })
  await act(async () => root.render(<QueryClientProvider client={client}><FinancialEventEntry repository={{ createFinancialEvent }}/></QueryClientProvider>))
  const set = (name: string, value: string) => {
    const input = host.querySelector(`[name="${name}"]`) as HTMLInputElement
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
    input.dispatchEvent(new Event('change', { bubbles: true }))
  }
  await act(async () => {
    set('event_date', '2025-01-05')
    set('cash_amount', '100.00')
    set('source', 'Extrato consultado')
    host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await pause()
  })
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('Conexão interrompida')
  await act(async () => {
    host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await pause()
  })
  expect(createFinancialEvent).toHaveBeenCalledTimes(2)
  expect(createFinancialEvent.mock.calls[0][1]).toBe(createFinancialEvent.mock.calls[1][1])
})
