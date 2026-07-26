import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import StockAnalysisTaskCard from '@/components/aichat/StockAnalysisTaskCard.vue'
import { stockAnalysisApi } from '@/api/stockAnalysis'
import { elStubs } from '@/test/stubs'

vi.mock('@/api/stockAnalysis', () => ({
  stockAnalysisApi: {
    cancelTask: vi.fn(),
    getTask: vi.fn(),
    getTaskResult: vi.fn(),
    retryTask: vi.fn(),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('StockAnalysisTaskCard', () => {
  it('polls an active task and emits a report card when completed', async () => {
    vi.mocked(stockAnalysisApi.getTask).mockResolvedValue({
      task_id: 'task-1',
      status: 'completed',
      symbol: '000001.SZ',
      symbol_name: '平安银行',
      market_type: 'A股',
      analysis_date: '2026-06-15',
      research_depth: '标准',
      selected_modules: ['market', 'news', 'fundamentals', 'risk'],
      progress: 100,
      current_step: 'completed',
      message: '股票分析已完成',
      error_message: null,
      report_id: 'report-1',
      created_at: '2026-06-15T00:00:00Z',
      started_at: '2026-06-15T00:00:01Z',
      completed_at: '2026-06-15T00:00:02Z',
    })
    vi.mocked(stockAnalysisApi.getTaskResult).mockResolvedValue({
      task_id: 'task-1',
      report_id: 'report-1',
      status: 'completed',
      report: {
        meta: { symbol: '000001.SZ' },
        executive_summary: '风险经理终审摘要',
        decision: {
          label: '持有',
          risk_level: '中等',
          confidence_score: 0.68,
        },
      },
    })

    const wrapper = mount(StockAnalysisTaskCard, {
      props: {
        task: {
          task_id: 'task-1',
          symbol: '000001.SZ',
          status: 'running',
          progress: 35,
          current_step: 'compat_pipeline',
          message: '正在执行兼容分析流水线',
        },
      },
      global: { stubs: { ...elStubs } },
    })
    await flushPromises()

    expect(stockAnalysisApi.getTask).toHaveBeenCalledWith('task-1')
    expect(stockAnalysisApi.getTaskResult).toHaveBeenCalledWith('task-1')
    expect(wrapper.emitted('taskUpdated')?.[0][0]).toMatchObject({
      status: 'completed',
      progress: 100,
    })
    expect(wrapper.emitted('resultLoaded')?.[0][0]).toMatchObject({
      report_id: 'report-1',
      decision_label: '持有',
      risk_level: '中等',
    })

    wrapper.unmount()
  })

  it('cancels an active task', async () => {
    vi.mocked(stockAnalysisApi.cancelTask).mockResolvedValue({
      task_id: 'task-1',
      status: 'cancelled',
      symbol: '000001.SZ',
      symbol_name: null,
      market_type: 'A股',
      analysis_date: '2026-06-15',
      research_depth: '标准',
      selected_modules: ['market'],
      progress: 100,
      current_step: 'cancelled',
      message: '股票分析已取消',
      error_message: null,
      report_id: null,
      created_at: '2026-06-15T00:00:00Z',
      started_at: null,
      completed_at: '2026-06-15T00:00:01Z',
    })

    const wrapper = mount(StockAnalysisTaskCard, {
      props: {
        autoPoll: false,
        task: {
          task_id: 'task-1',
          symbol: '000001.SZ',
          status: 'running',
          progress: 35,
          current_step: 'compat_pipeline',
          message: '正在执行兼容分析流水线',
        },
      },
      global: { stubs: { ...elStubs } },
    })

    const cancelButton = wrapper.findAll('button').find(button => button.text().includes('取消任务'))
    expect(cancelButton).toBeTruthy()
    await cancelButton!.trigger('click')
    await flushPromises()

    expect(stockAnalysisApi.cancelTask).toHaveBeenCalledWith('task-1')
    expect(wrapper.emitted('taskUpdated')?.[0][0]).toMatchObject({
      status: 'cancelled',
      current_step: 'cancelled',
    })
  })

  it('retries a failed task', async () => {
    vi.mocked(stockAnalysisApi.retryTask).mockResolvedValue({
      task_id: 'task-2',
      status: 'pending',
      symbol: '000001.SZ',
      symbol_name: null,
      market_type: 'A股',
      analysis_date: '2026-06-15',
      research_depth: '标准',
      selected_modules: ['market'],
      progress: 0,
      current_step: 'created',
      message: '股票分析任务已创建',
      error_message: null,
      report_id: null,
      created_at: '2026-06-15T00:00:00Z',
      started_at: null,
      completed_at: null,
    })

    const wrapper = mount(StockAnalysisTaskCard, {
      props: {
        autoPoll: false,
        task: {
          task_id: 'task-1',
          symbol: '000001.SZ',
          status: 'failed',
          progress: 100,
          current_step: 'failed',
          message: '股票分析失败',
        },
      },
      global: { stubs: { ...elStubs } },
    })

    const retryButton = wrapper.findAll('button').find(button => button.text().includes('重试任务'))
    expect(retryButton).toBeTruthy()
    await retryButton!.trigger('click')
    await flushPromises()

    expect(stockAnalysisApi.retryTask).toHaveBeenCalledWith('task-1')
    expect(wrapper.emitted('taskUpdated')?.[0][0]).toMatchObject({
      task_id: 'task-2',
      status: 'pending',
    })
  })
})
