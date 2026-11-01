import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { WealthEvolution } from './WealthEvolution'

let host: HTMLDivElement
let root: Root
let client: QueryClient
beforeEach(() => {
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  vi.stubGlobal('crypto', { randomUUID: () => '9a5d3a0d-f918-4b42-bc1a-8271e65b1514' })
})
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove(); vi.unstubAllGlobals() })

const observation = {
  id: 1, as_of: '2026-10-30', equities_market_value: '250.00', equities_source: 'Extrato da corretora',
  fixed_income_gross_value: null, fixed_income_net_value: null, fixed_income_coverage: 'partial' as const,
  fixed_income_sources: [], missing_fixed_income: ['CDB teste'], consolidated_gross_value: null,
  consolidated_net_value: null, consolidated_coverage: 'partial' as const, created_at: '2026-10-30T12:00:00Z',
}

describe('wealth evolution observations', () => {
  it('explains empty history and records a sourced observation through the private repository', async () => {
    const rows: typeof observation[] = []
    const repository = {
      wealthObservations: vi.fn(async () => rows),
      createWealthObservation: vi.fn(async (input: { as_of: string; equities_market_value: string; equities_source: string }) => {
        rows.push({ ...observation, ...input, id: 1 }); return observation
      }),
    }
    await act(async () => root.render(<QueryClientProvider client={client}><WealthEvolution repository={repository as never} identity="private-user"/></QueryClientProvider>))
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
    expect(host.textContent).toContain('Sem observações patrimoniais ainda')
    const value = host.querySelector<HTMLInputElement>('input[type="number"]')!
    const source = host.querySelector<HTMLInputElement>('input[maxlength="240"]')!
    await act(async () => {
      const setValue = (input: HTMLInputElement, next: string) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, next)
        input.dispatchEvent(new Event('input', { bubbles: true }))
        input.dispatchEvent(new Event('change', { bubbles: true }))
      }
      setValue(value, '1234.56')
      setValue(source, 'Extrato da corretora')
    })
    const form = host.querySelector('form')!
    await act(async () => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
    expect(repository.createWealthObservation).toHaveBeenCalledWith(expect.objectContaining({ equities_market_value: '1234.56', equities_source: 'Extrato da corretora' }), '9a5d3a0d-f918-4b42-bc1a-8271e65b1514')
  })

  it('labels partial CDB coverage and never renders an invented consolidated total', async () => {
    const repository = { wealthObservations: vi.fn(async () => [observation]) }
    await act(async () => root.render(<QueryClientProvider client={client}><WealthEvolution repository={repository as never} identity="owner"/></QueryClientProvider>))
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
    expect(host.textContent).toContain('CDB teste')
    expect(host.textContent).toContain('Total líquido')
    expect(host.textContent).toContain('Indisponível')
    expect(host.querySelector('table tbody tr')).not.toBeNull()
  })
})
