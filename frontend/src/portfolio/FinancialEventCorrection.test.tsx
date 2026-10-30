import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { FinancialEventCorrection } from './FinancialEventCorrection'
import type { UnifiedMovement } from '../repositories/PrivateRepository'

let host: HTMLDivElement, root: Root, client: QueryClient
const row: UnifiedMovement = {
  id: 'event:14', date: '2025-01-05', investment_class: 'PROVENTOS', asset: 'ITUB4', operation: 'DIVIDEND',
  quantity: null, unit_price: null, financial_value: '7.10000000', fees: null, cash_received: null,
  gross_amount: '8.00000000', tax_withheld: '0.90000000', source: 'Informe consultado', revision: 2,
}
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

async function render(reviseFinancialEvent = vi.fn(async (..._args: unknown[]) => ({}))) {
  const financialEventRevisions = vi.fn(async () => [])
  await act(async () => root.render(<QueryClientProvider client={client}><FinancialEventCorrection
    repository={{ reviseFinancialEvent, financialEventRevisions }} identity="owner-a" row={row} eventId={14}/></QueryClientProvider>))
  const details = host.querySelector('details')!
  await act(async () => { details.open = true; await pause() })
  return { reviseFinancialEvent, financialEventRevisions }
}

function setValue(selector: string, value: string) {
  const input = host.querySelector(selector) as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
  const prototype = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : input instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype
  Object.getOwnPropertyDescriptor(prototype, 'value')?.set?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

test('loads the audit trail and submits a replacement with the expected revision', async () => {
  const { reviseFinancialEvent, financialEventRevisions } = await render()
  expect(financialEventRevisions).toHaveBeenCalledWith(14, expect.any(AbortSignal))
  await act(async () => {
    setValue('[aria-label="Tipo corrigido ITUB4"]', 'JCP')
    setValue('[name="event_date"]', '2025-01-06')
    setValue('[name="cash_amount"]', '6.25')
    setValue('[name="gross_amount"]', '7.00')
    setValue('[name="tax_withheld"]', '0.75')
    setValue('[name="source"]', 'Novo informe')
    setValue('form textarea', 'Valor conferido no documento')
    host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await pause()
  })
  expect(reviseFinancialEvent).toHaveBeenCalledWith(14, {
    kind: 'REPLACE', expected_revision: 2, reason: 'Valor conferido no documento',
    replacement: { kind: 'JCP', event_date: '2025-01-06', ticker: 'ITUB4', cash_amount: '6.25', gross_amount: '7.00', tax_withheld: '0.75', source: 'Novo informe', description: null },
  }, '9a5d3a0d-f918-4b42-bc1a-8271e65b1514')
})

test('requires a second explicit action before voiding an event', async () => {
  const { reviseFinancialEvent } = await render()
  await act(async () => { setValue('form textarea', 'Registro duplicado'); await pause() })
  await act(async () => { (host.querySelector('button[type="button"].secondary') as HTMLButtonElement).click(); await pause() })
  expect(reviseFinancialEvent).not.toHaveBeenCalled()
  expect(host.querySelector('[aria-label="Confirmação da anulação"]')?.textContent).toContain('A anulação é permanente')
  await act(async () => { [...host.querySelectorAll('button')].find(button => button.textContent?.includes('Confirmar anulação'))!.click(); await pause() })
  expect(reviseFinancialEvent).toHaveBeenCalledWith(14, { kind: 'VOID', expected_revision: 2, reason: 'Registro duplicado' }, '9a5d3a0d-f918-4b42-bc1a-8271e65b1514')
})

test('reuses the idempotency key when retrying the same revision after a network error', async () => {
  const revise = vi.fn(async (..._args: unknown[]) => ({ revision: 3 }))
    .mockRejectedValueOnce(new Error('Conexão interrompida')).mockResolvedValueOnce({ revision: 3 })
  const { reviseFinancialEvent } = await render(revise)
  await act(async () => {
    setValue('form textarea', 'Correção confirmada')
    host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await pause()
  })
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('Conexão interrompida')
  await act(async () => {
    host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await pause()
  })
  expect(reviseFinancialEvent).toHaveBeenCalledTimes(2)
  expect(reviseFinancialEvent.mock.calls[0][2]).toBe(reviseFinancialEvent.mock.calls[1][2])
})
