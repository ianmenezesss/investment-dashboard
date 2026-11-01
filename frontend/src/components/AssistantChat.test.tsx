import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { AssistantChat } from './AssistantChat'

vi.mock('../runtime', () => ({ PUBLIC_DEMO: false, SUPABASE_AUTH: true, apiBase: () => '' }))

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  localStorage.clear()
  sessionStorage.clear()
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

async function mount() {
  await act(async () => root.render(<AssistantChat token="test-supabase-access-token"/>))
}

async function click(element: Element) {
  await act(async () => element.dispatchEvent(new MouseEvent('click', { bubbles: true })))
}

async function openChat() {
  await click(host.querySelector('[aria-label="Abrir conversa com Íris"]')!)
}

test('abre e fecha a conversa acessível com saudação e três sugestões', async () => {
  await mount()
  expect(host.querySelector('#iris-chat-panel')).toBeNull()
  await openChat()

  const panel = host.querySelector('#iris-chat-panel')!
  expect(panel.getAttribute('role')).toBe('dialog')
  expect(host.querySelector('#iris-chat-title')?.textContent).toBe('Íris')
  expect(host.textContent).toContain('Assistente de educação financeira')
  expect(host.textContent).toContain('Suas perguntas são enviadas à Groq para resposta')
  expect(host.textContent).toContain('não inclua informações pessoais ou financeiras')
  expect(host.textContent).toContain('Olá! Sou a Íris, sua assistente de educação financeira. Posso ajudar você a entender conceitos financeiros e utilizar as ferramentas do Investment Dashboard. O que gostaria de saber?')
  expect([...host.querySelectorAll('.iris-suggestions button')].map(button => button.textContent?.replace('↑', '').trim())).toEqual([
    'O que é CDB?', 'Como funciona o CDI?', 'Como usar o dashboard?',
  ])
  expect(document.activeElement).toBe(panel)

  await click(host.querySelector('[aria-label="Fechar conversa com Íris"]')!)
  expect(host.querySelector('#iris-chat-panel')).toBeNull()
  expect(document.activeElement).toBe(host.querySelector('[aria-label="Abrir conversa com Íris"]'))

  await openChat()
  await act(async () => host.querySelector('#iris-chat-panel')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
  expect(host.querySelector('#iris-chat-panel')).toBeNull()
})

test('sugestão usa o endpoint autenticado e mantém histórico somente enquanto o componente existe', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ answer: 'CDB é um título de renda fixa emitido por bancos.' }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }))
  vi.stubGlobal('fetch', fetchMock)
  await mount()
  await openChat()
  await click(host.querySelector('.iris-suggestions button')!)
  await vi.waitFor(() => expect(host.textContent).toContain('CDB é um título de renda fixa emitido por bancos.'))

  expect(fetchMock).toHaveBeenCalledTimes(1)
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
  expect(url).toContain('/api/assistant/chat')
  expect(init.method).toBe('POST')
  expect((init.headers as Record<string, string>).Authorization).toBe('Bearer test-supabase-access-token')
  expect(JSON.parse(init.body as string)).toEqual({ message: 'O que é CDB?' })

  await click(host.querySelector('[aria-label="Fechar conversa com Íris"]')!)
  await openChat()
  expect(host.textContent).toContain('CDB é um título de renda fixa emitido por bancos.')
  expect(localStorage.length).toBe(0)
  expect(sessionStorage.length).toBe(0)

  await act(async () => root.unmount())
  root = createRoot(host)
  await mount()
  await openChat()
  expect(host.textContent).toContain('Olá! Sou a Íris')
  expect(host.textContent).not.toContain('CDB é um título de renda fixa emitido por bancos.')
})

test('mostra carregamento durante envio por Enter e apresenta erros da API', async () => {
  let rejectRequest!: (response: Response) => void
  const fetchMock = vi.fn(() => new Promise<Response>(resolve => { rejectRequest = resolve }))
  vi.stubGlobal('fetch', fetchMock)
  await mount()
  await openChat()

  const input = host.querySelector<HTMLInputElement>('#iris-question')!
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
    setter.call(input, 'Como funciona o CDI?')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => input.form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(host.querySelector('[role="status"]')?.textContent).toContain('Íris está preparando uma resposta')
  expect((host.querySelector('[aria-label="Enviar pergunta"]') as HTMLButtonElement).disabled).toBe(true)

  await act(async () => rejectRequest(new Response(JSON.stringify({ detail: 'Assistente temporariamente indisponível.' }), {
    status: 503,
    headers: { 'Content-Type': 'application/json' },
  })))
  await vi.waitFor(() => expect(host.querySelector('[role="alert"]')?.textContent).toContain('Assistente temporariamente indisponível.'))
  expect(host.querySelector('[role="status"]')).toBeNull()
})
