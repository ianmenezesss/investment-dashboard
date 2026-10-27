// Produção continua pública por padrão; carteira privada exige opt-in explícito.
export const PUBLIC_DEMO = import.meta.env.VITE_PUBLIC_DEMO === 'true' || (import.meta.env.PROD && import.meta.env.VITE_APP_MODE !== 'private')
export const SUPABASE_AUTH = import.meta.env.VITE_AUTH_MODE === 'supabase' || import.meta.env.PROD

export function apiBase(): string {
  const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
  if (!base) return ''
  const url = new URL(base)
  if (url.username || url.password || url.search || url.hash || (url.protocol !== 'https:' && !(import.meta.env.DEV && ['localhost', '127.0.0.1'].includes(url.hostname) && url.protocol === 'http:'))) {
    throw new Error('Origem da API inválida')
  }
  return base
}
