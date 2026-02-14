import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import BacktestResultPage from './BacktestResultPage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  useRoute: () => ({ params: { id: 't1' } }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/stores/backtest', () => ({
  useBacktestStore: () => ({
    fetchResult: vi.fn().mockResolvedValue({
      task_id: 't1', status: 'completed', strategy_id: 's1', symbol: 'BTC',
      total_return: 15, annual_return: 20, sharpe_ratio: 1.5, max_drawdown: -10,
      win_rate: 60, total_trades: 50, equity_curve: [100000], equity_dates: ['2024-01-01'],
      drawdown_curve: [0], trades: [],
    }),
    currentResult: null,
  }),
}))

vi.mock('@/api/analytics', () => ({
  analyticsApi: {
    getBacktestDetail: vi.fn().mockResolvedValue({}),
    getKlineWithSignals: vi.fn().mockResolvedValue({}),
    getMonthlyReturns: vi.fn().mockResolvedValue({}),
    exportResults: vi.fn().mockResolvedValue(undefined),
  },
}))

describe('BacktestResultPage', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('mounts without error', () => {
    const wrapper = mount(BacktestResultPage, { global: { stubs: { ...elStubs, EquityCurve: true, DrawdownChart: true, TradeRecordsTable: true, TradeSignalChart: true, ReturnHeatmap: true, MetricCard: true, PerformancePanel: true } } })
    expect(wrapper.exists()).toBe(true)
  })
})
