import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '@/App.vue'

vi.mock('element-plus/dist/locale/zh-cn.mjs', () => ({ default: {} }))

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
