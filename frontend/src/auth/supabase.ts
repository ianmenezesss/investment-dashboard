import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { PUBLIC_DEMO, SUPABASE_AUTH } from '../runtime'

let instance: SupabaseClient | undefined
export function getSupabase(): SupabaseClient | null {
  if (PUBLIC_DEMO || !SUPABASE_AUTH) return null
  if (instance) return instance
  const url = (import.meta.env.VITE_SUPABASE_URL ?? '').trim()
  const key = (import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? '').trim()
  let validUrl = false
  try { const parsed = new URL(url); validUrl = parsed.protocol === 'https:' && !parsed.username && !parsed.password && !parsed.search && !parsed.hash && parsed.pathname === '/' } catch { /* configuração inválida */ }
  if (!url || !key) throw new Error('O acesso privado ainda não está configurado. Preencha frontend/.env.local com a Project URL e a Publishable Key e reinicie o Vite.')
  if (!validUrl) throw new Error('A Project URL deve conter somente a origem HTTPS do Supabase, sem /rest/v1 ou /auth/v1. Corrija frontend/.env.local e reinicie o Vite.')
  if (!key.startsWith('sb_publishable_')) throw new Error('Use a Publishable Key pública do projeto no frontend/.env.local. Chaves administrativas e tokens JWT não são aceitos.')
  instance = createClient(url, key, { auth: {
    storage: window.sessionStorage,
    storageKey: 'investment-auth-session',
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: false,
  } })
  return instance
}
