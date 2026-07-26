import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { APP_PATHS, LEGACY_PATHS, toAppChildPath } from '@/navigation/routes'

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
        path: toAppChildPath(APP_PATHS.dashboard),
        name: 'Dashboard',
        component: () => import('@/views/DashboardPage.vue'),
      },
      {
        path: 'investment',
        redirect: { name: 'InvestmentStrategies' },
      },
      {
        path: 'investment/strategies',
        name: 'InvestmentStrategies',
        component: () => import('@/views/StrategyPage.vue'),
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
        path: toAppChildPath(APP_PATHS.research.strategies),
        name: 'ResearchStrategies',
        component: () => import('@/views/StrategyPage.vue'),
      },
      {
        path: toAppChildPath(APP_PATHS.research.workspaces),
        name: 'ResearchWorkspaces',
        component: () => import('@/views/workspace/WorkspaceListPage.vue'),
        meta: { workspaceType: 'research' },
      },
      {
        path: toAppChildPath(APP_PATHS.research.workspacePattern),
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
        redirect: { name: 'ResearchWorkspaces' },
      },
      {
        path: 'ai',
        redirect: { name: 'AIChatCanonical' },
      },
      {
        path: toAppChildPath(APP_PATHS.ai.chat),
        name: 'AIChatCanonical',
        component: () => import('@/views/AIChatPage.vue'),
      },
      {
        path: toAppChildPath(APP_PATHS.ai.knowledgeBase),
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
        path: 'ai/prompt-governance',
        redirect: { name: 'ConfigPromptTemplates' },
        meta: { requiresAdmin: true },
      },
      {
        path: 'ai/prompt-templates',
        redirect: { name: 'ConfigPromptTemplates' },
        meta: { requiresAdmin: true },
      },
      {
        path: 'ai/observability',
        redirect: { name: 'ConfigAIObservability' },
        meta: { requiresAdmin: true },
      },
      {
        path: 'ai/ai-observability',
        redirect: { name: 'ConfigAIObservability' },
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
        component: () => import('@/views/config/ConfigAILayout.vue'),
        meta: { requiresAdmin: true },
        children: [
          {
            path: '',
            redirect: { name: 'ConfigAIProviders' },
          },
          {
            path: 'providers',
            name: 'ConfigAIProviders',
            component: () => import('@/views/config/AIProviderConfigPage.vue'),
          },
          {
            path: 'prompt-governance',
            name: 'ConfigPromptTemplates',
            component: () => import('@/views/PromptTemplatesPage.vue'),
          },
          {
            path: 'observability',
            name: 'ConfigAIObservability',
            component: () => import('@/views/AIObservabilityPage.vue'),
          },
        ],
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
        path: toAppChildPath(LEGACY_PATHS.aiChat),
        redirect: { name: 'AIChatCanonical' },
      },
      {
        path: 'admin/ai-observability',
        name: 'AIObservability',
        redirect: { name: 'ConfigAIObservability' },
        meta: { requiresAdmin: true },
      },
      {
        path: 'admin/prompt-templates',
        name: 'PromptTemplates',
        redirect: { name: 'ConfigPromptTemplates' },
        meta: { requiresAdmin: true },
      },
      {
        path: 'ai-trading',
        name: 'AITrading',
        component: () => import('@/views/AITradingPage.vue'),
      },
      {
        path: toAppChildPath(APP_PATHS.backtest.list),
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
        path: toAppChildPath(APP_PATHS.backtest.resultPattern),
        name: 'BacktestResult',
        component: () => import('@/views/BacktestResultPage.vue'),
      },
      {
        path: 'paper-trading/:instanceId',
        name: 'PaperTradingDetail',
        component: () => import('@/views/PaperTradingDetailPage.vue'),
      },
      {
        path: 'paper-risk',
        name: 'RiskControl',
        component: () => import('@/views/RiskControlPage.vue'),
      },
      {
        path: toAppChildPath(LEGACY_PATHS.backtestResultPattern),
        redirect: to => ({ path: APP_PATHS.backtest.result(String(to.params.id ?? '')) }),
      },
      {
        path: toAppChildPath(LEGACY_PATHS.strategy),
        redirect: { name: 'ResearchStrategies' },
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
        path: toAppChildPath(LEGACY_PATHS.workspace),
        redirect: { name: 'ResearchWorkspaces' },
      },
      {
        path: toAppChildPath(LEGACY_PATHS.workspaceDetailPattern),
        redirect: to => ({ name: 'ResearchWorkspaceDetail', params: { id: String(to.params.id ?? '') } }),
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
        redirect: { name: 'ResearchWorkspaces' },
      },
      {
        path: toAppChildPath(LEGACY_PATHS.knowledgeBase),
        redirect: to => ({ name: 'AIKnowledgeBase', query: to.query }),
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
