import { describe, it, expect, vi, beforeEach } from 'vitest'
import { backtestApi } from '@/api/backtest'
import api from '@/api/index'
import type {
  BacktestListResponse,
  BacktestRequest,
  BacktestResponse,
  BacktestResult,
  BacktestStatusResponse,
} from '@/types'

const mockBacktestResponse: BacktestResponse = {
  task_id: 't1',
  status: 'pending',
}

const mockBacktestResult: BacktestResult = {
  task_id: 't1',
  strategy_id: 's1',
  symbol: '000001',
  start_date: '2024-01-01',
  end_date: '2024-06-01',
  status: 'completed',
  total_return: 0.12,
  annual_return: 0.18,
  sharpe_ratio: 1.2,
  max_drawdown: -0.08,
  win_rate: 0.6,
  total_trades: 20,
  profitable_trades: 12,
  losing_trades: 8,
  equity_curve: [100000, 102000],
  equity_dates: ['2024-01-01', '2024-06-01'],
  drawdown_curve: [0, -0.08],
  trades: [],
  created_at: '2024-06-02T00:00:00',
}

const mockBacktestStatusResponse: BacktestStatusResponse = {
  task_id: 't1',
  status: 'running',
}

const mockBacktestListResponse: BacktestListResponse = {
  total: 0,
  items: [],
}

vi.mock('@/api/index', () => ({
  default: { post: vi.fn(), get: vi.fn(), delete: vi.fn() },
}))

describe('backtestApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('run calls POST /backtests/run', async () => {
    vi.mocked(api.post).mockResolvedValue(mockBacktestResponse)
    const data: BacktestRequest = { strategy_id: 's1', symbol: '000001', start_date: '2024-01-01', end_date: '2024-06-01', initial_cash: 100000, commission: 0.001 }
    await backtestApi.run(data)
    expect(api.post).toHaveBeenCalledWith('/backtests/run', data)
  })

  it('getResult calls GET /backtests/:id', async () => {
    vi.mocked(api.get).mockResolvedValue(mockBacktestResult)
    await backtestApi.getResult('t1')
    expect(api.get).toHaveBeenCalledWith('/backtests/t1')
  })

  it('getStatus calls GET /backtests/:id/status', async () => {
    vi.mocked(api.get).mockResolvedValue(mockBacktestStatusResponse)
    await backtestApi.getStatus('t1')
    expect(api.get).toHaveBeenCalledWith('/backtests/t1/status')
  })

  it('list calls GET /backtests/ with params', async () => {
    vi.mocked(api.get).mockResolvedValue(mockBacktestListResponse)
    await backtestApi.list(10, 5)
    expect(api.get).toHaveBeenCalledWith('/backtests/', { params: { limit: 10, offset: 5 } })
  })

  it('list uses defaults', async () => {
    vi.mocked(api.get).mockResolvedValue(mockBacktestListResponse)
    await backtestApi.list()
    expect(api.get).toHaveBeenCalledWith('/backtests/', { params: { limit: 20, offset: 0 } })
  })

  it('cancel calls POST /backtests/:id/cancel', async () => {
    vi.mocked(api.post).mockResolvedValue(undefined)
    await backtestApi.cancel('t1')
    expect(api.post).toHaveBeenCalledWith('/backtests/t1/cancel')
  })

  it('delete calls DELETE /backtests/:id', async () => {
    vi.mocked(api.delete).mockResolvedValue(undefined)
    await backtestApi.delete('t1')
    expect(api.delete).toHaveBeenCalledWith('/backtests/t1')
  })
})
