import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import BacktestResultPage from '@/views/BacktestResultPage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  useRoute: () => ({ params: { id: 't1' } }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('vue-i18n', () => ({
  createI18n: vi.fn(() => ({ global: { t: (key: string) => key } })),
  useI18n: vi.fn(() => ({ t: (key: string) => key })),
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({ templates: [], total: 0 }),
  },
}))

vi.mock('@/stores/backtest', () => ({
  useBacktestStore: () => ({
    fetchResult: vi.fn().mockResolvedValue({
      task_id: 't1',
      strategy_id: 's1',
      symbol: 'BTC',
      start_date: '2024-01-01',
      end_date: '2024-01-31',
      status: 'completed',
      total_return: 15,
      annual_return: 20,
      sharpe_ratio: 1.5,
      max_drawdown: -10,
      win_rate: 60,
      total_trades: 50,
      profitable_trades: 30,
      losing_trades: 20,
      equity_curve: [100000],
      equity_dates: ['2024-01-01'],
      drawdown_curve: [0],
      trades: [],
      created_at: '2024-02-01T00:00:00',
    }),
    currentResult: null,
  }),
}))

vi.mock('@/api/analytics', () => ({
  analyticsApi: {
    getBacktestDetail: vi.fn().mockResolvedValue({
      task_id: 't1',
      strategy_name: 'SMA',
      symbol: 'BTC',
      start_date: '2024-01-01',
      end_date: '2024-01-31',
      metrics: {
        initial_capital: 100000,
        final_assets: 115000,
        total_return: 0.15,
        annualized_return: 0.2,
        max_drawdown: -0.1,
        max_drawdown_duration: 3,
        sharpe_ratio: 1.5,
        sortino_ratio: 1.2,
        calmar_ratio: 1.1,
        win_rate: 0.6,
        profit_factor: 1.8,
        trade_count: 50,
        avg_trade_return: 0.01,
        avg_holding_days: 5,
        avg_win: 0.02,
        avg_loss: -0.01,
        max_consecutive_wins: 4,
        max_consecutive_losses: 2,
      },
      equity_curve: [{ date: '2024-01-01', total_assets: 100000, cash: 100000, position_value: 0 }],
      drawdown_curve: [{ date: '2024-01-01', drawdown: 0, peak: 100000, trough: 100000 }],
      trades: [],
      created_at: '2024-02-01T00:00:00',
    }),
    getKlineWithSignals: vi.fn().mockResolvedValue({
      symbol: 'BTC',
      klines: [{ date: '2024-01-01', open: 1, high: 2, low: 0.5, close: 1.5, volume: 100 }],
      signals: [],
      indicators: {},
    }),
    getMonthlyReturns: vi.fn().mockResolvedValue({ returns: [], years: [], summary: {} }),
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
