import api from './index'
import type {
  BacktestRequest,
  BacktestResponse,
  BacktestResult,
  BacktestListResponse,
  BacktestStatusResponse,
} from '@/types'
import type { RobustnessTestResultResponse, RobustnessValidationRequest } from '@/types/trust'

const BACKTEST_API_BASE = '/backtests'

export const backtestApi = {
  async run(data: BacktestRequest): Promise<BacktestResponse> {
    return api.post<BacktestResponse, BacktestRequest>(`${BACKTEST_API_BASE}/run`, data)
  },

  async getResult(taskId: string): Promise<BacktestResult> {
    return api.get<BacktestResult>(`${BACKTEST_API_BASE}/${taskId}`)
  },

  async getStatus(taskId: string): Promise<BacktestStatusResponse> {
    return api.get<BacktestStatusResponse>(`${BACKTEST_API_BASE}/${taskId}/status`)
  },

  async list(limit = 20, offset = 0): Promise<BacktestListResponse> {
    return api.get<BacktestListResponse>(`${BACKTEST_API_BASE}/`, { params: { limit, offset } })
  },

  async cancel(taskId: string): Promise<void> {
    return api.post<void>(`${BACKTEST_API_BASE}/${taskId}/cancel`)
  },

  async delete(taskId: string): Promise<void> {
    return api.delete<void>(`${BACKTEST_API_BASE}/${taskId}`)
  },

  async runRobustness(
    taskId: string,
    data: RobustnessValidationRequest = {},
  ): Promise<RobustnessTestResultResponse> {
    return api.post<RobustnessTestResultResponse, RobustnessValidationRequest>(
      `${BACKTEST_API_BASE}/${taskId}/robustness`,
      data,
    )
  },

  async getRobustness(taskId: string): Promise<RobustnessTestResultResponse> {
    return api.get<RobustnessTestResultResponse>(`${BACKTEST_API_BASE}/${taskId}/robustness`)
  },
}
