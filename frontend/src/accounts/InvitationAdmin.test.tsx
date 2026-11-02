import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, expect, test, vi } from 'vitest'
import { InvitationAdmin } from './InvitationAdmin'

const token = 'fictional-invitation-ui-token'
type Page<T> = { items: T[]; page: number; page_size: number; total: number; total_pages: number }
let host: HTMLDivElement
let root: Root

function paged<T>(items: T[] = [], total = items.length, page = 1): Page<T> {
  return { items, page, page_size: 5, total, total_pages: total ? Math.ceil(total / 5) : 0 }
}

async function renderAdmin() {
  host = document.createElement('div'); document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => root.render(<InvitationAdmin token={token}/>))
  await vi.waitFor(() => expect(host.textContent).toContain('Página'))
  const summary = [...host.querySelectorAll('summary')].find(item => item.textContent === 'Administração')
  if (summary) await act(async () => summary.click())
}

async function changeInput(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  await act(async () => {
    setter.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
    input.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

afterEach(async () => {
  if (root) await act(async () => root.unmount())
  host?.remove()
  vi.unstubAllGlobals()
})

test('painel separa Contas, Convites e Solicitações e consulta páginas e filtros no backend', async () => {
  const member = { user_id: 'user-1', email: 'member@example.test', account_label: 'member@example.test', email_source: 'membership', status: 'active', access_type: 'permanent', activated_at: null, trial_expires_at: null, can_reactivate: false, can_revoke: true, protected_admin: false }
  const invite = { id: 'invite-1', email: 'person@example.test', created_at: '2026-11-01T10:00:00Z', expires_at: '2026-11-08T10:00:00Z', status: 'pending', email_send_status: 'requested', email_send_attempts: 1, send_history: [] }
  const request = { id: 'request-1', email: 'visitor@example.test', requested_at: '2026-11-01T10:00:00Z', status: 'pending' }
  const calls: { url: URL; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    const url = new URL(input, 'http://localhost'); calls.push({ url, init })
    if (url.pathname.endsWith('/members')) return new Response(JSON.stringify(paged([member], 7, Number(url.searchParams.get('page')))), { status: 200 })
    if (url.pathname.endsWith('/invitations')) return new Response(JSON.stringify(paged([invite], 1)), { status: 200 })
    if (url.pathname.endsWith('/access-requests')) return new Response(JSON.stringify(paged([request], 1)), { status: 200 })
    return new Response('{}', { status: 200 })
  }))
  await renderAdmin()

  expect(host.textContent).toContain('member@example.test')
  expect(host.textContent).toContain('1–5 de 7')
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent?.includes('Próxima'))!.click())
  await vi.waitFor(() => expect(calls.some(call => call.url.pathname.endsWith('/members') && call.url.searchParams.get('page') === '2')).toBe(true))

  await changeInput(host.querySelector('#admin-search')!, 'member@')
  await vi.waitFor(() => expect(calls.some(call => call.url.searchParams.get('search') === 'member@')).toBe(true))
  const status = host.querySelector('#admin-status') as HTMLSelectElement
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!.call(status, 'active')
    status.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await vi.waitFor(() => expect(calls.some(call => call.url.pathname.endsWith('/members') && call.url.searchParams.get('status') === 'active')).toBe(true))

  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent?.includes('Convites'))!.click())
  await vi.waitFor(() => expect(host.textContent).toContain('person@example.test'))
  expect(host.textContent).toContain('Solicitação aceita pelo Supabase')
  const invitationStatus = host.querySelector('#admin-status') as HTMLSelectElement
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!.call(invitationStatus, 'pending')
    invitationStatus.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await vi.waitFor(() => expect(calls.some(call => call.url.pathname.endsWith('/invitations') && call.url.searchParams.get('status') === 'pending')).toBe(true))
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent?.includes('Solicitações'))!.click())
  await vi.waitFor(() => expect(host.textContent).toContain('visitor@example.test'))
  expect(calls.every(call => (call.init?.headers as Record<string, string>)?.Authorization === `Bearer ${token}`)).toBe(true)
})

test('revogação da conta exige confirmação explícita e atualiza a lista', async () => {
  const member = { user_id: 'user-1', email: 'member@example.test', account_label: 'member@example.test', email_source: 'membership', status: 'active', access_type: 'permanent', activated_at: null, trial_expires_at: null, can_reactivate: false, can_revoke: true, protected_admin: false }
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    calls.push({ url: input, init })
    const path = new URL(input, 'http://localhost').pathname
    if (path.endsWith('/members')) return new Response(JSON.stringify(paged([member], 1)), { status: 200 })
    if (path.endsWith('/invitations') || path.endsWith('/access-requests')) return new Response(JSON.stringify(paged()), { status: 200 })
    if (path.endsWith('/revoke')) return new Response('{"status":"revoked"}', { status: 200 })
    return new Response('{}', { status: 200 })
  }))
  await renderAdmin()
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent === 'Revogar acesso')!.click())
  expect(document.body.textContent).toContain('Revogar acesso à plataforma?')
  expect(calls.some(call => call.url.endsWith('/revoke'))).toBe(false)
  await act(async () => [...document.body.querySelectorAll('button')].find(button => button.textContent?.includes('Revogar acesso') && button.closest('[role="alertdialog"]'))!.click())
  await vi.waitFor(() => expect(calls.some(call => call.url.endsWith('/members/user-1/revoke') && call.init?.method === 'POST')).toBe(true))
  await vi.waitFor(() => expect(host.textContent).toContain('Acesso financeiro revogado'))
})

test('convite permanente é enviado pelo endpoint autenticado e a entrega não é presumida', async () => {
  const invite = { id: 'invite-new', email: 'new@example.test', created_at: '2026-11-01T10:00:00Z', expires_at: '2026-11-08T10:00:00Z', status: 'pending', email_send_status: 'requested', email_send_attempts: 1, send_history: [] }
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    calls.push({ url: input, init })
    const path = new URL(input, 'http://localhost').pathname
    if (path.endsWith('/members') || path.endsWith('/access-requests')) return new Response(JSON.stringify(paged()), { status: 200 })
    if (path.endsWith('/invitations') && init?.method === 'POST') return new Response(JSON.stringify(invite), { status: 201 })
    if (path.endsWith('/invitations')) return new Response(JSON.stringify(paged([invite], 1)), { status: 200 })
    return new Response('{}', { status: 200 })
  }))
  await renderAdmin()
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent?.includes('Convites'))!.click())
  await vi.waitFor(() => expect(host.querySelector('#invite-email')).not.toBeNull())
  await changeInput(host.querySelector('#invite-email') as HTMLInputElement, 'new@example.test')
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  await vi.waitFor(() => expect(host.textContent).toContain('A entrega do e-mail não é confirmada'))
  expect(calls.some(call => call.url.endsWith('/invitations') && call.init?.method === 'POST'
    && JSON.parse(String(call.init.body)).expires_in_days === 7)).toBe(true)
  expect(calls.every(call => (call.init?.headers as Record<string, string>)?.Authorization === `Bearer ${token}`)).toBe(true)
})

test('falha no envio apresenta erro e não mostra confirmação de sucesso', async () => {
  const invite = { id: 'invite-1', email: 'person@example.test', created_at: '2026-11-01T10:00:00Z', expires_at: '2026-11-08T10:00:00Z', status: 'pending', email_send_status: 'failed', email_send_attempts: 1, send_history: [{ attempted_at: '2026-11-01T10:00:00Z', outcome: 'failed', method: 'invite', http_status: 429, provider_code: 'over_email_send_rate_limit' }] }
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    calls.push({ url: input, init })
    const path = new URL(input, 'http://localhost').pathname
    if (path.endsWith('/members') || path.endsWith('/access-requests')) return new Response(JSON.stringify(paged()), { status: 200 })
    if (path.endsWith('/invitations') && !init?.method) return new Response(JSON.stringify(paged([invite], 1)), { status: 200 })
    if (path.endsWith('/resend')) return new Response('{"detail":"Limite do Supabase atingido"}', { status: 502 })
    return new Response(JSON.stringify(paged([invite], 1)), { status: 200 })
  }))
  await renderAdmin()
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent?.includes('Convites'))!.click())
  await vi.waitFor(() => expect(host.textContent).toContain('person@example.test'))
  expect(host.textContent).toContain('HTTP 429')
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent === 'Tentar envio novamente')!.click())
  await vi.waitFor(() => expect(host.textContent).toContain('Limite do Supabase atingido'))
  expect(host.textContent).not.toContain('Nova tentativa solicitada')
  expect(calls.some(call => call.url.endsWith('/invitations/invite-1/resend') && call.init?.method === 'POST')).toBe(true)
})

test('resultado incerto exige confirmação explícita antes de um possível reenvio', async () => {
  const invite = { id: 'invite-uncertain', email: 'person@example.test', created_at: '2026-11-01T10:00:00Z', expires_at: '2026-11-08T10:00:00Z', status: 'pending', email_send_status: 'uncertain', email_send_attempts: 1, send_history: [{ attempted_at: '2026-11-01T10:00:00Z', outcome: 'uncertain', method: 'invite', http_status: null, provider_code: 'network_or_timeout' }] }
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    calls.push({ url: input, init })
    const path = new URL(input, 'http://localhost').pathname
    if (path.endsWith('/members') || path.endsWith('/access-requests')) return new Response(JSON.stringify(paged()), { status: 200 })
    if (path.endsWith('/invitations') && !init?.method) return new Response(JSON.stringify(paged([invite], 1)), { status: 200 })
    if (path.endsWith('/resend')) return new Response('{"status":"requested"}', { status: 202 })
    return new Response(JSON.stringify(paged([invite], 1)), { status: 200 })
  }))
  await renderAdmin()
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent?.includes('Convites'))!.click())
  await vi.waitFor(() => expect(host.textContent).toContain('person@example.test'))
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent === 'Tentar envio novamente')!.click())
  expect(host.textContent).toContain('O pedido anterior teve resultado incerto')
  expect(calls.some(call => call.init?.method === 'POST')).toBe(false)
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent === 'Confirmar nova tentativa')!.click())
  await vi.waitFor(() => expect(calls.some(call => call.url.endsWith('/invitations/invite-uncertain/resend') && call.init?.method === 'POST')).toBe(true))
})

test('aprovação de solicitação passa pelo backend e atualiza o estado visível', async () => {
  const request = { id: 'request-1', email: 'visitor@example.test', requested_at: '2026-11-01T10:00:00Z', status: 'pending' }
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    calls.push({ url: input, init })
    const path = new URL(input, 'http://localhost').pathname
    if (path.endsWith('/members') || path.endsWith('/invitations')) return new Response(JSON.stringify(paged()), { status: 200 })
    if (path.endsWith('/access-requests')) return new Response(JSON.stringify(paged([request], 1)), { status: 200 })
    if (path.endsWith('/approve')) return new Response('{"status":"approved","delivery_confirmed":false}', { status: 200 })
    return new Response('{}', { status: 200 })
  }))
  await renderAdmin()
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent?.includes('Solicitações'))!.click())
  await vi.waitFor(() => expect(host.textContent).toContain('visitor@example.test'))
  const before = calls.filter(call => new URL(call.url, 'http://localhost').pathname.endsWith('/access-requests')).length
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent === 'Aprovar e enviar convite')!.click())
  await vi.waitFor(() => expect(host.textContent).toContain('entrega não confirmada'))
  expect(calls.some(call => call.url.endsWith('/access-requests/request-1/approve') && call.init?.method === 'POST')).toBe(true)
  expect(calls.filter(call => new URL(call.url, 'http://localhost').pathname.endsWith('/access-requests')).length).toBeGreaterThan(before)
})
