import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { elStubs } from '@/test/stubs'
import StockAnalysisPage from '@/views/investment/StockAnalysisPage.vue'

const mocks = vi.hoisted(() => ({
  createTask: vi.fn(),
  getTask: vi.fn(),
  getTaskResult: vi.fn(),
  getLatestResult: vi.fn(),
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
    getLatestResult: mocks.getLatestResult,
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
    mocks.getLatestResult.mockResolvedValue(null)
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

  it('restores the latest completed report and its export actions on mount', async () => {
    mocks.getLatestResult.mockResolvedValue({
      task: {
        ...baseTask,
        status: 'completed',
        progress: 100,
        current_step: 'completed',
        report_id: 'latest-report-1',
      },
      report: {
        meta: { symbol: '000001.SZ', symbol_name: '平安银行', market_type: 'A股' },
        executive_summary: '这是最近一次成功分析。',
        decision: { label: '持有', confidence_score: 0.62, risk_level: '中等' },
        sections: [],
      },
    })

    const wrapper = mountPage()
    await flushPromises()

    expect(mocks.getLatestResult).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.report-panel').exists()).toBe(true)
    expect(wrapper.text()).toContain('平安银行')
    expect(wrapper.find('.export-actions').text()).toContain('PDF')
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

  it('renders completed report sections as sanitized Markdown instead of raw syntax', async () => {
    mocks.createTask.mockResolvedValue({
      ...baseTask,
      status: 'completed',
      progress: 100,
      report_id: 'report-1',
    })
    mocks.getTaskResult.mockResolvedValue({
      task_id: 'task-1',
      report_id: 'report-1',
      status: 'completed',
      report: {
        meta: { symbol: '000001.SZ', symbol_name: '平安银行' },
        executive_summary: '结论：保持审慎。',
        decision: { label: '持有', confidence_score: 0.62, risk_level: '中等' },
        sections: [
          {
            id: 'technical',
            title: '技术与市场分析',
            summary: '# 盘面结论\n\n**趋势：** 区间震荡。',
            findings: [],
          },
        ],
      },
    })

    const wrapper = mountPage()
    await flushPromises()
    const startButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('开始智能分析'))
    await startButton!.trigger('click')
    await flushPromises()

    const rendered = wrapper.find('.report-section .report-markdown-content')
    expect(rendered.exists()).toBe(true)
    expect(rendered.html()).toContain('<h1>盘面结论</h1>')
    expect(rendered.html()).toContain('<strong>趋势：</strong> 区间震荡。')
  })
})
