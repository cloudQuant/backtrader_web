import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

describe('stockAnalysisApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('gets task, cancels task, result, and exports report', async () => {
    const { stockAnalysisApi } = await import('@/api/stockAnalysis')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    const post = vi.mocked(apiModule.post).mockResolvedValue({} as never)

    await stockAnalysisApi.getTask('task-1')
    expect(get).toHaveBeenCalledWith('/stock-analysis/tasks/task-1')

    await stockAnalysisApi.getTaskResult('task-1')
    expect(get).toHaveBeenCalledWith('/stock-analysis/tasks/task-1/result')

    await stockAnalysisApi.cancelTask('task-1')
    expect(post).toHaveBeenCalledWith('/stock-analysis/tasks/task-1/cancel')

    await stockAnalysisApi.retryTask('task-1')
    expect(post).toHaveBeenCalledWith('/stock-analysis/tasks/task-1/retry')

    await stockAnalysisApi.exportReport('report-1', 'pdf')
    expect(get).toHaveBeenCalledWith('/stock-analysis/reports/report-1/export', {
      params: { format: 'pdf' },
      responseType: 'blob',
    })

    await stockAnalysisApi.saveToKnowledgeBase('report-1', 'kb-1', '股票分析报告')
    expect(post).toHaveBeenCalledWith(
      '/stock-analysis/reports/report-1/save-to-knowledge-base',
      {
        knowledge_base_id: 'kb-1',
        title: '股票分析报告',
      },
    )

    await stockAnalysisApi.saveToWorkspace('report-1', 'workspace-1', '股票工作区报告')
    expect(post).toHaveBeenCalledWith(
      '/stock-analysis/reports/report-1/save-to-workspace',
      {
        workspace_id: 'workspace-1',
        title: '股票工作区报告',
      },
    )
  })

  it('creates stock analysis tasks through the dedicated endpoint', async () => {
    const { stockAnalysisApi } = await import('@/api/stockAnalysis')
    const apiModule = (await import('@/api/index')).default
    const post = vi.mocked(apiModule.post).mockResolvedValue({} as never)
    const payload = {
      symbol: '000001.SZ',
      market_type: 'A股',
      analysis_date: '2026-06-15',
      research_depth: '标准',
      selected_modules: ['market', 'fundamentals', 'news', 'risk'],
      include_sentiment: false,
      include_risk: true,
      language: 'zh-CN',
      model_id: 'openai:gpt-4.1',
    }

    await stockAnalysisApi.createTask(payload)

    expect(post).toHaveBeenCalledWith('/stock-analysis/tasks', payload)
  })
})
