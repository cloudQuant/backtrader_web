import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DataPage from '@/views/DataPage.vue'
import { elStubs } from '@/test/stubs'
import type { MarketAssetType } from '@/api/marketData'

const apiMocks = vi.hoisted(() => ({
  lookupInstrument: vi.fn(),
  listTables: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/api/marketData', () => ({
  marketDataApi: {
    lookupInstrument: apiMocks.lookupInstrument,
  },
}))

vi.mock('@/api/akshare', () => ({
  akshareTablesApi: {
    list: apiMocks.listTables,
  },
}))

const assetNames: Record<MarketAssetType, string> = {
  stock: '平安银行',
  futures: 'IM2606',
  bond: '电气转债',
  fund: '沪深300ETF',
  option: '151.ni2609C184000',
  fx: '美元离岸人民币',
  crypto: 'BTCJPY',
}

const assetSymbols: Record<MarketAssetType, string> = {
  stock: '000001',
  futures: 'IM2606',
  bond: 'sh110074',
  fund: '510300',
  option: '151.ni2609C184000',
  fx: 'USDCNH',
  crypto: 'BTCJPY',
}

function createLookupFixture(assetType: MarketAssetType) {
  const baseSnapshot = {
    data_source_table: 'akshare_data',
    price: assetType === 'crypto' ? 10000000 : 12.34,
    open: 12.1,
    high: 12.4,
    low: 12,
    volume: 1000,
    update_time: '2026-06-19T09:30:00',
  }
  const snapshots = {
    stock: {
      ...baseSnapshot,
      turnover: 186000000,
      market_cap: 320000000000,
      float_market_cap: 250000000000,
      pe: 8.1,
      pb: 0.9,
      change_pct: 0.98,
    },
    futures: {
      ...baseSnapshot,
      settle: 3250,
      previous_settle: 3220,
      open_interest: 280000,
      bid: 3251,
      ask: 3252,
    },
    bond: {
      ...baseSnapshot,
      turnover: 8200000,
      bid: 112.31,
      ask: 112.34,
      change_pct: -0.12,
    },
    fund: {
      ...baseSnapshot,
      turnover: 56000000,
      change_pct: 0.35,
    },
    option: {
      ...baseSnapshot,
      change: 0.08,
      change_pct: 2.1,
    },
    fx: {
      ...baseSnapshot,
      price: 7.2431,
      previous_close: 7.221,
      change_pct: 0.31,
      volume: null,
    },
    crypto: {
      ...baseSnapshot,
      open: null,
      change: 1250,
      change_pct: 1.8,
      market: 'CRYPTO',
    },
  }
  const cryptoRows = [
    { date: '2026-06-19', name: 'Asset Manager', volume: 2000, open_interest: 8000, change: 120 },
    { date: '2026-06-19', name: 'Leveraged Funds', volume: 1800, open_interest: 7600, change: -80 },
  ]
  const ohlcvRows = [
    {
      date: '2026-06-18',
      open: 12.1,
      high: 12.4,
      low: 12,
      close: 12.34,
      volume: 1000,
      turnover: assetType === 'stock' || assetType === 'fund' || assetType === 'bond' ? 8800000 : null,
      change_pct: 0.98,
      open_interest: assetType === 'futures' ? 275000 : null,
      settle: assetType === 'futures' ? 3230 : null,
    },
    {
      date: '2026-06-19',
      open: 12.3,
      high: 12.6,
      low: 12.2,
      close: 12.5,
      volume: 1200,
      turnover: assetType === 'stock' || assetType === 'fund' || assetType === 'bond' ? 9600000 : null,
      change_pct: 1.3,
      open_interest: assetType === 'futures' ? 280000 : null,
      settle: assetType === 'futures' ? 3250 : null,
    },
  ]

  return {
    asset_type: assetType,
    symbol: assetSymbols[assetType],
    name: assetNames[assetType],
    market: assetType === 'fx' ? 'FX' : 'CN',
    provider: 'akshare_data',
    snapshot: snapshots[assetType],
    history: {
      period: 'daily',
      total: assetType === 'crypto' ? cryptoRows.length : ohlcvRows.length,
      rows: assetType === 'crypto' ? cryptoRows : ohlcvRows,
    },
    indicators: {
      latest_close: assetType === 'crypto' ? null : 12.5,
      return_pct: assetType === 'crypto' ? null : 1.29,
      highest_close: assetType === 'crypto' ? null : 12.5,
      lowest_close: assetType === 'crypto' ? null : 12.34,
      avg_volume: assetType === 'crypto' ? 1900 : 1100,
      observation_count: 2,
    },
    warnings: [],
  }
}

describe('DataPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.lookupInstrument.mockImplementation(({ asset_type }: { asset_type: MarketAssetType }) => (
      Promise.resolve(createLookupFixture(asset_type))
    ))
    apiMocks.listTables.mockResolvedValue({
      items: [
        {
          id: 1,
          table_name: 'stock_zh_a_hist_000001',
          table_comment: 'A股历史行情',
          category: 'stocks',
          script_id: 'stock_zh_a_hist',
          row_count: 1200,
          last_update_time: '2026-06-19T09:30:00',
          last_update_status: 'success',
          data_start_date: '2026-01-01',
          data_end_date: '2026-06-19',
          symbol_raw: '000001',
          symbol_normalized: '000001',
          market: 'CN',
          asset_type: 'stock',
          metadata: {},
          created_at: '2026-06-19T09:30:00',
          updated_at: '2026-06-19T09:30:00',
        },
      ],
      total: 1,
      page: 1,
      page_size: 8,
    })
  })

  async function mountPage(path = '/data/market') {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/data/market', component: DataPage }],
    })
    await router.push(path)
    await router.isReady()
    const wrapper = mount(DataPage, {
      global: {
        plugins: [router],
        stubs: elStubs,
      },
    })
    await flushPromises()
    return wrapper
  }

  it('renders one historical data tab per supported asset type', async () => {
    const wrapper = await mountPage()

    expect(wrapper.text()).toContain('历史数据')
    expect(wrapper.text()).toContain('股票')
    expect(wrapper.text()).toContain('期货')
    expect(wrapper.text()).toContain('债券')
    expect(wrapper.text()).toContain('基金')
    expect(wrapper.text()).toContain('期权')
    expect(wrapper.text()).toContain('外汇')
    expect(wrapper.text()).toContain('数字货币')
    expect(wrapper.find('.options-card').exists()).toBe(false)
    expect(apiMocks.lookupInstrument).toHaveBeenCalledWith({
      asset_type: 'stock',
      symbol: '000001',
      period: 'daily',
      start_date: expect.any(String),
      end_date: expect.any(String),
      market: undefined,
    })
    expect((wrapper.vm as any).result.name).toBe('平安银行')
    expect((wrapper.vm as any).historyRows).toHaveLength(2)
    expect(wrapper.text()).toContain('+1.29%')
    expect(wrapper.find('[data-test="market-main-chart"]').exists()).toBe(true)
    expect(apiMocks.listTables).toHaveBeenCalled()
  })

  it('shows a stock-specific valuation and liquidity panel', async () => {
    const wrapper = await mountPage()

    expect(wrapper.text()).toContain('估值与流动性')
    expect(wrapper.text()).toContain('总市值')
    expect(wrapper.text()).toContain('PE / PB')
    expect(wrapper.text()).not.toContain('合约监控')
    expect((wrapper.vm as any).assetKpiCards.map((card: { label: string }) => card.label)).toEqual([
      '最新价',
      '区间涨跌',
      '成交额',
      'PE / PB',
    ])
  })

  it('shows futures contract controls instead of stock valuation fields', async () => {
    const wrapper = await mountPage()
    const futuresTab = wrapper.findAll('.asset-tab').find((button) => button.text().includes('期货'))

    await futuresTab?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('合约监控')
    expect(wrapper.text()).toContain('持仓量')
    expect(wrapper.text()).toContain('结算价')
    expect(wrapper.text()).toContain('买一 / 卖一')
    expect(wrapper.text()).not.toContain('总市值')
    expect((wrapper.vm as any).assetKpiCards.map((card: { label: string }) => card.label)).toEqual([
      '最新价',
      '持仓量',
      '结算价',
      '买卖价差',
    ])
  })

  it('uses crypto position columns when crypto history has no ohlc prices', async () => {
    const wrapper = await mountPage()
    const cryptoTab = wrapper.findAll('.asset-tab').find((button) => button.text().includes('数字货币'))

    await cryptoTab?.trigger('click')
    await flushPromises()

    const keys = (wrapper.vm as any).historyTableColumns.map((column: { key: string }) => column.key)
    expect(wrapper.text()).toContain('数字货币持仓')
    expect(keys).toEqual(['date', 'name', 'volume', 'open_interest', 'change'])
    expect(keys).not.toContain('open')
    expect(keys).not.toContain('close')
  })

  it('uses the options tab as its own historical asset query', async () => {
    const wrapper = await mountPage('/data/market?tab=options')

    await flushPromises()

    expect(apiMocks.lookupInstrument).toHaveBeenCalledWith({
      asset_type: 'option',
      symbol: '151.ni2609C184000',
      period: 'daily',
      start_date: expect.any(String),
      end_date: expect.any(String),
      market: undefined,
    })
    expect((wrapper.vm as any).form.asset_type).toBe('option')
    expect((wrapper.vm as any).result.asset_type).toBe('option')
  })

  it('queries only the selected tab asset when switching tabs', async () => {
    const wrapper = await mountPage()
    const optionsTab = wrapper.findAll('.asset-tab').find((button) => button.text().includes('期权'))

    await optionsTab?.trigger('click')
    await flushPromises()

    expect(apiMocks.lookupInstrument).toHaveBeenLastCalledWith({
      asset_type: 'option',
      symbol: '151.ni2609C184000',
      period: 'daily',
      start_date: expect.any(String),
      end_date: expect.any(String),
      market: undefined,
    })
    expect((wrapper.vm as any).result.asset_type).toBe('option')
    expect(wrapper.text()).not.toContain('Put / Call Ratio')
  })
})
