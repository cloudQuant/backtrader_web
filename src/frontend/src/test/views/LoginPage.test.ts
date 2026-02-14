import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LoginPage from '@/views/LoginPage.vue'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ query: {} }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElCard: { name: 'ElCard', template: '<div><slot /><slot name="header" /></div>' },
  ElForm: { name: 'ElForm', template: '<form @submit.prevent><slot /></form>', methods: { validate: (cb: Function) => cb(true) } },
  ElFormItem: { name: 'ElFormItem', template: '<div><slot /></div>' },
  ElInput: { name: 'ElInput', template: '<input />', props: ['modelValue'] },
  ElButton: { name: 'ElButton', template: '<button><slot /></button>' },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    login: vi.fn().mockResolvedValue(undefined),
    isAuthenticated: false,
  }),
}))

describe('LoginPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders login form', () => {
    const wrapper = mount(LoginPage, {
      global: {
        stubs: {
          'router-link': { template: '<a><slot /></a>' },
          'el-card': { template: '<div><slot /><slot name="header" /></div>' },
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>' },
          'el-input': { template: '<input />' },
          'el-button': { template: '<button><slot /></button>' },
        },
      },
    })
    expect(wrapper.text()).toContain('Backtrader Web')
    expect(wrapper.text()).toContain('登录')
    expect(wrapper.text()).toContain('立即注册')
  })

  it('has reactive form data', () => {
    const wrapper = mount(LoginPage, {
      global: {
        stubs: {
          'router-link': { template: '<a><slot /></a>' },
          'el-card': { template: '<div><slot /><slot name="header" /></div>' },
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>' },
          'el-input': { template: '<input />' },
          'el-button': { template: '<button><slot /></button>' },
        },
      },
    })
    expect(wrapper.vm.form.username).toBe('')
    expect(wrapper.vm.form.password).toBe('')
    expect(wrapper.vm.loading).toBe(false)
  })
})
