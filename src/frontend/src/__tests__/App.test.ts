import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import App from '@/App.vue'

vi.mock('element-plus/dist/locale/zh-cn.mjs', () => ({ default: {} }))
vi.mock('element-plus/dist/locale/en.mjs', () => ({ default: {} }))
vi.mock('vue-i18n', () => ({
  createI18n: vi.fn(() => ({ global: { t: (key: string) => key } })),
  useI18n: vi.fn(() => ({ t: (key: string) => key, locale: ref('zh-CN') })),
}))

describe('App', () => {
  it('mounts without error', () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          'el-config-provider': { template: '<div><slot /></div>' },
          'router-view': { template: '<div />' },
        },
      },
    })
    expect(wrapper.exists()).toBe(true)
  })
})
