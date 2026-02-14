import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsPage from '@/views/SettingsPage.vue'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { username: 'admin', email: 'a@b.com', created_at: '2024-01-01' },
  }),
}))

vi.mock('@/api/index', () => ({
  default: { put: vi.fn().mockResolvedValue({}) },
}))

const stubs = {
  'el-card': { template: '<div><slot /><slot name="header" /></div>' },
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div><slot /></div>' },
  'el-input': { template: '<input />' },
  'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
}

describe('SettingsPage', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('renders sections', () => {
    const wrapper = mount(SettingsPage, { global: { stubs } })
    expect(wrapper.text()).toContain('个人信息')
    expect(wrapper.text()).toContain('修改密码')
    expect(wrapper.text()).toContain('关于')
    expect(wrapper.text()).toContain('Backtrader Web')
  })

  it('loads user info on mount', async () => {
    const wrapper = mount(SettingsPage, { global: { stubs } })
    await wrapper.vm.$nextTick()
    const vm = wrapper.vm as any
    expect(vm.userForm.username).toBe('admin')
    expect(vm.userForm.email).toBe('a@b.com')
  })

  it('changePassword validates empty fields', async () => {
    const { ElMessage } = await import('element-plus')
    const wrapper = mount(SettingsPage, { global: { stubs } })
    const vm = wrapper.vm as any
    await vm.changePassword()
    expect(ElMessage.warning).toHaveBeenCalledWith('请填写密码')
  })

  it('changePassword validates mismatch', async () => {
    const { ElMessage } = await import('element-plus')
    const wrapper = mount(SettingsPage, { global: { stubs } })
    const vm = wrapper.vm as any
    vm.passwordForm.oldPassword = 'old123456'
    vm.passwordForm.newPassword = 'new12345678'
    vm.passwordForm.confirmPassword = 'different'
    await vm.changePassword()
    expect(ElMessage.error).toHaveBeenCalledWith('两次输入的新密码不一致')
  })

  it('changePassword validates min length', async () => {
    const { ElMessage } = await import('element-plus')
    const wrapper = mount(SettingsPage, { global: { stubs } })
    const vm = wrapper.vm as any
    vm.passwordForm.oldPassword = 'old12345'
    vm.passwordForm.newPassword = 'short'
    vm.passwordForm.confirmPassword = 'short'
    await vm.changePassword()
    expect(ElMessage.error).toHaveBeenCalledWith('密码至少8位')
  })

  it('changePassword succeeds', async () => {
    const { ElMessage } = await import('element-plus')
    const wrapper = mount(SettingsPage, { global: { stubs } })
    const vm = wrapper.vm as any
    vm.passwordForm.oldPassword = 'old12345678'
    vm.passwordForm.newPassword = 'new12345678'
    vm.passwordForm.confirmPassword = 'new12345678'
    await vm.changePassword()
    expect(ElMessage.success).toHaveBeenCalledWith('密码修改成功')
    expect(vm.passwordForm.oldPassword).toBe('')
  })
})
