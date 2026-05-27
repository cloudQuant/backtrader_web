import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import { AUTH_EXPIRED_EVENT } from './utils/session'
import { useAuthStore } from './stores/auth'
import { AuditTracker } from './utils/auditTracker'
import i18n from './i18n'

// Element Plus base styles (CSS variables, reset) — required for auto-import to work
import 'element-plus/dist/index.css'

import './style.css'
import './styles/design-system.scss'

function installPerformanceMeasureGuard(): void {
  if (typeof window === 'undefined' || typeof Performance === 'undefined') {
    return
  }

  const originalMeasure = Performance.prototype.measure
  ;(Performance.prototype as unknown as Record<string, unknown>).measure = function (...args: Parameters<Performance['measure']>) {
    try {
      return originalMeasure.apply(this, args)
    } catch (error) {
      if (
        error instanceof TypeError
        && typeof error.message === 'string'
        && error.message.includes('cannot have a negative time stamp')
      ) {
        return undefined
      }
      throw error
    }
  }
}

installPerformanceMeasureGuard()

async function bootstrap() {
  const app = createApp(App)
  const pinia = createPinia()
  pinia.use(piniaPluginPersistedstate)

  // 全局错误处理：捕获未处理的组件渲染错误
  app.config.errorHandler = (err, _instance, info) => {
    console.error('[Global Error Handler]', err, info)
    // 在生产环境中可以上报到错误监控服务（如 Sentry）
    if (import.meta.env.PROD) {
      // TODO: 集成错误上报服务
      // reportError({ error: err, component: info })
    }
  }

  // 捕获未处理的 Promise rejection
  window.addEventListener('unhandledrejection', (event) => {
    console.error('[Unhandled Promise Rejection]', event.reason)
    // 防止某些浏览器在控制台显示默认错误
    // event.preventDefault()
  })

  // 注册Element Plus图标
  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
  }

  app.use(pinia)
  app.use(i18n)

  const authStore = useAuthStore(pinia)
  await authStore.initialize()

  app.use(router)
  await router.isReady()

  // Initialize audit tracker — only tracks when user is authenticated
  const auditTracker = new AuditTracker(() => authStore.user?.id ?? null)
  if (authStore.isAuthenticated) {
    auditTracker.start(router)
  }

  // Watch auth state changes to start/stop tracker
  const { watch } = await import('vue')
  watch(
    () => authStore.isAuthenticated,
    (isAuth) => {
      if (isAuth) {
        auditTracker.start(router)
      } else {
        void auditTracker.flush()
        auditTracker.stop()
      }
    },
  )

  window.addEventListener(AUTH_EXPIRED_EVENT, () => {
    const currentRoute = router.currentRoute.value
    if (currentRoute.name === 'Login') {
      return
    }

    // Clear all business store state on auth expiry
    authStore.logout()

    void router.push({
      name: 'Login',
      query: currentRoute.fullPath ? { redirect: currentRoute.fullPath } : undefined,
    })
  })

  app.mount('#app')
}

void bootstrap()
