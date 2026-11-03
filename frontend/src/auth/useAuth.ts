import { useCallback, useEffect, useRef, useState } from 'react'
import type { Session, SupabaseClient } from '@supabase/supabase-js'
import { getSupabase } from './supabase'
import { apiBase } from '../runtime'

type Status = 'loading' | 'anonymous' | 'authenticated'
type AccessStatus = 'active' | 'trial_expired'
class ActivationError extends Error {
  constructor(public status: number) { super('account_activation_failed') }
}
export function useAuth(enabled: boolean, clearPrivate: () => void, skipActivation = false) {
  const [session, setSession] = useState<Session | null>(null)
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState('')
  const [accessStatus, setAccessStatus] = useState<AccessStatus>('active')
  const [trialExpiresAt, setTrialExpiresAt] = useState<number | null>(null)
  const [accessActivatedAt, setAccessActivatedAt] = useState<string | null>(null)
  const generation = useRef(0)
  const client = useRef<SupabaseClient | null>(null)
  const clear = useRef(clearPrivate)
  clear.current = clearPrivate
  const activeSession = useRef<Session | null>(null)
  const blocked = useRef(false)
  const verifyLogin = useRef<((next: Session, revision: number) => Promise<void>) | null>(null)

  const accept = useCallback((next: Session | null) => {
    // SIGNED_IN also reconfirms a session on tab focus; it is not an account switch.
    if (activeSession.current?.user.id !== next?.user.id) { clear.current(); setAccessStatus('active'); setTrialExpiresAt(null); setAccessActivatedAt(null) }
    activeSession.current = next
    setSession(next); setStatus(next ? 'authenticated' : 'anonymous')
  }, [])

  const ending = useRef(false)
  const endSession = useCallback((message: string) => {
    if (ending.current) return
    const current = ++generation.current
    blocked.current = true
    ending.current = true
    activeSession.current = null
    setSession(null); setStatus('loading'); setError(message); clear.current()
    void (async () => {
      try { await client.current?.auth.signOut({ scope: 'local' }) } catch { /* falhar fechado */ }
      finally {
        if (generation.current === current) { window.sessionStorage.removeItem('investment-auth-session'); setStatus('anonymous') }
        ending.current = false
      }
    })()
  }, [])
  const expire = useCallback(() => endSession('Sua sessão expirou. Entre novamente.'), [endSession])

  const markTrialExpired = useCallback(() => {
    if (accessStatus === 'trial_expired') return
    setAccessStatus('trial_expired'); clear.current()
  }, [accessStatus])

  useEffect(() => {
    const current = ++generation.current
    let alive = true
    if (!enabled) { verifyLogin.current = null; accept(null); return }
    blocked.current = false
    let sdk: SupabaseClient | null
    try { sdk = getSupabase(); client.current = sdk } catch (e) { setError((e as Error).message); setStatus('anonymous'); return }
    if (!sdk) { setStatus('anonymous'); return }
    setStatus('loading'); setError('')
    const pending = new Set<number>()
    const verify = async (next: Session, revision: number) => {
      try {
        const verified = await sdk.auth.getUser(next.access_token)
        if (!alive || revision !== generation.current || blocked.current) return
        if (verified.error || verified.data.user?.id !== next.user.id || (next.expires_at ?? 0) * 1000 <= Date.now()) throw new Error('expired')
        if (skipActivation) {
          accept(next); setAccessStatus('active'); setTrialExpiresAt(null); setError('')
          return
        }
        const activation = await fetch(`${apiBase()}/api/account/activate`, { method: 'POST', headers: { Authorization: `Bearer ${next.access_token}` } })
        if (!activation.ok) throw new ActivationError(activation.status)
        const activationState = await activation.json() as { status?: string; trial_expires_at?: string; activated_at?: string }
        accept(next); setAccessStatus(activationState.status === 'trial_expired' || activationState.status === 'expired' ? 'trial_expired' : 'active')
        const expiration = activationState.trial_expires_at ? Date.parse(activationState.trial_expires_at) : NaN
        setTrialExpiresAt(Number.isFinite(expiration) ? expiration : null); setAccessActivatedAt(activationState.activated_at ?? null); setError('')
      } catch (cause) {
        if (!alive || revision !== generation.current || blocked.current) return
        if (cause instanceof ActivationError && cause.status === 403) {
          endSession('Sua conta não está autorizada a acessar esta carteira. Solicite acesso ao administrador.')
        } else if (cause instanceof TypeError || cause instanceof ActivationError && cause.status !== 401) {
          accept(null); setError('Não foi possível confirmar a autorização da conta. Tente entrar novamente em instantes.')
        } else expire()
      }
    }
    verifyLogin.current = verify
    // Callback síncrono: não chamar operações async do SDK dentro do lock de auth.
    const { data: { subscription } } = sdk.auth.onAuthStateChange((event, next) => {
      if (!alive || ending.current || event === 'INITIAL_SESSION') return
      if (event === 'SIGNED_OUT') {
        generation.current++; blocked.current = true
        accept(null); setError('Sessão encerrada. Entre novamente.'); return
      }
      if (blocked.current || !next) return
      const revision = ++generation.current
      if (activeSession.current?.user.id === next.user.id && (next.expires_at ?? 0) * 1000 > Date.now()) {
        accept(next); setError('')
      } else {
        // A new identity must be verified; never reuse the previous account's data.
        accept(null); setStatus('loading')
        // Run SDK calls outside the synchronous auth callback/lock.
        const timer = window.setTimeout(() => { pending.delete(timer); void verify(next, revision) }, 0)
        pending.add(timer)
      }
    })
    void (async () => {
      try {
        const { data, error: storedError } = await sdk.auth.getSession()
        if (storedError) throw storedError
        if (!alive || current !== generation.current) return
        if (!data.session) { accept(null); return }
        // Storage recupera a sessão, mas não é prova de identidade.
        await verify(data.session, current)
      } catch {
        if (alive && current === generation.current) expire()
      }
    })()
    return () => { alive = false; verifyLogin.current = null; generation.current++; pending.forEach(timer => window.clearTimeout(timer)); subscription.unsubscribe() }
  }, [enabled, expire, endSession, accept, skipActivation])

  useEffect(() => {
    if (!session?.expires_at) return
    const timeout = window.setTimeout(expire, Math.max(0, session.expires_at * 1000 - Date.now()))
    return () => window.clearTimeout(timeout)
  }, [session, expire])

  useEffect(() => {
    if (!session || accessStatus !== 'active' || trialExpiresAt === null) return
    const timeout = window.setTimeout(() => {
      if (trialExpiresAt <= Date.now()) markTrialExpired()
    }, Math.max(0, trialExpiresAt - Date.now()))
    return () => window.clearTimeout(timeout)
  }, [session, accessStatus, trialExpiresAt, markTrialExpired])

  async function login(email: string, password: string) {
    if (!enabled || !client.current) return
    blocked.current = false
    const current = ++generation.current
    activeSession.current = null
    setStatus('loading'); setError(''); setSession(null); clear.current()
    try {
      const { data, error: loginError } = await client.current.auth.signInWithPassword({ email: email.trim(), password })
      if (loginError || !data.session) {
        if (current === generation.current) { setStatus('anonymous'); setError('Não foi possível entrar. Confira suas credenciais e tente novamente.') }
        return
      }
      // SIGNED_IN pode atualizar o estado antes desta Promise retornar.
      if (current === generation.current) await verifyLogin.current?.(data.session, current)
    } catch {
      if (current === generation.current) { setStatus('anonymous'); setError('Não foi possível conectar ao serviço de autenticação.') }
    }
  }

  async function reauthenticate(password: string) {
    const email = session?.user.email
    if (!enabled || !client.current || !email) throw new Error('Não foi possível confirmar esta sessão.')
    try {
      const { data, error: authError } = await client.current.auth.signInWithPassword({ email, password })
      if (authError || !data.session || data.session.user.id !== session?.user.id) {
        throw new Error('Senha incorreta ou confirmação adicional necessária.')
      }
      accept(data.session)
      return data.session
    } catch (cause) {
      if (cause instanceof Error && cause.message.includes('confirmação adicional')) throw cause
      throw new Error('Não foi possível confirmar a senha. Confira e tente novamente.')
    }
  }

  async function logout() {
    const current = ++generation.current
    blocked.current = true
    ending.current = true
    activeSession.current = null
    setSession(null); setStatus('loading'); setError(''); clear.current()
    try { const result = await client.current?.auth.signOut({ scope: 'local' }); if (result?.error) throw result.error }
    catch { setError('A sessão foi removida deste navegador. Não foi possível confirmar o encerramento no servidor.') }
    finally {
      if (current === generation.current) { window.sessionStorage.removeItem('investment-auth-session'); setStatus('anonymous') }
      ending.current = false
    }
  }

  return { session, status, error, login, reauthenticate, logout, expire, accessStatus, trialExpiresAt, accessActivatedAt, markTrialExpired }
}
