import { describe, it, expect, vi, beforeEach } from 'vitest'
import { backtestApi } from './backtest'
import api from './index'

vi.mock('./index', () => ({
  default: { post: vi.fn(), get: vi.fn(), delete: vi.fn() },
}))

describe('backtestApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('run calls POST /backtest/run', async () => {
    vi.mocked(api.post).mockResolvedValue({ task_id: 't1', status: 'pending' })
    const data = { strategy_id: 's1', symbol: '000001', start_date: '2024-01-01', end_date: '2024-06-01', initial_cash: 100000, commission: 0.001 }
    await backtestApi.run(data as any)
    expect(api.post).toHaveBeenCalledWith('/backtest/run', data)
  })

  it('getResult calls GET /backtest/:id', async () => {
    vi.mocked(api.get).mockResolvedValue({ task_id: 't1' })
    await backtestApi.getResult('t1')
    expect(api.get).toHaveBeenCalledWith('/backtest/t1')
  })

  it('getStatus calls GET /backtest/:id/status', async () => {
    vi.mocked(api.get).mockResolvedValue({ task_id: 't1', status: 'running' })
    await backtestApi.getStatus('t1')
    expect(api.get).toHaveBeenCalledWith('/backtest/t1/status')
  })

  it('list calls GET /backtest/ with params', async () => {
    vi.mocked(api.get).mockResolvedValue({ total: 0, items: [] })
    await backtestApi.list(10, 5)
    expect(api.get).toHaveBeenCalledWith('/backtest/', { params: { limit: 10, offset: 5 } })
  })

  it('list uses defaults', async () => {
    vi.mocked(api.get).mockResolvedValue({ total: 0, items: [] })
    await backtestApi.list()
    expect(api.get).toHaveBeenCalledWith('/backtest/', { params: { limit: 20, offset: 0 } })
  })

  it('cancel calls POST /backtest/:id/cancel', async () => {
    vi.mocked(api.post).mockResolvedValue(undefined)
    await backtestApi.cancel('t1')
    expect(api.post).toHaveBeenCalledWith('/backtest/t1/cancel')
  })

  it('delete calls DELETE /backtest/:id', async () => {
    vi.mocked(api.delete).mockResolvedValue(undefined)
    await backtestApi.delete('t1')
    expect(api.delete).toHaveBeenCalledWith('/backtest/t1')
  })
})
