import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { useQuoteStore } from '@/stores/quote'
import QuotePage from '@/views/QuotePage.vue'
import { mountWithPlugins } from '@/test/mountWithPlugins'

const storageState = new Map<string, string>()

const quoteApiMocks = vi.hoisted(() => ({
  listSources: vi.fn(),
  getSymbols: vi.fn(),
  addSymbols: vi.fn(),
  removeSymbols: vi.fn(),
  searchSymbols: vi.fn(),
  getQuotes: vi.fn(),
  getChartData: vi.fn(),
}))

const messageMocks = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
}))

const chartMocks = vi.hoisted(() => ({
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
}))

const echartsInitMock = vi.hoisted(() => vi.fn(() => chartMocks))

vi.mock('element-plus', () => ({
  ElMessage: messageMocks,
}))

vi.mock('@element-plus/icons-vue', () => {
  const icon = { template: '<span class="icon-stub" />' }

  return {
    Search: icon,
    Refresh: icon,
    Plus: icon,
    Loading: icon,
    Delete: icon,
    Setting: icon,
    Filter: icon,
    Rank: icon,
    DataLine: icon,
    WarningFilled: icon,
  }
})

vi.mock('@/api/quote', () => ({
  quoteApi: quoteApiMocks,
}))

vi.mock('echarts', () => ({
  init: echartsInitMock,
}))

describe('QuotePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    storageState.clear()
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => storageState.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => {
        storageState.set(key, value)
      }),
      removeItem: vi.fn((key: string) => {
        storageState.delete(key)
      }),
      clear: vi.fn(() => {
        storageState.clear()
      }),
    })

    quoteApiMocks.listSources.mockResolvedValue({
      sources: [
        {
          source: 'eastmoney',
          source_label: '东方财富',
          status: 'available',
          status_message: null,
          capabilities: ['quotes'],
        },
      ],
    })
    quoteApiMocks.getSymbols.mockResolvedValue({
      source: 'eastmoney',
      default_symbols: [],
      custom_symbols: ['AG2406'],
    })
    quoteApiMocks.addSymbols.mockResolvedValue({
      source: 'eastmoney',
      symbols: ['AG2406'],
    })
    quoteApiMocks.removeSymbols.mockResolvedValue({
      source: 'eastmoney',
      symbols: [],
    })
    quoteApiMocks.searchSymbols.mockResolvedValue({
      source: 'eastmoney',
      keyword: 'rb',
      results: [
        {
          symbol: 'RB2405',
          name: '螺纹钢主力',
          exchange: 'SHFE',
          category: 'futures',
        },
      ],
    })
    quoteApiMocks.getQuotes.mockResolvedValue({
      source: 'eastmoney',
      source_label: '东方财富',
      total: 1,
      ticks: [
        {
          source: 'eastmoney',
          source_label: '东方财富',
          symbol: 'RB2405',
          name: '螺纹钢主力',
          exchange: 'SHFE',
          category: 'futures',
          last_price: 3500,
          change: 10,
          change_pct: 1.2,
          bid_price: 3499,
          ask_price: 3501,
          high_price: 3510,
          low_price: 3480,
          open_price: 3490,
          prev_close: 3490,
          volume: 125000,
          turnover: 1000000,
          open_interest: 80000,
          update_time: '2026-01-01T09:30:00Z',
          status: 'trading',
          error_message: null,
        },
      ],
      fields: [
        { prop: 'symbol', label: '代码', visible: true, always_show: true },
        { prop: 'last_price', label: '最新价', visible: true },
        { prop: 'change_pct', label: '涨跌幅', visible: true },
      ],
      update_time: '2026-01-01T09:30:00Z',
      refresh_mode: 'polling',
    })
    quoteApiMocks.getChartData.mockResolvedValue({
      source: 'eastmoney',
      symbol: 'RB2405',
      timeframe: 'M5',
      total: 2,
      bars: [
        { date: '2026-01-01 09:30', open: 3490, high: 3510, low: 3488, close: 3500, volume: 1000 },
        { date: '2026-01-01 09:35', open: 3500, high: 3512, low: 3498, close: 3508, volume: 1200 },
      ],
    })
  })

  it('loads quotes and covers symbol, sort, column, format, and chart helpers', async () => {
    const wrapper = mountWithPlugins(QuotePage, {
      customStubs: {
        Search: true,
        Refresh: true,
        Plus: true,
        Loading: true,
        Delete: true,
        Setting: true,
        Filter: true,
        Rank: true,
        DataLine: true,
        WarningFilled: true,
        'el-popover': { template: '<div class="el-popover"><slot name="reference" /><slot /></div>' },
        'el-drawer': { template: '<div class="el-drawer"><slot /></div>' },
      },
    })

    await flushPromises()

    const store = useQuoteStore()
    expect(quoteApiMocks.listSources).toHaveBeenCalledTimes(1)
    expect(quoteApiMocks.getQuotes).toHaveBeenCalledWith('eastmoney')
    expect(quoteApiMocks.getSymbols).toHaveBeenCalledWith('eastmoney')
    expect(store.filteredTicks).toHaveLength(1)
    expect(wrapper.findAll('.quote-mobile-card')).toHaveLength(1)
    expect(wrapper.find('.quote-mobile-card').text()).toContain('RB2405')

    const vm = wrapper.vm as any
    vm.addKeyword = 'rb'
    vm.handleAddSearch()
    vi.runAllTimers()
    await flushPromises()
    expect(quoteApiMocks.searchSymbols).toHaveBeenCalledWith('eastmoney', 'rb')

    vm.addSymbolDirect = 'ag2406'
    await vm.handleDirectAdd()
    await flushPromises()
    expect(quoteApiMocks.addSymbols).toHaveBeenCalledWith('eastmoney', ['AG2406'])
    expect(messageMocks.success).toHaveBeenCalledWith('已添加 AG2406')

    vm.handleSourceClick({
      source: 'sim',
      source_label: '模拟源',
      status: 'not_configured',
      status_message: '未配置',
      capabilities: [],
    })
    expect(messageMocks.warning).toHaveBeenCalledWith('未配置')

    vm.handleSortChange({ prop: 'last_price', order: 'ascending' })
    expect(store.sortField).toBe('last_price')
    expect(store.sortOrder).toBe('asc')

    expect(vm.fmtPct(1.23)).toBe('+1.23%')
    expect(vm.fmtVol(120000)).toContain('万')
    expect(vm.formatTime('2026-01-01T09:30:00Z')).toBeTruthy()
    expect(vm.priceClass({ change_pct: 1.2 })).toContain('text-red-600')
    expect(vm.changeClass(-1)).toBe('text-green-600')
    expect(vm.isCustomSymbol('AG2406')).toBe(true)

    vm.showColumnDialog = true
    await wrapper.vm.$nextTick()
    vm.onColDragStart(0)
    vm.onColDrop(1)
    vm.handleSaveColumns()
    expect(store.columnConfig[0].prop).toBe('last_price')
    vm.handleResetColumns()
    expect(store.columnConfig[0].prop).toBe('symbol')

    await vm.handleRowClick(store.filteredTicks[0])
    await flushPromises()
    expect(quoteApiMocks.getChartData).toHaveBeenCalledWith('eastmoney', 'RB2405', 'M5')

    echartsInitMock.mockClear()
    chartMocks.setOption.mockClear()
    vm.chartContainerRef = document.createElement('div')
    vm.renderChart()
    expect(echartsInitMock).toHaveBeenCalledTimes(1)
    expect(chartMocks.setOption).toHaveBeenCalledTimes(1)

    vm.flashSymbols = new Set(['RB2405'])
    expect(vm.rowClassName({ row: { symbol: 'RB2405' } })).toBe('tick-flash')
  })
})
