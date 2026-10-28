import { afterEach, expect, test, vi } from 'vitest'
import { existsSync } from 'node:fs'
import publicConfig from '../vercel.public.json'
import { selectVercelConfig } from './vercel-config'

const privateEnv = {
  VITE_APP_MODE: 'private', VITE_PUBLIC_DEMO: 'false', VITE_AUTH_MODE: 'supabase',
  VITE_SUPABASE_URL: 'https://project.supabase.co',
  VITE_API_BASE_URL: 'https://investment-dashboard-3ogz.onrender.com',
}
afterEach(() => vi.unstubAllEnvs())

test.each([{}, { VITE_APP_MODE: 'demo' }, { VITE_APP_MODE: 'private', VITE_PUBLIC_DEMO: 'true' }])(
  'configuração pública permanece integralmente igual ao original', env => {
    expect(selectVercelConfig(env)).toEqual(publicConfig)
  },
)

test('privado permite somente as origens exatas e preserva os demais headers e rewrite SPA', () => {
  const config = selectVercelConfig(privateEnv)
  const headers = config.headers[0].headers
  const csp = headers.find(h => h.key === 'Content-Security-Policy')!.value
  expect(csp.split(';').map(s => s.trim())).toContain(
    "connect-src 'self' https://project.supabase.co https://investment-dashboard-3ogz.onrender.com",
  )
  expect(csp).not.toMatch(/YOUR-|\*/)
  expect(csp).toContain("frame-ancestors 'none'")
  expect(config.rewrites).toEqual(publicConfig.rewrites)
  expect(headers.filter(h => h.key !== 'Content-Security-Policy')).toEqual(
    publicConfig.headers[0].headers.filter(h => h.key !== 'Content-Security-Policy'),
  )
  expect(selectVercelConfig({})).toEqual(publicConfig)
})

test.each(['VITE_API_BASE_URL', 'VITE_SUPABASE_URL'])(
  '%s inválida interrompe a configuração sem expor o valor', name => {
    for (const value of ['', 'http://insecure.example', 'https://host.example/api',
      'https://secret-user:secret-password@host.example', 'https://*.example',
      'https://host.example?secret=value', 'https://host.example#fragment',
      'https://YOUR-PROJECT.supabase.co', 'https://YOUR-API.onrender.com']) {
      expect(() => selectVercelConfig({ ...privateEnv, [name]: value })).toThrow(name)
      try { selectVercelConfig({ ...privateEnv, [name]: value }) }
      catch (error) { expect((error as Error).message).not.toContain('secret-password') }
    }
  },
)

test('origens com barra final são normalizadas sem inserir caminhos na CSP', () => {
  expect(selectVercelConfig({ ...privateEnv, VITE_API_BASE_URL: privateEnv.VITE_API_BASE_URL + '/' }))
    .toEqual(selectVercelConfig(privateEnv))
})

test.each([
  { ...privateEnv, VITE_PUBLIC_DEMO: undefined },
  { ...privateEnv, VITE_AUTH_MODE: 'local' },
])('configuração privada incompleta falha fechada', env => {
  expect(() => selectVercelConfig(env)).toThrow('Projeto privado exige')
})

test('entrypoint Vercel seleciona a configuração a partir do ambiente do projeto', async () => {
  vi.resetModules()
  for (const [name, value] of Object.entries(privateEnv)) vi.stubEnv(name, value)
  const { config } = await import('../vercel')
  expect(config).toEqual(selectVercelConfig(privateEnv))
  expect(existsSync(new URL('../vercel.json', import.meta.url))).toBe(false)
})
