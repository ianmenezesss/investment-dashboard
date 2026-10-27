import { beforeEach, expect, test, vi } from 'vitest'
const create = vi.hoisted(() => vi.fn((_url: string, _key: string, _options: { auth: Record<string, unknown> }) => ({ auth: {} })))
vi.mock('@supabase/supabase-js', () => ({ createClient: create }))
vi.mock('../runtime', () => ({ PUBLIC_DEMO: false, SUPABASE_AUTH: true }))
beforeEach(() => { vi.resetModules(); create.mockClear(); vi.stubEnv('VITE_SUPABASE_URL', 'https://project.example'); vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_testOnly') })

test('cliente usa armazenamento por aba e recuperação por URL fica desativada', async () => {
  const { getSupabase } = await import('./supabase')
  expect(getSupabase()).toBe(getSupabase())
  expect(create).toHaveBeenCalledTimes(1)
  expect(create.mock.calls[0][2].auth).toMatchObject({ storage: sessionStorage, persistSession: true, autoRefreshToken: true, detectSessionInUrl: false })
})

test.each(['sb_secret_testOnly', 'legacy-token-not-accepted', ''])('configuração inadequada da chave é recusada sem criar cliente', async key => {
  vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', key)
  const { getSupabase } = await import('./supabase')
  expect(() => getSupabase()).toThrow('Publishable Key')
  expect(create).not.toHaveBeenCalled()
})

test('URL de endpoint REST é recusada com instrução específica, sem criar cliente', async () => {
  vi.stubEnv('VITE_SUPABASE_URL', 'https://project.example/rest/v1')
  const { getSupabase } = await import('./supabase')
  expect(() => getSupabase()).toThrow('sem /rest/v1 ou /auth/v1')
  expect(create).not.toHaveBeenCalled()
})
