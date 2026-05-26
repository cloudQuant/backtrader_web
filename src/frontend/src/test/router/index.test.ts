import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// Mock stores before importing router
vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn(),
}))

// Mock all lazy-loaded views so import() calls resolve
vi.mock('@/views/LoginPage.vue', () => ({ default: { template: '<div>Login</div>' } }))
vi.mock('@/views/RegisterPage.vue', () => ({ default: { template: '<div>Register</div>' } }))
vi.mock('@/views/DashboardPage.vue', () => ({ default: { template: '<div>Dashboard</div>' } }))
vi.mock('@/views/BacktestPage.vue', () => ({ default: { template: '<div>Backtest</div>' } }))
vi.mock('@/views/BacktestResultPage.vue', () => ({ default: { template: '<div>Result</div>' } }))
vi.mock('@/views/StrategyPage.vue', () => ({ default: { template: '<div>Strategy</div>' } }))
vi.mock('@/views/DataPage.vue', () => ({ default: { template: '<div>Data</div>' } }))
vi.mock('@/views/data/DataLayout.vue', () => ({ default: { template: '<div><router-view /></div>' } }))
vi.mock('@/views/data/DataMarketPage.vue', () => ({ default: { template: '<div>Data Market</div>' } }))
vi.mock('@/views/data/DataScriptsPage.vue', () => ({ default: { template: '<div>Data Scripts</div>' } }))
vi.mock('@/views/data/DataScriptDetailPage.vue', () => ({ default: { template: '<div>Data Script Detail</div>' } }))
vi.mock('@/views/data/DataTasksPage.vue', () => ({ default: { template: '<div>Data Tasks</div>' } }))
vi.mock('@/views/data/DataExecutionsPage.vue', () => ({ default: { template: '<div>Data Executions</div>' } }))
vi.mock('@/views/data/DataTablesPage.vue', () => ({ default: { template: '<div>Data Tables</div>' } }))
vi.mock('@/views/data/DataTableDetailPage.vue', () => ({ default: { template: '<div>Data Table Detail</div>' } }))
vi.mock('@/views/data/DataInterfacesPage.vue', () => ({ default: { template: '<div>Data Interfaces</div>' } }))
vi.mock('@/views/PortfolioPage.vue', () => ({ default: { template: '<div>Portfolio</div>' } }))
vi.mock('@/views/SettingsPage.vue', () => ({ default: { template: '<div>Settings</div>' } }))
vi.mock('@/views/AIChatPage.vue', () => ({ default: { template: '<div>AI Chat</div>' } }))
vi.mock('@/views/AIObservabilityPage.vue', () => ({ default: { template: '<div>AI Observability</div>' } }))
vi.mock('@/views/PromptTemplatesPage.vue', () => ({ default: { template: '<div>Prompt Templates</div>' } }))
vi.mock('@/views/KnowledgeBasePage.vue', () => ({ default: { template: '<div>Knowledge Base</div>' } }))
vi.mock('@/views/KnowledgeBaseDocumentPage.vue', () => ({ default: { template: '<div>Knowledge Base Document</div>' } }))
vi.mock('@/components/common/AppLayout.vue', () => ({ default: { template: '<div><router-view /></div>' } }))

import { useAuthStore } from '@/stores/auth'
import router from '@/router/index'

function mockAuthStore(isAuthenticated: boolean, isAdmin = false) {
  vi.mocked(useAuthStore).mockReturnValue({
    isAuthenticated,
    user: isAuthenticated ? { is_admin: isAdmin } : null,
  } as ReturnType<typeof useAuthStore>)
}

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
    expect(names).toContain('TradingWorkspaceList')
    expect(names).toContain('TradingWorkspaceDetail')
    expect(names).toContain('Data')
    expect(names).toContain('AIChat')
    expect(names).toContain('AIObservability')
    expect(names).toContain('PromptTemplates')
    expect(names).toContain('KnowledgeBase')
    expect(names).toContain('KnowledgeBaseDocument')
  })

  it('guard redirects unauthenticated user to Login', async () => {
    mockAuthStore(false)
    await router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Login')
  })

  it('guard allows unauthenticated user on /login', async () => {
    mockAuthStore(false)
    await router.push('/login')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Login')
  })

  it('guard allows unauthenticated user on /register', async () => {
    mockAuthStore(false)
    await router.push('/register')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Register')
  })

  it('guard redirects authenticated user from /login to Dashboard', async () => {
    mockAuthStore(true)
    await router.push('/login')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Dashboard')
  })

  it('guard redirects authenticated user from /register to Dashboard', async () => {
    mockAuthStore(true)
    await router.push('/register')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Dashboard')
  })

  it('guard allows authenticated user to access /', async () => {
    mockAuthStore(true)
    await router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Dashboard')
  })

  it('guard allows authenticated user on /settings', async () => {
    mockAuthStore(true)
    await router.push('/settings')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Settings')
  })

  it('guard allows authenticated user on /ai-chat', async () => {
    mockAuthStore(true)
    await router.push('/ai-chat')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('AIChat')
  })

  it('guard allows authenticated user on /knowledge-base', async () => {
    mockAuthStore(true)
    await router.push('/knowledge-base')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('KnowledgeBase')
  })

  it('guard passes redirect query for protected routes', async () => {
    mockAuthStore(false)
    await router.push('/backtest')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('Login')
    expect(router.currentRoute.value.query.redirect).toBe('/backtest')
  })

  it('guard redirects non-admin user away from /data/interfaces', async () => {
    mockAuthStore(true, false)
    await router.push('/data/interfaces')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataMarket')
  })

  it('guard allows admin user to access /data/interfaces', async () => {
    mockAuthStore(true, true)
    await router.push('/data/interfaces')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataInterfaces')
  })

  it('guard redirects non-admin user away from /admin/ai-observability', async () => {
    mockAuthStore(true, false)
    await router.push('/admin/ai-observability')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataMarket')
  })

  it('guard allows admin user to access /admin/ai-observability', async () => {
    mockAuthStore(true, true)
    await router.push('/admin/ai-observability')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('AIObservability')
  })

  it('guard redirects non-admin user away from /admin/prompt-templates', async () => {
    mockAuthStore(true, false)
    await router.push('/admin/prompt-templates')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataMarket')
  })

  it('guard allows admin user to access /admin/prompt-templates', async () => {
    mockAuthStore(true, true)
    await router.push('/admin/prompt-templates')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('PromptTemplates')
  })

  it('redirects legacy /live-trading route to trading workspace', async () => {
    mockAuthStore(true)
    await router.push('/live-trading')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('TradingWorkspaceList')
  })
})
