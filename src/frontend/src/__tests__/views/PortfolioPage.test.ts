import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PortfolioPage from '@/views/PortfolioPage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

// Use the actual zh-CN locale so `t('portfolio.unitYi')` -> '亿' for assertions
// like formatMoney(-2e8) -> '-2.00亿'. Aligns with the global setup.ts mock.
vi.mock('vue-i18n', async () => {
  const { ref } = await import('vue')
  const zhCN = (await import('@/i18n/locales/zh-CN')).default
  function flatten(obj: Record<string, unknown>, prefix = ''): Record<string, string> {
    const out: Record<string, string> = {}
    for (const [k, v] of Object.entries(obj)) {
      const key = prefix ? `${prefix}.${k}` : k
      if (v && typeof v === 'object') Object.assign(out, flatten(v as Record<string, unknown>, key))
      else out[key] = String(v)
    }
    return out
  }
  const flat = flatten(zhCN as Record<string, unknown>)
  const t = (key: string, named?: Record<string, unknown>) => {
    const tpl = flat[key] ?? key
    if (!named) return tpl
    return tpl.replace(/\{(\w+)\}/g, (_, n) => (n in named ? String(named[n]) : `{${n}}`))
  }
  return {
    createI18n: vi.fn(() => ({ global: { t, locale: ref('zh-CN') }, install: vi.fn() })),
    useI18n: vi.fn(() => ({ t, locale: ref('zh-CN') })),
  }
})

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({ templates: [], total: 0 }),
  },
}))

vi.mock('@/api/portfolio', () => ({
  portfolioApi: {
    getOverview: vi.fn().mockResolvedValue({
      total_assets: 100000, total_cash: 50000, total_position_value: 50000,
      total_initial_capital: 80000, total_pnl: 20000, total_pnl_pct: 25,
      strategy_count: 2, running_count: 1, strategies: [
        { strategy_id: 's1', strategy_name: 'SMA', status: 'running', assets: 60000, pnl: 10000, pnl_pct: 20 },
      ],
    }),
    getPositions: vi.fn().mockResolvedValue({ total: 0, positions: [] }),
    getTrades: vi.fn().mockResolvedValue({ total: 0, trades: [] }),
    getEquity: vi.fn().mockResolvedValue({ dates: ['2024-01-01'], total_equity: [100000], drawdown: [0], strategies: [] }),
    getAllocation: vi.fn().mockResolvedValue({ total: 1, items: [{ name: 'BTC', value: 50000, pct: 50 }] }),
  },
}))

vi.mock('@/api/workspace', () => ({
  workspaceApi: {
    list: vi.fn().mockResolvedValue({
      total: 2,
      items: [
        {
          id: 'ws-running',
          user_id: 'u1',
          name: 'CTA 交易工作区',
          description: null,
          workspace_type: 'trading',
          settings: {},
          trading_config: {},
          unit_count: 2,
          completed_count: 0,
          status: 'running',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-02T00:00:00Z',
        },
        {
          id: 'ws-idle',
          user_id: 'u1',
          name: '暂停工作区',
          description: null,
          workspace_type: 'trading',
          settings: {},
          trading_config: {},
          unit_count: 1,
          completed_count: 0,
          status: 'idle',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-02T00:00:00Z',
        },
      ],
    }),
    getTradingPositions: vi.fn().mockResolvedValue({
      positions: [
        {
          unit_id: 'unit-1',
          unit_name: 'RB 趋势',
          symbol: 'RB2510',
          symbol_name: '螺纹钢',
          trading_mode: 'live',
          long_position: 2,
          short_position: 0,
          avg_price: 3500,
          latest_price: 3600,
          position_pnl: 200,
          market_value: 7200,
        },
      ],
      total_long_value: 7200,
      total_short_value: 0,
      total_pnl: 200,
    }),
    getTradingDailySummary: vi.fn().mockResolvedValue({
      summaries: [
        {
          trading_date: '2026-06-19',
          daily_pnl: 200,
          trade_count: 3,
          cumulative_pnl: 1200,
          max_drawdown: 0.02,
        },
      ],
    }),
  },
}))

describe('PortfolioPage', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const doMount = () => mount(PortfolioPage, { global: { stubs: { ...elStubs, EquityCurve: true } } })

  it('mounts without error', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('formatMoney formats billions', () => {
    const vm = doMount().vm as any
    expect(vm.formatMoney(1.5e8)).toBe('1.50亿')
  })

  it('formatMoney formats ten-thousands', () => {
    const vm = doMount().vm as any
    expect(vm.formatMoney(15000)).toBe('1.50万')
  })

  it('formatMoney formats small values', () => {
    const vm = doMount().vm as any
    expect(vm.formatMoney(99.5)).toBe('99.50')
  })

  it('loadData loads dashboard and running trading workspaces', async () => {
    const vm = doMount().vm as any
    await vm.loadData()
    expect(vm.overview.total_assets).toBe(100000)
    expect(vm.runningWorkspaces).toHaveLength(1)
    expect(vm.selectedWorkspaceIds).toEqual(['ws-running'])
    expect(vm.loading).toBe(false)
  })

  it('loadTabData loads selected workspace positions', async () => {
    const vm = doMount().vm as any
    await vm.loadData()
    await vm.loadTabData('positions')
    expect(vm.positions.length).toBe(1)
    expect(vm.positions[0].strategy_name).toContain('CTA 交易工作区')
    expect(vm.positions[0].data_name).toBe('RB2510')
  })

  it('loadTabData loads selected workspace trading summaries as trade rows', async () => {
    const vm = doMount().vm as any
    await vm.loadData()
    await vm.loadTabData('trades')
    expect(vm.trades.length).toBe(1)
    expect(vm.trades[0].strategy_name).toBe('CTA 交易工作区')
    expect(vm.trades[0].size).toBe(3)
  })

  it('loadTabData loads equity', async () => {
    const vm = doMount().vm as any
    await vm.loadTabData('equity')
    expect(vm.equityData).toBeTruthy()
  })

  it('loadTabData loads allocation', async () => {
    const vm = doMount().vm as any
    await vm.loadTabData('allocation')
    expect(vm.allocationItems.length).toBe(1)
  })

  it('loadTabData skips already loaded tabs', async () => {
    const vm = doMount().vm as any
    await vm.loadTabData('positions')
    await vm.loadTabData('positions')
    // Second call should be a no-op (already in loadedTabs set)
  })

  it('activeTab defaults to workspaces', () => {
    const vm = doMount().vm as any
    expect(vm.activeTab).toBe('workspaces')
  })

  it('renderEquityChart does nothing without equityData', () => {
    const vm = doMount().vm as any
    vm.equityData = null
    vm.renderEquityChart() // should not throw
  })

  it('renderDrawdownChart does nothing without equityData', () => {
    const vm = doMount().vm as any
    vm.equityData = null
    vm.renderDrawdownChart() // should not throw
  })

  it('renderAllocationChart does nothing without data', () => {
    const vm = doMount().vm as any
    vm.allocationItems = []
    vm.renderAllocationChart() // should not throw
  })

  it('handleResize is callable', () => {
    const vm = doMount().vm as any
    vm.handleResize() // should not throw
  })

  it('formatMoney handles negative values', () => {
    const vm = doMount().vm as any
    expect(vm.formatMoney(-2e8)).toBe('-2.00亿')
    expect(vm.formatMoney(-50000)).toBe('-5.00万')
    expect(vm.formatMoney(-50)).toBe('-50.00')
  })
})
