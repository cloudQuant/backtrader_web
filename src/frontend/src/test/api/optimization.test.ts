import { describe, it, expect, vi, beforeEach } from 'vitest'
import { optimizationApi } from '@/api/optimization'
import request from '@/api/index'
import type {
  OptimizationBacktestSubmitRequest,
  OptimizationProgress,
  OptimizationResults,
  OptimizationSubmitRequest,
  OptimizationSubmitResponse,
  StrategyParamsResponse,
} from '@/api/optimization'

const mockStrategyParamsResponse: StrategyParamsResponse = {
  strategy_id: 's1',
  strategy_name: 'SMA',
  params: [],
}

const mockOptimizationSubmitResponse: OptimizationSubmitResponse = {
  task_id: 't1',
  total_combinations: 10,
  message: '已提交',
}

const mockOptimizationBacktestSubmitResponse: OptimizationSubmitResponse = {
  task_id: 't2',
  total_combinations: 20,
  message: '已提交',
}

const mockOptimizationProgress: OptimizationProgress = {
  task_id: 't1',
  status: 'running',
  strategy_id: 's1',
  total: 10,
  completed: 5,
  failed: 0,
  progress: 50,
  n_workers: 4,
  created_at: '',
}

const mockOptimizationResults: OptimizationResults = {
  task_id: 't1',
  status: 'completed',
  strategy_id: 's1',
  param_names: ['fast', 'slow'],
  metric_names: ['annual_return'],
  total: 10,
  completed: 10,
  failed: 0,
  rows: [],
  best: null,
}

const mockOptimizationCancelResponse: { message: string; task_id: string } = {
  message: 'ok',
  task_id: 't1',
}

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

describe('optimizationApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('getStrategyParams', async () => {
    vi.mocked(request.get).mockResolvedValue(mockStrategyParamsResponse)
    await optimizationApi.getStrategyParams('s1')
    expect(request.get).toHaveBeenCalledWith('/optimization/strategy-params/s1')
  })

  it('submit', async () => {
    vi.mocked(request.post).mockResolvedValue(mockOptimizationSubmitResponse)
    const data: OptimizationSubmitRequest = { strategy_id: 's1', param_ranges: {}, n_workers: 4 }
    await optimizationApi.submit(data)
    expect(request.post).toHaveBeenCalledWith('/optimization/submit', data)
  })

  it('submitBacktest', async () => {
    vi.mocked(request.post).mockResolvedValue(mockOptimizationBacktestSubmitResponse)
    const data: OptimizationBacktestSubmitRequest = {
      strategy_id: 's1',
      backtest_config: {
        strategy_id: 's1',
        symbol: '000001.SZ',
        start_date: '2024-01-01',
        end_date: '2024-02-01',
      },
      method: 'bayesian',
      param_bounds: { fast: { type: 'int', min: 5, max: 15 } },
      n_trials: 20,
    }
    await optimizationApi.submitBacktest(data)
    expect(request.post).toHaveBeenCalledWith('/optimization/submit/backtest', data)
  })

  it('getProgress', async () => {
    vi.mocked(request.get).mockResolvedValue(mockOptimizationProgress)
    await optimizationApi.getProgress('t1')
    expect(request.get).toHaveBeenCalledWith('/optimization/progress/t1')
  })

  it('getResults', async () => {
    vi.mocked(request.get).mockResolvedValue(mockOptimizationResults)
    await optimizationApi.getResults('t1')
    expect(request.get).toHaveBeenCalledWith('/optimization/results/t1')
  })

  it('cancel', async () => {
    vi.mocked(request.post).mockResolvedValue(mockOptimizationCancelResponse)
    await optimizationApi.cancel('t1')
    expect(request.post).toHaveBeenCalledWith('/optimization/cancel/t1')
  })
})
