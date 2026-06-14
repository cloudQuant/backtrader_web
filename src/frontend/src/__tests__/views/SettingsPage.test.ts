import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, it, expect, vi } from 'vitest'
import SettingsPage from '@/views/SettingsPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  put: vi.fn().mockResolvedValue({}),
  getMyUsage: vi.fn(),
  getMyAvailableModels: vi.fn(),
  updateMyPreferences: vi.fn(),
  testMyPreferences: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { username: 'admin', email: 'a@b.com', created_at: '2024-01-01' },
  }),
}))

vi.mock('@/api/index', () => ({
  default: { put: apiMocks.put },
}))

vi.mock('@/api/aiObservability', () => ({
  aiObservabilityApi: {
    getMyUsage: apiMocks.getMyUsage,
    getMyAvailableModels: apiMocks.getMyAvailableModels,
    updateMyPreferences: apiMocks.updateMyPreferences,
    testMyPreferences: apiMocks.testMyPreferences,
  },
}))

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.put.mockResolvedValue({})
    apiMocks.getMyUsage.mockResolvedValue({
      summary: {
        total_calls: 2,
        successful_calls: 2,
        failed_calls: 0,
        total_tokens: 120,
        estimated_cost_usd: 0.003,
        avg_latency_ms: 210,
      },
      by_day: [],
      by_service: [],
      by_model: [],
    })
    apiMocks.getMyAvailableModels.mockResolvedValue({
      providers: [{ name: 'ollama', display_name: 'Ollama', provider_type: 'litellm', base_url: 'http://localhost:11434', models: ['ollama/qwen2.5-coder:7b'] }],
      models: [
        { provider: 'openai', model: 'gpt-4o-mini', display_name: 'OpenAI / gpt-4o-mini' },
        { provider: 'ollama', model: 'ollama/qwen2.5-coder:7b', display_name: 'Ollama / ollama/qwen2.5-coder:7b' },
      ],
      preferences: { provider: 'ollama', model: 'ollama/qwen2.5-coder:7b' },
    })
    apiMocks.updateMyPreferences.mockResolvedValue({
      preferences: { provider: 'openai', model: 'gpt-4o-mini' },
    })
    apiMocks.testMyPreferences.mockResolvedValue({
      provider: 'ollama',
      model: 'ollama/qwen2.5-coder:7b',
      available: true,
    })
  })

  it('renders sections', () => {
    const wrapper = mountWithPlugins(SettingsPage)
    expect(wrapper.text()).toContain('个人信息')
    expect(wrapper.text()).toContain('修改密码')
    expect(wrapper.text()).toContain('我的 AI 用量')
    expect(wrapper.text()).toContain('关于')
    expect(wrapper.text()).toContain('AI for Trader')
  })

  it('loads current user AI usage on mount', async () => {
    const wrapper = mountWithPlugins(SettingsPage)
    await flushPromises()
    expect(apiMocks.getMyUsage).toHaveBeenCalled()
    expect(wrapper.text()).toContain('2')
    expect(wrapper.text()).toContain('120')
    expect(wrapper.text()).toContain('$0.003000')
  })

  it('loads and renders AI model preferences on mount', async () => {
    const wrapper = mountWithPlugins(SettingsPage)
    await flushPromises()
    expect(apiMocks.getMyAvailableModels).toHaveBeenCalled()
    expect(wrapper.text()).toContain('AI 模型偏好')
    expect(wrapper.text()).toContain('Ollama / ollama/qwen2.5-coder:7b')
  })

  it('saves AI model preferences', async () => {
    const { ElMessage } = await import('element-plus')
    const wrapper = mountWithPlugins(SettingsPage)
    await flushPromises()
    const vm = wrapper.vm as any
    vm.aiModelPreference.selectedModelKey = 'openai::gpt-4o-mini'
    await vm.saveAIModelPreference()
    expect(apiMocks.updateMyPreferences).toHaveBeenCalledWith({
      provider: 'openai',
      model: 'gpt-4o-mini',
    })
    expect(ElMessage.success).toHaveBeenCalledWith('AI 模型偏好已保存')
  })

  it('tests selected AI model connectivity', async () => {
    const { ElMessage } = await import('element-plus')
    const wrapper = mountWithPlugins(SettingsPage)
    await flushPromises()
    const vm = wrapper.vm as any
    await vm.testAIModelPreference()
    expect(apiMocks.testMyPreferences).toHaveBeenCalledWith({
      provider: 'ollama',
      model: 'ollama/qwen2.5-coder:7b',
    })
    expect(ElMessage.success).toHaveBeenCalledWith('AI 模型连通性正常')
  })

  it('loads user info on mount', async () => {
    const wrapper = mountWithPlugins(SettingsPage)
    await wrapper.vm.$nextTick()
    const vm = wrapper.vm as any
    expect(vm.userForm.username).toBe('admin')
    expect(vm.userForm.email).toBe('a@b.com')
  })

  it('changePassword validates empty fields', async () => {
    const { ElMessage } = await import('element-plus')
    const wrapper = mountWithPlugins(SettingsPage)
    const vm = wrapper.vm as any
    await vm.changePassword()
    expect(ElMessage.warning).toHaveBeenCalledWith('请填写密码')
  })

  it('changePassword validates mismatch', async () => {
    const { ElMessage } = await import('element-plus')
    const wrapper = mountWithPlugins(SettingsPage)
    const vm = wrapper.vm as any
    vm.passwordForm.oldPassword = 'old123456'
    vm.passwordForm.newPassword = 'new12345678'
    vm.passwordForm.confirmPassword = 'different'
    await vm.changePassword()
    expect(ElMessage.error).toHaveBeenCalledWith('两次输入的新密码不一致')
  })

  it('changePassword validates min length', async () => {
    const { ElMessage } = await import('element-plus')
    const wrapper = mountWithPlugins(SettingsPage)
    const vm = wrapper.vm as any
    vm.passwordForm.oldPassword = 'old12345'
    vm.passwordForm.newPassword = 'short'
    vm.passwordForm.confirmPassword = 'short'
    await vm.changePassword()
    expect(ElMessage.error).toHaveBeenCalledWith('密码至少8位')
  })

  it('changePassword succeeds', async () => {
    const { ElMessage } = await import('element-plus')
    const wrapper = mountWithPlugins(SettingsPage)
    const vm = wrapper.vm as any
    vm.passwordForm.oldPassword = 'old12345678'
    vm.passwordForm.newPassword = 'new12345678'
    vm.passwordForm.confirmPassword = 'new12345678'
    await vm.changePassword()
    expect(ElMessage.success).toHaveBeenCalledWith('密码修改成功')
    expect(vm.passwordForm.oldPassword).toBe('')
  })
})
