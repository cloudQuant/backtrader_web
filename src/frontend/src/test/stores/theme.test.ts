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

  it('initializes with light mode by default', () => {
    const store = useThemeStore()
    expect(store.mode).toBe('light')
  })

  it('reads saved theme from localStorage', () => {
    localStorage.setItem('theme-mode', 'dark')
    const store = useThemeStore()
    expect(store.mode).toBe('dark')
  })

  it('setTheme updates mode and saves to localStorage', () => {
    const store = useThemeStore()
    store.setTheme('dark')
    expect(store.mode).toBe('dark')
    expect(localStorage.getItem('theme-mode')).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('setTheme to light removes dark class', () => {
    const store = useThemeStore()
    store.setTheme('dark')
    store.setTheme('light')
    expect(store.mode).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('toggleTheme switches between light and dark', () => {
    const store = useThemeStore()
    expect(store.mode).toBe('light')
    store.toggleTheme()
    expect(store.mode).toBe('dark')
    store.toggleTheme()
    expect(store.mode).toBe('light')
  })

  it('getActualTheme returns mode for non-auto', () => {
    const store = useThemeStore()
    store.setTheme('dark')
    expect(store.getActualTheme()).toBe('dark')
    store.setTheme('light')
    expect(store.getActualTheme()).toBe('light')
  })

  it('setTheme auto uses system preference', () => {
    const matchMediaMock = vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
    })
    Object.defineProperty(window, 'matchMedia', { value: matchMediaMock, writable: true })
    const store = useThemeStore()
    store.setTheme('auto')
    expect(store.mode).toBe('auto')
    expect(store.getActualTheme()).toBe('dark')
  })

  it('init applies theme and creates meta tag', () => {
    const store = useThemeStore()
    store.init()
    const meta = document.querySelector('meta[name="theme-color"]')
    expect(meta).toBeTruthy()
  })

  it('init with auto mode listens for system changes', () => {
    const addEventListenerMock = vi.fn()
    Object.defineProperty(window, 'matchMedia', {
      value: vi.fn().mockReturnValue({
        matches: false,
        addEventListener: addEventListenerMock,
      }),
      writable: true,
    })
    localStorage.setItem('theme-mode', 'auto')
    const store = useThemeStore()
    store.init()
    expect(addEventListenerMock).toHaveBeenCalledWith('change', expect.any(Function))
  })
})
