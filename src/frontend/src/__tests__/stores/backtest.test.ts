import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useBacktestStore } from '@/stores/backtest'

vi.mock('@/api/backtest', () => ({
  backtestApi: {
    run: vi.fn().mockResolvedValue({ task_id: 'task-123', status: 'pending' }),
    getResult: vi.fn().mockResolvedValue({
      task_id: 'task-123',
      strategy_id: '001_ma_cross',
      symbol: '000001.SZ',
      start_date: '2023-01-01',
      end_date: '2023-12-31',
      status: 'completed',
      total_return: 15.5,
      annual_return: 12.3,
      sharpe_ratio: 1.8,
      max_drawdown: 12.5,
      win_rate: 60,
      total_trades: 10,
      profitable_trades: 6,
      losing_trades: 4,
      equity_curve: [100000, 102000, 105000],
      equity_dates: ['2023-01-01', '2023-06-01', '2023-12-31'],
      drawdown_curve: [0, -2.5, -1.2],
      trades: [],
      created_at: '2024-01-01T00:00:00',
    }),
    list: vi.fn().mockResolvedValue({ total: 0, items: [] }),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({ templates: [], total: 0 }),
  },
}))

vi.mock('vue-i18n', () => ({
  createI18n: vi.fn(() => ({ global: { t: (key: string) => key } })),
  useI18n: vi.fn(() => ({ t: (key: string) => key })),
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
