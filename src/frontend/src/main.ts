import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import { AUTH_EXPIRED_EVENT } from './utils/session'
import { useAuthStore } from './stores/auth'
import i18n from './i18n'
import './style.css'

function installPerformanceMeasureGuard(): void {
  if (typeof window === 'undefined' || typeof Performance === 'undefined') {
    return
  }

  const originalMeasure = Performance.prototype.measure
  ;(Performance.prototype as any).measure = function (...args: Parameters<Performance['measure']>) {
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

  // 注册Element Plus图标
  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
  }

  app.use(pinia)
  app.use(i18n)
  app.use(ElementPlus)

  const authStore = useAuthStore(pinia)
  await authStore.initialize()

  app.use(router)
  await router.isReady()

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
