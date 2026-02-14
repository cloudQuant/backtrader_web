import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import RegisterPage from './RegisterPage.vue'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    register: vi.fn().mockResolvedValue(undefined),
  }),
}))

const stubs = {
  'router-link': { template: '<a><slot /></a>' },
  'el-card': { template: '<div><slot /><slot name="header" /></div>' },
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div><slot /></div>' },
  'el-input': { template: '<input />' },
  'el-button': { template: '<button><slot /></button>' },
}

describe('RegisterPage', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('renders register form', () => {
    const wrapper = mount(RegisterPage, { global: { stubs } })
    expect(wrapper.text()).toContain('注册账号')
    expect(wrapper.text()).toContain('注册')
    expect(wrapper.text()).toContain('立即登录')
  })

  it('has reactive form with 4 fields', () => {
    const wrapper = mount(RegisterPage, { global: { stubs } })
    const vm = wrapper.vm as any
    expect(vm.form.username).toBe('')
    expect(vm.form.email).toBe('')
    expect(vm.form.password).toBe('')
    expect(vm.form.confirmPassword).toBe('')
  })

  it('validateConfirmPassword rejects mismatch', () => {
    const wrapper = mount(RegisterPage, { global: { stubs } })
    const vm = wrapper.vm as any
    vm.form.password = 'abc123'
    const cb = vi.fn()
    vm.rules.confirmPassword[1].validator(null, 'different', cb)
    expect(cb).toHaveBeenCalledWith(expect.any(Error))
  })

  it('validateConfirmPassword accepts match', () => {
    const wrapper = mount(RegisterPage, { global: { stubs } })
    const vm = wrapper.vm as any
    vm.form.password = 'abc123'
    const cb = vi.fn()
    vm.rules.confirmPassword[1].validator(null, 'abc123', cb)
    expect(cb).toHaveBeenCalledWith()
  })
})
