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

  const ending = useRef(false)
  const expire = useCallback(() => {
    const current = ++generation.current
    ending.current = true
    setSession(null); setStatus('loading'); setError('Sua sessão expirou. Entre novamente.'); clear.current()
    client.current?.auth.stopAutoRefresh()
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
    if (!enabled) { setSession(null); setStatus('anonymous'); return }
    let sdk: SupabaseClient | null
    try { sdk = getSupabase(); client.current = sdk } catch (e) { setError((e as Error).message); setStatus('anonymous'); return }
    if (!sdk) { setStatus('anonymous'); return }
    setStatus('loading'); setError('')
    // Callback síncrono: não chamar operações async do SDK dentro do lock de auth.
    const { data: { subscription } } = sdk.auth.onAuthStateChange((event, next) => {
      if (!alive || ending.current || event === 'INITIAL_SESSION') return
      generation.current++
      clear.current()
      setSession(next); setStatus(next ? 'authenticated' : 'anonymous')
      if (event === 'SIGNED_OUT') setError('Sessão encerrada. Entre novamente.')
      else setError('')
    })
    sdk.auth.startAutoRefresh()
    void (async () => {
      try {
        const { data, error: storedError } = await sdk.auth.getSession()
        if (storedError) throw storedError
        if (!data.session) { if (alive && current === generation.current) setStatus('anonymous'); return }
        // Storage recupera a sessão, mas não é prova de identidade.
        const verified = await sdk.auth.getUser(data.session.access_token)
        if (verified.error || verified.data.user?.id !== data.session.user.id || (data.session.expires_at ?? 0) * 1000 <= Date.now()) throw new Error('expired')
        if (alive && current === generation.current) { clear.current(); setSession(data.session); setStatus('authenticated') }
      } catch {
        if (alive && current === generation.current) expire()
      }
    })()
    return () => { alive = false; generation.current++; subscription.unsubscribe(); sdk.auth.stopAutoRefresh() }
  }, [enabled, expire])

  useEffect(() => {
    if (!session?.expires_at) return
    const timeout = window.setTimeout(expire, Math.max(0, session.expires_at * 1000 - Date.now()))
    return () => window.clearTimeout(timeout)
  }, [session, expire])

  async function login(email: string, password: string) {
    if (!enabled || !client.current) return
    const current = ++generation.current
    setStatus('loading'); setError(''); setSession(null); clear.current()
    try {
      const { data, error: loginError } = await client.current.auth.signInWithPassword({ email: email.trim(), password })
      if (loginError || !data.session) {
        if (current === generation.current) { setStatus('anonymous'); setError('Não foi possível entrar. Confira suas credenciais e tente novamente.') }
        return
      }
      // SIGNED_IN pode atualizar o estado antes desta Promise retornar.
      if (current === generation.current) { setSession(data.session); setStatus('authenticated') }
      client.current.auth.startAutoRefresh()
    } catch {
      if (current === generation.current) { setStatus('anonymous'); setError('Não foi possível conectar ao serviço de autenticação.') }
    }
  }

  async function logout() {
    const current = ++generation.current
    ending.current = true
    setSession(null); setStatus('loading'); setError(''); clear.current()
    client.current?.auth.stopAutoRefresh()
    try { const result = await client.current?.auth.signOut({ scope: 'local' }); if (result?.error) throw result.error }
    catch { setError('A sessão foi removida deste navegador. Não foi possível confirmar o encerramento no servidor.') }
    finally {
      if (current === generation.current) { window.sessionStorage.removeItem('investment-auth-session'); setStatus('anonymous') }
      ending.current = false
    }
  }

  return { session, status, error, login, logout, expire }
}
