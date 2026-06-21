import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginPage.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/RegisterPage.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('@/components/common/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'Dashboard',
        component: () => import('@/views/DashboardPage.vue'),
      },
      {
        path: 'investment',
        redirect: { name: 'InvestmentStockAnalysis' },
      },
      {
        path: 'investment/stock-analysis',
        name: 'InvestmentStockAnalysis',
        component: () => import('@/views/investment/StockAnalysisPage.vue'),
      },
      {
        path: 'research',
        redirect: { name: 'ResearchWorkspaces' },
      },
      {
        path: 'research/strategies',
        name: 'ResearchStrategies',
        component: () => import('@/views/StrategyPage.vue'),
      },
      {
        path: 'research/workspaces',
        name: 'ResearchWorkspaces',
        component: () => import('@/views/workspace/WorkspaceListPage.vue'),
        meta: { workspaceType: 'research' },
      },
      {
        path: 'research/workspaces/:id',
        name: 'ResearchWorkspaceDetail',
        component: () => import('@/views/workspace/WorkspaceDetailPage.vue'),
        meta: { workspaceType: 'research' },
      },
      {
        path: 'research/backtests/legacy',
        name: 'ResearchBacktestLegacy',
        component: () => import('@/views/BacktestPage.vue'),
      },
      {
        path: 'research/backtests/:id',
        name: 'ResearchBacktestResult',
        component: () => import('@/views/BacktestResultPage.vue'),
      },
      {
        path: 'research/tools',
        name: 'ResearchQuantTools',
        component: () => import('@/views/QuantToolsPage.vue'),
      },
      {
        path: 'ai',
        redirect: { name: 'AIChatCanonical' },
      },
      {
        path: 'ai/chat',
        name: 'AIChatCanonical',
        component: () => import('@/views/AIChatPage.vue'),
      },
      {
        path: 'ai/knowledge-base',
        name: 'AIKnowledgeBase',
        component: () => import('@/views/KnowledgeBasePage.vue'),
      },
      {
        path: 'ai/knowledge-base/:id',
        name: 'AIKnowledgeBaseDetail',
        component: () => import('@/views/KnowledgeBasePage.vue'),
      },
      {
        path: 'ai/knowledge-base/:kbId/documents/:docId',
        name: 'AIKnowledgeBaseDocument',
        component: () => import('@/views/KnowledgeBaseDocumentPage.vue'),
      },
      {
        path: 'ai/observability',
        name: 'AIObservabilityCanonical',
        component: () => import('@/views/AIObservabilityPage.vue'),
        meta: { requiresAdmin: true },
      },
      {
        path: 'ai/prompt-governance',
        name: 'PromptTemplatesCanonical',
        component: () => import('@/views/PromptTemplatesPage.vue'),
        meta: { requiresAdmin: true },
      },
      {
        path: 'config',
        redirect: { name: 'ConfigDataScripts' },
        meta: { requiresAdmin: true },
      },
      {
        path: 'config/data',
        component: () => import('@/views/config/ConfigDataLayout.vue'),
        meta: { requiresAdmin: true },
        children: [
          {
            path: '',
            redirect: { name: 'ConfigDataScripts' },
          },
          {
            path: 'scripts',
            name: 'ConfigDataScripts',
            component: () => import('@/views/data/DataScriptsPage.vue'),
          },
          {
            path: 'scripts/:id',
            name: 'ConfigDataScriptDetail',
            component: () => import('@/views/data/DataScriptDetailPage.vue'),
          },
          {
            path: 'tasks',
            name: 'ConfigDataTasks',
            component: () => import('@/views/data/DataTasksPage.vue'),
          },
          {
            path: 'executions',
            name: 'ConfigDataExecutions',
            component: () => import('@/views/data/DataExecutionsPage.vue'),
          },
          {
            path: 'tables',
            name: 'ConfigDataTablesLegacy',
            redirect: { name: 'DataTables' },
          },
          {
            path: 'tables/:id',
            name: 'ConfigDataTableDetailLegacy',
            redirect: to => ({ name: 'DataTableDetail', params: { id: String(to.params.id ?? '') } }),
          },
          {
            path: 'sync',
            name: 'ConfigDataSync',
            component: () => import('@/views/data/DataSyncPage.vue'),
          },
          {
            path: 'interfaces',
            name: 'ConfigDataInterfaces',
            component: () => import('@/views/data/DataInterfacesPage.vue'),
          },
          {
            path: 'governance',
            name: 'ConfigDataGovernance',
            component: () => import('@/views/data/DataGovernancePage.vue'),
          },
          {
            path: 'airflow',
            name: 'ConfigDataAirflow',
            component: () => import('@/views/data/AirflowDagsPage.vue'),
          },
        ],
      },
      {
        path: 'config/ai',
        redirect: { name: 'ConfigAIProviders' },
        meta: { requiresAdmin: true },
      },
      {
        path: 'config/ai/providers',
        name: 'ConfigAIProviders',
        component: () => import('@/views/config/AIProviderConfigPage.vue'),
        meta: { requiresAdmin: true },
      },
      {
        path: 'config/gateways',
        name: 'ConfigGateways',
        component: () => import('@/views/GatewayStatusPage.vue'),
        meta: { requiresAdmin: true },
      },
      {
        path: 'admin',
        redirect: { name: 'AdminSettings' },
        meta: { requiresAdmin: true },
      },
      {
        path: 'ai-chat',
        name: 'AIChat',
        component: () => import('@/views/AIChatPage.vue'),
      },
      {
        path: 'admin/ai-observability',
        name: 'AIObservability',
        component: () => import('@/views/AIObservabilityPage.vue'),
        meta: { requiresAdmin: true },
      },
      {
        path: 'admin/prompt-templates',
        name: 'PromptTemplates',
        component: () => import('@/views/PromptTemplatesPage.vue'),
        meta: { requiresAdmin: true },
      },
      {
        path: 'ai-trading',
        name: 'AITrading',
        component: () => import('@/views/AITradingPage.vue'),
      },
      {
        path: 'backtest',
        name: 'Backtest',
        component: () => import('@/views/workspace/WorkspaceListPage.vue'),
        meta: { workspaceType: 'research' },
      },
      {
        path: 'backtest/workspace/:id',
        name: 'BacktestWorkspaceDetail',
        component: () => import('@/views/workspace/WorkspaceDetailPage.vue'),
        meta: { workspaceType: 'research' },
      },
      {
        path: 'backtest/legacy',
        name: 'BacktestLegacy',
        component: () => import('@/views/BacktestPage.vue'),
      },
      {
        path: 'backtest/result/:id',
        name: 'BacktestResult',
        component: () => import('@/views/BacktestResultPage.vue'),
      },
      {
        path: 'backtest/:id',
        redirect: to => ({ path: `/backtest/result/${String(to.params.id ?? '')}` }),
      },
      {
        path: 'strategy',
        name: 'Strategy',
        component: () => import('@/views/StrategyPage.vue'),
      },
      {
        path: 'data',
        name: 'Data',
        component: () => import('@/views/data/DataLayout.vue'),
        children: [
          {
            path: '',
            name: 'DataHome',
            redirect: { name: 'DataMarket' },
          },
          {
            path: 'market',
            name: 'DataMarket',
            component: () => import('@/views/data/DataMarketPage.vue'),
          },
          {
            path: 'quote',
            name: 'DataQuote',
            component: () => import('@/views/QuotePage.vue'),
          },
          {
            path: 'intelligence/equity',
            name: 'DataEquityResearch',
            component: () => import('@/views/EquityResearchPage.vue'),
          },
          {
            path: 'intelligence/news',
            name: 'DataNewsIntelligence',
            component: () => import('@/views/NewsIntelligencePage.vue'),
          },
          {
            path: 'intelligence/options',
            redirect: { name: 'DataMarket', query: { tab: 'options' } },
          },
          {
            path: 'intelligence/scanners',
            name: 'DataScanners',
            component: () => import('@/views/ScannerPage.vue'),
          },
          {
            path: 'scripts',
            name: 'DataScripts',
            redirect: { name: 'ConfigDataScripts' },
          },
          {
            path: 'scripts/:id',
            name: 'DataScriptDetail',
            redirect: to => ({ name: 'ConfigDataScriptDetail', params: { id: String(to.params.id ?? '') } }),
          },
          {
            path: 'tasks',
            name: 'DataTasks',
            redirect: { name: 'ConfigDataTasks' },
          },
          {
            path: 'executions',
            name: 'DataExecutions',
            redirect: { name: 'ConfigDataExecutions' },
          },
          {
            path: 'tables',
            name: 'DataTables',
            component: () => import('@/views/data/DataTablesPage.vue'),
          },
          {
            path: 'tables/:id',
            name: 'DataTableDetail',
            component: () => import('@/views/data/DataTableDetailPage.vue'),
          },
          {
            path: 'topics',
            name: 'DataTopics',
            component: () => import('@/views/data/DataTopicsPage.vue'),
          },
          {
            path: 'sync',
            name: 'DataSync',
            redirect: { name: 'ConfigDataSync' },
            meta: { requiresAdmin: true },
          },
          {
            path: 'interfaces',
            name: 'DataInterfaces',
            redirect: { name: 'ConfigDataInterfaces' },
            meta: { requiresAdmin: true },
          },
          {
            path: 'governance',
            name: 'DataGovernance',
            redirect: { name: 'ConfigDataGovernance' },
            meta: { requiresAdmin: true },
          },
          {
            path: 'airflow',
            name: 'DataAirflow',
            redirect: { name: 'ConfigDataAirflow' },
            meta: { requiresAdmin: true },
          },
        ],
      },
      {
        path: 'simulate',
        redirect: { name: 'TradingWorkspaceList' },
      },
      {
        path: 'simulate/:id',
        redirect: to => ({ name: 'TradingWorkspaceDetail', params: { id: String(to.params.id ?? '') } }),
      },
      {
        path: 'live-trading',
        redirect: { name: 'TradingWorkspaceList' },
      },
      {
        path: 'live-trading/:id',
        redirect: to => ({ name: 'TradingWorkspaceDetail', params: { id: String(to.params.id ?? '') } }),
      },
      {
        path: 'gateways',
        redirect: { name: 'ConfigGateways' },
      },
      {
        path: 'quote',
        name: 'Quote',
        component: () => import('@/views/QuotePage.vue'),
      },
      {
        path: 'workspace',
        name: 'WorkspaceList',
        component: () => import('@/views/workspace/WorkspaceListPage.vue'),
        meta: { workspaceType: 'research' },
      },
      {
        path: 'workspace/:id',
        name: 'WorkspaceDetail',
        component: () => import('@/views/workspace/WorkspaceDetailPage.vue'),
        meta: { workspaceType: 'research' },
      },
      {
        path: 'trading',
        name: 'TradingWorkspaceList',
        component: () => import('@/views/workspace/WorkspaceListPage.vue'),
        meta: { workspaceType: 'trading' },
      },
      {
        path: 'trading/workspaces',
        name: 'TradingOperationsWorkspaces',
        component: () => import('@/views/workspace/WorkspaceListPage.vue'),
        meta: { workspaceType: 'trading' },
      },
      {
        path: 'trading/brokers',
        redirect: { name: 'TradingWorkspaceList' },
      },
      {
        path: 'trading/gateways',
        redirect: { name: 'ConfigGateways' },
      },
      {
        path: 'trading/ai',
        name: 'TradingAI',
        component: () => import('@/views/AITradingPage.vue'),
      },
      {
        path: 'trading/:id',
        name: 'TradingWorkspaceDetail',
        component: () => import('@/views/workspace/WorkspaceDetailPage.vue'),
        meta: { workspaceType: 'trading' },
      },
      {
        path: 'portfolio',
        name: 'Portfolio',
        component: () => import('@/views/PortfolioPage.vue'),
      },
      {
        path: 'portfolio/overview',
        name: 'PortfolioOverview',
        component: () => import('@/views/PortfolioPage.vue'),
      },
      {
        path: 'brokers',
        redirect: { name: 'TradingWorkspaceList' },
      },
      {
        path: 'portfolio-ledger',
        redirect: { name: 'PortfolioOverview' },
      },
      {
        path: 'portfolio/ledger',
        redirect: { name: 'PortfolioOverview' },
      },
      {
        path: 'equity-research',
        name: 'EquityResearch',
        component: () => import('@/views/EquityResearchPage.vue'),
      },
      {
        path: 'news-intelligence',
        name: 'NewsIntelligence',
        component: () => import('@/views/NewsIntelligencePage.vue'),
      },
      {
        path: 'options-chain',
        redirect: { name: 'DataMarket', query: { tab: 'options' } },
      },
      {
        path: 'scanners',
        name: 'Scanners',
        component: () => import('@/views/ScannerPage.vue'),
      },
      {
        path: 'quant-tools',
        name: 'QuantTools',
        component: () => import('@/views/QuantToolsPage.vue'),
      },
      {
        path: 'knowledge-base',
        name: 'KnowledgeBase',
        component: () => import('@/views/KnowledgeBasePage.vue'),
      },
      {
        path: 'knowledge-base/:id',
        name: 'KnowledgeBaseDetail',
        component: () => import('@/views/KnowledgeBasePage.vue'),
      },
      {
        path: 'knowledge-base/:kbId/documents/:docId',
        name: 'KnowledgeBaseDocument',
        component: () => import('@/views/KnowledgeBaseDocumentPage.vue'),
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/SettingsPage.vue'),
      },
      {
        path: 'admin/settings',
        name: 'AdminSettings',
        component: () => import('@/views/SettingsPage.vue'),
        meta: { requiresAdmin: true },
      },
    ]
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
  } else if ((to.name === 'Login' || to.name === 'Register') && authStore.isAuthenticated) {
    next({ name: 'Dashboard' })
  } else if (
    to.matched.some((record) => record.meta.requiresAdmin)
    && !(authStore.user?.is_admin ?? false)
  ) {
    next({ name: 'DataMarket' })
  } else {
    next()
  }
})

export default router
