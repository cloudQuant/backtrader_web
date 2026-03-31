import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import enUS from './locales/en-US'

// 获取存储的语言设置，默认为中文
function getStoredLocale(): string {
  const stored = localStorage.getItem('locale')
  if (stored && ['zh-CN', 'en-US'].includes(stored)) {
    return stored
  }
  // 根据浏览器语言自动选择
  const browserLang = navigator.language
  if (browserLang.startsWith('zh')) {
    return 'zh-CN'
  }
  return 'en-US'
}

const i18n = createI18n({
  legacy: false, // 使用 Composition API 模式
  locale: getStoredLocale(),
  fallbackLocale: 'en-US',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

// 切换语言并持久化
export function setLocale(locale: string): void {
  if (['zh-CN', 'en-US'].includes(locale)) {
    i18n.global.locale.value = locale as 'zh-CN' | 'en-US'
    localStorage.setItem('locale', locale)
    // 更新 HTML lang 属性
    document.documentElement.lang = locale === 'zh-CN' ? 'zh' : 'en'
  }
}

// 获取当前语言
export function getLocale(): string {
  return i18n.global.locale.value
}

// 获取语言标签
export function getLocaleLabel(locale: string): string {
  const labels: Record<string, string> = {
    'zh-CN': '中文',
    'en-US': 'English',
  }
  return labels[locale] || locale
}

export default i18n
