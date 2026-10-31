import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, test } from 'vitest'
import { GoalsPage } from './GoalsPage'
import { goalsStorageKey } from './goalStorage'

let host: HTMLDivElement, root: Root
const setField = (name: string, value: string) => {
  const field = host.querySelector(`[name="${name}"]`) as HTMLInputElement
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(field, value)
  field.dispatchEvent(new Event('input', { bubbles: true })); field.dispatchEvent(new Event('change', { bubbles: true }))
}
const button = (label: string) => [...host.querySelectorAll('button')].find(item => item.textContent?.includes(label)) as HTMLButtonElement

beforeEach(() => { localStorage.clear(); host = document.createElement('div'); document.body.append(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); host.remove(); localStorage.clear() })

test('creates a private local goal with manual reference and progress bar', async () => {
  await act(async () => root.render(<GoalsPage identity="owner-a"/>))
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
  await act(async () => root.render(<GoalsPage identity="owner-a"/>))
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
  await act(async () => root.render(<GoalsPage identity="owner-a"/>))
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('preservados')
  expect(localStorage.getItem(key)).toBe('{corrupt')
})
