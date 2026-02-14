import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import EquityCurve from '@/components/charts/EquityCurve.vue'

// Mock echarts before importing
const mockChartInstance = {
  setOption: vi.fn(),
  dispose: vi.fn(),
  resize: vi.fn(),
  getDom: () => document.createElement('div'),
}

vi.mock('echarts', () => ({
  init: vi.fn(() => mockChartInstance),
  graphic: {
    LinearGradient: class LinearGradient {
      constructor(public config: any) {}
    },
  },
}))

describe('EquityCurve', () => {
  beforeEach(() => {
    // Create a div element for chartRef
    const div = document.createElement('div')
    div.id = 'chart-container'
    document.body.appendChild(div)
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('should render title', () => {
    const wrapper = mount(EquityCurve, {
      props: {
        data: [],
      },
    })
    expect(wrapper.text()).toContain('资金曲线')
  })

  it('should use default height', () => {
    const wrapper = mount(EquityCurve, {
      props: {
        data: [],
      },
    })
    const chartDiv = wrapper.find('.equity-curve > div')
    expect(chartDiv.attributes('style')).toContain('height: 350px')
  })

  it('should use custom height', () => {
    const wrapper = mount(EquityCurve, {
      props: {
        data: [],
        height: 500,
      },
    })
    const chartDiv = wrapper.find('.equity-curve > div')
    expect(chartDiv.attributes('style')).toContain('height: 500px')
  })

  it('should handle empty data', () => {
    const wrapper = mount(EquityCurve, {
      props: {
        data: [],
      },
    })
    expect(wrapper.find('.equity-curve').exists()).toBe(true)
  })

  it('should accept equity array prop', () => {
    const wrapper = mount(EquityCurve, {
      props: {
        equity: [100000, 101000, 102000],
        dates: ['2024-01-01', '2024-01-02', '2024-01-03'],
      },
    })
    expect(wrapper.find('.equity-curve').exists()).toBe(true)
  })

  it('should accept drawdown array prop', () => {
    const wrapper = mount(EquityCurve, {
      props: {
        equity: [100000, 101000],
        dates: ['2024-01-01', '2024-01-02'],
        drawdown: [0, -5],
      },
    })
    expect(wrapper.find('.equity-curve').exists()).toBe(true)
  })

  it('should accept trades prop', () => {
    const wrapper = mount(EquityCurve, {
      props: {
        equity: [100000, 101000],
        dates: ['2024-01-01', '2024-01-02'],
        trades: [
          { date: '2024-01-01', type: 'buy', price: 100 },
          { date: '2024-01-02', type: 'sell', price: 110 },
        ],
      },
    })
    expect(wrapper.find('.equity-curve').exists()).toBe(true)
  })

  it('should use data prop with EquityPoint structure', () => {
    const equityData = [
      { date: '2024-01-01', total_assets: 100000 },
      { date: '2024-01-02', total_assets: 101000 },
      { date: '2024-01-03', total_assets: 102000 },
    ]
    const wrapper = mount(EquityCurve, {
      props: {
        data: equityData,
      },
    })
    expect(wrapper.find('.equity-curve').exists()).toBe(true)
  })

  it('should handle detail data with cash and position_value', () => {
    const equityData = [
      { date: '2024-01-01', total_assets: 100000, cash: 50000, position_value: 50000 },
      { date: '2024-01-02', total_assets: 101000, cash: 51000, position_value: 50000 },
    ]
    const wrapper = mount(EquityCurve, {
      props: {
        data: equityData,
      },
    })
    expect(wrapper.find('.equity-curve').exists()).toBe(true)
  })
})
