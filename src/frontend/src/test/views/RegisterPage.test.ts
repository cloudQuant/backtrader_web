import { describe, it, expect, vi } from 'vitest'
import RegisterPage from '@/views/RegisterPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    register: vi.fn().mockResolvedValue(undefined),
  }),
}))

describe('RegisterPage', () => {
  it('renders register form', () => {
    const wrapper = mountWithPlugins(RegisterPage)
    expect(wrapper.text()).toContain('注册账号')
    expect(wrapper.text()).toContain('注册')
    expect(wrapper.text()).toContain('立即登录')
  })

  it('has reactive form with 4 fields', () => {
    const wrapper = mountWithPlugins(RegisterPage)
    const vm = wrapper.vm as any
    expect(vm.form.username).toBe('')
    expect(vm.form.email).toBe('')
    expect(vm.form.password).toBe('')
    expect(vm.form.confirmPassword).toBe('')
  })

  it('validateConfirmPassword rejects mismatch', () => {
    const wrapper = mountWithPlugins(RegisterPage)
    const vm = wrapper.vm as any
    vm.form.password = 'abc123'
    const cb = vi.fn()
    vm.rules.confirmPassword[1].validator(null, 'different', cb)
    expect(cb).toHaveBeenCalledWith(expect.any(Error))
  })

  it('validateConfirmPassword accepts match', () => {
    const wrapper = mountWithPlugins(RegisterPage)
    const vm = wrapper.vm as any
    vm.form.password = 'abc123'
    const cb = vi.fn()
    vm.rules.confirmPassword[1].validator(null, 'abc123', cb)
    expect(cb).toHaveBeenCalledWith()
  })
})
