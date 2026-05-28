import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OverfittingPanel from '@/components/backtest/OverfittingPanel.vue'
import { elStubs } from '@/test/stubs'
import type { StrategyOverfittingTaskResult } from '@/api/strategy'

const result: StrategyOverfittingTaskResult = {
  task_id: 'ot-1',
  backtest_id: 'bt-1',
  status: 'completed',
  overall_level: 'low',
  robustness_score: 82,
  summary: '检测完成。',
  methods: [
    {
      method: 'monte_carlo',
      status: 'completed',
      risk_level: 'low',
      score: 82,
      explanation: 'Monte Carlo 稳健。',
      metrics: {
        actual_compound_return_pct: 12.3456,
        bootstrap_percentile: 96,
        iterations: 300,
        bootstrap_distribution_pct: [-4, 1, 5, 9, 12],
      },
      degraded: false,
    },
    {
      method: 'walk_forward',
      status: 'completed',
      risk_level: 'medium',
      score: 61,
      explanation: 'Walk-forward 有一定衰减。',
      metrics: {
        window_count: 3,
        avg_is_sharpe: 1.6,
        avg_oos_sharpe: 0.9,
        sharpe_decay_pct: 43.75,
        return_decay_pct: 30.1,
        windows: [
          { train_start: '2020-01-01', test_start: '2020-07-01', is_sharpe: 1.6, oos_sharpe: 1.1 },
          { train_start: '2020-03-01', test_start: '2020-09-01', is_sharpe: 1.7, oos_sharpe: 0.9 },
        ],
      },
      degraded: false,
    },
    {
      method: 'out_of_sample',
      status: 'completed',
      risk_level: 'high',
      score: 42,
      explanation: '样本外表现较弱。',
      metrics: {
        is_sharpe: 1.8,
        oos_sharpe: 0.7,
        sharpe_decay_pct: 61.11,
        return_decay_pct: 70,
        p_value: 0.08,
        is_annual_return: 18,
        oos_annual_return: 6,
      },
      degraded: false,
    },
  ],
  error_message: null,
}

describe('OverfittingPanel', () => {
  it('emits rerun with selected methods', async () => {
    const wrapper = mount(OverfittingPanel, {
      props: { result },
      global: { stubs: elStubs },
    })

    const button = wrapper.findAll('button').find((item) => item.text().includes('重新检测'))
    expect(button).toBeTruthy()
    await button?.trigger('click')

    expect(wrapper.emitted('rerun')?.[0]).toEqual([
      ['walk_forward', 'out_of_sample', 'monte_carlo'],
    ])
  })

  it('updates selected methods before rerun', async () => {
    const wrapper = mount(OverfittingPanel, {
      props: { result },
      global: { stubs: elStubs },
    })

    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    await checkboxes[0].setValue(false)
    const button = wrapper.findAll('button').find((item) => item.text().includes('重新检测'))
    await button?.trigger('click')

    expect(wrapper.emitted('rerun')?.[0]).toEqual([
      ['out_of_sample', 'monte_carlo'],
    ])
  })

  it('renders curated evidence cards for each method', () => {
    const wrapper = mount(OverfittingPanel, {
      props: { result },
      global: { stubs: elStubs },
    })

    const text = wrapper.text()
    expect(text).toContain('实际复合收益')
    expect(text).toContain('Bootstrap 分位')
    expect(text).toContain('96.00%')
    expect(text).toContain('窗口数')
    expect(text).toContain('Sharpe 衰减')
    expect(text).toContain('p-value')
  })

  it('renders method tabs and evidence visualization', async () => {
    const wrapper = mount(OverfittingPanel, {
      props: { result },
      global: { stubs: elStubs },
    })

    expect(wrapper.text()).toContain('检测方法图表')
    expect(wrapper.find('[data-test="overfitting-chart-walk_forward"]').exists()).toBe(true)

    await wrapper.find('[data-test="method-tab-monte_carlo"]').trigger('click')

    expect(wrapper.find('[data-test="overfitting-chart-monte_carlo"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('随机分布')
  })
})
