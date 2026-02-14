import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// Mock stores before importing router
vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn(),
}))

// Mock all lazy-loaded views so import() calls resolve
vi.mock('@/views/LoginPage.vue', () => ({ default: { template: '<div>Login</div>' } }))
vi.mock('@/views/RegisterPage.vue', () => ({ default: { template: '<div>Register</div>' } }))
vi.mock('@/views/Dashboard.vue', () => ({ default: { template: '<div>Dashboard</div>' } }))
vi.mock('@/views/BacktestPage.vue', () => ({ default: { template: '<div>Backtest</div>' } }))
vi.mock('@/views/BacktestResultPage.vue', () => ({ default: { template: '<div>Result</div>' } }))
vi.mock('@/views/OptimizationPage.vue', () => ({ default: { template: '<div>Optimization</div>' } }))
vi.mock('@/views/StrategyPage.vue', () => ({ default: { template: '<div>Strategy</div>' } }))
vi.mock('@/views/DataPage.vue', () => ({ default: { template: '<div>Data</div>' } }))
vi.mock('@/views/LiveTradingPage.vue', () => ({ default: { template: '<div>LiveTrading</div>' } }))
vi.mock('@/views/LiveTradingDetailPage.vue', () => ({ default: { template: '<div>Detail</div>' } }))
vi.mock('@/views/PortfolioPage.vue', () => ({ default: { template: '<div>Portfolio</div>' } }))
vi.mock('@/views/SettingsPage.vue', () => ({ default: { template: '<div>Settings</div>' } }))
vi.mock('@/components/common/AppLayout.vue', () => ({ default: { template: '<div><router-view /></div>' } }))

import { useAuthStore } from '@/stores/auth'
import router from './index'

describe('router', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('exports a router instance', () => {
    expect(router).toBeDefined()
    expect(router.getRoutes).toBeDefined()
  })

  it('has all expected route names', () => {
    const names = router.getRoutes().map(r => r.name).filter(Boolean)
    expect(names).toContain('Login')
    expect(names).toContain('Register')
    expect(names).toContain('Dashboard')
    expect(names).toContain('Backtest')
    expect(names).toContain('BacktestResult')
    expect(names).toContain('Strategy')
    expect(names).toContain('Settings')
    expect(names).toContain('Portfolio')
    expect(names).toContain('LiveTrading')
    expect(names).toContain('LiveTradingDetail')
    expect(names).toContain('Optimization')
    expect(names).toContain('Data')
  })

  it('guard redirects unauthenticated user to Login', async () => {
    vi.mocked(useAuthStore).mockReturnValue({ isAuthenticated: false } as any)
    await router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Login')
  })

  it('guard allows unauthenticated user on /login', async () => {
    vi.mocked(useAuthStore).mockReturnValue({ isAuthenticated: false } as any)
    await router.push('/login')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Login')
  })

  it('guard allows unauthenticated user on /register', async () => {
    vi.mocked(useAuthStore).mockReturnValue({ isAuthenticated: false } as any)
    await router.push('/register')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Register')
  })

  it('guard redirects authenticated user from /login to Dashboard', async () => {
    vi.mocked(useAuthStore).mockReturnValue({ isAuthenticated: true } as any)
    await router.push('/login')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Dashboard')
  })

  it('guard redirects authenticated user from /register to Dashboard', async () => {
    vi.mocked(useAuthStore).mockReturnValue({ isAuthenticated: true } as any)
    await router.push('/register')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Dashboard')
  })

  it('guard allows authenticated user to access /', async () => {
    vi.mocked(useAuthStore).mockReturnValue({ isAuthenticated: true } as any)
    await router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Dashboard')
  })

  it('guard allows authenticated user on /settings', async () => {
    vi.mocked(useAuthStore).mockReturnValue({ isAuthenticated: true } as any)
    await router.push('/settings')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Settings')
  })

  it('guard passes redirect query for protected routes', async () => {
    vi.mocked(useAuthStore).mockReturnValue({ isAuthenticated: false } as any)
    await router.push('/backtest')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Login')
    expect(router.currentRoute.value.query.redirect).toBe('/backtest')
  })
})
