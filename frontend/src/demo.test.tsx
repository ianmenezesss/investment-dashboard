import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App'
import { request } from './api'
import { DEMO_STORAGE_KEY } from './repositories/DemoRepository'
import { initialOperations } from './demo/fixtures'

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
    for (const [name, value] of Object.entries({ ticker: 'DEMO4', kind: 'BUY', date: new Date().toLocaleDateString('en-CA'), quantity: '10', price: '20', fees: '2' })) {
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
    expect(host.textContent).toContain('DEMO4')
    const confirmDelete = document.querySelector('[role="alertdialog"]')!
    await act(async () => ([...confirmDelete.querySelectorAll('button')].find(b => b.textContent?.includes('Excluir operação'))!).click())
    expect(host.textContent).not.toContain('DEMO4')
    const restore = [...host.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Restaurar')!
    await act(async () => restore.click())
    const confirmReset = document.querySelector('[role="alertdialog"]')!
    await act(async () => ([...confirmReset.querySelectorAll('button')].find(b => b.textContent?.includes('Restaurar carteira'))!).click())
    expect(JSON.parse(localStorage.getItem(DEMO_STORAGE_KEY)!).operations).toHaveLength(initialOperations.length)
    expect(fetchMock).not.toHaveBeenCalled()
  } finally { await act(async () => root.unmount()); client.clear(); host.remove(); vi.restoreAllMocks() }
})

test('restauração exige confirmação, cancela com Escape e devolve foco ao botão de origem', async () => {
  const saved = JSON.stringify({ kind: 'investment-demo', version: 1, operations: [{ id: 99, ticker: 'TEST4', kind: 'BUY', date: '2026-01-01', quantity: '10', price: '20', fees: '0' }] })
  localStorage.setItem(DEMO_STORAGE_KEY, saved)
  const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock)
  const host = document.createElement('div'); document.body.appendChild(host)
  const root = createRoot(host), client = new QueryClient()
  try {
    await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter><App/></MemoryRouter></QueryClientProvider>))
    const origin = [...host.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Restaurar')!
    const open = async () => { origin.focus(); await act(async () => origin.click()) }
    await open()
    let dialog = document.querySelector('[role="alertdialog"]')!
    expect(dialog).not.toBeNull()
    expect(dialog.textContent).toContain('Restaurar carteira demonstrativa?')
    expect(dialog.getAttribute('aria-labelledby')).toBeTruthy()
    expect(dialog.getAttribute('aria-describedby')).toBeTruthy()
    expect(document.activeElement?.textContent).toBe('Cancelar')
    expect(localStorage.getItem(DEMO_STORAGE_KEY)).toBe(saved)
    await act(async () => (document.activeElement as HTMLButtonElement).click())
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 25)) })
    expect(document.activeElement).toBe(origin)
    expect(localStorage.getItem(DEMO_STORAGE_KEY)).toBe(saved)
    await open()
    await act(async () => document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })))
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 25)) })
    expect(document.querySelector('[role="alertdialog"]')).toBeNull()
    expect(document.activeElement).toBe(origin)
    expect(localStorage.getItem(DEMO_STORAGE_KEY)).toBe(saved)
    await open()
    dialog = document.querySelector('[role="alertdialog"]')!
    await act(async () => ([...dialog.querySelectorAll('button')].find(b => b.textContent?.includes('Restaurar carteira'))!).click())
    expect(JSON.parse(localStorage.getItem(DEMO_STORAGE_KEY)!)).toMatchObject({ version: 2, seedVersion: 2 })
    expect(JSON.parse(localStorage.getItem(DEMO_STORAGE_KEY)!).operations).toHaveLength(26)
    expect(fetchMock).not.toHaveBeenCalled()
  } finally { await act(async () => root.unmount()); client.clear(); host.remove() }
})

test('Ações mostra posições e operações; controles de período e exclusão são identificáveis', async () => {
  const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock)
  const host = document.createElement('div'); document.body.appendChild(host)
  const root = createRoot(host), client = new QueryClient()
  try {
    await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/acoes']}><App/></MemoryRouter></QueryClientProvider>))
    expect(host.textContent).toContain('Posições por custo médio')
    expect(host.textContent).toContain('Operações em ações')
    expect(host.querySelectorAll('table')).toHaveLength(2)
    expect(host.textContent).toContain('Compra')
    expect(host.textContent).toContain('Venda')
    expect(host.querySelector('button[aria-label="Ordenar por data"]')).not.toBeNull()
    expect(host.querySelector('button[aria-pressed="true"]')?.textContent).toBe('Tudo')
    expect(host.querySelector('[aria-label^="Excluir operação"]')?.getAttribute('title')).toContain('Excluir operação de')
    expect(fetchMock).not.toHaveBeenCalled()
  } finally { await act(async () => root.unmount()); client.clear(); host.remove() }
})

test('exportação demonstrativa contém apenas operações fictícias e não consulta API', async () => {
  const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock)
  const create = vi.fn((_object: Blob | MediaSource) => 'blob:demo-test'), revoke = vi.fn()
  const oldCreate = URL.createObjectURL, oldRevoke = URL.revokeObjectURL
  URL.createObjectURL = create; URL.revokeObjectURL = revoke
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const host = document.createElement('div'); document.body.appendChild(host)
  const root = createRoot(host), client = new QueryClient()
  try {
    await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter><App/></MemoryRouter></QueryClientProvider>))
    const button = [...host.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Exportar')!
    await act(async () => button.click())
    expect(create).toHaveBeenCalledTimes(1)
    const blob = create.mock.calls[0][0] as Blob
    const contents = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsText(blob) })
    expect(JSON.parse(contents)).toMatchObject({ demonstration: true })
    expect(JSON.parse(contents).operations).toHaveLength(26)
    expect(revoke).toHaveBeenCalledWith('blob:demo-test')
    expect(fetchMock).not.toHaveBeenCalled()
  } finally { await act(async () => root.unmount()); client.clear(); host.remove(); click.mockRestore(); URL.createObjectURL = oldCreate; URL.revokeObjectURL = oldRevoke }
})
