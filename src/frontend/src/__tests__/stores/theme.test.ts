import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useThemeStore } from '@/stores/theme'

// Ensure a proper localStorage mock exists for this test suite
const storage: Record<string, string> = {}
const localStorageMock = {
  getItem: vi.fn((key: string) => storage[key] ?? null),
  setItem: vi.fn((key: string, value: string) => { storage[key] = value }),
  removeItem: vi.fn((key: string) => { delete storage[key] }),
  clear: vi.fn(() => { Object.keys(storage).forEach(k => delete storage[k]) }),
  get length() { return Object.keys(storage).length },
  key: vi.fn((i: number) => Object.keys(storage)[i] ?? null),
}
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

describe('useThemeStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorageMock.clear()
    vi.clearAllMocks()
    document.documentElement.classList.remove('dark')
    document.documentElement.style.cssText = ''
    document.querySelector('meta[name="theme-color"]')?.remove()
  })

  it('initializes with aurora mode by default', () => {
    const store = useThemeStore()
    expect(store.mode).toBe('aurora')
  })

  it('setTheme updates mode', () => {
    const store = useThemeStore()
    store.setTheme('obsidian')
    expect(store.mode).toBe('obsidian')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('setTheme to light-based theme removes dark class', () => {
    const store = useThemeStore()
    store.setTheme('obsidian')
    store.setTheme('aurora')
    expect(store.mode).toBe('aurora')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('toggleTheme switches between aurora and obsidian', () => {
    const store = useThemeStore()
    expect(store.mode).toBe('aurora')
    store.toggleTheme()
    expect(store.mode).toBe('obsidian')
    store.toggleTheme()
    expect(store.mode).toBe('aurora')
  })

  it('getActualTheme returns dark for dark-based themes', () => {
    const store = useThemeStore()
    store.setTheme('obsidian')
    expect(store.getActualTheme()).toBe('dark')
    store.setTheme('nebula')
    expect(store.getActualTheme()).toBe('dark')
    store.setTheme('solaris')
    expect(store.getActualTheme()).toBe('dark')
  })

  it('getActualTheme returns light for light-based themes', () => {
    const store = useThemeStore()
    store.setTheme('aurora')
    expect(store.getActualTheme()).toBe('light')
    store.setTheme('glacier')
    expect(store.getActualTheme()).toBe('light')
    store.setTheme('meridian')
    expect(store.getActualTheme()).toBe('light')
    store.setTheme('verdant')
    expect(store.getActualTheme()).toBe('light')
  })

  it('all 7 themes apply CSS variables', () => {
    const store = useThemeStore()
    const themes = ['aurora', 'obsidian', 'nebula', 'solaris', 'glacier', 'meridian', 'verdant'] as const
    for (const theme of themes) {
      store.setTheme(theme)
      expect(document.documentElement.style.getPropertyValue('--bg-color')).toBeTruthy()
      expect(document.documentElement.style.getPropertyValue('--bg-color-sidebar')).toBeTruthy()
      expect(document.documentElement.style.getPropertyValue('--sidebar-active-color')).toBeTruthy()
      expect(document.documentElement.dataset.theme).toBe(theme)
    }
  })

  it('init applies theme and creates meta tag', () => {
    const store = useThemeStore()
    store.init()
    const meta = document.querySelector('meta[name="theme-color"]')
    expect(meta).toBeTruthy()
  })

  it('currentThemeLabel returns correct label', () => {
    const store = useThemeStore()
    expect(store.currentThemeLabel).toBe('极光')
    store.setTheme('solaris')
    expect(store.currentThemeLabel).toBe('烈阳')
  })

  it('currentThemeIcon returns correct icon', () => {
    const store = useThemeStore()
    expect(store.currentThemeIcon).toBe('💎')
    store.setTheme('nebula')
    expect(store.currentThemeIcon).toBe('🔮')
  })
})
