import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Dashboard from './Dashboard.vue'
import { elStubs } from '@/test/stubs'

vi.mock('@element-plus/icons-vue', () => ({
  DataLine: { template: '<span />' },
  Document: { template: '<span />' },
  Grid: { template: '<span />' },
  TrendCharts: { template: '<span />' },
  Trophy: { template: '<span />' },
}))

vi.mock('@/stores/backtest', () => ({
  useBacktestStore: () => ({
    fetchResults: vi.fn().mockResolvedValue(undefined),
    results: [
      { task_id: 't1', strategy_id: 's1', symbol: 'BTC', total_return: 15.5, sharpe_ratio: 1.2, max_drawdown: -8.3, status: 'completed', created_at: '2024-01-01' },
    ],
    total: 10,
  }),
}))

vi.mock('@/stores/strategy', () => ({
  useStrategyStore: () => ({
    fetchStrategies: vi.fn().mockResolvedValue(undefined),
    fetchTemplates: vi.fn().mockResolvedValue(undefined),
    templates: [{ id: 's1', name: 'SMA Cross' }],
    total: 5,
  }),
}))

describe('Dashboard', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  const doMount = () => mount(Dashboard, { global: { stubs: elStubs } })

  it('renders without error', () => {
    const wrapper = doMount()
    expect(wrapper.exists()).toBe(true)
  })

  it('has stat refs', () => {
    const vm = doMount().vm as any
    expect(vm.stats).toBeDefined()
    expect(vm.stats.backtestCount).toBe(0)
  })

  it('getStatusType returns correct types', () => {
    const vm = doMount().vm as any
    expect(vm.getStatusType('completed')).toBe('success')
    expect(vm.getStatusType('running')).toBe('warning')
    expect(vm.getStatusType('pending')).toBe('info')
    expect(vm.getStatusType('failed')).toBe('danger')
    expect(vm.getStatusType('unknown')).toBe('info')
  })

  it('getStatusText returns correct text', () => {
    const vm = doMount().vm as any
    expect(vm.getStatusText('completed')).toBe('完成')
    expect(vm.getStatusText('running')).toBe('运行中')
    expect(vm.getStatusText('failed')).toBe('失败')
    expect(vm.getStatusText('xyz')).toBe('xyz')
  })

  it('getStrategyName resolves from templates', () => {
    const vm = doMount().vm as any
    expect(vm.getStrategyName('s1')).toBe('SMA Cross')
    expect(vm.getStrategyName('unknown_id')).toBe('unknown_id')
  })
})
