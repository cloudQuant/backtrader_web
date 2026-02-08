/**
 * 回测分析API
 */
import request from './index'
import type {
  BacktestDetailResponse,
  KlineWithSignalsResponse,
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
   * 导出回测结果
   */
  async exportResults(taskId: string, format: 'csv' | 'json' = 'csv'): Promise<void> {
    const response = await request.get(`/analytics/${taskId}/export`, {
      params: { format },
      responseType: 'blob',
    })
    const blob = new Blob([response as any])
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `backtest_${taskId}.${format}`
    link.click()
    URL.revokeObjectURL(link.href)
  },
}
