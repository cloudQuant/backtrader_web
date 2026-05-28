import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('vue-router', () => ({
  useRoute: vi.fn(),
  useRouter: vi.fn(),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn(),
}))

import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import DataLayout from '@/views/data/DataLayout.vue'

const tabPaneStub = defineComponent({
  name: 'ElTabPaneStub',
  props: ['label'],
  template: '<div class="tab-pane">{{ label }}</div>',
})

function mountLayout(isAdmin: boolean) {
  vi.mocked(useRoute).mockReturnValue({ path: '/data/market' } as any)
  vi.mocked(useRouter).mockReturnValue({ push: vi.fn() } as any)
  vi.mocked(useAuthStore).mockReturnValue({
    user: { is_admin: isAdmin },
  } as any)

  return mount(DataLayout, {
    global: {
      stubs: {
        'el-card': { template: '<div class="el-card"><slot /><slot name="header" /></div>' },
        'el-tag': { template: '<span class="el-tag"><slot /></span>' },
        'el-tabs': { template: '<div class="el-tabs"><slot /></div>' },
        'el-tab-pane': tabPaneStub,
        'router-view': { template: '<div class="router-view" />' },
      },
    },
  })
}

describe('DataLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('hides 接口管理 tab for non-admin users', () => {
    const wrapper = mountLayout(false)

    expect(wrapper.text()).not.toContain('接口管理')
    expect(wrapper.text()).toContain('只读模式')
  })

  it('shows 接口管理 tab for admin users', () => {
    const wrapper = mountLayout(true)

    expect(wrapper.text()).toContain('接口管理')
    expect(wrapper.text()).toContain('管理员模式')
  })
})
