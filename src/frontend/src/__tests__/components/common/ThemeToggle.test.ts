import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import ThemeToggle from '@/components/common/ThemeToggle.vue'
import { useThemeStore } from '@/stores/theme'
import { elStubs } from '@/test/stubs'

function doMount() {
  return mount(ThemeToggle, { global: { stubs: elStubs } })
}

describe('ThemeToggle', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('mounts and exposes the current theme icon', () => {
    const wrapper = doMount()
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.html()).toContain('theme-toggle-icon')
  })

  it('handleCommand delegates to the theme store setTheme', () => {
    const wrapper = doMount()
    const store = useThemeStore()
    const spy = vi.spyOn(store, 'setTheme')
    ;(wrapper.vm as any).handleCommand('dark')
    expect(spy).toHaveBeenCalledWith('dark')
    expect(store.mode).toBe('dark')
  })

  it('reflects the selected mode after a command', () => {
    const wrapper = doMount()
    ;(wrapper.vm as any).handleCommand('light')
    const store = useThemeStore()
    expect(store.mode).toBe('light')
  })
})
