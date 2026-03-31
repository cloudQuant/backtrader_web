import { describe, it, expect, vi } from 'vitest'
import LoginPage from '@/views/LoginPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

type LoginPageVm = {
  form: { username: string; password: string }
  loading: boolean
}

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    login: vi.fn().mockResolvedValue(undefined),
    isAuthenticated: false,
  }),
}))

vi.mock('vue-i18n', () => ({
  createI18n: vi.fn(() => ({ global: { t: (key: string) => key } })),
  useI18n: vi.fn(() => ({ t: (key: string) => key })),
}))

describe('LoginPage', () => {
  it('renders login form', () => {
    const wrapper = mountWithPlugins(LoginPage)
    expect(wrapper.text()).toContain('Backtrader Web')
    // i18n mock returns keys
    expect(wrapper.text()).toContain('auth.login')
    expect(wrapper.text()).toContain('auth.registerNow')
  })

  it('has reactive form data', () => {
    const wrapper = mountWithPlugins(LoginPage)
    const vm = wrapper.vm as unknown as LoginPageVm
    expect(vm.form.username).toBe('')
    expect(vm.form.password).toBe('')
    expect(vm.loading).toBe(false)
  })
})
