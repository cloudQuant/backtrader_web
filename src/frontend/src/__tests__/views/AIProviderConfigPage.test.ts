import { flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { mountWithPlugins } from '@/__tests__/mountWithPlugins'
import type { AIProviderConfig } from '@/api/aiObservability'
import { aiObservabilityApi } from '@/api/aiObservability'
import AIProviderConfigPage from '@/views/config/AIProviderConfigPage.vue'

const fixtures = vi.hoisted(() => {
  const providers: AIProviderConfig[] = [
    {
      provider: 'local_openai',
      display_name: 'Local OpenAI',
      provider_type: 'openai_compatible',
      base_url: 'https://llm.example.com/v1',
      api_key_env: null,
      api_key_configured: true,
      models: ['local-model', 'second-model'],
      enabled: true,
      source: 'override',
    },
    {
      provider: 'ark',
      display_name: 'Volcengine Ark',
      provider_type: 'litellm',
      base_url: null,
      api_key_env: 'ARK_API_KEY',
      api_key_configured: false,
      models: ['ark/deepseek-v3'],
      enabled: false,
      source: 'default',
    },
  ]

  return { providers }
})

vi.mock('@/api/aiObservability', () => ({
  aiObservabilityApi: {
    deleteAdminAIProviderConfig: vi.fn(),
    getAdminAIProviderConfigs: vi.fn(),
    updateAdminAIProviderConfig: vi.fn(),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

describe('AIProviderConfigPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(aiObservabilityApi.getAdminAIProviderConfigs).mockResolvedValue({
      items: [...fixtures.providers],
    })
    vi.mocked(aiObservabilityApi.updateAdminAIProviderConfig).mockResolvedValue(fixtures.providers[0])
    vi.mocked(aiObservabilityApi.deleteAdminAIProviderConfig).mockResolvedValue(undefined)
  })

  it('loads provider list without exposing saved keys', async () => {
    const wrapper = mountWithPlugins(AIProviderConfigPage)
    await flushPromises()

    expect(wrapper.find('[data-test="ai-provider-hero"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="ai-provider-metrics"]').findAll('.provider-metric')).toHaveLength(4)
    expect(wrapper.find('[data-test="ai-provider-workbench"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="ai-provider-table"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="ai-provider-mobile-list"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('AI 模型服务控制台')
    expect(wrapper.text()).toContain('Local OpenAI')
    expect(wrapper.text()).toContain('Volcengine Ark')
    expect(wrapper.text()).not.toContain('sk-')
    expect((wrapper.vm as any).providerDrafts[0].api_key).toBe('')
    expect((wrapper.vm as any).providerDrafts[0].modelsText).toContain('local-model')
    expect(aiObservabilityApi.getAdminAIProviderConfigs).toHaveBeenCalled()
  })

  it('filters providers by status, type, and search keyword', async () => {
    const wrapper = mountWithPlugins(AIProviderConfigPage)
    await flushPromises()

    const vm = wrapper.vm as any
    vm.statusFilter = 'disabled'
    await nextTick()

    expect(wrapper.text()).not.toContain('Local OpenAI')
    expect(wrapper.text()).toContain('Volcengine Ark')

    vm.statusFilter = 'all'
    vm.typeFilter = 'openai_compatible'
    await nextTick()

    expect(wrapper.text()).toContain('Local OpenAI')
    expect(wrapper.text()).not.toContain('Volcengine Ark')

    vm.typeFilter = 'all'
    vm.providerSearch = 'deepseek'
    await nextTick()

    expect(wrapper.text()).not.toContain('Local OpenAI')
    expect(wrapper.text()).toContain('Volcengine Ark')
  })

  it('saves edits through the dialog draft', async () => {
    const wrapper = mountWithPlugins(AIProviderConfigPage)
    await flushPromises()

    const vm = wrapper.vm as any
    vm.openEditDialog(vm.providerDrafts[0])
    vm.editor.display_name = 'Updated OpenAI'
    vm.editor.modelsText = 'local-model\nsecond-model'
    vi.mocked(aiObservabilityApi.updateAdminAIProviderConfig).mockResolvedValueOnce({
      provider: 'local_openai',
      display_name: 'Updated OpenAI',
      provider_type: 'openai_compatible',
      base_url: 'https://llm.example.com/v1',
      api_key_env: null,
      api_key_configured: true,
      models: ['local-model', 'second-model'],
      enabled: true,
      source: 'override',
    })

    await vm.saveEditor()

    expect(aiObservabilityApi.updateAdminAIProviderConfig).toHaveBeenCalledWith('local_openai', {
      display_name: 'Updated OpenAI',
      provider_type: 'openai_compatible',
      base_url: 'https://llm.example.com/v1',
      api_key: null,
      api_key_env: null,
      models: ['local-model', 'second-model'],
      enabled: true,
    })
    expect(vm.editorVisible).toBe(false)
    expect(vm.providerDrafts[0].display_name).toBe('Updated OpenAI')
  })

  it('creates, toggles, and deletes providers from the workbench actions', async () => {
    const wrapper = mountWithPlugins(AIProviderConfigPage)
    await flushPromises()

    const vm = wrapper.vm as any
    vm.openCreateDialog()
    vm.editor.provider = 'custom_ai'
    vm.editor.display_name = 'Custom AI'
    vm.editor.modelsText = 'custom-model'
    vi.mocked(aiObservabilityApi.updateAdminAIProviderConfig).mockResolvedValueOnce({
      provider: 'custom_ai',
      display_name: 'Custom AI',
      provider_type: 'openai_compatible',
      base_url: 'https://api.openai.com/v1',
      api_key_env: null,
      api_key_configured: false,
      models: ['custom-model'],
      enabled: true,
      source: 'override',
    })

    await vm.saveEditor()
    expect(aiObservabilityApi.updateAdminAIProviderConfig).toHaveBeenCalledWith('custom_ai', {
      display_name: 'Custom AI',
      provider_type: 'openai_compatible',
      base_url: 'https://api.openai.com/v1',
      api_key: null,
      api_key_env: null,
      models: ['custom-model'],
      enabled: true,
    })
    expect(vm.providerDrafts.some((item: { provider: string }) => item.provider === 'custom_ai')).toBe(true)

    vi.mocked(aiObservabilityApi.updateAdminAIProviderConfig).mockResolvedValueOnce({
      ...fixtures.providers[1],
      enabled: true,
    })
    await vm.toggleProviderEnabled(vm.providerDrafts.find((item: { provider: string }) => item.provider === 'ark'), true)

    expect(aiObservabilityApi.updateAdminAIProviderConfig).toHaveBeenCalledWith('ark', {
      display_name: 'Volcengine Ark',
      provider_type: 'litellm',
      base_url: null,
      api_key: null,
      api_key_env: 'ARK_API_KEY',
      models: ['ark/deepseek-v3'],
      enabled: true,
    })

    await vm.deleteProvider(vm.providerDrafts.find((item: { provider: string }) => item.provider === 'custom_ai'))

    expect(aiObservabilityApi.deleteAdminAIProviderConfig).toHaveBeenCalledWith('custom_ai')
    expect(vm.providerDrafts.some((item: { provider: string }) => item.provider === 'custom_ai')).toBe(false)
  })
})
