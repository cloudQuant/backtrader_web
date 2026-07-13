import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import i18n from '@/i18n'

function tt(key: string): string {
  return i18n.global.t(key)
}

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

/** Build the theme options list with localized label/description. */
function buildThemeOptions(): ThemeOption[] {
  return [
    { value: 'aurora',   label: tt('themeStore.labelAurora'),   icon: '💎', description: tt('themeStore.descAurora') },
    { value: 'obsidian', label: tt('themeStore.labelObsidian'), icon: '🌙', description: tt('themeStore.descObsidian') },
    { value: 'nebula',   label: tt('themeStore.labelNebula'),   icon: '🔮', description: tt('themeStore.descNebula') },
    { value: 'solaris',  label: tt('themeStore.labelSolaris'),  icon: '⚡', description: tt('themeStore.descSolaris') },
    { value: 'glacier',  label: tt('themeStore.labelGlacier'),  icon: '🧊', description: tt('themeStore.descGlacier') },
    { value: 'meridian', label: tt('themeStore.labelMeridian'), icon: '☀️', description: tt('themeStore.descMeridian') },
    { value: 'verdant',  label: tt('themeStore.labelVerdant'),  icon: '🌿', description: tt('themeStore.descVerdant') },
  ]
}

/**
 * All available themes with metadata for the UI selector.
 *
 * Exported as an array literal for backward compatibility. Inside the store
 * `themes` is a computed ref that rebuilds on access so locale switches
 * reflect in the UI immediately. Direct access via THEME_OPTIONS returns the
 * current locale snapshot.
 */
export const THEME_OPTIONS: ThemeOption[] = buildThemeOptions()

/** CSS variable definitions for each theme. */
const THEME_VARIABLES: Record<string, Record<string, string>> = {
  // Aurora — Coinbase-inspired: clean blue, trust-focused, institutional
  aurora: {
    '--bg-color': 'var(--theme-aurora-bg-color)',
    '--bg-color-page': 'var(--theme-aurora-bg-color-page)',
    '--bg-color-overlay': 'var(--theme-aurora-bg-color-overlay)',
    '--bg-color-sidebar': 'var(--theme-aurora-bg-color-sidebar)',
    '--sidebar-text-color': 'var(--theme-aurora-sidebar-text-color)',
    '--sidebar-text-color-muted': 'var(--theme-aurora-sidebar-text-color-muted)',
    '--sidebar-active-color': 'var(--theme-aurora-sidebar-active-color)',
    '--sidebar-active-bg': 'var(--theme-aurora-sidebar-active-bg)',
    '--sidebar-hover-bg': 'var(--theme-aurora-sidebar-hover-bg)',
    '--sidebar-border-color': 'var(--theme-aurora-sidebar-border-color)',
    '--text-color-primary': 'var(--theme-aurora-text-color-primary)',
    '--text-color-regular': 'var(--theme-aurora-text-color-regular)',
    '--text-color-secondary': 'var(--theme-aurora-text-color-secondary)',
    '--text-color-placeholder': 'var(--theme-aurora-text-color-placeholder)',
    '--border-color': 'var(--theme-aurora-border-color)',
    '--border-color-light': 'var(--theme-aurora-border-color-light)',
    '--border-color-lighter': 'var(--theme-aurora-border-color-lighter)',
    '--fill-color': 'var(--theme-aurora-fill-color)',
    '--fill-color-light': 'var(--theme-aurora-fill-color-light)',
    '--fill-color-lighter': 'var(--theme-aurora-fill-color-lighter)',
    '--shadow-color': 'var(--theme-aurora-shadow-color)',
    '--primary-color': 'var(--theme-aurora-accent-color)',
    '--primary-on-color': 'var(--theme-aurora-primary-on-color)',
    '--accent-color': 'var(--theme-aurora-accent-color)',
    '--success-color': 'var(--theme-aurora-success-color)',
    '--warning-color': 'var(--theme-aurora-warning-color)',
    '--danger-color': 'var(--theme-aurora-danger-color)',
  },

  // Obsidian — Revolut-inspired: sleek dark, gradient cards, fintech precision
  obsidian: {
    '--bg-color': 'var(--theme-obsidian-bg-color)',
    '--bg-color-page': 'var(--theme-obsidian-bg-color-page)',
    '--bg-color-overlay': 'var(--theme-obsidian-bg-color-overlay)',
    '--bg-color-sidebar': 'var(--theme-obsidian-bg-color-sidebar)',
    '--sidebar-text-color': 'var(--theme-obsidian-sidebar-text-color)',
    '--sidebar-text-color-muted': 'var(--theme-obsidian-sidebar-text-color-muted)',
    '--sidebar-active-color': 'var(--theme-obsidian-sidebar-active-color)',
    '--sidebar-active-bg': 'var(--theme-obsidian-sidebar-active-bg)',
    '--sidebar-hover-bg': 'var(--theme-obsidian-sidebar-hover-bg)',
    '--sidebar-border-color': 'var(--theme-obsidian-sidebar-border-color)',
    '--text-color-primary': 'var(--theme-obsidian-text-color-primary)',
    '--text-color-regular': 'var(--theme-obsidian-text-color-regular)',
    '--text-color-secondary': 'var(--theme-obsidian-text-color-secondary)',
    '--text-color-placeholder': 'var(--theme-obsidian-text-color-placeholder)',
    '--border-color': 'var(--theme-obsidian-border-color)',
    '--border-color-light': 'var(--theme-obsidian-border-color-light)',
    '--border-color-lighter': 'var(--theme-obsidian-border-color-lighter)',
    '--fill-color': 'var(--theme-obsidian-fill-color)',
    '--fill-color-light': 'var(--theme-obsidian-fill-color-light)',
    '--fill-color-lighter': 'var(--theme-obsidian-fill-color-lighter)',
    '--shadow-color': 'var(--theme-obsidian-shadow-color)',
    '--primary-color': 'var(--theme-obsidian-accent-color)',
    '--primary-on-color': 'var(--theme-obsidian-primary-on-color)',
    '--accent-color': 'var(--theme-obsidian-accent-color)',
    '--success-color': 'var(--theme-obsidian-success-color)',
    '--warning-color': 'var(--theme-obsidian-warning-color)',
    '--danger-color': 'var(--theme-obsidian-danger-color)',
  },

  // Nebula — Kraken-inspired: purple-accented dark, data-dense dashboards
  nebula: {
    '--bg-color': 'var(--theme-nebula-bg-color)',
    '--bg-color-page': 'var(--theme-nebula-bg-color-page)',
    '--bg-color-overlay': 'var(--theme-nebula-bg-color-overlay)',
    '--bg-color-sidebar': 'var(--theme-nebula-bg-color-sidebar)',
    '--sidebar-text-color': 'var(--theme-nebula-sidebar-text-color)',
    '--sidebar-text-color-muted': 'var(--theme-nebula-sidebar-text-color-muted)',
    '--sidebar-active-color': 'var(--theme-nebula-sidebar-active-color)',
    '--sidebar-active-bg': 'var(--theme-nebula-sidebar-active-bg)',
    '--sidebar-hover-bg': 'var(--theme-nebula-sidebar-hover-bg)',
    '--sidebar-border-color': 'var(--theme-nebula-sidebar-border-color)',
    '--text-color-primary': 'var(--theme-nebula-text-color-primary)',
    '--text-color-regular': 'var(--theme-nebula-text-color-regular)',
    '--text-color-secondary': 'var(--theme-nebula-text-color-secondary)',
    '--text-color-placeholder': 'var(--theme-nebula-text-color-placeholder)',
    '--border-color': 'var(--theme-nebula-border-color)',
    '--border-color-light': 'var(--theme-nebula-border-color-light)',
    '--border-color-lighter': 'var(--theme-nebula-border-color-lighter)',
    '--fill-color': 'var(--theme-nebula-fill-color)',
    '--fill-color-light': 'var(--theme-nebula-fill-color-light)',
    '--fill-color-lighter': 'var(--theme-nebula-fill-color-lighter)',
    '--shadow-color': 'var(--theme-nebula-shadow-color)',
    '--primary-color': 'var(--theme-nebula-accent-color)',
    '--primary-on-color': 'var(--theme-nebula-primary-on-color)',
    '--accent-color': 'var(--theme-nebula-accent-color)',
    '--success-color': 'var(--theme-nebula-success-color)',
    '--warning-color': 'var(--theme-nebula-warning-color)',
    '--danger-color': 'var(--theme-nebula-danger-color)',
  },

  // Solaris — Binance-inspired: bold yellow on monochrome, trading-floor urgency
  // Key differentiator: warm-tinted dark background + prominent gold accents
  solaris: {
    '--bg-color': 'var(--theme-solaris-bg-color)',
    '--bg-color-page': 'var(--theme-solaris-bg-color-page)',
    '--bg-color-overlay': 'var(--theme-solaris-bg-color-overlay)',
    '--bg-color-sidebar': 'var(--theme-solaris-bg-color-sidebar)',
    '--sidebar-text-color': 'var(--theme-solaris-sidebar-text-color)',
    '--sidebar-text-color-muted': 'var(--theme-solaris-sidebar-text-color-muted)',
    '--sidebar-active-color': 'var(--theme-solaris-sidebar-active-color)',
    '--sidebar-active-bg': 'var(--theme-solaris-sidebar-active-bg)',
    '--sidebar-hover-bg': 'var(--theme-solaris-sidebar-hover-bg)',
    '--sidebar-border-color': 'var(--theme-solaris-sidebar-border-color)',
    '--text-color-primary': 'var(--theme-solaris-text-color-primary)',
    '--text-color-regular': 'var(--theme-solaris-text-color-regular)',
    '--text-color-secondary': 'var(--theme-solaris-text-color-secondary)',
    '--text-color-placeholder': 'var(--theme-solaris-text-color-placeholder)',
    '--border-color': 'var(--theme-solaris-border-color)',
    '--border-color-light': 'var(--theme-solaris-border-color-light)',
    '--border-color-lighter': 'var(--theme-solaris-border-color-lighter)',
    '--fill-color': 'var(--theme-solaris-fill-color)',
    '--fill-color-light': 'var(--theme-solaris-fill-color-light)',
    '--fill-color-lighter': 'var(--theme-solaris-fill-color-lighter)',
    '--shadow-color': 'var(--theme-solaris-shadow-color)',
    '--primary-color': 'var(--theme-solaris-accent-color)',
    '--primary-on-color': 'var(--theme-solaris-primary-on-color)',
    '--accent-color': 'var(--theme-solaris-accent-color)',
    '--success-color': 'var(--theme-solaris-success-color)',
    '--warning-color': 'var(--theme-solaris-warning-color)',
    '--danger-color': 'var(--theme-solaris-danger-color)',
  },

  // Glacier — Stripe-inspired: signature purple gradients, weight-300 elegance
  glacier: {
    '--bg-color': 'var(--theme-glacier-bg-color)',
    '--bg-color-page': 'var(--theme-glacier-bg-color-page)',
    '--bg-color-overlay': 'var(--theme-glacier-bg-color-overlay)',
    '--bg-color-sidebar': 'var(--theme-glacier-bg-color-sidebar)',
    '--sidebar-text-color': 'var(--theme-glacier-sidebar-text-color)',
    '--sidebar-text-color-muted': 'var(--theme-glacier-sidebar-text-color-muted)',
    '--sidebar-active-color': 'var(--theme-glacier-sidebar-active-color)',
    '--sidebar-active-bg': 'var(--theme-glacier-sidebar-active-bg)',
    '--sidebar-hover-bg': 'var(--theme-glacier-sidebar-hover-bg)',
    '--sidebar-border-color': 'var(--theme-glacier-sidebar-border-color)',
    '--text-color-primary': 'var(--theme-glacier-text-color-primary)',
    '--text-color-regular': 'var(--theme-glacier-text-color-regular)',
    '--text-color-secondary': 'var(--theme-glacier-text-color-secondary)',
    '--text-color-placeholder': 'var(--theme-glacier-text-color-placeholder)',
    '--border-color': 'var(--theme-glacier-border-color)',
    '--border-color-light': 'var(--theme-glacier-border-color-light)',
    '--border-color-lighter': 'var(--theme-glacier-border-color-lighter)',
    '--fill-color': 'var(--theme-glacier-fill-color)',
    '--fill-color-light': 'var(--theme-glacier-fill-color-light)',
    '--fill-color-lighter': 'var(--theme-glacier-fill-color-lighter)',
    '--shadow-color': 'var(--theme-glacier-shadow-color)',
    '--primary-color': 'var(--theme-glacier-accent-color)',
    '--primary-on-color': 'var(--theme-glacier-primary-on-color)',
    '--accent-color': 'var(--theme-glacier-accent-color)',
    '--success-color': 'var(--theme-glacier-success-color)',
    '--warning-color': 'var(--theme-glacier-warning-color)',
    '--danger-color': 'var(--theme-glacier-danger-color)',
  },

  // Meridian — Mastercard-inspired: warm cream canvas, editorial warmth
  meridian: {
    '--bg-color': 'var(--theme-meridian-bg-color)',
    '--bg-color-page': 'var(--theme-meridian-bg-color-page)',
    '--bg-color-overlay': 'var(--theme-meridian-bg-color-overlay)',
    '--bg-color-sidebar': 'var(--theme-meridian-bg-color-sidebar)',
    '--sidebar-text-color': 'var(--theme-meridian-sidebar-text-color)',
    '--sidebar-text-color-muted': 'var(--theme-meridian-sidebar-text-color-muted)',
    '--sidebar-active-color': 'var(--theme-meridian-sidebar-active-color)',
    '--sidebar-active-bg': 'var(--theme-meridian-sidebar-active-bg)',
    '--sidebar-hover-bg': 'var(--theme-meridian-sidebar-hover-bg)',
    '--sidebar-border-color': 'var(--theme-meridian-sidebar-border-color)',
    '--text-color-primary': 'var(--theme-meridian-text-color-primary)',
    '--text-color-regular': 'var(--theme-meridian-text-color-regular)',
    '--text-color-secondary': 'var(--theme-meridian-text-color-secondary)',
    '--text-color-placeholder': 'var(--theme-meridian-text-color-placeholder)',
    '--border-color': 'var(--theme-meridian-border-color)',
    '--border-color-light': 'var(--theme-meridian-border-color-light)',
    '--border-color-lighter': 'var(--theme-meridian-border-color-lighter)',
    '--fill-color': 'var(--theme-meridian-fill-color)',
    '--fill-color-light': 'var(--theme-meridian-fill-color-light)',
    '--fill-color-lighter': 'var(--theme-meridian-fill-color-lighter)',
    '--shadow-color': 'var(--theme-meridian-shadow-color)',
    '--primary-color': 'var(--theme-meridian-accent-color)',
    '--primary-on-color': 'var(--theme-meridian-primary-on-color)',
    '--accent-color': 'var(--theme-meridian-accent-color)',
    '--success-color': 'var(--theme-meridian-success-color)',
    '--warning-color': 'var(--theme-meridian-warning-color)',
    '--danger-color': 'var(--theme-meridian-danger-color)',
  },

  // Verdant — Wise-inspired: bright green accent, friendly and clear
  verdant: {
    '--bg-color': 'var(--theme-verdant-bg-color)',
    '--bg-color-page': 'var(--theme-verdant-bg-color-page)',
    '--bg-color-overlay': 'var(--theme-verdant-bg-color-overlay)',
    '--bg-color-sidebar': 'var(--theme-verdant-bg-color-sidebar)',
    '--sidebar-text-color': 'var(--theme-verdant-sidebar-text-color)',
    '--sidebar-text-color-muted': 'var(--theme-verdant-sidebar-text-color-muted)',
    '--sidebar-active-color': 'var(--theme-verdant-sidebar-active-color)',
    '--sidebar-active-bg': 'var(--theme-verdant-sidebar-active-bg)',
    '--sidebar-hover-bg': 'var(--theme-verdant-sidebar-hover-bg)',
    '--sidebar-border-color': 'var(--theme-verdant-sidebar-border-color)',
    '--text-color-primary': 'var(--theme-verdant-text-color-primary)',
    '--text-color-regular': 'var(--theme-verdant-text-color-regular)',
    '--text-color-secondary': 'var(--theme-verdant-text-color-secondary)',
    '--text-color-placeholder': 'var(--theme-verdant-text-color-placeholder)',
    '--border-color': 'var(--theme-verdant-border-color)',
    '--border-color-light': 'var(--theme-verdant-border-color-light)',
    '--border-color-lighter': 'var(--theme-verdant-border-color-lighter)',
    '--fill-color': 'var(--theme-verdant-fill-color)',
    '--fill-color-light': 'var(--theme-verdant-fill-color-light)',
    '--fill-color-lighter': 'var(--theme-verdant-fill-color-lighter)',
    '--shadow-color': 'var(--theme-verdant-shadow-color)',
    '--primary-color': 'var(--theme-verdant-accent-color)',
    '--primary-on-color': 'var(--theme-verdant-primary-on-color)',
    '--accent-color': 'var(--theme-verdant-accent-color)',
    '--success-color': 'var(--theme-verdant-success-color)',
    '--warning-color': 'var(--theme-verdant-warning-color)',
    '--danger-color': 'var(--theme-verdant-danger-color)',
  },
}

const THEME_META_COLOR_VARS: Record<ThemeMode, string> = {
  aurora: '--theme-aurora-bg-color',
  obsidian: '--theme-obsidian-bg-color',
  nebula: '--theme-nebula-bg-color',
  solaris: '--theme-solaris-bg-color',
  glacier: '--theme-glacier-bg-color',
  meridian: '--theme-meridian-bg-color',
  verdant: '--theme-verdant-bg-color',
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>('aurora')
  const sidebarCollapsed = ref(false)

  /** List of available themes for the UI (rebuilt per call so locale switches reflect). */
  const themes = computed(() => buildThemeOptions())

  /** Current theme label for display (locale-aware). */
  const currentThemeLabel = computed(() => {
    const option = buildThemeOptions().find(t => t.value === mode.value)
    return option?.label ?? tt('themeStore.labelAurora')
  })

  /** Current theme icon for display. */
  const currentThemeIcon = computed(() => {
    const option = buildThemeOptions().find(t => t.value === mode.value)
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
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }))
    }

    // Update meta theme-color
    const metaThemeColor = document.querySelector('meta[name="theme-color"]')
    if (metaThemeColor) {
      const themeColorVar = THEME_META_COLOR_VARS[theme] || '--theme-aurora-bg-color'
      const resolvedThemeColor = getComputedStyle(html).getPropertyValue(themeColorVar).trim()
      metaThemeColor.setAttribute('content', resolvedThemeColor || '#FFFFFF')
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
