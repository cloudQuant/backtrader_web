import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PerformancePanel from '@/components/charts/PerformancePanel.vue'

// Create a stub that renders the title prop
const MetricCardStub = {
  name: 'MetricCard',
  props: ['title', 'value', 'format', 'change', 'color', 'precision', 'tooltip'],
  template: '<div class="metric-card" :data-title="title">{{ title }}</div>',
}

describe('PerformancePanel', () => {
  it('should render title', () => {
    const wrapper = mount(PerformancePanel, {
      global: {
        stubs: {
          MetricCard: MetricCardStub,
        },
      },
    })
    expect(wrapper.text()).toContain('绩效概览')
  })

  it('should render main metrics section', () => {
    const wrapper = mount(PerformancePanel, {
      props: {
        metrics: {
          initial_capital: 100000,
          final_assets: 120000,
          total_return: 0.2,
          annualized_return: 0.25,
        },
      },
      global: {
        stubs: {
          MetricCard: MetricCardStub,
        },
      },
    })
    expect(wrapper.text()).toContain('初始资金')
    expect(wrapper.text()).toContain('最终资产')
    expect(wrapper.text()).toContain('总收益率')
    expect(wrapper.text()).toContain('年化收益')
  })

  it('should render risk metrics section', () => {
    const wrapper = mount(PerformancePanel, {
      props: {
        metrics: {
          max_drawdown: -0.1,
          sharpe_ratio: 1.5,
          win_rate: 0.6,
          profit_factor: 2.0,
        },
      },
      global: {
        stubs: {
          MetricCard: MetricCardStub,
        },
      },
    })
    expect(wrapper.text()).toContain('最大回撤')
    expect(wrapper.text()).toContain('夏普比率')
    expect(wrapper.text()).toContain('胜率')
    expect(wrapper.text()).toContain('盈亏比')
  })

  it('should render trade statistics section', () => {
    const wrapper = mount(PerformancePanel, {
      props: {
        metrics: {
          trade_count: 50,
          avg_holding_days: 5,
          max_consecutive_wins: 5,
          max_consecutive_losses: 3,
        },
      },
      global: {
        stubs: {
          MetricCard: MetricCardStub,
        },
      },
    })
    expect(wrapper.text()).toContain('交易次数')
    expect(wrapper.text()).toContain('平均持仓')
    expect(wrapper.text()).toContain('最大连赢')
    expect(wrapper.text()).toContain('最大连亏')
  })

  it('should handle undefined metrics', () => {
    const wrapper = mount(PerformancePanel, {
      props: {
        metrics: undefined,
      },
      global: {
        stubs: {
          MetricCard: MetricCardStub,
        },
      },
    })
    expect(wrapper.find('.performance-panel').exists()).toBe(true)
  })

  it('should render all metrics with complete data', () => {
    const completeMetrics = {
      initial_capital: 100000,
      final_assets: 120000,
      total_return: 0.2,
      annualized_return: 0.25,
      max_drawdown: -0.1,
      sharpe_ratio: 1.5,
      win_rate: 0.6,
      profit_factor: 2.0,
      trade_count: 50,
      avg_holding_days: 5,
      max_consecutive_wins: 5,
      max_consecutive_losses: 3,
    }
    const wrapper = mount(PerformancePanel, {
      props: {
        metrics: completeMetrics,
      },
      global: {
        stubs: {
          MetricCard: MetricCardStub,
        },
      },
    })
    expect(wrapper.find('.performance-panel').exists()).toBe(true)
    expect(wrapper.findAll('.metric-card').length).toBe(12)
  })
})
