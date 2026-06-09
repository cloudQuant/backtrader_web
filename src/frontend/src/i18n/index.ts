import { createI18n } from 'vue-i18n'

import {
  DEFAULT_LOCALE,
  MESSAGES,
  SUPPORTED_LOCALES,
  getEntry,
  isSupportedLocale,
  type LocaleCode,
} from './locales/registry'

const STORAGE_KEY = 'locale'

/**
 * Infer a supported locale from the browser language by matching the language
 * subtag (the part before the first hyphen), case-insensitively. Falls back to
 * the default locale when there is no match.
 */
function inferFromBrowser(): LocaleCode {
  const raw = (typeof navigator !== 'undefined' && navigator.language) || ''
  const sub = raw.split('-')[0]?.toLowerCase()
  if (sub) {
    const hit = SUPPORTED_LOCALES.find(
      (code) => code.split('-')[0].toLowerCase() === sub,
    )
    if (hit) return hit
  }
  return DEFAULT_LOCALE
}

/**
 * Resolve the initial locale: a valid persisted value wins; otherwise infer
 * from the browser language; otherwise the default locale.
 */
export function getStoredLocale(): LocaleCode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored && isSupportedLocale(stored)) {
      return stored
    }
  } catch {
    // localStorage unavailable (e.g. private mode) — fall through to inference.
  }
  return inferFromBrowser()
}

const i18n = createI18n({
  legacy: false, // Composition API mode
  locale: getStoredLocale(),
  fallbackLocale: DEFAULT_LOCALE,
  messages: MESSAGES,
})

/** Set `<html lang>` to the full BCP 47 code for the given locale. */
function applyHtmlLang(code: LocaleCode): void {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = getEntry(code).code
  }
}

// Apply initial document language.
applyHtmlLang(i18n.global.locale.value as LocaleCode)

export interface SetLocaleResult {
  ok: boolean
  reason?: 'unsupported' | 'persist-failed'
}

/**
 * Switch the active locale and persist the choice.
 *
 * - Rejects unsupported codes without changing any state.
 * - On success, updates vue-i18n, `<html lang>`, and localStorage.
 * - If persistence fails, the locale still switches and the result flags
 *   `persist-failed` so callers can surface a warning.
 */
export function setLocale(code: string): SetLocaleResult {
  if (!isSupportedLocale(code)) {
    return { ok: false, reason: 'unsupported' }
  }
  i18n.global.locale.value = code
  applyHtmlLang(code)
  try {
    localStorage.setItem(STORAGE_KEY, code)
  } catch {
    return { ok: true, reason: 'persist-failed' }
  }
  return { ok: true }
}

/** Current active locale. */
export function getLocale(): LocaleCode {
  return i18n.global.locale.value as LocaleCode
}

/** Native label for a locale; returns the raw code for unknown values. */
export function getLocaleLabel(code: string): string {
  return isSupportedLocale(code) ? getEntry(code).label : code
}

export default i18n
