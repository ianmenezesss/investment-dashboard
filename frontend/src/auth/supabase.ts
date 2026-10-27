import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { PUBLIC_DEMO, SUPABASE_AUTH } from '../runtime'

let instance: SupabaseClient | undefined
export function getSupabase(): SupabaseClient | null {
  if (PUBLIC_DEMO || !SUPABASE_AUTH) return null
  if (instance) return instance
  const url = import.meta.env.VITE_SUPABASE_URL ?? ''
  const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? ''
  let validUrl = false
  try { const parsed = new URL(url); validUrl = parsed.protocol === 'https:' && !parsed.username && !parsed.password && !parsed.search && !parsed.hash && parsed.pathname === '/' } catch { /* configuração inválida */ }
  if (!validUrl || !key.startsWith('sb_publishable_')) {
    throw new Error('Configure VITE_SUPABASE_URL e VITE_SUPABASE_PUBLISHABLE_KEY para entrar. Use apenas a Publishable Key pública.')
  }
  instance = createClient(url, key, { auth: {
    storage: window.sessionStorage,
    storageKey: 'investment-auth-session',
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: false,
  } })
  return instance
}
