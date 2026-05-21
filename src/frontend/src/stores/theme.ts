import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * Available theme identifiers.
 * - light: Default light theme
 * - dark: Dark theme for low-light environments
 * - blue: Professional blue theme
 * - green: Trading-oriented green theme
 * - auto: Follow system preference (resolves to light or dark)
 */
export type ThemeMode = 'light' | 'dark' | 'blue' | 'green' | 'auto'

export interface ThemeOption {
  value: ThemeMode
  label: string
  icon: string
  description: string
}

/** All available themes with metadata for the UI selector. */
export const THEME_OPTIONS: ThemeOption[] = [
  { value: 'light', label: '浅色', icon: '☀️', description: '默认浅色主题' },
  { value: 'dark', label: '深色', icon: '🌙', description: '深色护眼主题' },
  { value: 'blue', label: '专业蓝', icon: '💎', description: '专业金融风格' },
  { value: 'green', label: '交易绿', icon: '📈', description: '交易看盘风格' },
  { value: 'auto', label: '跟随系统', icon: '🖥️', description: '自动跟随系统设置' },
]

/** CSS variable definitions for each theme. */
const THEME_VARIABLES: Record<string, Record<string, string>> = {
  light: {
    '--bg-color': '#FFFFFF',
    '--bg-color-page': '#F2F3F5',
    '--bg-color-overlay': '#FFFFFF',
    '--bg-color-sidebar': '#1e293b',
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
    '--accent-color': '#409eff',
    '--success-color': '#67c23a',
    '--danger-color': '#f56c6c',
  },
  dark: {
    '--bg-color': '#141414',
    '--bg-color-page': '#0A0A0A',
    '--bg-color-overlay': '#1D1D1D',
    '--bg-color-sidebar': '#0f0f0f',
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
    '--accent-color': '#409eff',
    '--success-color': '#67c23a',
    '--danger-color': '#f56c6c',
  },
  blue: {
    '--bg-color': '#f0f5ff',
    '--bg-color-page': '#e8eef8',
    '--bg-color-overlay': '#ffffff',
    '--bg-color-sidebar': '#1e3a5f',
    '--text-color-primary': '#1a2a4a',
    '--text-color-regular': '#3a4a6a',
    '--text-color-secondary': '#5a6a8a',
    '--text-color-placeholder': '#8a9aba',
    '--border-color': '#b8cce8',
    '--border-color-light': '#d0dff0',
    '--border-color-lighter': '#e0ecf8',
    '--fill-color': '#e0ecf8',
    '--fill-color-light': '#eaf2fc',
    '--fill-color-lighter': '#f5f9ff',
    '--shadow-color': 'rgba(30, 58, 95, 0.1)',
    '--accent-color': '#2563eb',
    '--success-color': '#059669',
    '--danger-color': '#dc2626',
  },
  green: {
    '--bg-color': '#f0fdf4',
    '--bg-color-page': '#e8f8ec',
    '--bg-color-overlay': '#ffffff',
    '--bg-color-sidebar': '#14532d',
    '--text-color-primary': '#14532d',
    '--text-color-regular': '#2d5a3f',
    '--text-color-secondary': '#4a7a5f',
    '--text-color-placeholder': '#7aaa8f',
    '--border-color': '#a7d8b8',
    '--border-color-light': '#c0e8d0',
    '--border-color-lighter': '#d8f0e0',
    '--fill-color': '#d8f0e0',
    '--fill-color-light': '#e8f8ec',
    '--fill-color-lighter': '#f5fdf8',
    '--shadow-color': 'rgba(20, 83, 45, 0.1)',
    '--accent-color': '#16a34a',
    '--success-color': '#16a34a',
    '--danger-color': '#dc2626',
  },
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>('light')
  const sidebarCollapsed = ref(false)

  /** List of available themes for the UI. */
  const themes = computed(() => THEME_OPTIONS)

  /** Current theme label for display. */
  const currentThemeLabel = computed(() => {
    const option = THEME_OPTIONS.find(t => t.value === mode.value)
    return option?.label ?? '浅色'
  })

  /** Current theme icon for display. */
  const currentThemeIcon = computed(() => {
    const option = THEME_OPTIONS.find(t => t.value === mode.value)
    return option?.icon ?? '☀️'
  })

  /**
   * Resolve the effective base theme (light or dark) for Element Plus class toggling.
   * Blue and green themes use light-mode Element Plus components.
   */
  function resolveBaseTheme(theme: ThemeMode): 'light' | 'dark' {
    if (theme === 'dark') return 'dark'
    if (theme === 'auto') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
    return 'light' // light, blue, green all use light base
  }

  /**
   * Apply theme to DOM: set data-theme attribute, toggle dark class, update CSS variables.
   */
  function applyTheme(theme: ThemeMode) {
    const html = document.documentElement
    const effectiveTheme = theme === 'auto' ? resolveBaseTheme('auto') : theme
    const baseTheme = resolveBaseTheme(theme)

    // Set data-theme for CSS selectors
    html.dataset.theme = effectiveTheme

    // Toggle Element Plus dark class
    if (baseTheme === 'dark') {
      html.classList.add('dark')
    } else {
      html.classList.remove('dark')
    }

    // Apply CSS variables
    const variables = THEME_VARIABLES[effectiveTheme] || THEME_VARIABLES.light
    Object.entries(variables).forEach(([key, value]) => {
      html.style.setProperty(key, value)
    })

    // Update meta theme-color
    const metaThemeColor = document.querySelector('meta[name="theme-color"]')
    if (metaThemeColor) {
      metaThemeColor.setAttribute('content', variables['--bg-color'] || '#FFFFFF')
    }
  }

  /** Toggle between light and dark (simple toggle for the button). */
  function toggleTheme() {
    const next = mode.value === 'dark' ? 'light' : 'dark'
    setTheme(next)
  }

  /** Set a specific theme. */
  function setTheme(theme: ThemeMode) {
    mode.value = theme
    applyTheme(theme)
  }

  /** Get the actual rendered theme (resolves 'auto'). */
  function getActualTheme(): 'light' | 'dark' {
    return resolveBaseTheme(mode.value)
  }

  /** Initialize theme on app mount. */
  function init() {
    applyTheme(mode.value)

    // Listen for system theme changes when in auto mode
    if (mode.value === 'auto') {
      window.matchMedia('(prefers-color-scheme: dark)')
        .addEventListener('change', () => {
          if (mode.value === 'auto') {
            applyTheme('auto')
          }
        })
    }

    // Add meta theme-color if missing
    if (!document.querySelector('meta[name="theme-color"]')) {
      const meta = document.createElement('meta')
      meta.name = 'theme-color'
      meta.content = getActualTheme() === 'dark' ? '#141414' : '#FFFFFF'
      document.head.appendChild(meta)
    }
  }

  return {
    mode,
    sidebarCollapsed,
    themes,
    currentThemeLabel,
    currentThemeIcon,
    toggleTheme,
    setTheme,
    getActualTheme,
    init,
  }
}, {
  persist: {
    storage: localStorage,
    paths: ['mode', 'sidebarCollapsed'],
  },
})
