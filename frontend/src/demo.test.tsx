import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App'
import { request } from './api'
import { DEMO_STORAGE_KEY } from './repositories/DemoRepository'

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

test('build de produção permanece público mesmo com configuração local de demonstração desativada', async () => {
  vi.resetModules()
  vi.stubEnv('PROD', true)
  vi.stubEnv('VITE_PUBLIC_DEMO', 'false')
  vi.stubEnv('VITE_APP_MODE', 'demo')
  try {
    const runtime = await import('./runtime')
    expect(runtime.PUBLIC_DEMO).toBe(true)
  } finally {
    vi.stubEnv('PROD', false)
    vi.stubEnv('VITE_PUBLIC_DEMO', 'true')
  }
})

test('demonstração pública bloqueia chamadas HTTP inclusive fora dos componentes', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  await expect(request('operations', 'not-a-real-token', { method: 'POST' })).rejects.toThrow('não acessa a API privada')
  await expect(request('export', 'not-a-real-token')).rejects.toThrow('não acessa a API privada')
  expect(fetchMock).not.toHaveBeenCalled()
})

test('visitante navega entre dashboard e histórico sem autenticação ou rede', async () => {
  const fetchMock = vi.fn().mockRejectedValue(new Error('API indisponível'))
  vi.stubGlobal('fetch', fetchMock)
  const host = document.createElement('div')
  document.body.appendChild(host)
  const root = createRoot(host)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  try {
    await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter><App/></MemoryRouter></QueryClientProvider>))
    expect(host.textContent).toContain('Modo Demonstração')
    expect(host.textContent).toContain('ITUB4')
    expect(host.querySelector('input[type="password"]')).toBeNull()
    const create = [...host.querySelectorAll('button')].find(b => b.textContent?.includes('Nova operação'))!
    expect(create.disabled).toBe(false)
    const history = host.querySelector('a[href="/historico"]')!
    await act(async () => history.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })))
    expect(host.textContent).toContain('Histórico de operações')
    expect(host.querySelector('[aria-label^="Excluir operação"]')).not.toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  } finally {
    await act(async () => root.unmount())
    client.clear()
    host.remove()
  }
})

test('compra pela interface persiste, atualiza carteira, permite excluir e restaurar sem rede', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  const host = document.createElement('div'); document.body.appendChild(host)
  let root = createRoot(host)
  const client = new QueryClient()
  const render = async () => { await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter><App/></MemoryRouter></QueryClientProvider>)) }
  try {
    await render()
    const create = [...host.querySelectorAll('button')].find(b => b.textContent?.includes('Nova operação'))!
    await act(async () => create.click())
    const form = document.querySelector('[role="dialog"] form') as HTMLFormElement
    expect(form).not.toBeNull()
    for (const [name, value] of Object.entries({ ticker: 'DEMO4', kind: 'BUY', date: '2026-01-01', quantity: '10', price: '20', fees: '2' })) {
      (form.elements.namedItem(name) as HTMLInputElement).value = value
    }
    await act(async () => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
    expect(host.textContent).toContain('DEMO4')
    const stored = JSON.parse(localStorage.getItem(DEMO_STORAGE_KEY)!)
    expect(stored.operations.at(-1)).toMatchObject({ ticker: 'DEMO4', quantity: '10', price: '20', fees: '2' })
    await act(async () => root.unmount()); root = createRoot(host); await render()
    expect(host.textContent).toContain('DEMO4')
    const row = [...host.querySelectorAll('tr')].find(tr => tr.textContent?.includes('DEMO4'))!
    await act(async () => (row.querySelector('button[aria-label^="Excluir"]') as HTMLButtonElement).click())
    expect(host.textContent).not.toContain('DEMO4')
    const restore = [...host.querySelectorAll('button')].find(b => b.textContent === 'Restaurar demonstração')!
    await act(async () => restore.click())
    expect(JSON.parse(localStorage.getItem(DEMO_STORAGE_KEY)!).operations).toHaveLength(4)
    expect(fetchMock).not.toHaveBeenCalled()
  } finally { await act(async () => root.unmount()); client.clear(); host.remove(); vi.restoreAllMocks() }
})
