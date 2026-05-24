import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * Available theme identifiers.
 *
 * Inspired by leading fintech platforms:
 * - aurora: Clean trust-focused style (Coinbase-inspired)
 * - obsidian: Sleek dark interface (Revolut-inspired)
 * - nebula: Purple-accented data-dense UI (Kraken-inspired)
 * - solaris: Bold yellow on monochrome (Binance-inspired)
 * - glacier: Signature purple gradients (Stripe-inspired)
 * - meridian: Warm cream editorial feel (Mastercard-inspired)
 * - verdant: Bright green friendly style (Wise-inspired)
 */
export type ThemeMode =
  | 'aurora'
  | 'obsidian'
  | 'nebula'
  | 'solaris'
  | 'glacier'
  | 'meridian'
  | 'verdant'

export interface ThemeOption {
  value: ThemeMode
  label: string
  icon: string
  description: string
}

/** All available themes with metadata for the UI selector. */
export const THEME_OPTIONS: ThemeOption[] = [
  { value: 'aurora', label: '极光', icon: '💎', description: '清爽信赖·机构风格' },
  { value: 'obsidian', label: '黑曜', icon: '🌙', description: '暗夜精密·科技质感' },
  { value: 'nebula', label: '星云', icon: '🔮', description: '紫韵数据·专业看盘' },
  { value: 'solaris', label: '烈阳', icon: '⚡', description: '金色脉冲·交易激情' },
  { value: 'glacier', label: '冰川', icon: '🧊', description: '紫调优雅·极简美学' },
  { value: 'meridian', label: '暖阳', icon: '☀️', description: '暖色编辑·温润阅读' },
  { value: 'verdant', label: '翠谷', icon: '🌿', description: '清新绿意·友好明快' },
]

/** CSS variable definitions for each theme. */
const THEME_VARIABLES: Record<string, Record<string, string>> = {
  // Aurora — Coinbase-inspired: clean blue, trust-focused, institutional
  aurora: {
    '--bg-color': '#FFFFFF',
    '--bg-color-page': '#F7F8FA',
    '--bg-color-overlay': '#FFFFFF',
    '--bg-color-sidebar': '#FFFFFF',
    '--sidebar-text-color': '#1E2329',
    '--sidebar-text-color-muted': '#5E6673',
    '--sidebar-active-color': '#1652F0',
    '--sidebar-active-bg': 'rgba(22, 82, 240, 0.08)',
    '--sidebar-hover-bg': 'rgba(22, 82, 240, 0.04)',
    '--sidebar-border-color': '#E8ECEF',
    '--text-color-primary': '#1E2329',
    '--text-color-regular': '#474D57',
    '--text-color-secondary': '#707A8A',
    '--text-color-placeholder': '#AEB4BC',
    '--border-color': '#E8ECEF',
    '--border-color-light': '#F0F2F5',
    '--border-color-lighter': '#F5F7FA',
    '--fill-color': '#F0F2F5',
    '--fill-color-light': '#F7F8FA',
    '--fill-color-lighter': '#FAFBFC',
    '--shadow-color': 'rgba(0, 0, 0, 0.08)',
    '--accent-color': '#1652F0',
    '--success-color': '#05B169',
    '--danger-color': '#CF304A',
  },

  // Obsidian — Revolut-inspired: sleek dark, gradient cards, fintech precision
  obsidian: {
    '--bg-color': '#191C1F',
    '--bg-color-page': '#0D0F11',
    '--bg-color-overlay': '#242830',
    '--bg-color-sidebar': '#141618',
    '--sidebar-text-color': '#F0F2F5',
    '--sidebar-text-color-muted': '#8A919E',
    '--sidebar-active-color': '#6C7BFF',
    '--sidebar-active-bg': 'rgba(108, 123, 255, 0.12)',
    '--sidebar-hover-bg': 'rgba(255, 255, 255, 0.04)',
    '--sidebar-border-color': '#2C3038',
    '--text-color-primary': '#F0F2F5',
    '--text-color-regular': '#C8CDD5',
    '--text-color-secondary': '#8A919E',
    '--text-color-placeholder': '#5C6370',
    '--border-color': '#2C3038',
    '--border-color-light': '#363C44',
    '--border-color-lighter': '#242830',
    '--fill-color': '#242830',
    '--fill-color-light': '#1E2226',
    '--fill-color-lighter': '#191C1F',
    '--shadow-color': 'rgba(0, 0, 0, 0.5)',
    '--accent-color': '#6C7BFF',
    '--success-color': '#00D68F',
    '--danger-color': '#FF4D6A',
  },

  // Nebula — Kraken-inspired: purple-accented dark, data-dense dashboards
  nebula: {
    '--bg-color': '#1B1426',
    '--bg-color-page': '#110D1A',
    '--bg-color-overlay': '#251D33',
    '--bg-color-sidebar': '#150F20',
    '--sidebar-text-color': '#E8E0F5',
    '--sidebar-text-color-muted': '#9B8FB5',
    '--sidebar-active-color': '#B07FFF',
    '--sidebar-active-bg': 'rgba(176, 127, 255, 0.15)',
    '--sidebar-hover-bg': 'rgba(176, 127, 255, 0.06)',
    '--sidebar-border-color': '#2D2440',
    '--text-color-primary': '#E8E0F5',
    '--text-color-regular': '#C4B8D9',
    '--text-color-secondary': '#9B8FB5',
    '--text-color-placeholder': '#6B5F80',
    '--border-color': '#2D2440',
    '--border-color-light': '#382E4D',
    '--border-color-lighter': '#251D33',
    '--fill-color': '#251D33',
    '--fill-color-light': '#1F1829',
    '--fill-color-lighter': '#1B1426',
    '--shadow-color': 'rgba(0, 0, 0, 0.5)',
    '--accent-color': '#B07FFF',
    '--success-color': '#00E5A0',
    '--danger-color': '#FF5C7C',
  },

  // Solaris — Binance-inspired: bold yellow on monochrome, trading-floor urgency
  // Key differentiator: warm-tinted dark background + prominent gold accents
  solaris: {
    '--bg-color': '#1E1E1E',
    '--bg-color-page': '#121212',
    '--bg-color-overlay': '#2A2A2A',
    '--bg-color-sidebar': '#1A1A1A',
    '--sidebar-text-color': '#F0E6D3',
    '--sidebar-text-color-muted': '#A89B8C',
    '--sidebar-active-color': '#F0B90B',
    '--sidebar-active-bg': 'rgba(240, 185, 11, 0.12)',
    '--sidebar-hover-bg': 'rgba(240, 185, 11, 0.05)',
    '--sidebar-border-color': '#3A3530',
    '--text-color-primary': '#F0E6D3',
    '--text-color-regular': '#C8B9A8',
    '--text-color-secondary': '#A89B8C',
    '--text-color-placeholder': '#6B6055',
    '--border-color': '#3A3530',
    '--border-color-light': '#4A4035',
    '--border-color-lighter': '#2A2520',
    '--fill-color': '#2A2520',
    '--fill-color-light': '#222018',
    '--fill-color-lighter': '#1E1C16',
    '--shadow-color': 'rgba(0, 0, 0, 0.5)',
    '--accent-color': '#F0B90B',
    '--success-color': '#0ECB81',
    '--danger-color': '#F6465D',
  },

  // Glacier — Stripe-inspired: signature purple gradients, weight-300 elegance
  glacier: {
    '--bg-color': '#FFFFFF',
    '--bg-color-page': '#F6F9FC',
    '--bg-color-overlay': '#FFFFFF',
    '--bg-color-sidebar': '#F6F9FC',
    '--sidebar-text-color': '#32325D',
    '--sidebar-text-color-muted': '#6B7C93',
    '--sidebar-active-color': '#635BFF',
    '--sidebar-active-bg': 'rgba(99, 91, 255, 0.08)',
    '--sidebar-hover-bg': 'rgba(99, 91, 255, 0.04)',
    '--sidebar-border-color': '#E3E8EE',
    '--text-color-primary': '#32325D',
    '--text-color-regular': '#525F7F',
    '--text-color-secondary': '#6B7C93',
    '--text-color-placeholder': '#ADB5BD',
    '--border-color': '#E3E8EE',
    '--border-color-light': '#EDF0F4',
    '--border-color-lighter': '#F6F9FC',
    '--fill-color': '#F0F3F7',
    '--fill-color-light': '#F6F9FC',
    '--fill-color-lighter': '#FAFCFE',
    '--shadow-color': 'rgba(50, 50, 93, 0.1)',
    '--accent-color': '#635BFF',
    '--success-color': '#3ECF8E',
    '--danger-color': '#E25950',
  },

  // Meridian — Mastercard-inspired: warm cream canvas, editorial warmth
  meridian: {
    '--bg-color': '#FFFBF5',
    '--bg-color-page': '#FFF7EE',
    '--bg-color-overlay': '#FFFFFF',
    '--bg-color-sidebar': '#FFFBF5',
    '--sidebar-text-color': '#2D2926',
    '--sidebar-text-color-muted': '#6B5E54',
    '--sidebar-active-color': '#CF4500',
    '--sidebar-active-bg': 'rgba(207, 69, 0, 0.08)',
    '--sidebar-hover-bg': 'rgba(207, 69, 0, 0.04)',
    '--sidebar-border-color': '#EDE5DA',
    '--text-color-primary': '#2D2926',
    '--text-color-regular': '#4A4340',
    '--text-color-secondary': '#6B5E54',
    '--text-color-placeholder': '#A89B90',
    '--border-color': '#EDE5DA',
    '--border-color-light': '#F5EFE7',
    '--border-color-lighter': '#FAF6F0',
    '--fill-color': '#F5EFE7',
    '--fill-color-light': '#FAF6F0',
    '--fill-color-lighter': '#FFFCF8',
    '--shadow-color': 'rgba(45, 41, 38, 0.08)',
    '--accent-color': '#CF4500',
    '--success-color': '#2E7D32',
    '--danger-color': '#C62828',
  },

  // Verdant — Wise-inspired: bright green accent, friendly and clear
  verdant: {
    '--bg-color': '#FFFFFF',
    '--bg-color-page': '#F2F7F2',
    '--bg-color-overlay': '#FFFFFF',
    '--bg-color-sidebar': '#FFFFFF',
    '--sidebar-text-color': '#1A3A2A',
    '--sidebar-text-color-muted': '#4A6B5A',
    '--sidebar-active-color': '#00B856',
    '--sidebar-active-bg': 'rgba(0, 184, 86, 0.08)',
    '--sidebar-hover-bg': 'rgba(0, 184, 86, 0.04)',
    '--sidebar-border-color': '#DCE8E0',
    '--text-color-primary': '#1A3A2A',
    '--text-color-regular': '#37574A',
    '--text-color-secondary': '#4A6B5A',
    '--text-color-placeholder': '#8FA89A',
    '--border-color': '#DCE8E0',
    '--border-color-light': '#E8F0EA',
    '--border-color-lighter': '#F2F7F2',
    '--fill-color': '#E8F0EA',
    '--fill-color-light': '#F2F7F2',
    '--fill-color-lighter': '#F8FBF8',
    '--shadow-color': 'rgba(26, 58, 42, 0.08)',
    '--accent-color': '#00B856',
    '--success-color': '#00B856',
    '--danger-color': '#D32F2F',
  },
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>('aurora')
  const sidebarCollapsed = ref(false)

  /** List of available themes for the UI. */
  const themes = computed(() => THEME_OPTIONS)

  /** Current theme label for display. */
  const currentThemeLabel = computed(() => {
    const option = THEME_OPTIONS.find(t => t.value === mode.value)
    return option?.label ?? '极光'
  })

  /** Current theme icon for display. */
  const currentThemeIcon = computed(() => {
    const option = THEME_OPTIONS.find(t => t.value === mode.value)
    return option?.icon ?? '💎'
  })

  /**
   * Resolve the effective base theme (light or dark) for Element Plus class toggling.
   * Dark-based themes: obsidian, nebula, solaris
   * Light-based themes: aurora, glacier, meridian, verdant
   */
  function resolveBaseTheme(theme: ThemeMode): 'light' | 'dark' {
    if (['obsidian', 'nebula', 'solaris'].includes(theme)) return 'dark'
    return 'light'
  }

  /**
   * Apply theme to DOM: set data-theme attribute, toggle dark class, update CSS variables.
   */
  function applyTheme(theme: ThemeMode) {
    const html = document.documentElement
    const baseTheme = resolveBaseTheme(theme)

    // Set data-theme for CSS selectors
    html.dataset.theme = theme

    // Toggle Element Plus dark class
    if (baseTheme === 'dark') {
      html.classList.add('dark')
    } else {
      html.classList.remove('dark')
    }

    // Apply CSS variables
    const variables = THEME_VARIABLES[theme] || THEME_VARIABLES.aurora
    Object.entries(variables).forEach(([key, value]) => {
      html.style.setProperty(key, value)
    })

    // Update meta theme-color
    const metaThemeColor = document.querySelector('meta[name="theme-color"]')
    if (metaThemeColor) {
      metaThemeColor.setAttribute('content', variables['--bg-color'] || '#FFFFFF')
    }
  }

  /** Toggle between aurora and obsidian (simple light/dark toggle). */
  function toggleTheme() {
    const next = resolveBaseTheme(mode.value) === 'dark' ? 'aurora' : 'obsidian'
    setTheme(next)
  }

  /** Set a specific theme. */
  function setTheme(theme: ThemeMode) {
    mode.value = theme
    applyTheme(theme)
  }

  /** Get the actual rendered base theme (light or dark). */
  function getActualTheme(): 'light' | 'dark' {
    return resolveBaseTheme(mode.value)
  }

  /** Initialize theme on app mount. */
  function init() {
    applyTheme(mode.value)

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
