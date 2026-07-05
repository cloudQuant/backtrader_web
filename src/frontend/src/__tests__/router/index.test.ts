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
vi.mock('@/views/QuotePage.vue', () => ({ default: { template: '<div>Quote</div>' } }))
vi.mock('@/views/data/DataLayout.vue', () => ({ default: { template: '<div><router-view /></div>' } }))
vi.mock('@/views/config/ConfigDataLayout.vue', () => ({ default: { template: '<div><router-view /></div>' } }))
vi.mock('@/views/config/ConfigAILayout.vue', () => ({ default: { template: '<div><router-view /></div>' } }))
vi.mock('@/views/config/AIProviderConfigPage.vue', () => ({ default: { template: '<div>AI Provider Config</div>' } }))
vi.mock('@/views/data/DataMarketPage.vue', () => ({ default: { template: '<div>Data Market</div>' } }))
vi.mock('@/views/data/DataScriptsPage.vue', () => ({ default: { template: '<div>Data Scripts</div>' } }))
vi.mock('@/views/data/DataScriptDetailPage.vue', () => ({ default: { template: '<div>Data Script Detail</div>' } }))
vi.mock('@/views/data/DataTasksPage.vue', () => ({ default: { template: '<div>Data Tasks</div>' } }))
vi.mock('@/views/data/DataExecutionsPage.vue', () => ({ default: { template: '<div>Data Executions</div>' } }))
vi.mock('@/views/data/DataTablesPage.vue', () => ({ default: { template: '<div>Data Tables</div>' } }))
vi.mock('@/views/data/DataTableDetailPage.vue', () => ({ default: { template: '<div>Data Table Detail</div>' } }))
vi.mock('@/views/data/DataTopicsPage.vue', () => ({ default: { template: '<div>Data Topics</div>' } }))
vi.mock('@/views/data/DataInterfacesPage.vue', () => ({ default: { template: '<div>Data Interfaces</div>' } }))
vi.mock('@/views/data/DataGovernancePage.vue', () => ({ default: { template: '<div>Data Governance</div>' } }))
vi.mock('@/views/data/AirflowDagsPage.vue', () => ({ default: { template: '<div>Airflow DAGs</div>' } }))
vi.mock('@/views/PortfolioPage.vue', () => ({ default: { template: '<div>Portfolio</div>' } }))
vi.mock('@/views/BrokerProfilesPage.vue', () => ({ default: { template: '<div>Broker Profiles</div>' } }))
vi.mock('@/views/PortfolioLedgerPage.vue', () => ({ default: { template: '<div>Portfolio Ledger</div>' } }))
vi.mock('@/views/GatewayStatusPage.vue', () => ({ default: { template: '<div>Gateways</div>' } }))
vi.mock('@/views/AITradingPage.vue', () => ({ default: { template: '<div>AI Trading</div>' } }))
vi.mock('@/views/workspace/WorkspaceListPage.vue', () => ({ default: { template: '<div>Workspace List</div>' } }))
vi.mock('@/views/workspace/WorkspaceDetailPage.vue', () => ({ default: { template: '<div>Workspace Detail</div>' } }))
vi.mock('@/views/NewsIntelligencePage.vue', () => ({ default: { template: '<div>News Intelligence</div>' } }))
vi.mock('@/views/OptionsChainPage.vue', () => ({ default: { template: '<div>Options Chain</div>' } }))
vi.mock('@/views/ScannerPage.vue', () => ({ default: { template: '<div>Scanner</div>' } }))
vi.mock('@/views/QuantToolsPage.vue', () => ({ default: { template: '<div>Quant Tools</div>' } }))
vi.mock('@/views/investment/StockAnalysisPage.vue', () => ({ default: { template: '<div>Stock Analysis</div>' } }))
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
    expect(names).toContain('NewsIntelligence')
    expect(names).toContain('Scanners')
    expect(names).toContain('QuantTools')
    expect(names).toContain('TradingWorkspaceList')
    expect(names).toContain('TradingWorkspaceDetail')
    expect(names).toContain('Data')
    expect(names).toContain('DataTopics')
    expect(names).toContain('ConfigDataGovernance')
    expect(names).toContain('ConfigAIProviders')
    expect(names).toContain('ConfigAIObservability')
    expect(names).toContain('ConfigPromptTemplates')
    expect(names).toContain('AIChat')
    expect(names).toContain('AIChatCanonical')
    expect(names).toContain('AIObservability')
    expect(names).not.toContain('AIObservabilityLegacyRedirect')
    expect(names).toContain('PromptTemplates')
    expect(names).not.toContain('PromptTemplatesLegacyRedirect')
    expect(names).not.toContain('AIObservabilityCanonical')
    expect(names).not.toContain('PromptTemplatesCanonical')
    expect(names).toContain('KnowledgeBase')
    expect(names).toContain('AIKnowledgeBase')
    expect(names).toContain('KnowledgeBaseDocument')
    expect(names).toContain('ResearchStrategies')
    expect(names).toContain('ResearchWorkspaces')
    expect(names).toContain('ResearchBacktestResult')
    expect(names).toContain('InvestmentStrategies')
    expect(names).toContain('InvestmentStockAnalysis')
    expect(names).toContain('DataQuote')
    expect(names).toContain('ConfigGateways')
    expect(names).toContain('PortfolioOverview')
    expect(names).not.toContain('BrokerProfiles')
    expect(names).not.toContain('TradingBrokerProfiles')
    expect(names).not.toContain('PortfolioLedger')
    expect(names).not.toContain('PortfolioLedgerCanonical')
    expect(names).not.toContain('OptionsChain')
    expect(names).not.toContain('DataOptionsChain')
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

  it('redirects removed /brokers entry to trading workspaces', async () => {
    mockAuthStore(true)
    await router.push('/brokers')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('TradingWorkspaceList')
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

  it('guard allows authenticated user on canonical /research/strategies', async () => {
    mockAuthStore(true)
    await router.push('/research/strategies')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('ResearchStrategies')
  })

  it('guard allows authenticated user on canonical /data/quote', async () => {
    mockAuthStore(true)
    await router.push('/data/quote')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataQuote')
  })

  it('guard allows authenticated user on canonical /investment/stock-analysis', async () => {
    mockAuthStore(true)
    await router.push('/investment/stock-analysis')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('InvestmentStockAnalysis')
  })

  it('guard allows authenticated user on canonical /investment/strategies', async () => {
    mockAuthStore(true)
    await router.push('/investment/strategies')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('InvestmentStrategies')
  })

  it('serves data tables from market data for non-admin users', async () => {
    mockAuthStore(true, false)
    await router.push('/data/tables')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataTables')

    await router.push('/data/tables/1292')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataTableDetail')
    expect(router.currentRoute.value.params.id).toBe('1292')
  })

  it('redirects old config data table routes to market data', async () => {
    mockAuthStore(true, true)
    await router.push('/config/data/tables')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataTables')
    expect(router.currentRoute.value.path).toBe('/data/tables')

    await router.push('/config/data/tables/1292')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataTableDetail')
    expect(router.currentRoute.value.path).toBe('/data/tables/1292')
  })

  it('redirects removed canonical /trading/brokers entry to trading workspaces', async () => {
    mockAuthStore(true)
    await router.push('/trading/brokers')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('TradingWorkspaceList')
  })

  it('moves gateway management into config center', async () => {
    mockAuthStore(true, true)
    await router.push('/trading/gateways')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('ConfigGateways')
    expect(router.currentRoute.value.path).toBe('/config/gateways')
  })

  it('redirects removed portfolio ledger entry to portfolio overview', async () => {
    mockAuthStore(true)
    await router.push('/portfolio/ledger')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('PortfolioOverview')
  })

  it('moves options chain into data query options tab', async () => {
    mockAuthStore(true)
    await router.push('/data/intelligence/options')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataMarket')
    expect(router.currentRoute.value.query.tab).toBe('options')
  })

  it('guard allows authenticated user on canonical /ai/chat', async () => {
    mockAuthStore(true)
    await router.push('/ai/chat')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('AIChatCanonical')
  })

  it('guard allows authenticated user on canonical /ai/knowledge-base', async () => {
    mockAuthStore(true)
    await router.push('/ai/knowledge-base')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('AIKnowledgeBase')
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
    expect(router.currentRoute.value.name).toBe('ConfigDataInterfaces')
  })

  it('guard redirects non-admin user away from /data/governance', async () => {
    mockAuthStore(true, false)
    await router.push('/data/governance')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataMarket')
  })

  it('guard allows admin user to access /data/governance', async () => {
    mockAuthStore(true, true)
    await router.push('/data/governance')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('ConfigDataGovernance')
  })

  it('guard allows authenticated user to access /data/topics', async () => {
    mockAuthStore(true, false)
    await router.push('/data/topics')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataTopics')
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
    expect(router.currentRoute.value.name).toBe('ConfigAIObservability')
  })

  it('guard allows admin user to access config AI observability', async () => {
    mockAuthStore(true, true)
    await router.push('/config/ai/observability')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('ConfigAIObservability')
  })

  it('redirects legacy AI knowledge area observability to config center', async () => {
    mockAuthStore(true, true)
    await router.push('/ai/observability')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('ConfigAIObservability')
    expect(router.currentRoute.value.path).toBe('/config/ai/observability')

    await router.push('/ai/ai-observability')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('ConfigAIObservability')
    expect(router.currentRoute.value.path).toBe('/config/ai/observability')
  })

  it('guard redirects non-admin user away from config AI observability', async () => {
    mockAuthStore(true, false)
    await router.push('/')
    await router.isReady()
    await router.push('/config/ai/observability')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataMarket')
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
    expect(router.currentRoute.value.name).toBe('ConfigPromptTemplates')
  })

  it('guard allows admin user to access config prompt governance', async () => {
    mockAuthStore(true, true)
    await router.push('/config/ai/prompt-governance')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('ConfigPromptTemplates')
  })

  it('redirects legacy AI knowledge area prompt governance to config center', async () => {
    mockAuthStore(true, true)
    await router.push('/ai/prompt-governance')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('ConfigPromptTemplates')
    expect(router.currentRoute.value.path).toBe('/config/ai/prompt-governance')

    await router.push('/ai/prompt-templates')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('ConfigPromptTemplates')
    expect(router.currentRoute.value.path).toBe('/config/ai/prompt-governance')
  })

  it('guard redirects non-admin user away from config prompt governance', async () => {
    mockAuthStore(true, false)
    await router.push('/')
    await router.isReady()
    await router.push('/config/ai/prompt-governance')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('DataMarket')
  })

  it('redirects legacy /live-trading route to trading workspace', async () => {
    mockAuthStore(true)
    await router.push('/live-trading')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('TradingWorkspaceList')
  })
})
