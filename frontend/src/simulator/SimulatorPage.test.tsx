import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { SimulatorPage } from './SimulatorPage'

let host: HTMLDivElement
let root: Root
beforeEach(() => { host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

describe('simulator interface', () => {
  it('renders three editable hypothetical scenarios without accessing portfolio services', async () => {
    await act(async () => root.render(<SimulatorPage/>))
    expect(host.textContent).toContain('Conservador')
    expect(host.textContent).toContain('Moderado')
    expect(host.textContent).toContain('Otimista')
    expect(host.textContent).toContain('não lê nem altera operações')
    expect(host.querySelectorAll('input[type="number"]').length).toBeGreaterThanOrEqual(6)
  })
  it('shows validation errors instead of rendering results for an invalid term', async () => {
    await act(async () => root.render(<SimulatorPage/>))
    await act(async () => { const term = host.querySelector<HTMLInputElement>('input[type="number"][min="1"]')!; Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(term, '601'); term.dispatchEvent(new Event('input', { bubbles: true })); term.dispatchEvent(new Event('change', { bubbles: true })) })
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('Prazo')
  })
})
