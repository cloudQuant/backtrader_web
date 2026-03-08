import { describe, it, expect, vi } from 'vitest'
import LoginPage from '@/views/LoginPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    login: vi.fn().mockResolvedValue(undefined),
    isAuthenticated: false,
  }),
}))

describe('LoginPage', () => {
  it('renders login form', () => {
    const wrapper = mountWithPlugins(LoginPage)
    expect(wrapper.text()).toContain('Backtrader Web')
    expect(wrapper.text()).toContain('登录')
    expect(wrapper.text()).toContain('立即注册')
  })

  it('has reactive form data', () => {
    const wrapper = mountWithPlugins(LoginPage)
    expect(wrapper.vm.form.username).toBe('')
    expect(wrapper.vm.form.password).toBe('')
    expect(wrapper.vm.loading).toBe(false)
  })
})
