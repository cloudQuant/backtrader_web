import { describe, it, expect, vi } from 'vitest'
import RegisterPage from '@/views/RegisterPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

type RegisterPageVm = {
  form: {
    username: string
    email: string
    password: string
    confirmPassword: string
  }
  rules: {
    confirmPassword: Array<{
      validator?: (_rule: unknown, value: string, callback: (error?: string | Error) => void) => void
    }>
  }
}

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    register: vi.fn().mockResolvedValue(undefined),
  }),
}))

vi.mock('vue-i18n', () => ({
  createI18n: vi.fn(() => ({ global: { t: (key: string) => key } })),
  useI18n: vi.fn(() => ({ t: (key: string) => key })),
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({ templates: [], total: 0 }),
  },
}))

describe('RegisterPage', () => {
  it('renders register form', () => {
    const wrapper = mountWithPlugins(RegisterPage)
    // i18n mock returns keys
    expect(wrapper.text()).toContain('auth.registerTitle')
    expect(wrapper.text()).toContain('auth.register')
    expect(wrapper.text()).toContain('auth.loginNow')
  })

  it('has reactive form with 4 fields', () => {
    const wrapper = mountWithPlugins(RegisterPage)
    const vm = wrapper.vm as unknown as RegisterPageVm
    expect(vm.form.username).toBe('')
    expect(vm.form.email).toBe('')
    expect(vm.form.password).toBe('')
    expect(vm.form.confirmPassword).toBe('')
  })

  it('validateConfirmPassword rejects mismatch', () => {
    const wrapper = mountWithPlugins(RegisterPage)
    const vm = wrapper.vm as unknown as RegisterPageVm
    vm.form.password = 'abc123'
    const cb = vi.fn()
    const validator = vm.rules.confirmPassword[1]?.validator
    if (validator) validator(null, 'different', cb)
    expect(cb).toHaveBeenCalledWith(expect.any(Error))
  })

  it('validateConfirmPassword accepts match', () => {
    const wrapper = mountWithPlugins(RegisterPage)
    const vm = wrapper.vm as unknown as RegisterPageVm
    vm.form.password = 'abc123'
    const cb = vi.fn()
    const validator = vm.rules.confirmPassword[1]?.validator
    if (validator) validator(null, 'abc123', cb)
    expect(cb).toHaveBeenCalledWith()
  })
})
