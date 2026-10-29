import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { MovementHistory } from './MovementHistory'
import type { UnifiedMovement } from '../repositories/PrivateRepository'

let host: HTMLDivElement, root: Root, client: QueryClient
const movements: UnifiedMovement[] = [
  { id: 'equity:1', date: '2025-01-02', investment_class: 'AÇÕES', asset: 'ITUB4', operation: 'BUY', quantity: '2', unit_price: '10.25', financial_value: '20.50', fees: '0.50', cash_received: null },
  { id: 'cdb:1', date: '2025-01-03', investment_class: 'CDB', asset: 'CDB Banco A', operation: 'APPLICATION', quantity: null, unit_price: null, financial_value: '125.25', fees: null, cash_received: null },
  { id: 'equity:2', date: '2025-01-03', investment_class: 'AÇÕES', asset: 'VALE3', operation: 'BUY', quantity: '1', unit_price: '30', financial_value: '30', fees: '0', cash_received: null },
  { id: 'cdb:2', date: '2025-01-04', investment_class: 'CDB', asset: 'CDB Banco A', operation: 'REDEMPTION', quantity: null, unit_price: null, financial_value: '20.00', fees: null, cash_received: '20.75' },
]
const pause = () => new Promise(resolve => setTimeout(resolve, 25))
async function render(repository: { movements: () => Promise<UnifiedMovement[]> }) {
  await act(async () => root.render(<QueryClientProvider client={client}><MovementHistory repository={repository as never} identity="owner-a"/></QueryClientProvider>))
  await act(async () => { await pause() })
}
beforeEach(() => { host = document.createElement('div'); document.body.append(host); root = createRoot(host); client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }) })
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove() })

test('renders unified chronologically filtered history and BR formatting without manufacturing CDB fields', async () => {
  await render({ movements: async () => movements })
  expect(movements.map(row => row.id)).toEqual(['equity:1', 'cdb:1', 'equity:2', 'cdb:2'])
  const rendered = (host.textContent ?? '').replace(/\u00a0/g, ' ')
  expect(rendered).toContain('R$ 20,50')
  expect(rendered).toContain('R$ 0,50')
  expect(host.textContent).toContain('CDB Banco A')
  expect(rendered).toContain('R$ 20,75')
  expect(host.textContent).toContain('Aplicação')
  expect(host.textContent).toContain('Resgate')
  expect(host.textContent).toContain('02/01/2025')
  const rows = [...host.querySelectorAll('tbody tr')]
  expect(rows.map(row => row.textContent?.includes('Resgate'))).toEqual([true, false, false, false])
  expect(rows[1].textContent).toContain('VALE3')
  expect(rows[2].textContent).toContain('CDB Banco A')
  await act(async () => { const input = host.querySelector('[aria-label="Data inicial"]') as HTMLInputElement; Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, '2025-01-03'); input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true })) })
  await act(async () => { await pause() })
  expect(host.querySelectorAll('tbody tr')).toHaveLength(3)
  await act(async () => { (host.querySelector('[aria-label="Filtrar por classe"]') as HTMLSelectElement).value = 'CDB'; host.querySelector('[aria-label="Filtrar por classe"]')!.dispatchEvent(new Event('change', { bubbles: true })) })
  await act(async () => { await pause() })
  expect(host.querySelectorAll('tbody tr')).toHaveLength(2)
  await act(async () => { const input = host.querySelector('[aria-label="Filtrar por ativo"]') as HTMLInputElement; Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, 'Banco A'); input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true })) })
  await act(async () => { await pause() })
  expect(host.querySelectorAll('tbody tr')).toHaveLength(2)
  await act(async () => { const input = host.querySelector('[aria-label="Filtrar por ativo"]') as HTMLInputElement; Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, 'inexistente'); input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true })) })
  await act(async () => { await pause() })
  expect(host.textContent).toContain('Nenhuma movimentação encontrada')
  expect(movements.map(row => row.id)).toEqual(['equity:1', 'cdb:1', 'equity:2', 'cdb:2'])
})

test('shows explicit empty and error states', async () => {
  await render({ movements: async () => [] })
  expect(host.textContent).toContain('Nenhuma movimentação encontrada')
  client.clear()
  const repository = { movements: vi.fn(async () => { throw new Error('offline') }) }
  await render(repository)
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('Não foi possível carregar o histórico')
  expect(host.querySelector('button')?.textContent).toContain('Tentar novamente')
  client.clear()
  await render({ movements: async () => ({ unexpected: true } as unknown as UnifiedMovement[]) })
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('Não foi possível carregar o histórico')
})
