import type { Session, SupabaseClient } from '@supabase/supabase-js'

type Credentials =
  | { kind: 'implicit'; accessToken: string; refreshToken: string }
  | { kind: 'otp'; tokenHash: string; type: 'invite' | 'recovery' }
  | { kind: 'pkce'; code: string }
  | { kind: 'stored' }
  | { kind: 'invalid' }

export type InvitationCallback = { invitationId: string; cleanPath: string; credentials: Credentials }

export function parseInvitationCallback(rawUrl: string): InvitationCallback {
  const url = new URL(rawUrl)
  const query = url.searchParams
  const hash = new URLSearchParams(url.hash.slice(1))
  const invitationId = query.get('invitation_id') ?? ''
  const validId = /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(invitationId)
  const cleanPath = url.pathname + (validId ? `?invitation_id=${encodeURIComponent(invitationId)}` : '')
  const invalid: InvitationCallback = { invitationId, cleanPath, credentials: { kind: 'invalid' } }
  if (!validId || query.has('error') || query.has('error_code') || hash.has('error') || hash.has('error_code')) return invalid

  const code = query.get('code')
  const tokenHash = query.get('token_hash')
  const accessToken = hash.get('access_token')
  const refreshToken = hash.get('refresh_token')
  const type = query.get('type') ?? hash.get('type')
  const methods = Number(!!code) + Number(!!tokenHash) + Number(!!accessToken || !!refreshToken)
  if (methods > 1) return invalid
  if (code) return { invitationId, cleanPath, credentials: { kind: 'pkce', code } }
  if (tokenHash && (type === 'invite' || type === 'recovery')) return { invitationId, cleanPath, credentials: { kind: 'otp', tokenHash, type } }
  if (accessToken && refreshToken && (type === 'invite' || type === 'recovery')) {
    return { invitationId, cleanPath, credentials: { kind: 'implicit', accessToken, refreshToken } }
  }
  if (methods || type) return invalid
  return { invitationId, cleanPath, credentials: { kind: 'stored' } }
}

export async function restoreInvitationSession(client: SupabaseClient, callback: InvitationCallback): Promise<Session> {
  const credentials = callback.credentials
  if (credentials.kind === 'invalid') throw new Error('invalid_invitation_link')
  const result = credentials.kind === 'implicit'
    ? await client.auth.setSession({ access_token: credentials.accessToken, refresh_token: credentials.refreshToken })
    : credentials.kind === 'otp'
      ? await client.auth.verifyOtp({ token_hash: credentials.tokenHash, type: credentials.type })
      : credentials.kind === 'pkce'
        ? await client.auth.exchangeCodeForSession(credentials.code)
        : await client.auth.getSession()
  const session = result.data.session
  if (result.error || !session || (session.expires_at ?? 0) * 1000 <= Date.now()) throw new Error('invalid_invitation_session')
  const verified = await client.auth.getUser(session.access_token)
  if (verified.error || verified.data.user?.id !== session.user.id) throw new Error('invalid_invitation_identity')
  return session
}
