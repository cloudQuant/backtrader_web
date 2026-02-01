import api from './index'
import type {
  BacktestRequest,
  BacktestResponse,
  BacktestResult,
  BacktestListResponse,
} from '@/types'

export const backtestApi = {
  async run(data: BacktestRequest): Promise<BacktestResponse> {
    return api.post('/backtest/run', data)
  },

  async getResult(taskId: string): Promise<BacktestResult> {
    return api.get(`/backtest/${taskId}`)
  },

  async getStatus(taskId: string): Promise<{ task_id: string; status: string }> {
    return api.get(`/backtest/${taskId}/status`)
  },

  async list(limit = 20, offset = 0): Promise<BacktestListResponse> {
    return api.get('/backtest/', { params: { limit, offset } })
  },

  async delete(taskId: string): Promise<void> {
    return api.delete(`/backtest/${taskId}`)
  },
}
