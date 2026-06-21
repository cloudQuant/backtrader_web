import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { elStubs } from '@/test/stubs'
import StockAnalysisPage from '@/views/investment/StockAnalysisPage.vue'

const mocks = vi.hoisted(() => ({
  createTask: vi.fn(),
  getTask: vi.fn(),
  getTaskResult: vi.fn(),
  exportReport: vi.fn(),
  getMyAvailableModels: vi.fn(),
  messageSuccess: vi.fn(),
  messageWarning: vi.fn(),
  messageError: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
}))

vi.mock('@/api/stockAnalysis', () => ({
  stockAnalysisApi: {
    createTask: mocks.createTask,
    getTask: mocks.getTask,
    getTaskResult: mocks.getTaskResult,
    exportReport: mocks.exportReport,
  },
}))

vi.mock('@/api/aiObservability', () => ({
  aiObservabilityApi: {
    getMyAvailableModels: mocks.getMyAvailableModels,
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: mocks.messageSuccess,
    warning: mocks.messageWarning,
    error: mocks.messageError,
  },
}))

const baseTask = {
  task_id: 'task-1',
  status: 'pending',
  symbol: '000001.SZ',
  market_type: 'A股',
  analysis_date: '2026-06-20',
  research_depth: '标准',
  selected_modules: ['market', 'fundamentals', 'news', 'risk'],
  progress: 0,
  current_step: 'created',
  message: null,
  created_at: '2026-06-20T00:00:00Z',
  started_at: null,
  completed_at: null,
  error_message: null,
  report_id: null,
}

function mountPage() {
  return mount(StockAnalysisPage, {
    global: {
      stubs: elStubs,
    },
  })
}

describe('StockAnalysisPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getMyAvailableModels.mockResolvedValue({
      providers: [],
      models: [{ provider: 'openai', model: 'gpt-4.1', display_name: 'GPT-4.1' }],
      preferences: { provider: 'openai', model: 'gpt-4.1' },
    })
    mocks.createTask.mockResolvedValue(baseTask)
    mocks.getTask.mockResolvedValue(baseTask)
  })

  it('renders a standalone single-stock analysis workspace instead of chat', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('单股分析')
    expect(wrapper.text()).toContain('股票代码')
    expect(wrapper.text()).toContain('分析配置')
    expect(wrapper.text()).toContain('研究模块')
    expect(wrapper.text()).toContain('开始智能分析')
    expect(wrapper.text()).not.toContain('AI 助手对话')
  })

  it('creates stock analysis task from the form defaults', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const startButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('开始智能分析'))
    expect(startButton).toBeDefined()
    await startButton!.trigger('click')
    await flushPromises()

    expect(mocks.createTask).toHaveBeenCalledWith({
      symbol: '000001.SZ',
      market_type: 'A股',
      analysis_date: expect.any(String),
      research_depth: '标准',
      selected_modules: ['market', 'fundamentals', 'news', 'risk'],
      include_sentiment: false,
      include_risk: true,
      language: 'zh-CN',
      model_id: 'openai:gpt-4.1',
    })
    expect(wrapper.text()).toContain('分析任务已提交')
  })

  it('updates selected modules when research depth changes', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const vm = wrapper.vm as unknown as {
      form: { researchDepth: string; selectedModules: string[] }
    }

    expect(vm.form.selectedModules).toEqual(['market', 'fundamentals', 'news', 'risk'])

    vm.form.researchDepth = '快速'
    await nextTick()
    expect(vm.form.selectedModules).toEqual(['market'])

    vm.form.researchDepth = '深度'
    await nextTick()
    expect(vm.form.selectedModules).toEqual(['market', 'fundamentals', 'news', 'social', 'risk'])

    vm.form.researchDepth = '全面'
    await nextTick()
    expect(vm.form.selectedModules).toEqual(['market', 'fundamentals', 'news', 'social', 'risk'])
  })
})
