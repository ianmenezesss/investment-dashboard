import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { AccessRequestPage } from './AccessRequestPage'

let host: HTMLDivElement
let root: Root
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals() })

test('envia somente o e-mail e mostra a resposta neutra após o envio', async () => {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response('{"message":"accepted"}', { status: 202 }))
  vi.stubGlobal('fetch', fetchMock)
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
  await act(async () => root.render(<MemoryRouter><AccessRequestPage/></MemoryRouter>))
  const email = host.querySelector('input[type="email"]') as HTMLInputElement
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(email, 'visitor@example.test')
  await act(async () => email.dispatchEvent(new Event('input', { bubbles: true })))
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(fetchMock.mock.calls[0][0]).toContain('/api/access-requests')
  const request = fetchMock.mock.calls[0][1] as RequestInit
  expect(request.headers).toEqual({ 'Content-Type': 'application/json' })
  expect(JSON.parse(String(request.body))).toEqual({ email: 'visitor@example.test' })
  expect(host.textContent).toContain('Se sua solicitação puder ser processada')
  expect(host.querySelector('.access-request-back')?.textContent).toContain('Voltar ao login')
})
