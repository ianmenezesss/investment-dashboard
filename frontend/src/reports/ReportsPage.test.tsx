import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ReportsPage } from './ReportsPage'

let host: HTMLDivElement
let root: Root
let client: QueryClient
beforeEach(() => { host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host); client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }) })
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove(); vi.restoreAllMocks() })

describe('reports PDF output', () => {
  it('prints the currently filtered report and shows its generation date', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    const repository = { movements: vi.fn(async () => []), composition: vi.fn(async () => ({
      as_of: '2026-10-30', equities: [], fixed_income: [], declared_positions: [], missing_fixed_income: [], market_values: null,
      coverage: 'available', missing_components: [], equity_basis: 'open_acquisition_cost', fixed_income_basis: 'effective_open_principal',
      declared_values_separate: true, class_totals: { equities_open_cost: '0', fixed_income_open_principal: '0', declared_positions: '0' },
    })) }
    await act(async () => root.render(<QueryClientProvider client={client}><ReportsPage repository={repository as never} identity="owner-1"/></QueryClientProvider>))
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
    expect(host.textContent).toContain('Gerado em')
    await act(async () => { host.querySelector<HTMLButtonElement>('.reports-print-button')!.click() })
    expect(print).toHaveBeenCalledOnce()
    expect(repository.movements).toHaveBeenCalledOnce()
    expect(repository.composition).toHaveBeenCalledOnce()
  })
})
