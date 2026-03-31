/**
 * 参数优化 API
 */
import request from './index'
import type { BacktestRequest } from '@/types'

export interface StrategyParam {
  name: string
  type: string
  default: number
  description: string
}

export interface StrategyParamsResponse {
  strategy_id: string
  strategy_name: string
  params: StrategyParam[]
}

export interface ParamRangeSpec {
  start: number
  end: number
  step: number
  type: string
}

export interface OptimizationSubmitRequest {
  strategy_id: string
  param_ranges: Record<string, ParamRangeSpec>
  n_workers: number
}

export interface OptimizationBacktestSubmitRequest {
  strategy_id: string
  backtest_config: BacktestRequest
  method: 'grid' | 'bayesian'
  metric?: 'sharpe_ratio' | 'max_drawdown' | 'total_return'
  param_grid?: Record<string, Array<number | string>>
  param_bounds?: Record<string, Record<string, unknown>>
  n_trials?: number
}

export interface OptimizationSubmitResponse {
  task_id: string
  total_combinations: number
  message: string
}

export interface OptimizationProgress {
  task_id: string
  status: string
  strategy_id: string
  total: number
  completed: number
  failed: number
  progress: number
  n_workers: number
  created_at: string
}

export interface OptimizationRow {
  [key: string]: number
}

export interface OptimizationResults {
  task_id: string
  status: string
  strategy_id: string
  param_names: string[]
  metric_names: string[]
  total: number
  completed: number
  failed: number
  rows: OptimizationRow[]
  best: OptimizationRow | null
}

export const optimizationApi = {
  getStrategyParams(strategyId: string): Promise<StrategyParamsResponse> {
    return request.get<StrategyParamsResponse>(`/optimization/strategy-params/${strategyId}`)
  },

  submit(data: OptimizationSubmitRequest): Promise<OptimizationSubmitResponse> {
    return request.post<OptimizationSubmitResponse, OptimizationSubmitRequest>('/optimization/submit', data)
  },

  submitBacktest(data: OptimizationBacktestSubmitRequest): Promise<OptimizationSubmitResponse> {
    return request.post<OptimizationSubmitResponse, OptimizationBacktestSubmitRequest>('/optimization/submit/backtest', data)
  },

  getProgress(taskId: string): Promise<OptimizationProgress> {
    return request.get<OptimizationProgress>(`/optimization/progress/${taskId}`)
  },

  getResults(taskId: string): Promise<OptimizationResults> {
    return request.get<OptimizationResults>(`/optimization/results/${taskId}`)
  },

  cancel(taskId: string): Promise<{ message: string; task_id: string }> {
    return request.post<{ message: string; task_id: string }>(`/optimization/cancel/${taskId}`)
  },
}
