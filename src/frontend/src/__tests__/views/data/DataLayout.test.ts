import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DataLayout from '@/views/data/DataLayout.vue'

function mountLayout() {
  return mount(DataLayout, {
    global: {
      stubs: {
        'router-view': { template: '<div class="router-view" />' },
      },
    },
  })
}

describe('DataLayout', () => {
  it('renders only the active market data child page shell', () => {
    const wrapper = mountLayout()

    expect(wrapper.find('.router-view').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('行情报价')
    expect(wrapper.text()).not.toContain('市场数据')
    expect(wrapper.text()).not.toContain('市场主题')
    expect(wrapper.text()).not.toContain('市场数据中心')
    expect(wrapper.text()).not.toContain('集中查看行情报价、市场主题和投研情报入口')
  })

  it('keeps operational data management tabs out of market data shell', () => {
    const wrapper = mountLayout()

    expect(wrapper.text()).not.toContain('数据接口')
    expect(wrapper.text()).not.toContain('定时任务')
    expect(wrapper.text()).not.toContain('执行记录')
    expect(wrapper.text()).not.toContain('数据同步')
    expect(wrapper.text()).not.toContain('接口管理')
    expect(wrapper.text()).not.toContain('管理员模式')
  })
})
