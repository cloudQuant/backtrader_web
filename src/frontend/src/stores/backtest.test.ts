import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useBacktestStore } from './backtest'

vi.mock('@/api/backtest', () => ({
  backtestApi: {
    run: vi.fn().mockResolvedValue({ task_id: 'task-123', status: 'pending' }),
    getResult: vi.fn().mockResolvedValue({
      task_id: 'task-123',
      total_return: 15.5,
      sharpe_ratio: 1.8,
      max_drawdown: 12.5,
      trades: [],
    }),
    list: vi.fn().mockResolvedValue({ total: 0, items: [] }),
    delete: vi.fn().mockResolvedValue({}),
  },
}))

describe('useBacktestStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('should start with empty state', () => {
    const store = useBacktestStore()
    expect(store.results).toEqual([])
    expect(store.currentResult).toBeNull()
    expect(store.loading).toBe(false)
  })

  it('should run backtest and return task_id', async () => {
    const store = useBacktestStore()
    const result = await store.runBacktest({
      strategy_id: '001_ma_cross',
      symbol: '000001.SZ',
      start_date: '2023-01-01',
      end_date: '2023-12-31',
      initial_cash: 100000,
      commission: 0.001,
      params: {},
    })
    expect(result).toBeDefined()
    expect(result.task_id).toBe('task-123')
  })

  it('should fetch result by task_id', async () => {
    const store = useBacktestStore()
    await store.fetchResult('task-123')
    expect(store.currentResult).not.toBeNull()
    expect(store.currentResult?.total_return).toBe(15.5)
  })

  it('should fetch results list', async () => {
    const store = useBacktestStore()
    await store.fetchResults()
    expect(store.results).toEqual([])
    expect(store.total).toBe(0)
  })
})
