import { vi } from 'vitest'
vi.stubEnv('VITE_PUBLIC_DEMO', 'true')
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true, ResizeObserver: class { observe() {} unobserve() {} disconnect() {} } })
