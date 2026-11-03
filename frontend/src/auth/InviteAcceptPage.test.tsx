import { act, StrictMode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ auth: { setSession: vi.fn(), getUser: vi.fn(), getSession: vi.fn() } }))
vi.mock('./supabase', () => ({ getSupabase: () => ({ auth: mocks.auth }) }))
vi.mock('../runtime', () => ({ apiBase: () => '' }))
import { InviteAcceptPage } from './InviteAcceptPage'

const invitationId = '55555555-5555-4555-8555-555555555555'
const path = `/invite/accept?invitation_id=${invitationId}`
let host: HTMLDivElement
let root: Root

beforeEach(() => {
  vi.clearAllMocks()
  const session = { access_token: 'verified-access', expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: 'verified-user' } }
  mocks.auth.setSession.mockResolvedValue({ data: { session }, error: null })
  mocks.auth.getUser.mockResolvedValue({ data: { user: session.user }, error: null })
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})

test('StrictMode consome o link uma vez e remove tokens antes da chamada de elegibilidade', async () => {
  const callbackPath = `${path}#access_token=mail-access&refresh_token=mail-refresh&type=invite`
  window.history.replaceState({}, '', callbackPath)
  const fetchMock = vi.fn(async (_input: string) => {
    expect(window.location.hash).toBe('')
    expect(window.location.search).toBe(`?invitation_id=${invitationId}`)
    return new Response('{"eligible":true}')
  })
  vi.stubGlobal('fetch', fetchMock)
  await act(async () => root.render(<StrictMode><MemoryRouter initialEntries={[callbackPath]}><InviteAcceptPage/></MemoryRouter></StrictMode>))
  await vi.waitFor(() => expect(host.querySelector('#invite-password')).not.toBeNull())
  expect(mocks.auth.setSession).toHaveBeenCalledOnce()
  expect(mocks.auth.getUser).toHaveBeenCalledOnce()
  expect(fetchMock.mock.calls.every(([input]) => String(input).includes('/eligibility'))).toBe(true)
  expect(host.textContent).not.toMatch(/mail-access|mail-refresh|verified-access/)
})

test('erro recebido do Supabase elimina a URL sensível e oferece orientação sem refletir detalhes', async () => {
  const callbackPath = `${path}#error=access_denied&error_description=secret-provider-details&access_token=expired-access`
  window.history.replaceState({}, '', callbackPath)
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  await act(async () => root.render(<MemoryRouter initialEntries={[callbackPath]}><InviteAcceptPage/></MemoryRouter>))
  await vi.waitFor(() => expect(host.querySelector('[role="alert"]')).not.toBeNull())
  expect(window.location.hash).toBe('')
  expect(host.textContent).not.toMatch(/secret-provider-details|expired-access/)
  expect(host.textContent).toContain('já foi utilizado')
  expect(mocks.auth.getSession).not.toHaveBeenCalled()
  expect(fetchMock).not.toHaveBeenCalled()
})
