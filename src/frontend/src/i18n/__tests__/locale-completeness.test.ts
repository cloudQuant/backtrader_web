import { describe, expect, it } from 'vitest'

import enUS from '@/i18n/locales/en-US'
import zhCN from '@/i18n/locales/zh-CN'
import jaJP from '@/i18n/locales/ja-JP'
import deDE from '@/i18n/locales/de-DE'
import frFR from '@/i18n/locales/fr-FR'
import itIT from '@/i18n/locales/it-IT'
import ruRU from '@/i18n/locales/ru-RU'

type Tree = Record<string, unknown>

/** Flatten a nested message object into a set of dotted key paths. */
function flattenKeys(obj: Tree, prefix = ''): string[] {
  const keys: string[] = []
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value !== null && typeof value === 'object') {
      keys.push(...flattenKeys(value as Tree, path))
    } else {
      keys.push(path)
    }
  }
  return keys
}

function flattenEntries(obj: Tree, prefix = ''): Array<[string, unknown]> {
  const entries: Array<[string, unknown]> = []
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value !== null && typeof value === 'object') {
      entries.push(...flattenEntries(value as Tree, path))
    } else {
      entries.push([path, value])
    }
  }
  return entries
}

const baseline = new Set(flattenKeys(enUS as Tree))

const locales: Record<string, Tree> = {
  'zh-CN': zhCN as Tree,
  'ja-JP': jaJP as Tree,
  'de-DE': deDE as Tree,
  'fr-FR': frFR as Tree,
  'it-IT': itIT as Tree,
  'ru-RU': ruRU as Tree,
}

describe('locale completeness', () => {
  for (const [name, bundle] of Object.entries(locales)) {
    describe(name, () => {
      const keys = flattenKeys(bundle)

      it('has no missing keys versus en-US baseline', () => {
        const missing = [...baseline].filter((k) => !keys.includes(k))
        expect(missing).toEqual([])
      })

      it('has no extra keys versus en-US baseline', () => {
        const extra = keys.filter((k) => !baseline.has(k))
        expect(extra).toEqual([])
      })

      it('has only non-empty string leaf values', () => {
        const empties = flattenEntries(bundle)
          .filter(([, v]) => typeof v !== 'string' || (v as string).trim().length === 0)
          .map(([k]) => k)
        expect(empties).toEqual([])
      })
    })
  }
})
