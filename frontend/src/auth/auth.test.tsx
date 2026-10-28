import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { Session } from '@supabase/supabase-js'

const mock = vi.hoisted(() => ({
  callback: null as null | ((event: string, session: unknown) => void),
  auth: { getSession: vi.fn(), getUser: vi.fn(), signInWithPassword: vi.fn(), signOut: vi.fn(), onAuthStateChange: vi.fn(), startAutoRefresh: vi.fn(), stopAutoRefresh: vi.fn() },
}))
vi.mock('./supabase', () => ({ getSupabase: () => ({ auth: mock.auth }) }))
vi.mock('../runtime', () => ({ PUBLIC_DEMO: false, SUPABASE_AUTH: true, apiBase: () => '' }))
import { useAuth } from './useAuth'
import { LoginPanel } from './LoginPanel'
import App from '../App'
import { ApiError, request } from '../api'

const session = { access_token: 'test-access-a', refresh_token: 'test-refresh-a', expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: '11111111-1111-4111-8111-111111111111', email: 'investor@example.test' } } as Session
let host: HTMLDivElement
let root: Root
const clear = vi.fn()
function Harness() {
  const auth = useAuth(true, clear)
  return <><span data-status>{auth.status}</span><span data-token>{auth.session?.access_token}</span>{auth.session ? <button onClick={() => void auth.logout()}>Sair</button> : <LoginPanel loading={auth.status === 'loading'} error={auth.error} onLogin={auth.login}/>}<button onClick={auth.expire}>Expirar</button></>
}
beforeEach(() => {
  vi.clearAllMocks()
  mock.callback = null
  mock.auth.getSession.mockResolvedValue({ data: { session: null }, error: null })
  mock.auth.getUser.mockResolvedValue({ data: { user: session.user }, error: null })
  mock.auth.signInWithPassword.mockResolvedValue({ data: { session }, error: null })
  mock.auth.signOut.mockResolvedValue({ error: null })
  mock.auth.onAuthStateChange.mockImplementation(callback => { mock.callback = callback; return { data: { subscription: { unsubscribe: vi.fn() } } } })
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
  sessionStorage.clear()
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals() })

async function submit() {
  await act(async () => {
    for (const [selector, value] of [['input[type="email"]', 'investor@example.test'], ['input[type="password"]', 'test-password-only']]) {
      const input = host.querySelector(selector) as HTMLInputElement
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
      input.dispatchEvent(new Event('input', { bubbles: true }))
    }
  })
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
}

test('login por senha, envio do access token ao FastAPI e logout', async () => {
  const fetchMock = vi.fn(async (input: string, _init?: RequestInit) => new Response(JSON.stringify(input.includes('dashboard') ? { holdings: [], acquisition_cost: '0', total_purchases: '0', realized_profit: '0' } : []), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter><App/></MemoryRouter></QueryClientProvider>))
  expect(fetchMock).not.toHaveBeenCalled()
  expect(host.querySelector('.sidebar')).toBeNull()
  expect(host.querySelector('table')).toBeNull()
  await submit()
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
  expect(mock.auth.signInWithPassword).toHaveBeenCalledWith({ email: 'investor@example.test', password: 'test-password-only' })
  expect(fetchMock).toHaveBeenCalled()
  expect(host.querySelector('.sidebar')).not.toBeNull()
  expect(host.textContent).toContain('Carteira conectada')
  expect(host.textContent).toContain('investor@example.test')
  expect(fetchMock.mock.calls.every(call => (call[1] as RequestInit).headers && ((call[1] as RequestInit).headers as Record<string, string>).Authorization === 'Bearer test-access-a')).toBe(true)
  const disconnect = [...host.querySelectorAll('button')].find(button => button.textContent?.trim() === 'Sair')!
  await act(async () => disconnect.click())
  expect(mock.auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
  expect(client.getQueryData(['summary', session.user.id])).toBeUndefined()
  expect(host.querySelector('form[aria-label="Login da carteira"]')).not.toBeNull()
  client.clear()
})

test.each(['/acoes', '/historico', '/cdbs', '/metas', '/simulador'])('rota privada %s não renderiza carteira nem faz rede sem login', async route => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient()
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[route]}><App/></MemoryRouter></QueryClientProvider>))
  expect(host.querySelector('form[aria-label="Login da carteira"]')).not.toBeNull()
  expect(host.querySelector('.sidebar')).toBeNull()
  expect(host.querySelector('table')).toBeNull()
  expect(fetchMock).not.toHaveBeenCalled()
  client.clear()
})

test('403 da API mantém somente login e feedback de falta de autorização', async () => {
  mock.auth.getSession.mockResolvedValue({ data: { session }, error: null })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 403 })))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter><App/></MemoryRouter></QueryClientProvider>))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)) })
  expect(host.querySelector('.sidebar')).toBeNull()
  expect(host.textContent).toContain('Sua conta não está autorizada')
  client.clear()
})

test('demonstração privada permite navegar e voltar ao login sem consultas financeiras', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient()
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter><App/></MemoryRouter></QueryClientProvider>))
  await act(async () => (host.querySelector('.login-demo') as HTMLButtonElement).click())
  expect(host.textContent).toContain('Modo Demonstração')
  expect(host.querySelector('.sidebar')).not.toBeNull()
  const history = host.querySelector('a[href="/demo/historico"]')!
  await act(async () => history.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })))
  expect(host.textContent).toContain('Histórico de operações')
  const back = [...host.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Entrar')!
  await act(async () => back.click())
  expect(host.querySelector('.sidebar')).toBeNull()
  expect(host.querySelector('form[aria-label="Login da carteira"]')).not.toBeNull()
  expect(fetchMock).not.toHaveBeenCalled()
  client.clear()
})

test('botão de visibilidade alterna somente o tipo do campo de senha', async () => {
  await act(async () => root.render(<Harness/>))
  await act(async () => (host.querySelector('[aria-label="Mostrar senha"]') as HTMLButtonElement).click())
  expect(host.querySelector('#login-password')!.getAttribute('type')).toBe('text')
  await act(async () => (host.querySelector('[aria-label="Ocultar senha"]') as HTMLButtonElement).click())
  expect(host.querySelector('#login-password')!.getAttribute('type')).toBe('password')
})

test('restauração não renderiza carteira nem consulta API enquanto getUser está pendente', async () => {
  mock.auth.getSession.mockResolvedValue({ data: { session }, error: null })
  let resolveUser!: (value: unknown) => void
  mock.auth.getUser.mockReturnValue(new Promise(resolve => { resolveUser = resolve }))
  const fetchMock = vi.fn(async (input: string) => new Response(JSON.stringify(input.includes('dashboard') ? { holdings: [], acquisition_cost: '0', total_purchases: '0', realized_profit: '0' } : []), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/acoes']}><RouteProbe/><App/></MemoryRouter></QueryClientProvider>))
  expect(host.querySelector('.sidebar')).toBeNull()
  expect(host.querySelector('form[aria-label="Login da carteira"]')).toBeNull()
  expect(host.querySelector('[data-route]')!.textContent).toBe('/acoes')
  expect(fetchMock).not.toHaveBeenCalled()
  await act(async () => resolveUser({ data: { user: session.user }, error: null }))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
  expect(host.querySelector('.sidebar')).not.toBeNull()
  expect(host.querySelector('[data-route]')!.textContent).toBe('/acoes')
  client.clear()
})

function RouteProbe() { return <output data-route>{useLocation().pathname}</output> }

function financialResponse(input: string) {
  return new Response(JSON.stringify(input.includes('dashboard')
    ? { holdings: [], acquisition_cost: '0', total_purchases: '0', realized_profit: '0' } : []), { status: 200 })
}

test('renovação no retorno à aba mantém dashboard enquanto a API revalida com o novo JWT', async () => {
  mock.auth.getSession.mockResolvedValue({ data: { session }, error: null })
  const fetchMock = vi.fn(async (input: string, _init?: RequestInit) => financialResponse(input))
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/historico']}><RouteProbe/><App/></MemoryRouter></QueryClientProvider>))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
  const cached = client.getQueryData(['summary', session.user.id])
  const pending: { input: string; resolve: (value: Response) => void }[] = []
  fetchMock.mockImplementation(input => new Promise(resolve => pending.push({ input, resolve })))
  await act(async () => {
    window.dispatchEvent(new Event('focus'))
    mock.callback!('TOKEN_REFRESHED', { ...session, access_token: 'test-access-renewed' })
  })
  expect(host.querySelector('.sidebar')).not.toBeNull()
  expect(host.querySelector('form[aria-label="Login da carteira"]')).toBeNull()
  expect(host.querySelector('[data-route]')!.textContent).toBe('/historico')
  expect(client.getQueryData(['summary', session.user.id])).toBe(cached)
  expect(fetchMock.mock.calls.some(call => (call[1]?.headers as Record<string, string>)?.Authorization === 'Bearer test-access-renewed')).toBe(true)
  await act(async () => pending.forEach(item => item.resolve(financialResponse(item.input))))
  client.clear()
})

test('falha transitória de rede no refoco mantém dados e mostra erro sem abrir login', async () => {
  mock.auth.getSession.mockResolvedValue({ data: { session }, error: null })
  const fetchMock = vi.fn(async (input: string) => financialResponse(input))
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/historico']}><RouteProbe/><App/></MemoryRouter></QueryClientProvider>))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
  fetchMock.mockRejectedValue(new TypeError('Falha de rede temporária'))
  await act(async () => { await client.refetchQueries() })
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
  expect(host.querySelector('.sidebar')).not.toBeNull()
  expect(host.querySelector('[role="alert"]')!.textContent).toContain('Falha de rede temporária')
  expect(host.querySelector('form[aria-label="Login da carteira"]')).toBeNull()
  expect(host.querySelector('[data-route]')!.textContent).toBe('/historico')
  client.clear()
})

test('logout remoto durante restauração invalida a resposta antiga e eventos de refresh tardios', async () => {
  mock.auth.getSession.mockResolvedValue({ data: { session }, error: null })
  let resolveUser!: (value: unknown) => void
  mock.auth.getUser.mockReturnValue(new Promise(resolve => { resolveUser = resolve }))
  await act(async () => root.render(<Harness/>))
  await act(async () => mock.callback!('SIGNED_OUT', null))
  await act(async () => resolveUser({ data: { user: session.user }, error: null }))
  await act(async () => mock.callback!('TOKEN_REFRESHED', session))
  expect(host.querySelector('[data-status]')!.textContent).toBe('anonymous')
  expect(host.querySelector('[data-token]')!.textContent).toBe('')
  expect(host.textContent).toContain('Sessão encerrada')
})

test('troca de identidade limpa dados e aguarda getUser sem reutilizar a sessão anterior', async () => {
  mock.auth.getSession.mockResolvedValue({ data: { session }, error: null })
  await act(async () => root.render(<Harness/>))
  clear.mockClear()
  const other = { ...session, user: { ...session.user, id: '22222222-2222-4222-8222-222222222222' } }
  let resolveUser!: (value: unknown) => void
  mock.auth.getUser.mockReturnValue(new Promise(resolve => { resolveUser = resolve }))
  await act(async () => mock.callback!('SIGNED_IN', other))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
  expect(clear).toHaveBeenCalled()
  expect(host.querySelector('[data-status]')!.textContent).toBe('loading')
  expect(host.querySelector('[data-token]')!.textContent).toBe('')
  await act(async () => resolveUser({ data: { user: other.user }, error: null }))
  expect(host.querySelector('[data-status]')!.textContent).toBe('authenticated')
})

test('expiração real encerra a sessão e não aceita renovação tardia após o encerramento', async () => {
  vi.useFakeTimers()
  try {
    mock.auth.getSession.mockResolvedValue({ data: { session: { ...session, expires_at: Math.floor(Date.now() / 1000) + 2 } }, error: null })
    await act(async () => root.render(<Harness/>))
    expect(host.querySelector('[data-status]')!.textContent).toBe('authenticated')
    await act(async () => { await vi.advanceTimersByTimeAsync(2001) })
    expect(host.querySelector('[data-status]')!.textContent).toBe('anonymous')
    expect(mock.auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
    await act(async () => mock.callback!('TOKEN_REFRESHED', session))
    expect(host.querySelector('[data-token]')!.textContent).toBe('')
  } finally { vi.useRealTimers() }
})

test('hook deixa o SDK singleton gerenciar a visibilidade e auto-refresh do navegador', async () => {
  await act(async () => root.render(<Harness/>))
  await act(async () => root.render(null))
  expect(mock.auth.startAutoRefresh).not.toHaveBeenCalled()
  expect(mock.auth.stopAutoRefresh).not.toHaveBeenCalled()
})

test.each([401, 403])('erro %s da API prevalece sobre erro transitório de outra consulta no refoco', async status => {
  mock.auth.getSession.mockResolvedValue({ data: { session }, error: null })
  const fetchMock = vi.fn(async (input: string) => financialResponse(input))
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter><App/></MemoryRouter></QueryClientProvider>))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
  fetchMock.mockImplementation(async input => {
    if (input.includes('dashboard')) throw new TypeError('Falha de rede')
    return new Response('{}', { status })
  })
  await act(async () => { await client.refetchQueries() })
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
  expect(host.querySelector('.sidebar')).toBeNull()
  expect(host.querySelector('form[aria-label="Login da carteira"]')).not.toBeNull()
  if (status === 401) expect(mock.auth.signOut).toHaveBeenCalled()
  else expect(host.textContent).toContain('Sua conta não está autorizada')
  client.clear()
})

test('retorno à aba com SIGNED_IN repetido preserva tela, cache, modal e rota', async () => {
  mock.auth.getSession.mockResolvedValue({ data: { session }, error: null })
  const fetchMock = vi.fn(async (input: string) => new Response(JSON.stringify(input.includes('dashboard')
    ? { holdings: [], acquisition_cost: '0', total_purchases: '0', realized_profit: '0' } : []), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter><RouteProbe/><App/></MemoryRouter></QueryClientProvider>))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
  const history = host.querySelector('a[href="/historico"]')!
  await act(async () => history.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })))
  await act(async () => ([...host.querySelectorAll('button')].find(b => b.textContent?.includes('Nova operação'))!).click())
  const cached = client.getQueryData(['summary', session.user.id])
  const visibility = vi.spyOn(document, 'visibilityState', 'get')
  try {
    for (let i = 0; i < 3; i++) {
      await act(async () => {
        visibility.mockReturnValue('hidden'); document.dispatchEvent(new Event('visibilitychange'))
        visibility.mockReturnValue('visible'); document.dispatchEvent(new Event('visibilitychange'))
        window.dispatchEvent(new Event('focus'))
        // Supabase reconfirms the same session when the tab becomes visible.
        mock.callback!('SIGNED_IN', { ...session })
      })
      expect(host.querySelector('.sidebar')).not.toBeNull()
      expect(host.querySelector('form[aria-label="Login da carteira"]')).toBeNull()
      expect(host.querySelector('[data-route]')!.textContent).toBe('/historico')
      expect(document.querySelector('[role="dialog"]')).not.toBeNull()
      expect(client.getQueryData(['summary', session.user.id])).toBe(cached)
    }
  } finally { visibility.mockRestore(); client.clear() }
})

test('credenciais recusadas mostram erro seguro sem refletir senha', async () => {
  mock.auth.signInWithPassword.mockResolvedValue({ data: { session: null }, error: new Error('internal sensitive details') })
  await act(async () => root.render(<Harness/>))
  await submit()
  expect(host.textContent).toContain('Confira suas credenciais')
  expect(host.textContent).not.toContain('sensitive')
  expect((host.querySelector('input[type="password"]') as HTMLInputElement).value).toBe('')
})

test('recuperação da sessão exige getUser e restaura o access token', async () => {
  mock.auth.getSession.mockResolvedValue({ data: { session }, error: null })
  await act(async () => root.render(<Harness/>))
  expect(mock.auth.getUser).toHaveBeenCalledWith('test-access-a')
  expect(host.querySelector('[data-status]')!.textContent).toBe('authenticated')
  expect(host.querySelector('[data-token]')!.textContent).toBe('test-access-a')
})

test.each(['expirada', 'inválida'])('sessão recuperada %s é descartada', async kind => {
  mock.auth.getSession.mockResolvedValue({ data: { session: kind === 'expirada' ? { ...session, expires_at: 1 } : session }, error: null })
  if (kind === 'inválida') mock.auth.getUser.mockResolvedValue({ data: { user: null }, error: new Error('invalid token') })
  await act(async () => root.render(<Harness/>))
  expect(host.querySelector('[data-token]')!.textContent).toBe('')
  expect(host.textContent).toContain('Sua sessão expirou')
  expect(clear).toHaveBeenCalled()
})

test('renovação atualiza o JWT e encerramento remoto remove a sessão', async () => {
  mock.auth.getSession.mockResolvedValue({ data: { session }, error: null })
  await act(async () => root.render(<Harness/>))
  await act(async () => mock.callback!('TOKEN_REFRESHED', { ...session, access_token: 'test-access-new' }))
  expect(host.querySelector('[data-token]')!.textContent).toBe('test-access-new')
  await act(async () => mock.callback!('SIGNED_OUT', null))
  expect(host.querySelector('[data-status]')!.textContent).toBe('anonymous')
  expect(host.querySelector('[data-token]')!.textContent).toBe('')
})

test('API rejeita ausência de token antes de fazer rede e preserva status 401', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 401 }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(request('dashboard', '')).rejects.toBeInstanceOf(ApiError)
  expect(fetchMock).not.toHaveBeenCalled()
  await expect(request('dashboard', 'test-invalid')).rejects.toMatchObject({ status: 401 })
})

test('rejeição 401 do FastAPI encerra a sessão e esconde a carteira', async () => {
  mock.auth.getSession.mockResolvedValue({ data: { session }, error: null })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 401 })))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter><App/></MemoryRouter></QueryClientProvider>))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)) })
  expect(host.querySelector('form[aria-label="Login da carteira"]')).not.toBeNull()
  expect(mock.auth.signOut).toHaveBeenCalled()
  expect(client.getQueryData(['summary', session.user.id])).toBeUndefined()
  client.clear()
})
