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
      },
      {
        path: 'backtest/workspace/:id',
        name: 'BacktestWorkspaceDetail',
        component: () => import('@/views/workspace/WorkspaceDetailPage.vue'),
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
        path: 'optimization',
        name: 'Optimization',
        component: () => import('@/views/OptimizationPage.vue'),
      },
      {
        path: 'strategy',
        name: 'Strategy',
        component: () => import('@/views/StrategyPage.vue'),
      },
      {
        path: 'data',
        name: 'Data',
        component: () => import('@/views/DataPage.vue'),
      },
      {
        path: 'simulate',
        name: 'Simulate',
        component: () => import('@/views/SimulatePage.vue'),
      },
      {
        path: 'simulate/:id',
        name: 'SimulateDetail',
        component: () => import('@/views/SimulateDetailPage.vue'),
      },
      {
        path: 'live-trading',
        name: 'LiveTrading',
        component: () => import('@/views/LiveTradingPage.vue'),
      },
      {
        path: 'live-trading/:id',
        name: 'LiveTradingDetail',
        component: () => import('@/views/LiveTradingDetailPage.vue'),
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
      },
      {
        path: 'workspace/:id',
        name: 'WorkspaceDetail',
        component: () => import('@/views/workspace/WorkspaceDetailPage.vue'),
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
  } else {
    next()
  }
})

export default router
