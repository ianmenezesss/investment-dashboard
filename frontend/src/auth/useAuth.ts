import { useCallback, useEffect, useRef, useState } from 'react'
import type { Session, SupabaseClient } from '@supabase/supabase-js'
import { getSupabase } from './supabase'

type Status = 'loading' | 'anonymous' | 'authenticated'
export function useAuth(enabled: boolean, clearPrivate: () => void) {
  const [session, setSession] = useState<Session | null>(null)
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState('')
  const generation = useRef(0)
  const client = useRef<SupabaseClient | null>(null)
  const clear = useRef(clearPrivate)
  clear.current = clearPrivate
  const activeSession = useRef<Session | null>(null)
  const blocked = useRef(false)

  const accept = useCallback((next: Session | null) => {
    // SIGNED_IN also reconfirms a session on tab focus; it is not an account switch.
    if (activeSession.current?.user.id !== next?.user.id) clear.current()
    activeSession.current = next
    setSession(next); setStatus(next ? 'authenticated' : 'anonymous')
  }, [])

  const ending = useRef(false)
  const expire = useCallback(() => {
    if (ending.current) return
    const current = ++generation.current
    blocked.current = true
    ending.current = true
    activeSession.current = null
    setSession(null); setStatus('loading'); setError('Sua sessão expirou. Entre novamente.'); clear.current()
    void (async () => {
      try { await client.current?.auth.signOut({ scope: 'local' }) } catch { /* falhar fechado */ }
      finally {
        if (generation.current === current) { window.sessionStorage.removeItem('investment-auth-session'); setStatus('anonymous') }
        ending.current = false
      }
    })()
  }, [])

  useEffect(() => {
    const current = ++generation.current
    let alive = true
    if (!enabled) { accept(null); return }
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
        accept(next); setError('')
      } catch {
        if (alive && revision === generation.current && !blocked.current) expire()
      }
    }
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
    return () => { alive = false; generation.current++; pending.forEach(timer => window.clearTimeout(timer)); subscription.unsubscribe() }
  }, [enabled, expire, accept])

  useEffect(() => {
    if (!session?.expires_at) return
    const timeout = window.setTimeout(expire, Math.max(0, session.expires_at * 1000 - Date.now()))
    return () => window.clearTimeout(timeout)
  }, [session, expire])

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
      if (current === generation.current) accept(data.session)
    } catch {
      if (current === generation.current) { setStatus('anonymous'); setError('Não foi possível conectar ao serviço de autenticação.') }
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

  return { session, status, error, login, logout, expire }
}
