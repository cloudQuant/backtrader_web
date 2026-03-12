import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'auto'

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(
    (localStorage.getItem('theme-mode') as ThemeMode) || 'light'
  )

  /**
   * 应用主题到 DOM
   */
  function applyTheme(theme: 'light' | 'dark') {
    const html = document.documentElement
    
    if (theme === 'dark') {
      html.classList.add('dark')
    } else {
      html.classList.remove('dark')
    }
    
    // 更新 CSS 变量
    updateCSSVariables(theme)
    
    // 更新 meta theme-color
    const metaThemeColor = document.querySelector('meta[name="theme-color"]')
    if (metaThemeColor) {
      metaThemeColor.setAttribute('content', theme === 'dark' ? '#141414' : '#FFFFFF')
    }
  }

  /**
   * 更新 CSS 变量
   */
  function updateCSSVariables(theme: 'light' | 'dark') {
    const root = document.documentElement
    
    const lightColors = {
      '--bg-color': '#FFFFFF',
      '--bg-color-page': '#F2F3F5',
      '--bg-color-overlay': '#FFFFFF',
      '--text-color-primary': '#303133',
      '--text-color-regular': '#606266',
      '--text-color-secondary': '#909399',
      '--text-color-placeholder': '#C0C4CC',
      '--border-color': '#DCDFE6',
      '--border-color-light': '#E4E7ED',
      '--border-color-lighter': '#EBEEF5',
      '--fill-color': '#F0F2F5',
      '--fill-color-light': '#F5F7FA',
      '--fill-color-lighter': '#FAFAFA',
      '--shadow-color': 'rgba(0, 0, 0, 0.12)',
    }
    
    const darkColors = {
      '--bg-color': '#141414',
      '--bg-color-page': '#0A0A0A',
      '--bg-color-overlay': '#1D1D1D',
      '--text-color-primary': '#E5EAF3',
      '--text-color-regular': '#CFD3DC',
      '--text-color-secondary': '#A3A6AD',
      '--text-color-placeholder': '#8D9095',
      '--border-color': '#4C4D4F',
      '--border-color-light': '#414243',
      '--border-color-lighter': '#363637',
      '--fill-color': '#303030',
      '--fill-color-light': '#262727',
      '--fill-color-lighter': '#1D1D1D',
      '--shadow-color': 'rgba(0, 0, 0, 0.48)',
    }
    
    const colors = theme === 'dark' ? darkColors : lightColors
    
    Object.entries(colors).forEach(([key, value]) => {
      root.style.setProperty(key, value)
    })
  }

  /**
   * 切换主题
   */
  function toggleTheme() {
    const currentTheme = mode.value === 'dark' ? 'light' : 'dark'
    setTheme(currentTheme)
  }

  /**
   * 设置主题
   */
  function setTheme(theme: ThemeMode) {
    mode.value = theme
    localStorage.setItem('theme-mode', theme)
    
    if (theme === 'auto') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      applyTheme(prefersDark ? 'dark' : 'light')
    } else {
      applyTheme(theme)
    }
  }

  /**
   * 获取当前实际主题（auto 模式下返回实际应用的主题）
   */
  function getActualTheme(): 'light' | 'dark' {
    if (mode.value === 'auto') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
    return mode.value
  }

  /**
   * 初始化主题
   */
  function init() {
    // 应用初始主题
    if (mode.value === 'auto') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      applyTheme(prefersDark ? 'dark' : 'light')
      
      // 监听系统主题变化
      window.matchMedia('(prefers-color-scheme: dark)')
        .addEventListener('change', (e) => {
          if (mode.value === 'auto') {
            applyTheme(e.matches ? 'dark' : 'light')
          }
        })
    } else {
      applyTheme(mode.value)
    }
    
    // 添加 meta theme-color 标签
    if (!document.querySelector('meta[name="theme-color"]')) {
      const meta = document.createElement('meta')
      meta.name = 'theme-color'
      meta.content = getActualTheme() === 'dark' ? '#141414' : '#FFFFFF'
      document.head.appendChild(meta)
    }
  }

  return {
    mode,
    toggleTheme,
    setTheme,
    getActualTheme,
    init
  }
})
