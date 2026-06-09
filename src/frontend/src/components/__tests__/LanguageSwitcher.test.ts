import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { elStubs } from '@/__tests__/stubs'
import { LOCALE_ENTRIES } from '@/i18n/locales/registry'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'

const setLocaleMock = vi.fn((_code: string) => ({ ok: true }) as { ok: boolean; reason?: string })
const warningMock = vi.fn()
const activeLocale = ref('en-US')

vi.mock('@/i18n', () => ({
  setLocale: (code: string) => setLocaleMock(code),
  getLocaleLabel: (code: string) =>
    LOCALE_ENTRIES.find((e) => e.code === code)?.label ?? code,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: activeLocale,
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: (msg: string) => warningMock(msg) },
}))

function mountSwitcher() {
  return mount(LanguageSwitcher, { global: { stubs: elStubs } })
}

function emitCommand(wrapper: ReturnType<typeof mountSwitcher>, code: string) {
  const dropdown = wrapper.findComponent('.el-dropdown') as unknown as {
    vm: { $emit: (event: string, payload: string) => void }
  }
  return dropdown.vm.$emit('command', code)
}

afterEach(() => {
  setLocaleMock.mockReset()
  setLocaleMock.mockReturnValue({ ok: true })
  warningMock.mockReset()
  activeLocale.value = 'en-US'
})

describe('LanguageSwitcher', () => {
  it('renders one option per supported locale in order', () => {
    const wrapper = mountSwitcher()
    const items = wrapper.findAll('.el-dropdown-item')
    expect(items).toHaveLength(LOCALE_ENTRIES.length)
    expect(items.map((i) => i.text())).toEqual(LOCALE_ENTRIES.map((e) => e.label))
  })

  it('marks exactly one option active matching the current locale', () => {
    activeLocale.value = 'ja-JP'
    const wrapper = mountSwitcher()
    const active = wrapper.findAll('.el-dropdown-item.is-active')
    expect(active).toHaveLength(1)
    expect(active[0].text()).toBe('日本語')
  })

  it('exposes a non-empty accessible label on the trigger', () => {
    const wrapper = mountSwitcher()
    const trigger = wrapper.find('button.language-switcher')
    expect(trigger.attributes('aria-label')).toBe('nav.languageSwitcher')
  })

  it('calls setLocale when a different language is chosen', async () => {
    const wrapper = mountSwitcher()
    await emitCommand(wrapper, 'de-DE')
    expect(setLocaleMock).toHaveBeenCalledWith('de-DE')
  })

  it('does not call setLocale when the current language is chosen', async () => {
    const wrapper = mountSwitcher()
    await emitCommand(wrapper, 'en-US')
    expect(setLocaleMock).not.toHaveBeenCalled()
  })

  it('shows a warning when persistence fails', async () => {
    setLocaleMock.mockReturnValue({ ok: true, reason: 'persist-failed' })
    const wrapper = mountSwitcher()
    await emitCommand(wrapper, 'fr-FR')
    expect(warningMock).toHaveBeenCalledWith('common.localePersistFailed')
  })
})
