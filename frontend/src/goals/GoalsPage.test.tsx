import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { GoalsPage } from './GoalsPage'
import { createGoal, goalsStorageKey } from './goalStorage'

let host: HTMLDivElement, root: Root, client: QueryClient
const repository = { performance: () => new Promise<never>(() => {}) } as never
const renderPage = async (identity = 'owner-a', source = repository) => { await act(async () => root.render(<QueryClientProvider client={client}><GoalsPage identity={identity} repository={source}/></QueryClientProvider>)) }
const setField = (name: string, value: string) => {
  const field = host.querySelector(`[name="${name}"]`) as HTMLInputElement
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(field, value)
  field.dispatchEvent(new Event('input', { bubbles: true })); field.dispatchEvent(new Event('change', { bubbles: true }))
}
const button = (label: string) => [...host.querySelectorAll('button')].find(item => item.textContent?.includes(label)) as HTMLButtonElement

beforeEach(() => { localStorage.clear(); host = document.createElement('div'); document.body.append(host); root = createRoot(host); client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }) })
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove(); localStorage.clear() })

test('creates a private local goal with manual reference and progress bar', async () => {
  await renderPage()
  await act(async () => { setField('name', 'Reserva'); setField('targetAmount', '10000'); setField('targetDate', '2030-12-31'); setField('initialReferenceAmount', '1250'); host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })) })
  expect(host.textContent).toContain('Reserva')
  expect(host.textContent).toContain('R$ 1.250,00')
  expect(host.textContent).toContain('12,5%')
  expect(host.textContent).toContain('não são sincronizadas entre dispositivos')
  expect(host.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('12.5')
  expect(JSON.parse(localStorage.getItem(goalsStorageKey('owner-a'))!)).toHaveLength(1)
  expect(localStorage.getItem(goalsStorageKey('owner-b'))).toBeNull()
})

test('edits a goal without changing its progress and confirms deletion before removing it', async () => {
  await renderPage()
  await act(async () => { setField('name', 'Viagem'); setField('targetAmount', '12000'); setField('initialReferenceAmount', '500'); host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })) })
  await act(async () => (host.querySelector('[aria-label="Editar meta Viagem"]') as HTMLButtonElement).click())
  await act(async () => { setField('name', 'Viagem longa'); setField('targetAmount', '20000'); host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })) })
  expect(host.textContent).toContain('Viagem longa')
  expect(host.textContent).toContain('R$ 500,00')
  await act(async () => (host.querySelector('[aria-label="Excluir meta Viagem longa"]') as HTMLButtonElement).click())
  expect(host.querySelector('[role="alertdialog"]')).not.toBeNull()
  await act(async () => button('Excluir').click())
  expect(host.textContent).not.toContain('Viagem longa')
  expect(JSON.parse(localStorage.getItem(goalsStorageKey('owner-a'))!)).toEqual([])
})

test('shows local storage failures and preserves existing records instead of reporting a successful save', async () => {
  const key = goalsStorageKey('owner-a')
  localStorage.setItem(key, '{corrupt')
  await renderPage()
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('preservados')
  expect(localStorage.getItem(key)).toBe('{corrupt')
})

test('uses open-position capital without adding external flows and allows manual confirmation when data is partial', async () => {
  const goal = createGoal({ name: 'Objetivo', targetAmount: '1000', targetDate: null, initialReferenceAmount: '100' })
  localStorage.setItem(goalsStorageKey('owner-a'), JSON.stringify([goal]))
  const response = {
    as_of: '2026-10-30', flows: { recorded_contributions: '99999.99' },
    capital: { basis: 'equity_open_acquisition_cost_plus_effective_cdb_principal', open_positions_accounted: '500' },
    fixed_income: { missing_positions: [] },
    composition: { as_of: '2026-10-30', missing_fixed_income: [], declared_positions: [{ asset: 'CDB observado' }], missing_components: ['cotações de mercado para ações'] },
  }
  const load = vi.fn(async () => response)
  await renderPage('owner-a', { performance: load } as never)
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
  expect(load).toHaveBeenCalledTimes(1)
  expect(host.textContent).toContain('Base incompleta')
  await act(async () => button('Acompanhar capital investido').click())
  expect(host.textContent).toContain('50%')
  expect(host.textContent).toContain('Capital investido · custo/principal aberto')
  expect(host.textContent).toContain('Posição declarada excluída da base: CDB observado')
  await act(async () => button('Usar progresso manual').click())
  await act(async () => { setField('manualProgressAmount', '700'); host.querySelector('.goal-manual-form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })) })
  expect(host.textContent).toContain('70%')
  expect(host.textContent).toContain('Patrimônio informado manualmente')
  expect(JSON.parse(localStorage.getItem(goalsStorageKey('owner-a'))!)[0]).toMatchObject({ currentAmount: '700.00', manualProgressAmount: '700.00', progressSource: 'manual' })
})

test('shows the monthly contribution plan, lets the user edit scenario rates and saves assumptions locally', async () => {
  const goal = createGoal({ name: 'Objetivo', targetAmount: '10000', targetDate: null, initialReferenceAmount: '1000' })
  localStorage.setItem(goalsStorageKey('owner-a'), JSON.stringify([goal]))
  await renderPage()
  await act(async () => button('Planejar aportes e projeções').click())
  expect(host.textContent).toContain('Diferença até o alvo')
  expect(host.textContent).toContain('Projeção no horizonte')
  await act(async () => setField('annualRateConservative', '0'))
  expect(host.textContent).toContain('Conservador · 0% a.a.')
  expect(host.textContent).toContain('R$ 75,00')
  await act(async () => host.querySelector('.goal-planning form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(host.textContent).toContain('Premissas salvas neste dispositivo.')
  expect(JSON.parse(localStorage.getItem(goalsStorageKey('owner-a'))!)[0].planning).toMatchObject({ monthlyContribution: '500.00', annualRates: { conservative: '0' }, horizonMonths: '120' })
})
