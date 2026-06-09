import enUS from './en-US'

/**
 * Locale generation helper.
 *
 * The English bundle (`en-US`) is the canonical source of truth for the full
 * translation-key structure (~55 namespaces). New locales are produced by deep
 * cloning that structure and overlaying translated values, which guarantees
 * every locale exposes an identical key set with no missing or extra paths
 * (see Requirement 8 / locale-completeness test). Keys that are not yet
 * translated fall through to their English text — functionally identical to
 * vue-i18n's `fallbackLocale`, but kept structurally complete.
 */

type LocaleTree = { [key: string]: string | LocaleTree }

function deepClone<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item) => deepClone(item)) as unknown as T
  }
  if (value !== null && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [key, val] of Object.entries(value as Record<string, unknown>)) {
      out[key] = deepClone(val)
    }
    return out as T
  }
  return value
}

/**
 * Recursively overlay `overrides` onto `base`, mutating `base` in place.
 * Only keys already present in `base` are meaningful; override-only keys are
 * still applied but should mirror the canonical structure to avoid drift.
 */
function deepMerge(base: LocaleTree, overrides: DeepPartial<LocaleTree>): LocaleTree {
  for (const [key, val] of Object.entries(overrides)) {
    if (val === undefined) continue
    const current = base[key]
    if (
      val !== null
      && typeof val === 'object'
      && current !== null
      && typeof current === 'object'
      && !Array.isArray(val)
    ) {
      deepMerge(current as LocaleTree, val as DeepPartial<LocaleTree>)
    } else {
      base[key] = val as string | LocaleTree
    }
  }
  return base
}

export type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P]
}

export type LocaleMessages = typeof enUS

/**
 * Build a complete locale bundle from the English baseline plus translated
 * overrides for the high-visibility namespaces.
 */
export function buildLocale(overrides: DeepPartial<LocaleMessages>): LocaleMessages {
  const base = deepClone(enUS) as unknown as LocaleTree
  deepMerge(base, overrides as DeepPartial<LocaleTree>)
  return base as unknown as LocaleMessages
}
