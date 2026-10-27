// Diagnóstico sem imprimir URL, chave, UUID ou sessão; não realiza login.
import { loadEnv } from 'vite'
import { readFileSync } from 'node:fs'
import { parseEnv } from 'node:util'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const env = loadEnv('development', root, 'VITE_')
const backend = parseEnv(readFileSync(new URL('../../.env', import.meta.url), 'utf8'))
const url = (env.VITE_SUPABASE_URL ?? '').trim()
const key = (env.VITE_SUPABASE_PUBLISHABLE_KEY ?? '').trim()
let validUrl = false
try { const p = new URL(url); validUrl = p.protocol === 'https:' && p.pathname === '/' && !p.search && !p.hash && !p.username && !p.password } catch {}
const checks = {
  'Vite encontra Project URL válida (origem sem endpoint)': validUrl,
  'Vite encontra Publishable Key': key.startsWith('sb_publishable_'),
  'Frontend no modo Supabase privado': env.VITE_AUTH_MODE === 'supabase' && env.VITE_APP_MODE === 'private' && env.VITE_PUBLIC_DEMO === 'false',
  'Backend no modo Supabase': backend.AUTH_MODE === 'supabase',
  'Frontend e backend apontam para a mesma origem': url === backend.SUPABASE_URL,
}
try { const ids = JSON.parse(backend.ALLOWED_USER_IDS ?? '[]'); checks['Allowlist contém UUIDs válidos'] = Array.isArray(ids) && ids.length > 0 && ids.every(id => typeof id === 'string' && /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(id)) } catch { checks['Allowlist contém UUIDs válidos'] = false }
for (const [name, pass] of Object.entries(checks)) console.log(`${pass ? 'OK' : 'PENDENTE'}: ${name}`)
if (Object.values(checks).some(pass => !pass)) process.exitCode = 1
if (process.argv.includes('--remote') && validUrl && key.startsWith('sb_publishable_')) {
  try {
    const response = await fetch(`${url}/auth/v1/.well-known/jwks.json`, { signal: AbortSignal.timeout(10000) })
    const body = await response.json()
    const algorithms = [...new Set((body.keys ?? []).map(item => item.alg).filter(alg => ['ES256', 'RS256'].includes(alg)))]
    console.log(response.ok && algorithms.length ? `OK: JWKS público disponível com ${algorithms.join(', ')}` : 'PENDENTE: JWKS sem chave assimétrica compatível')
    if (!response.ok || !algorithms.length) process.exitCode = 1
    const settings = await fetch(`${url}/auth/v1/settings`, { headers: { apikey: key }, signal: AbortSignal.timeout(10000) })
    console.log(settings.ok ? 'OK: provedor reconhece a Publishable Key' : 'PENDENTE: provedor não aceitou a Publishable Key')
    if (!settings.ok) process.exitCode = 1
  } catch { console.log('PENDENTE: não foi possível verificar o provedor por rede; nenhum login foi tentado'); process.exitCode = 1 }
}
