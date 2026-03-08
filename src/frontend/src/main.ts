import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import { AUTH_EXPIRED_EVENT } from './utils/session'
import './style.css'

const app = createApp(App)

// 注册Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

window.addEventListener(AUTH_EXPIRED_EVENT, () => {
  const currentRoute = router.currentRoute.value
  if (currentRoute.name === 'Login') {
    return
  }

  void router.push({
    name: 'Login',
    query: currentRoute.fullPath ? { redirect: currentRoute.fullPath } : undefined,
  })
})

app.mount('#app')
