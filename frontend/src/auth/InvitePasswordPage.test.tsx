import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ updateUser: vi.fn(), getSession: vi.fn() }))
vi.mock('./supabase', () => ({ getSupabase: () => ({ auth: { updateUser: mocks.updateUser, getSession: mocks.getSession } }) }))
vi.mock('../runtime', () => ({ apiBase: () => '' }))
import { InvitePasswordPage } from './InvitePasswordPage'

let host: HTMLDivElement
let root: Root
const invitationId = '55555555-5555-4555-8555-555555555555'
const token = 'fictional-supabase-session-token'

beforeEach(() => {
  mocks.updateUser.mockReset().mockResolvedValue({ error: null })
  mocks.getSession.mockReset().mockResolvedValue({ data: { session: { access_token: token } }, error: null })
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals() })

function setInput(input: HTMLInputElement, value: string) {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

test('link antigo sem convite atual não mostra formulário nem altera senha', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 403 })))
  await act(async () => root.render(<MemoryRouter><InvitePasswordPage invitationId={invitationId} token={token} onComplete={vi.fn()}/></MemoryRouter>))
  await vi.waitFor(() => expect(host.textContent).toContain('não corresponde a um convite atual'))
  expect(host.querySelector('form')).toBeNull()
  expect(mocks.updateUser).not.toHaveBeenCalled()
  expect(host.querySelector('a[href="/login"]')).not.toBeNull()
})

test('troca a senha somente após claim do convite atual e ativa com claim vinculado', async () => {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    calls.push({ url: input, init })
    if (input.endsWith('/eligibility')) return new Response('{"eligible":true}', { status: 200 })
    if (input.endsWith('/claim') && init?.method === 'POST') return new Response('{"claim_token":"one-time-claim-token-long-enough-for-test-only"}', { status: 200 })
    if (input.endsWith('/api/account/activate')) return new Response('{"status":"active"}', { status: 200 })
    if (input.endsWith('/claim') && init?.method === 'DELETE') return new Response('{"released":true}', { status: 200 })
    return new Response('{}', { status: 404 })
  }))
  const onComplete = vi.fn()
  await act(async () => root.render(<MemoryRouter><InvitePasswordPage invitationId={invitationId} token={token} onComplete={onComplete}/></MemoryRouter>))
  await vi.waitFor(() => expect(host.querySelector('#invite-password')).not.toBeNull())
  const password = host.querySelector<HTMLInputElement>('#invite-password')!
  const confirm = host.querySelector<HTMLInputElement>('#invite-password-confirm')!
  await act(async () => { setInput(password, 'Sufficiently-Long-Password-123'); setInput(confirm, 'Sufficiently-Long-Password-123') })
  await act(async () => host.querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(calls.map(call => call.url)).toEqual([
    `/api/account/invitations/${invitationId}/eligibility`,
    `/api/account/invitations/${invitationId}/claim`,
    '/api/account/activate',
  ])
  expect(mocks.updateUser).toHaveBeenCalledWith({ password: 'Sufficiently-Long-Password-123' })
  const activation = calls[2].init!
  expect(activation.headers).toMatchObject({ Authorization: `Bearer ${token}` })
  expect(JSON.parse(String(activation.body))).toEqual({ invitation_id: invitationId, claim_token: 'one-time-claim-token-long-enough-for-test-only' })
  expect(onComplete).toHaveBeenCalledOnce()
})

test('conflito ao reivindicar convite impede a alteração de senha', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => input.endsWith('/eligibility')
    ? new Response('{"eligible":true}', { status: 200 }) : new Response('{}', { status: 409 })))
  await act(async () => root.render(<MemoryRouter><InvitePasswordPage invitationId={invitationId} token={token} onComplete={vi.fn()}/></MemoryRouter>))
  await vi.waitFor(() => expect(host.querySelector('form')).not.toBeNull())
  await act(async () => { setInput(host.querySelector<HTMLInputElement>('#invite-password')!, 'Sufficiently-Long-Password-123'); setInput(host.querySelector<HTMLInputElement>('#invite-password-confirm')!, 'Sufficiently-Long-Password-123') })
  await act(async () => host.querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(mocks.updateUser).not.toHaveBeenCalled()
  expect(host.textContent).toContain('não está mais disponível')
})

test('resposta de ativação perdida preserva o claim e repete somente a confirmação com token atualizado', async () => {
  const calls: { url: string; init?: RequestInit }[] = []
  let activations = 0
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    calls.push({ url: input, init })
    if (input.endsWith('/eligibility')) return new Response('{"eligible":true}')
    if (input.endsWith('/claim')) return new Response('{"claim_token":"retry-the-same-claim"}')
    if (input.endsWith('/activate')) {
      activations++
      if (activations === 1) throw new TypeError('Network response lost')
      return new Response('{"status":"active"}')
    }
    return new Response('{}', { status: 404 })
  }))
  mocks.updateUser.mockImplementation(async () => {
    mocks.getSession.mockResolvedValue({ data: { session: { access_token: 'refreshed-session' } }, error: null })
    return { error: null }
  })
  const complete = vi.fn()
  await act(async () => root.render(<MemoryRouter><InvitePasswordPage invitationId={invitationId} token={token} onComplete={complete}/></MemoryRouter>))
  await vi.waitFor(() => expect(host.querySelector('form')).not.toBeNull())
  await act(async () => {
    setInput(host.querySelector<HTMLInputElement>('#invite-password')!, 'Sufficiently-Long-Password-123')
    setInput(host.querySelector<HTMLInputElement>('#invite-password-confirm')!, 'Sufficiently-Long-Password-123')
  })
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(complete).not.toHaveBeenCalled()
  expect(host.textContent).toContain('antes da confirmação')
  expect(host.querySelector('input[type="password"]')).toBeNull()
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(complete).toHaveBeenCalledOnce()
  expect(mocks.updateUser).toHaveBeenCalledOnce()
  expect(calls.filter(call => call.url.endsWith('/claim'))).toHaveLength(1)
  expect(calls.filter(call => call.url.endsWith('/activate')).map(call => call.init)).toEqual([
    expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer refreshed-session' }), body: JSON.stringify({ invitation_id: invitationId, claim_token: 'retry-the-same-claim' }) }),
    expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer refreshed-session' }), body: JSON.stringify({ invitation_id: invitationId, claim_token: 'retry-the-same-claim' }) }),
  ])
})

test('dois submits no mesmo evento reservam e alteram a senha uma única vez', async () => {
  const fetchMock = vi.fn(async (input: string) => new Response(input.endsWith('/claim')
    ? '{"claim_token":"single-claim"}' : input.endsWith('/eligibility') ? '{"eligible":true}' : '{"status":"active"}'))
  vi.stubGlobal('fetch', fetchMock)
  await act(async () => root.render(<MemoryRouter><InvitePasswordPage invitationId={invitationId} token={token} onComplete={vi.fn()}/></MemoryRouter>))
  await vi.waitFor(() => expect(host.querySelector('form')).not.toBeNull())
  await act(async () => {
    setInput(host.querySelector<HTMLInputElement>('#invite-password')!, 'Sufficiently-Long-Password-123')
    setInput(host.querySelector<HTMLInputElement>('#invite-password-confirm')!, 'Sufficiently-Long-Password-123')
  })
  await act(async () => {
    host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  })
  expect(mocks.updateUser).toHaveBeenCalledOnce()
  expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/claim'))).toHaveLength(1)
})
