import { flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PromptTemplatesPage from '@/views/PromptTemplatesPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'
import type { PromptTemplate } from '@/api/promptTemplates'

const apiMocks = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  activate: vi.fn(),
  test: vi.fn(),
}))

const fixtures = vi.hoisted(() => {
  const templates: PromptTemplate[] = [
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
      content: '灰度模板 {{question}} {{context_text}}',
      status: 'draft',
      variables: ['question', 'context_text'],
      rollout_percentage: 25,
      created_at: '2026-05-27T00:00:00Z',
      created_by: 'admin',
    },
    {
      id: 'tpl-archived',
      name: 'strategy_review',
      version: 'legacy',
      content: '旧审查模板 {{strategy}}',
      status: 'archived',
      variables: ['strategy'],
      rollout_percentage: 0,
      created_at: '2026-05-20T00:00:00Z',
      created_by: 'admin',
    },
  ]

  return { templates }
})

vi.mock('@/api/promptTemplates', () => ({
  promptTemplatesApi: apiMocks,
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

describe('PromptTemplatesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.list.mockResolvedValue({ items: fixtures.templates })
    apiMocks.create.mockResolvedValue(fixtures.templates[1])
    apiMocks.activate.mockResolvedValue({ ...fixtures.templates[1], status: 'active' })
    apiMocks.test.mockResolvedValue({
      template_id: 'tpl-canary',
      name: 'knowledge_qa',
      version: 'canary',
      rendered_prompt: '灰度模板 什么是均线策略 相关上下文',
      missing_variables: [],
    })
  })

  it('loads prompt templates and renders the redesigned governance workbench', async () => {
    const wrapper = mountWithPlugins(PromptTemplatesPage)
    await flushPromises()

    expect(apiMocks.list).toHaveBeenCalled()
    expect(wrapper.find('[data-test="prompt-hero"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="prompt-metrics"]').findAll('.prompt-metric')).toHaveLength(4)
    expect(wrapper.find('[data-test="prompt-create-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="prompt-workbench"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="prompt-table"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="prompt-mobile-list"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Prompt 模板控制台')
    expect(wrapper.text()).toContain('knowledge_qa')
    expect(wrapper.text()).toContain('25%')
  })

  it('filters templates by status and keyword', async () => {
    const wrapper = mountWithPlugins(PromptTemplatesPage)
    await flushPromises()

    const vm = wrapper.vm as any
    vm.statusFilter = 'archived'
    await nextTick()

    expect(wrapper.text()).toContain('strategy_review')
    expect(wrapper.text()).not.toContain('canary')

    vm.statusFilter = 'all'
    vm.templateSearch = 'context_text'
    await nextTick()

    expect(wrapper.text()).toContain('canary')
    expect(wrapper.text()).not.toContain('strategy_review')
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

  it('activates and tests prompt rendering before promotion', async () => {
    const wrapper = mountWithPlugins(PromptTemplatesPage)
    await flushPromises()
    const vm = wrapper.vm as any

    await vm.activateTemplate('tpl-canary')
    expect(apiMocks.activate).toHaveBeenCalledWith('tpl-canary')

    vm.openTestDrawer(fixtures.templates[1])
    expect(vm.testDrawerVisible).toBe(true)
    vm.testVariablesText = JSON.stringify({
      question: '什么是均线策略',
      context_text: '相关上下文',
    })
    await vm.testTemplate()

    expect(apiMocks.test).toHaveBeenCalledWith('tpl-canary', {
      question: '什么是均线策略',
      context_text: '相关上下文',
    })
    expect(vm.testResult?.rendered_prompt).toContain('灰度模板')
  })
})
