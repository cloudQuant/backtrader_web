import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PortfolioPage from '@/views/PortfolioPage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
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
    getPositions: vi.fn().mockResolvedValue({ total: 1, positions: [
      { strategy_name: 'SMA', data_name: 'BTC', direction: 'long', size: 10, price: 100, market_value: 1000 },
    ] }),
    getTrades: vi.fn().mockResolvedValue({ total: 1, trades: [
      { strategy_name: 'SMA', data_name: 'BTC', direction: 'long', dtopen: '2024-01-01', dtclose: '2024-02-01', price: 100, size: 10, commission: 1, pnlcomm: 50, barlen: 30 },
    ] }),
    getEquity: vi.fn().mockResolvedValue({ dates: ['2024-01-01'], total_equity: [100000], drawdown: [0], strategies: [] }),
    getAllocation: vi.fn().mockResolvedValue({ total: 1, items: [{ name: 'BTC', value: 50000, pct: 50 }] }),
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

  it('loadData loads overview', async () => {
    const vm = doMount().vm as any
    await vm.loadData()
    expect(vm.overview.total_assets).toBe(100000)
    expect(vm.loading).toBe(false)
  })

  it('loadTabData loads positions', async () => {
    const vm = doMount().vm as any
    await vm.loadTabData('positions')
    expect(vm.positions.length).toBe(1)
  })

  it('loadTabData loads trades', async () => {
    const vm = doMount().vm as any
    await vm.loadTabData('trades')
    expect(vm.trades.length).toBe(1)
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

  it('activeTab defaults to strategies', () => {
    const vm = doMount().vm as any
    expect(vm.activeTab).toBe('strategies')
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
