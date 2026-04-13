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
            path: 'scripts',
            name: 'DataScripts',
            component: () => import('@/views/data/DataScriptsPage.vue'),
          },
          {
            path: 'scripts/:id',
            name: 'DataScriptDetail',
            component: () => import('@/views/data/DataScriptDetailPage.vue'),
          },
          {
            path: 'tasks',
            name: 'DataTasks',
            component: () => import('@/views/data/DataTasksPage.vue'),
          },
          {
            path: 'executions',
            name: 'DataExecutions',
            component: () => import('@/views/data/DataExecutionsPage.vue'),
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
            path: 'sync',
            name: 'DataSync',
            component: () => import('@/views/data/DataSyncPage.vue'),
            meta: { requiresAdmin: true },
          },
          {
            path: 'interfaces',
            name: 'DataInterfaces',
            component: () => import('@/views/data/DataInterfacesPage.vue'),
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
        name: 'Gateways',
        component: () => import('@/views/GatewayStatusPage.vue'),
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
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/SettingsPage.vue'),
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
