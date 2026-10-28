import publicConfig from '../vercel.public.json'
import privateTemplate from '../vercel.private.example.json'

type Environment = Record<string, string | undefined>

function httpsOrigin(value: string | undefined, name: string): string {
  try {
    const url = new URL((value ?? '').trim())
    if (url.protocol === 'https:' && !url.username && !url.password &&
      url.pathname === '/' && !url.search && !url.hash &&
      !url.hostname.includes('*') && !/YOUR-PROJECT|YOUR-API/i.test(url.hostname)) return url.origin
  } catch { /* Do not include environment values in deployment errors. */ }
  throw new Error(`${name}: configure uma origem HTTPS real, sem caminho, credenciais ou curinga.`)
}

export function selectVercelConfig(env: Environment) {
  // Match the frontend's production default and explicit demo override.
  if (env.VITE_APP_MODE !== 'private' || env.VITE_PUBLIC_DEMO === 'true') {
    return structuredClone(publicConfig)
  }
  if (env.VITE_PUBLIC_DEMO !== 'false' || env.VITE_AUTH_MODE !== 'supabase') {
    throw new Error('Projeto privado exige VITE_PUBLIC_DEMO=false e VITE_AUTH_MODE=supabase.')
  }
  const supabase = httpsOrigin(env.VITE_SUPABASE_URL, 'VITE_SUPABASE_URL')
  const api = httpsOrigin(env.VITE_API_BASE_URL, 'VITE_API_BASE_URL')
  const config = structuredClone(privateTemplate)
  for (const rule of config.headers) {
    for (const header of rule.headers) {
      if (header.key === 'Content-Security-Policy') {
        header.value = header.value
          .replace('https://YOUR-PROJECT.supabase.co', supabase)
          .replace('https://YOUR-API.onrender.com', api)
      }
    }
  }
  return config
}
