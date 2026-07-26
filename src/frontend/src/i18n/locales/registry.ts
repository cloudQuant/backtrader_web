import type { Language } from 'element-plus/es/locale'

import elEn from 'element-plus/dist/locale/en.mjs'
import elZhCn from 'element-plus/dist/locale/zh-cn.mjs'
import elJa from 'element-plus/dist/locale/ja.mjs'
import elDe from 'element-plus/dist/locale/de.mjs'
import elFr from 'element-plus/dist/locale/fr.mjs'
import elIt from 'element-plus/dist/locale/it.mjs'
import elRu from 'element-plus/dist/locale/ru.mjs'

import enUS from './en-US'
import zhCN from './zh-CN'
import jaJP from './ja-JP'
import deDE from './de-DE'
import frFR from './fr-FR'
import itIT from './it-IT'
import ruRU from './ru-RU'

/** Supported BCP 47 locale codes. */
export type LocaleCode =
  | 'en-US'
  | 'zh-CN'
  | 'ja-JP'
  | 'de-DE'
  | 'fr-FR'
  | 'it-IT'
  | 'ru-RU'

export interface LocaleEntry {
  /** BCP 47 code, used as vue-i18n key and `<html lang>` value. */
  code: LocaleCode
  /** Native self-label shown in the language switcher. */
  label: string
  /** vue-i18n message bundle. */
  messages: Record<string, unknown>
  /** Matching Element Plus locale module. */
  elementLocale: Language
}

/** Default locale and fallback. */
export const DEFAULT_LOCALE: LocaleCode = 'zh-CN'

/**
 * Single source of truth for supported locales. Registration order is also the
 * display order in the language switcher dropdown.
 *
 * i18n-ignore: the `label` values below are native self-names of each language
 * (e.g. "日本語"); translating them through t() would defeat a language picker.
 */
export const LOCALE_ENTRIES: readonly LocaleEntry[] = [
  { code: 'en-US', label: 'English', messages: enUS, elementLocale: elEn },
  { code: 'zh-CN', label: '中文', messages: zhCN, elementLocale: elZhCn },
  { code: 'ja-JP', label: '日本語', messages: jaJP, elementLocale: elJa },
  { code: 'de-DE', label: 'Deutsch', messages: deDE, elementLocale: elDe },
  { code: 'fr-FR', label: 'Français', messages: frFR, elementLocale: elFr },
  { code: 'it-IT', label: 'Italiano', messages: itIT, elementLocale: elIt },
  { code: 'ru-RU', label: 'Русский', messages: ruRU, elementLocale: elRu },
]

/** All supported locale codes, in display order. */
export const SUPPORTED_LOCALES: readonly LocaleCode[] = LOCALE_ENTRIES.map(
  (entry) => entry.code,
)

/**
 * vue-i18n messages map keyed by locale code. Declared as an explicit literal
 * (rather than derived via Object.fromEntries) so vue-i18n can infer the
 * Composition-mode message types.
 */
export const MESSAGES = {
  'en-US': enUS,
  'zh-CN': zhCN,
  'ja-JP': jaJP,
  'de-DE': deDE,
  'fr-FR': frFR,
  'it-IT': itIT,
  'ru-RU': ruRU,
}

/** Type guard: whether a string is a supported locale code. */
export function isSupportedLocale(code: string): code is LocaleCode {
  return (SUPPORTED_LOCALES as readonly string[]).includes(code)
}

/** Look up an entry by code, falling back to the default locale entry. */
export function getEntry(code: LocaleCode): LocaleEntry {
  return LOCALE_ENTRIES.find((entry) => entry.code === code) ?? LOCALE_ENTRIES[0]
}
