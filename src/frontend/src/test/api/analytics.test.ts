import { describe, it, expect, vi, beforeEach } from 'vitest'
import { analyticsApi } from '@/api/analytics'
import request from '@/api/index'

vi.mock('@/api/index', () => ({
  default: { get: vi.fn() },
}))

describe('analyticsApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('getBacktestDetail', async () => {
    vi.mocked(request.get).mockResolvedValue({ task_id: 't1' })
    await analyticsApi.getBacktestDetail('t1')
    expect(request.get).toHaveBeenCalledWith('/analytics/t1/detail')
  })

  it('getKlineWithSignals without dates', async () => {
    vi.mocked(request.get).mockResolvedValue({})
    await analyticsApi.getKlineWithSignals('t1')
    expect(request.get).toHaveBeenCalledWith('/analytics/t1/kline', { params: {} })
  })

  it('getKlineWithSignals with dates', async () => {
    vi.mocked(request.get).mockResolvedValue({})
    await analyticsApi.getKlineWithSignals('t1', '2024-01-01', '2024-06-01')
    expect(request.get).toHaveBeenCalledWith('/analytics/t1/kline', {
      params: { start_date: '2024-01-01', end_date: '2024-06-01' },
    })
  })

  it('getMonthlyReturns', async () => {
    vi.mocked(request.get).mockResolvedValue({})
    await analyticsApi.getMonthlyReturns('t1')
    expect(request.get).toHaveBeenCalledWith('/analytics/t1/monthly-returns')
  })

  it('exportResults calls api and creates link', async () => {
    vi.mocked(request.get).mockResolvedValue('blobdata')

    const mockLink = { href: '', download: '', click: vi.fn() } as any
    vi.spyOn(document, 'createElement').mockReturnValue(mockLink)
    globalThis.URL.createObjectURL = vi.fn().mockReturnValue('blob:url')
    globalThis.URL.revokeObjectURL = vi.fn()

    await analyticsApi.exportResults('t1', 'csv')

    expect(request.get).toHaveBeenCalledWith('/analytics/t1/export', {
      params: { format: 'csv' }, responseType: 'blob',
    })
    expect(mockLink.click).toHaveBeenCalled()
    expect(mockLink.download).toBe('backtest_t1.csv')
  })

  it('exportResults defaults to csv', async () => {
    vi.mocked(request.get).mockResolvedValue('blobdata')
    vi.spyOn(document, 'createElement').mockReturnValue({ href: '', download: '', click: vi.fn() } as any)
    globalThis.URL.createObjectURL = vi.fn().mockReturnValue('blob:url')
    globalThis.URL.revokeObjectURL = vi.fn()

    await analyticsApi.exportResults('t1')
    expect(request.get).toHaveBeenCalledWith('/analytics/t1/export', {
      params: { format: 'csv' }, responseType: 'blob',
    })
  })
})
