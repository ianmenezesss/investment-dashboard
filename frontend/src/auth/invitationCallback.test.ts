import type { SupabaseClient } from '@supabase/supabase-js'
import { expect, test, vi } from 'vitest'
import { parseInvitationCallback, restoreInvitationSession } from './invitationCallback'

const id = '55555555-5555-4555-8555-555555555555'
const base = `https://private.example/invite/accept?invitation_id=${id}`
const session = { access_token: 'verified-access', refresh_token: 'verified-refresh', expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: 'user-a' } }

function sdk() {
  const result = { data: { session }, error: null }
  return { auth: {
    setSession: vi.fn().mockResolvedValue(result), verifyOtp: vi.fn().mockResolvedValue(result),
    exchangeCodeForSession: vi.fn().mockResolvedValue(result), getSession: vi.fn().mockResolvedValue(result),
    getUser: vi.fn().mockResolvedValue({ data: { user: session.user }, error: null }),
  } }
}

test.each(['invite', 'recovery'])('callback implicit %s é verificado e gera URL limpa sem credenciais', async type => {
  const client = sdk()
  const callback = parseInvitationCallback(`${base}#access_token=mail-access&refresh_token=mail-refresh&type=${type}`)
  expect(callback.cleanPath).toBe(`/invite/accept?invitation_id=${id}`)
  const result = await restoreInvitationSession(client as unknown as SupabaseClient, callback)
  expect(result).toBe(session)
  expect(client.auth.setSession).toHaveBeenCalledWith({ access_token: 'mail-access', refresh_token: 'mail-refresh' })
  expect(client.auth.getUser).toHaveBeenCalledWith('verified-access')
  expect(client.auth.verifyOtp).not.toHaveBeenCalled()
})

test.each(['invite', 'recovery'])('template token_hash %s utiliza o tipo correspondente uma única vez', async type => {
  const client = sdk()
  await restoreInvitationSession(client as unknown as SupabaseClient, parseInvitationCallback(`${base}&token_hash=mail-hash&type=${type}`))
  expect(client.auth.verifyOtp).toHaveBeenCalledWith({ token_hash: 'mail-hash', type })
  expect(client.auth.getSession).not.toHaveBeenCalled()
})

test('callback PKCE troca código e exige identidade confirmada', async () => {
  const client = sdk()
  await restoreInvitationSession(client as unknown as SupabaseClient, parseInvitationCallback(`${base}&code=auth-code`))
  expect(client.auth.exchangeCodeForSession).toHaveBeenCalledWith('auth-code')
  expect(client.auth.getUser).toHaveBeenCalledOnce()
})

test.each([
  `${base}#error=access_denied&error_description=private-error&access_token=old-token`,
  `${base}&code=auth-code&token_hash=mail-hash&type=invite`,
  `${base}&token_hash=mail-hash&type=signup`,
  `${base}#access_token=mail-access&type=invite`,
  'https://private.example/invite/accept#access_token=mail-access&refresh_token=mail-refresh&type=invite',
])('callback inválido não reaproveita sessão do navegador: %s', async url => {
  const client = sdk()
  const callback = parseInvitationCallback(url)
  await expect(restoreInvitationSession(client as unknown as SupabaseClient, callback)).rejects.toThrow()
  expect(callback.cleanPath).not.toMatch(/token|code=|error/)
  expect(client.auth.getSession).not.toHaveBeenCalled()
  expect(client.auth.setSession).not.toHaveBeenCalled()
})

test('erro de código consumido não cai na sessão anterior', async () => {
  const client = sdk()
  client.auth.exchangeCodeForSession.mockResolvedValue({ data: { session: null }, error: new Error('used') })
  await expect(restoreInvitationSession(client as unknown as SupabaseClient, parseInvitationCallback(`${base}&code=used-code`))).rejects.toThrow()
  expect(client.auth.getSession).not.toHaveBeenCalled()
})

test('sessão recuperada cuja identidade diverge de getUser é recusada', async () => {
  const client = sdk()
  client.auth.getUser.mockResolvedValue({ data: { user: { id: 'different-user' } }, error: null })
  await expect(restoreInvitationSession(client as unknown as SupabaseClient, parseInvitationCallback(base))).rejects.toThrow('invalid_invitation_identity')
})
