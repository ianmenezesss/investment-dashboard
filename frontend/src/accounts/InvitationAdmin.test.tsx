import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, expect, test, vi } from 'vitest'
import { InvitationAdmin } from './InvitationAdmin'

const token = 'fictional-invitation-ui-token'
let host: HTMLDivElement
let root: Root

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

test('admin envia, lista e revoga convites pelo backend autenticado', async () => {
  const invite = { id: 'invite-1', email: 'person@example.test', expires_at: '2026-11-08T12:00:00Z', accepted: false, revoked: false }
  const calls: { url: string; init?: RequestInit }[] = []
  let active = [invite]
  const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
    calls.push({ url: input, init })
    if (init?.method === 'POST') {
      active = [{ ...invite, email: JSON.parse(String(init.body)).email }]
      return new Response(JSON.stringify(active[0]), { status: 201 })
    }
    if (init?.method === 'DELETE') {
      active = [{ ...invite, revoked: true }]
      return new Response('{"status":"revoked"}', { status: 200 })
    }
    if (input.endsWith('/access-requests')) return new Response(JSON.stringify([]), { status: 200 })
    return new Response(JSON.stringify(active), { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  host = document.createElement('div'); document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => root.render(<InvitationAdmin token={token}/>))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })

  expect(host.textContent).toContain('person@example.test')
  const input = host.querySelector('#invite-email') as HTMLInputElement
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, 'new@example.test')
  await act(async () => input.dispatchEvent(new Event('input', { bubbles: true })))
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(calls.some(call => call.init?.method === 'POST'
    && JSON.parse(String(call.init.body)).email === 'new@example.test')).toBe(true)
  expect(host.textContent).toContain('new@example.test')

  const revoke = [...host.querySelectorAll('button')].find(button => button.textContent === 'Revogar convite')!
  await act(async () => revoke.click())
  expect(calls.some(call => call.init?.method === 'DELETE' && call.url.endsWith('/invite-1'))).toBe(true)
  expect(host.textContent).toContain('revogado')
  expect(calls.every(call => (call.init?.headers as Record<string, string>)?.Authorization === `Bearer ${token}`)).toBe(true)
})

test('admin revisa solicitação e aprovação usa o endpoint autenticado existente', async () => {
  const request = { id: 'request-1', email: 'visitor@example.test', requested_at: '2026-11-01T10:00:00Z', status: 'pending' }
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    calls.push({ url: input, init })
    if (input.endsWith('/access-requests')) return new Response(JSON.stringify([request]), { status: 200 })
    return new Response(JSON.stringify([]), { status: 200 })
  }))
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
  await act(async () => root.render(<InvitationAdmin token={token}/>))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
  expect(host.textContent).toContain('Solicitações de acesso')
  expect(host.textContent).toContain('visitor@example.test')
  expect(host.textContent).toContain('pendente')
  const approve = [...host.querySelectorAll('button')].find(button => button.textContent === 'Aprovar e enviar convite')!
  await act(async () => approve.click())
  expect(calls.some(call => call.url.endsWith('/access-requests/request-1/approve') && call.init?.method === 'POST')).toBe(true)
  expect(calls.every(call => (call.init?.headers as Record<string, string>)?.Authorization === `Bearer ${token}`)).toBe(true)
})
