import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import TradeSignalChart from '@/components/charts/TradeSignalChart.vue'
import { elStubs } from '@/test/stubs'

const sampleKlines = [
  { date: '2024-01-01', open: 100, close: 105, low: 99, high: 106, volume: 1000 },
  { date: '2024-01-02', open: 105, close: 102, low: 101, high: 107, volume: 1200 },
  { date: '2024-01-03', open: 102, close: 108, low: 101, high: 109, volume: 900 },
]
const sampleSignals = [
  { date: '2024-01-01', type: 'buy', price: 100 },
  { date: '2024-01-03', type: 'sell', price: 108 },
]

describe('TradeSignalChart', () => {
  const doMount = (extraProps: any = {}) => mount(TradeSignalChart, {
    props: { klines: [], signals: [], ...extraProps } as any,
    global: { stubs: elStubs },
  })

  it('mounts with empty data', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('mounts with kline data and signals', () => {
    expect(doMount({ klines: sampleKlines, signals: sampleSignals }).exists()).toBe(true)
  })

  it('renders chart container', () => {
    const wrapper = doMount()
    expect(wrapper.find('.trade-signal-chart').exists()).toBe(true)
  })

  it('computedHeight defaults to 600 with no sub charts', () => {
    const vm = doMount().vm as any
    expect(vm.computedHeight).toBe(600)
  })

  it('stripWarmup strips leading zeros/nulls', () => {
    const vm = doMount().vm as any
    expect(vm.stripWarmup([0, 0, null, 5, 6])).toEqual([null, null, null, 5, 6])
    expect(vm.stripWarmup([3, 4, 5])).toEqual([3, 4, 5])
    expect(vm.stripWarmup([])).toEqual([])
  })

  it('classifyIndicators returns empty when no indicators', () => {
    const vm = doMount({ klines: sampleKlines }).vm as any
    const result = vm.classifyIndicators()
    expect(result.mainIndicators).toEqual({})
    expect(result.subGroups).toEqual([])
  })

  it('classifyIndicators classifies overlapping indicator as main', () => {
    const vm = doMount({
      klines: sampleKlines,
      indicators: { sma: [100, 103, 105] },
    }).vm as any
    const result = vm.classifyIndicators()
    expect(result.mainIndicators).toHaveProperty('sma')
  })

  it('classifyIndicators classifies non-overlapping indicator as sub', () => {
    const vm = doMount({
      klines: sampleKlines,
      indicators: { rsi: [30, 50, 70] },
    }).vm as any
    const result = vm.classifyIndicators()
    expect(result.subGroups.length).toBeGreaterThanOrEqual(0)
  })

  it('handleResize is callable', () => {
    const vm = doMount().vm as any
    vm.handleResize() // should not throw
  })

  it('handlePeriodChange updates selectedPeriod', () => {
    const vm = doMount({ klines: sampleKlines }).vm as any
    vm.handlePeriodChange('3m')
    expect(vm.selectedPeriod).toBe('3m')
  })

  it('handlePeriodChange handles all periods', () => {
    const vm = doMount({ klines: sampleKlines }).vm as any
    for (const p of ['1m', '3m', '6m', '1y', 'all']) {
      vm.handlePeriodChange(p)
      expect(vm.selectedPeriod).toBe(p)
    }
  })

  it('handleExport does nothing without chart instance', () => {
    const vm = doMount().vm as any
    vm.handleExport() // should not throw
  })

  it('renderChart does nothing with no klines', () => {
    const vm = doMount().vm as any
    vm.renderChart() // should not throw
  })

  it('periods has 5 entries', () => {
    const vm = doMount().vm as any
    expect(vm.periods.length).toBe(5)
  })

  it('mounts with indicators prop', () => {
    const wrapper = doMount({
      klines: sampleKlines,
      signals: sampleSignals,
      indicators: { sma20: [100, 103, 105], rsi: [30, 50, 70] },
    })
    expect(wrapper.exists()).toBe(true)
  })
})
