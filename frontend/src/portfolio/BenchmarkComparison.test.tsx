import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BenchmarkComparison } from './BenchmarkComparison'

let host: HTMLDivElement
let root: Root
let client: QueryClient
beforeEach(() => { host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host); client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }) })
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove(); vi.restoreAllMocks() })

describe('benchmark comparison display', () => {
  it('shows the shared monthly series and explains that it is not portfolio return', async () => {
    const repository = { benchmarks: vi.fn(async () => ({ period: '3M' as const, coverage_start: '2026-02-01', coverage_end: '2026-03-01', availability: 'available' as const, reason: null, source: 'BCB/SGS e brapi', bases: {}, points: [
      { month: '2026-02-01', values: { CDI: '100', IBOVESPA: '100', IPCA: '100' } },
      { month: '2026-03-01', values: { CDI: '101', IBOVESPA: '102', IPCA: '100.5' } },
    ] })) }
    await act(async () => root.render(<QueryClientProvider client={client}><BenchmarkComparison repository={repository as never} identity="owner"/></QueryClientProvider>))
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
    expect(host.textContent).toContain('não representa retorno da carteira')
    expect(host.textContent).toContain('Ibovespa: índice de preços, sem proventos')
    expect(repository.benchmarks).toHaveBeenCalledWith('3M', expect.any(AbortSignal))
  })

  it('explains when the free history feature is disabled', async () => {
    const repository = { benchmarks: vi.fn(async () => ({ period: '3M' as const, coverage_start: null, coverage_end: null, availability: 'disabled' as const, reason: 'feature_disabled' as const, source: 'BCB/SGS e brapi', bases: {}, points: [] })) }
    await act(async () => root.render(<QueryClientProvider client={client}><BenchmarkComparison repository={repository as never} identity="owner"/></QueryClientProvider>))
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
    expect(host.textContent).toContain('Histórico da Brapi desativado')
  })
})
