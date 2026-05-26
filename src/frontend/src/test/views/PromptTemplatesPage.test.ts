import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PromptTemplatesPage from '@/views/PromptTemplatesPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  activate: vi.fn(),
  test: vi.fn(),
}))

vi.mock('@/api/promptTemplates', () => ({
  promptTemplatesApi: apiMocks,
}))

const templateFixture = {
  items: [
    {
      id: 'tpl-stable',
      name: 'knowledge_qa',
      version: 'stable',
      content: '稳定模板 {{question}}',
      status: 'active',
      variables: ['question'],
      rollout_percentage: 0,
      created_at: '2026-05-26T00:00:00Z',
      created_by: 'admin',
    },
    {
      id: 'tpl-canary',
      name: 'knowledge_qa',
      version: 'canary',
      content: '灰度模板 {{question}}',
      status: 'draft',
      variables: ['question'],
      rollout_percentage: 25,
      created_at: '2026-05-26T00:00:00Z',
      created_by: 'admin',
    },
  ],
}

describe('PromptTemplatesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.list.mockResolvedValue(templateFixture)
    apiMocks.create.mockResolvedValue(templateFixture.items[1])
    apiMocks.activate.mockResolvedValue({ ...templateFixture.items[1], status: 'active' })
    apiMocks.test.mockResolvedValue({ rendered_prompt: '灰度模板 什么是均线策略', missing_variables: [] })
  })

  it('loads prompt templates on mount and renders rollout slider', async () => {
    const wrapper = mountWithPlugins(PromptTemplatesPage)
    await flushPromises()

    expect(apiMocks.list).toHaveBeenCalled()
    expect(wrapper.text()).toContain('Prompt 模板治理')
    expect(wrapper.text()).toContain('灰度比例')
    expect(wrapper.text()).toContain('25%')
  })

  it('creates prompt template with rollout percentage from form', async () => {
    const wrapper = mountWithPlugins(PromptTemplatesPage)
    await flushPromises()
    const vm = wrapper.vm as any

    vm.form.name = 'strategy_review'
    vm.form.version = 'canary'
    vm.form.content = '灰度模板 {{question}}'
    vm.form.variablesText = 'question'
    vm.form.rollout_percentage = 30
    await vm.createTemplate()

    expect(apiMocks.create).toHaveBeenCalledWith({
      name: 'strategy_review',
      version: 'canary',
      content: '灰度模板 {{question}}',
      variables: ['question'],
      rollout_percentage: 30,
    })
  })
})
