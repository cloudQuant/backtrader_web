import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PortfolioPage from '@/views/PortfolioPage.vue'
import { portfolioApi } from '@/api/portfolio'
import { workspaceApi } from '@/api/workspace'
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
      total_assets: 100000, total_cash: 50000, total_position_value: 50000, net_position_value: 50000,
      total_initial_capital: 80000, total_pnl: 20000, total_pnl_pct: 25,
      strategy_count: 2, running_count: 1, strategies: [
        { strategy_id: 's1', strategy_name: 'SMA', status: 'running', assets: 60000, pnl: 10000, pnl_pct: 20 },
      ],
    }),
    getPositions: vi.fn().mockResolvedValue({
      total: 0,
      positions: [],
      summary: {
        total_long_value: 0,
        total_short_value: 0,
        gross_market_value: 0,
        net_market_value: 0,
        total_pnl: 0,
        long_count: 0,
        short_count: 0,
        flat_count: 0,
      },
    }),
    getTrades: vi.fn().mockResolvedValue({
      total: 2,
      trades: [
        {
          strategy_id: 'unit-1',
          strategy_name: 'CTA 交易工作区 / RB 趋势',
          instance_id: 'unit-1',
          ref: 1,
          datetime: '2026-06-19 10:00:00',
          dtopen: '2026-06-19 09:30:00',
          dtclose: '2026-06-19 10:00:00',
          data_name: 'RB2510',
          direction: 'long',
          size: 2,
          price: 3600,
          value: 7200,
          commission: 3,
          pnl: 200,
          pnlcomm: 197,
          barlen: 12,
        },
        {
          strategy_id: 'idle-unit',
          strategy_name: '暂停工作区 / AG 趋势',
          instance_id: 'idle-unit',
          ref: 2,
          datetime: '2026-06-19 10:00:00',
          dtopen: '2026-06-19 09:30:00',
          dtclose: '2026-06-19 10:00:00',
          data_name: 'AG2512',
          direction: 'short',
          size: 1,
          price: 8000,
          value: 8000,
          commission: 3,
          pnl: -50,
          pnlcomm: -53,
          barlen: 8,
        },
      ],
    }),
    getEquity: vi.fn().mockResolvedValue({ dates: ['2024-01-01'], total_equity: [100000], total_drawdown: [0], strategies: [] }),
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
          margin_value: 720,
          multiplier: 10,
          margin_rate: 0.1,
          leverage: 10,
          commission: 3.5,
          gross_pnl: 203.5,
          position_source: 'gateway',
          asset_spec_source: 'ctp_gateway',
          valuation_status: 'confirmed',
          valuation_warnings: [],
        },
        {
          unit_id: 'unit-flat',
          unit_name: '空仓单元',
          symbol: 'AG2512',
          symbol_name: '白银',
          trading_mode: 'live',
          long_position: 0,
          short_position: 0,
          avg_price: 0,
          latest_price: 0,
          position_pnl: 0,
          market_value: 0,
        },
      ],
      total_long_value: 999999,
      total_short_value: 888888,
      total_pnl: 777,
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

  it('formatPositionSize preserves micro nonzero positions', () => {
    const vm = doMount().vm as any
    expect(vm.formatPositionSize(0.00004)).toBe('0.00004')
    expect(vm.formatPositionSize(-0.00004)).toBe('-0.00004')
    expect(vm.formatPositionSize(1.23456)).toBe('1.2346')
    expect(vm.formatPositionSize(0)).toBe('--')
  })

  it('hasOpenPosition ignores zero residuals but keeps hedged positions', () => {
    const vm = doMount().vm as any
    expect(vm.hasOpenPosition({ size: 1e-13, long_position: 0, short_position: 0 })).toBe(false)
    expect(vm.hasOpenPosition({ size: 0, long_position: 1, short_position: 1 })).toBe(true)
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
    expect(vm.positions[0].long_position).toBe(2)
    expect(vm.positions[0].latest_price).toBe(3600)
    expect(vm.positions[0].margin_value).toBe(720)
    expect(vm.positions[0].leverage).toBe(10)
    expect(vm.positions[0].commission).toBe(3.5)
    expect(vm.positions[0].position_source).toBe('gateway')
    expect(vm.positions[0].asset_spec_source).toBe('ctp_gateway')
    expect(vm.valuationStatusLabel(vm.positions[0])).toBe('交易所确认')
    expect(vm.positionSummary.total_long_value).toBe(7200)
    expect(vm.positionSummary.gross_market_value).toBe(7200)
    expect(vm.positionSummary.net_market_value).toBe(7200)
    expect(vm.positionSummary.total_pnl).toBe(200)
  })

  it('loadWorkspaceAggregates keeps hedged positions with zero net size', async () => {
    const vm = doMount().vm as any
    vm.runningWorkspaces = [
      {
        id: 'ws-running',
        user_id: 'u1',
        name: 'CTA 交易工作区',
        description: null,
        workspace_type: 'trading',
        settings: {},
        trading_config: {},
        unit_count: 1,
        completed_count: 0,
        status: 'running',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-02T00:00:00Z',
      },
    ]
    vm.selectedWorkspaceIds = ['ws-running']
    vi.mocked(workspaceApi.getTradingPositions).mockResolvedValueOnce({
      positions: [
        {
          unit_id: 'unit-hedged',
          unit_name: 'IF 双向',
          symbol: 'IF2609',
          symbol_name: null,
          trading_mode: 'live',
          long_position: 1,
          short_position: 1,
          avg_price: 5000,
          latest_price: 5010,
          position_pnl: 120,
          market_value: 1_002_000,
          margin_value: 120_240,
          multiplier: 300,
          margin_rate: 0.12,
          leverage: 8.33333333,
          commission: 10,
          gross_pnl: 130,
          position_source: 'gateway',
          asset_spec_source: 'ctp_gateway',
          valuation_status: 'confirmed',
          valuation_warnings: [],
        },
      ],
      total_long_value: 501_000,
      total_short_value: 501_000,
      total_pnl: 120,
    })
    vi.mocked(portfolioApi.getTrades).mockResolvedValueOnce({ total: 0, trades: [] })

    await vm.loadWorkspaceAggregates()

    expect(vm.positions).toHaveLength(1)
    expect(vm.positions[0].direction).toBe('hedged')
    expect(vm.positions[0].size).toBe(0)
    expect(vm.positions[0].long_position).toBe(1)
    expect(vm.positions[0].short_position).toBe(1)
    expect(vm.directionLabel('hedged')).toBe('双向')
    expect(vm.positionSummary.long_count).toBe(1)
    expect(vm.positionSummary.short_count).toBe(1)
    expect(vm.positionSummary.gross_market_value).toBe(1_002_000)
    expect(vm.positionSummary.net_market_value).toBe(0)
  })

  it('loadTabData loads selected workspace trade records', async () => {
    const vm = doMount().vm as any
    await vm.loadData()
    await vm.loadTabData('trades')
    expect(vm.trades.length).toBe(1)
    expect(vm.trades[0].strategy_name).toBe('CTA 交易工作区 / RB 趋势')
    expect(vm.trades[0].data_name).toBe('RB2510')
    expect(vm.trades[0].pnlcomm).toBe(197)
    expect(portfolioApi.getTrades).toHaveBeenCalledWith(1000, ['ws-running'])
  })

  it('loadWorkspaceAggregates requests trades per selected workspace', async () => {
    const vm = doMount().vm as any
    vm.runningWorkspaces = [
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
        id: 'ws-mt5',
        user_id: 'u1',
        name: 'MT5模拟工作区',
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
    ]
    vm.selectedWorkspaceIds = ['ws-running', 'ws-mt5']

    vi.mocked(portfolioApi.getTrades).mockClear()
    await vm.loadWorkspaceAggregates()

    expect(portfolioApi.getTrades).toHaveBeenCalledWith(1000, ['ws-running'])
    expect(portfolioApi.getTrades).toHaveBeenCalledWith(1000, ['ws-mt5'])
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

  it('tradeDirectionLabel supports backend buy/sell directions', () => {
    const vm = doMount().vm as any
    expect(vm.tradeDirectionLabel('buy')).toBe('多')
    expect(vm.tradeDirectionLabel('sell')).toBe('空')
    expect(vm.tradeDirectionClass('buy')).toBe('text-red-600')
    expect(vm.tradeDirectionClass('sell')).toBe('text-green-600')
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
