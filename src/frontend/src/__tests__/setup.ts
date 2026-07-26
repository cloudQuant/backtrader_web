/**
 * Vitest 测试设置文件
 * 在所有测试运行前执行
 */
import { config } from '@vue/test-utils'
import { ref } from 'vue'
import { vi } from 'vitest'

import { elStubs } from './stubs'
import zhCN from '@/i18n/locales/zh-CN'

function createMemoryStorage(): Storage {
  const entries = new Map<string, string>()
  return {
    get length() {
      return entries.size
    },
    clear() {
      entries.clear()
    },
    getItem(key: string) {
      return entries.get(key) ?? null
    },
    key(index: number) {
      return Array.from(entries.keys())[index] ?? null
    },
    removeItem(key: string) {
      entries.delete(key)
    },
    setItem(key: string, value: string) {
      entries.set(key, String(value))
    },
  } as Storage
}

function hasStorageApi(value: unknown): value is Storage {
  if (!value || typeof value !== 'object') return false
  const storage = value as Partial<Storage>
  return ['getItem', 'setItem', 'removeItem', 'clear', 'key'].every(
    method => typeof storage[method as keyof Storage] === 'function',
  )
}

function ensureStorageApi(name: 'localStorage' | 'sessionStorage') {
  if (hasStorageApi(globalThis[name])) return
  Object.defineProperty(globalThis, name, {
    value: createMemoryStorage(),
    configurable: true,
    writable: true,
  })
}

// Node 25 can expose an incomplete experimental Storage object when its
// --localstorage-file option is unset. Keep browser-facing tests independent
// from that host setting while allowing individual suites to stub Storage.
ensureStorageApi('localStorage')
ensureStorageApi('sessionStorage')

// Flatten the zh-CN nested object into a dotted-key map so `t('ns.key')`
// returns the localized string. Iteration 176 §C left many tests asserting
// directly against Chinese phrases, so this restores those assertions
// without requiring per-file vi.mock('vue-i18n', ...) overrides.
function flattenLocale(obj: Record<string, unknown>, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object') {
      Object.assign(out, flattenLocale(v as Record<string, unknown>, key))
    } else {
      out[key] = String(v)
    }
  }
  return out
}

const flatZhCN = flattenLocale(zhCN as Record<string, unknown>)

function tWithInterp(key: string, named?: Record<string, unknown>): string {
  const template = flatZhCN[key] ?? key
  if (!named) return template
  return template.replace(/\{(\w+)\}/g, (_, name) =>
    name in named ? String(named[name]) : `{${name}}`
  )
}

// Iteration 176 §C left many components calling useI18n() in <script setup>.
// Without a vue-i18n install (createI18n + app.use), those calls throw at
// mount time ("Need to install with `app.use` function"). Provide a
// passthrough that returns the actual zh-CN translation so existing
// per-test assertions on Chinese phrases keep working.
//
// Individual tests can still override this via vi.mock('vue-i18n', ...) when
// they need locale-specific assertions on en-US.
vi.mock('vue-i18n', () => ({
  createI18n: vi.fn(() => ({
    global: { t: tWithInterp, locale: ref('zh-CN') },
    install: vi.fn(),
  })),
  useI18n: vi.fn(() => ({
    t: tWithInterp,
    locale: ref('zh-CN'),
  })),
}))

// Iteration 176 §C TS-modules (api/index, stores/quote, stores/kbChat,
// composables/useBacktestRuntime, …) import the i18n singleton directly via
// `import i18n from '@/i18n'` and call `i18n.global.t(key, named)`. Mirror
// the same passthrough so these modules render zh-CN strings.
vi.mock('@/i18n', () => ({
  default: {
    global: {
      t: tWithInterp,
      locale: { value: 'zh-CN' },
    },
  },
  setLocale: vi.fn(() => ({ ok: true })),
  getLocale: vi.fn(() => 'zh-CN'),
  getLocaleLabel: (code: string) => code,
}))

config.global.stubs = {
  ...(config.global.stubs || {}),
  ...elStubs,
}

// Provide $t as a global property so templates that use Vue 2-style $t()
// (e.g., StrategyPage.vue line 176 `:label="$t('common.action')"`) keep
// working without mounting a real i18n plugin.
config.global.mocks = {
  ...(config.global.mocks || {}),
  $t: tWithInterp,
}

// Mock v-loading directive
config.global.directives = {
  ...(config.global.directives || {}),
  loading: {
    mounted: vi.fn(),
    updated: vi.fn(),
    unmounted: vi.fn(),
  },
}

// Mock echarts
vi.mock('echarts', () => {
  const mockChart = {
    setOption: vi.fn(),
    dispose: vi.fn(),
    resize: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
    getOption: vi.fn(),
    clear: vi.fn(),
    getDataURL: vi.fn(() => 'data:image/png;base64,mock'),
  }

  return {
    default: {
      init: vi.fn(() => mockChart),
      connect: vi.fn(),
      disconnect: vi.fn(),
      dispose: vi.fn(),
    },
    init: vi.fn(() => mockChart),
    connect: vi.fn(),
    disconnect: vi.fn(),
    dispose: vi.fn(),
    graphic: {
      LinearGradient: vi.fn(() => ({
        color: vi.fn(),
        x: vi.fn(),
        y: vi.fn(),
        x2: vi.fn(),
        y2: vi.fn(),
      })),
    },
  }
})

// Mock Element Plus icons - comprehensive list
vi.mock('@element-plus/icons-vue', async (importOriginal) => {
  // Spread the real icon module so every icon name resolves; this is robust to
  // components importing any icon without maintaining a hand-written list.
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual }
})
