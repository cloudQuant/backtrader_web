/**
 * 回测分析API
 */
import request from './index'
import type {
  BacktestDetailResponse,
  KlineWithSignalsResponse,
  OptimizationResponse,
  MonthlyReturnsResponse,
} from '@/types/analytics'

export const analyticsApi = {
  /**
   * 获取回测详情
   */
  getBacktestDetail(taskId: string): Promise<BacktestDetailResponse> {
    return request.get(`/analytics/${taskId}/detail`)
  },

  /**
   * 获取K线和交易信号
   */
  getKlineWithSignals(
    taskId: string,
    startDate?: string,
    endDate?: string
  ): Promise<KlineWithSignalsResponse> {
    const params: Record<string, string> = {}
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    return request.get(`/analytics/${taskId}/kline`, { params })
  },

  /**
   * 获取月度收益
   */
  getMonthlyReturns(taskId: string): Promise<MonthlyReturnsResponse> {
    return request.get(`/analytics/${taskId}/monthly-returns`)
  },

  /**
   * 获取参数优化结果
   */
  getOptimizationResults(
    taskId: string,
    sortBy = 'sharpe_ratio',
    order = 'desc',
    limit = 50
  ): Promise<OptimizationResponse> {
    return request.get(`/analytics/${taskId}/optimization`, {
      params: { sort_by: sortBy, order, limit },
    })
  },

  /**
   * 导出回测结果
   */
  exportResults(taskId: string, format: 'csv' | 'json' = 'csv'): void {
    const url = `/api/v1/analytics/${taskId}/export?format=${format}`
    window.open(url, '_blank')
  },
}
