import { afterEach, beforeEach, expect, test, vi } from 'vitest'

const origin = 'https://investment-dashboard-3ogz.onrender.com'
beforeEach(() => {
  vi.resetModules()
  vi.stubEnv('PROD', true)
  vi.stubEnv('DEV', false)
  vi.stubEnv('VITE_APP_MODE', 'private')
  vi.stubEnv('VITE_PUBLIC_DEMO', 'false')
  vi.stubEnv('VITE_API_BASE_URL', origin + '/')
})
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals() })

test('build privado envia Bearer para a origem Render configurada, sem cookies', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] })
  vi.stubGlobal('fetch', fetchMock)
  const { request } = await import('./api')
  await expect(request('operations', 'unit-test-access-token')).resolves.toEqual([])
  expect(fetchMock).toHaveBeenCalledWith(origin + '/api/operations', expect.objectContaining({
    credentials: 'omit', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer unit-test-access-token' },
  }))
})

test('build privado sem token não consulta o Render', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  const { request } = await import('./api')
  await expect(request('operations', '')).rejects.toMatchObject({ status: 401 })
  expect(fetchMock).not.toHaveBeenCalled()
})

test.each([401, 403])('resposta %s do Render preserva o erro de autorização', async status => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status, json: async () => ({}) }))
  const { request } = await import('./api')
  await expect(request('operations', 'unit-test-access-token')).rejects.toMatchObject({ status })
})

test('demonstração prevalece e bloqueia HTTP mesmo com URL Render configurada', async () => {
  vi.stubEnv('VITE_PUBLIC_DEMO', 'true')
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  const { request } = await import('./api')
  await expect(request('operations', 'unit-test-access-token')).rejects.toThrow('não acessa a API privada')
  expect(fetchMock).not.toHaveBeenCalled()
})

test('build sem opt-in privado continua demonstrativo', async () => {
  vi.stubEnv('VITE_APP_MODE', 'demo')
  const { PUBLIC_DEMO } = await import('./runtime')
  expect(PUBLIC_DEMO).toBe(true)
})
