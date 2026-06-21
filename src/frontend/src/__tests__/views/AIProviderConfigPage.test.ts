import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { mountWithPlugins } from '@/__tests__/mountWithPlugins'
import { aiObservabilityApi } from '@/api/aiObservability'
import AIProviderConfigPage from '@/views/config/AIProviderConfigPage.vue'

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
      items: [
        {
          provider: 'local_openai',
          display_name: 'Local OpenAI',
          provider_type: 'openai_compatible',
          base_url: 'https://llm.example.com/v1',
          api_key_env: null,
          api_key_configured: true,
          models: ['local-model'],
          enabled: true,
          source: 'override',
        },
      ],
    })
    vi.mocked(aiObservabilityApi.updateAdminAIProviderConfig).mockResolvedValue({
      provider: 'local_openai',
      display_name: 'Local OpenAI',
      provider_type: 'openai_compatible',
      base_url: 'https://llm.example.com/v1',
      api_key_env: null,
      api_key_configured: true,
      models: ['local-model'],
      enabled: true,
      source: 'override',
    })
    vi.mocked(aiObservabilityApi.deleteAdminAIProviderConfig).mockResolvedValue(undefined)
  })

  it('loads provider list without exposing saved keys', async () => {
    const wrapper = mountWithPlugins(AIProviderConfigPage)
    await flushPromises()

    expect(wrapper.text()).toContain('AI配置')
    expect(wrapper.text()).not.toContain('sk-')
    expect((wrapper.vm as any).providerDrafts[0].display_name).toBe('Local OpenAI')
    expect((wrapper.vm as any).providerDrafts[0].api_key).toBe('')
    expect((wrapper.vm as any).providerDrafts[0].modelsText).toContain('local-model')
    expect(aiObservabilityApi.getAdminAIProviderConfigs).toHaveBeenCalled()
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

  it('creates and deletes providers from the list actions', async () => {
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

    await vm.deleteProvider(vm.providerDrafts.find((item: { provider: string }) => item.provider === 'custom_ai'))

    expect(aiObservabilityApi.deleteAdminAIProviderConfig).toHaveBeenCalledWith('custom_ai')
    expect(vm.providerDrafts.some((item: { provider: string }) => item.provider === 'custom_ai')).toBe(false)
  })
})
