import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import ThemeSwitcher from '@/components/common/ThemeSwitcher.vue'
import { elStubs } from '@/test/stubs'

const buttonForwarding = {
  template: '<button class="el-button" v-bind="$attrs"><slot /></button>',
}

describe('ThemeSwitcher', () => {
  it('gives the icon-only trigger an accessible name', () => {
    setActivePinia(createPinia())
    const wrapper = mount(ThemeSwitcher, {
      global: { stubs: { ...elStubs, 'el-button': buttonForwarding } },
    })

    expect(wrapper.get('button').attributes('aria-label')).toContain('commonUi.themeCurrentLabel')
  })
})
