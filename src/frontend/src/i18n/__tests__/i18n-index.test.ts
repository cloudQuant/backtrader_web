import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Use the real i18n module and the real vue-i18n implementation here, overriding
// the global test-setup mocks so we exercise the actual locale logic.
vi.unmock('@/i18n')
vi.unmock('vue-i18n')

function stubLocalStorage(initial?: string, throwOnSet = false) {
  const store = new Map<string, string>()
  if (initial !== undefined) store.set('locale', initial)
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => {
      if (throwOnSet) throw new Error('quota exceeded')
      store.set(k, v)
    },
    removeItem: (k: string) => store.delete(k),
    clear: () => store.clear(),
  })
  return store
}

function setBrowserLanguage(lang: string) {
  Object.defineProperty(navigator, 'language', { value: lang, configurable: true })
}

async function loadModule() {
  vi.resetModules()
  return import('@/i18n')
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('getStoredLocale', () => {
  beforeEach(() => setBrowserLanguage('en-US'))

  it('prefers a valid persisted locale', async () => {
    stubLocalStorage('de-DE')
    const { getStoredLocale } = await loadModule()
    expect(getStoredLocale()).toBe('de-DE')
  })

  it('falls back to browser inference for an invalid persisted value', async () => {
    stubLocalStorage('xx-YY')
    setBrowserLanguage('fr-FR')
    const { getStoredLocale } = await loadModule()
    expect(getStoredLocale()).toBe('fr-FR')
  })

  it('matches the browser language subtag', async () => {
    stubLocalStorage()
    setBrowserLanguage('ja')
    const { getStoredLocale } = await loadModule()
    expect(getStoredLocale()).toBe('ja-JP')
  })

  it('defaults to en-US when nothing matches', async () => {
    stubLocalStorage()
    setBrowserLanguage('xx')
    const { getStoredLocale } = await loadModule()
    expect(getStoredLocale()).toBe('en-US')
  })
})

describe('setLocale', () => {
  beforeEach(() => setBrowserLanguage('en-US'))

  it('switches a supported locale, sets <html lang>, and persists', async () => {
    const store = stubLocalStorage()
    const { setLocale, getLocale } = await loadModule()
    const result = setLocale('ja-JP')
    expect(result).toEqual({ ok: true })
    expect(getLocale()).toBe('ja-JP')
    expect(document.documentElement.lang).toBe('ja-JP')
    expect(store.get('locale')).toBe('ja-JP')
  })

  it('rejects an unsupported locale without changing state', async () => {
    stubLocalStorage('en-US')
    const { setLocale, getLocale } = await loadModule()
    const before = getLocale()
    const result = setLocale('xx-YY')
    expect(result).toEqual({ ok: false, reason: 'unsupported' })
    expect(getLocale()).toBe(before)
  })

  it('reports persist-failed but still switches when storage write throws', async () => {
    stubLocalStorage(undefined, true)
    const { setLocale, getLocale } = await loadModule()
    const result = setLocale('ru-RU')
    expect(result).toEqual({ ok: true, reason: 'persist-failed' })
    expect(getLocale()).toBe('ru-RU')
    expect(document.documentElement.lang).toBe('ru-RU')
  })
})

describe('getLocaleLabel', () => {
  beforeEach(() => {
    setBrowserLanguage('en-US')
    stubLocalStorage()
  })

  it('returns the native label for a supported locale', async () => {
    const { getLocaleLabel } = await loadModule()
    expect(getLocaleLabel('ja-JP')).toBe('日本語')
    expect(getLocaleLabel('ru-RU')).toBe('Русский')
  })

  it('returns the raw code for an unknown locale', async () => {
    const { getLocaleLabel } = await loadModule()
    expect(getLocaleLabel('xx-YY')).toBe('xx-YY')
  })
})
