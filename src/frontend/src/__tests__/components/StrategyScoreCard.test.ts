import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StrategyScoreCard from '@/components/backtest/StrategyScoreCard.vue'
import { elStubs } from '@/test/stubs'
import type { StrategyScoreResponse } from '@/api/strategy'

const score: StrategyScoreResponse = {
  backtest_id: 'bt-1',
  total_score: 78.5,
  level: 'A',
  model_version: 'v1',
  disclaimer: '评分仅供研究参考，不构成投资建议。',
  dimensions: [
    {
      key: 'profitability',
      label: '收益质量',
      score: 82,
      weight: 0.2,
      explanation: '收益质量较好。',
      sub_metrics: { annual_return: 0.18, sharpe_ratio: 1.6 },
      degraded: false,
    },
    {
      key: 'risk_control',
      label: '风险控制',
      score: 68,
      weight: 0.2,
      explanation: '回撤可控。',
      sub_metrics: { max_drawdown: -0.12 },
      degraded: false,
    },
  ],
}

describe('StrategyScoreCard', () => {
  it('renders radar visualization and expands dimension metrics', async () => {
    const wrapper = mount(StrategyScoreCard, {
      props: { score },
      global: { stubs: elStubs },
    })

    expect(wrapper.text()).toContain('维度雷达图')
    expect(wrapper.find('[data-test="score-radar-chart"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('annual_return')

    await wrapper.find('[data-test="dimension-profitability"]').trigger('click')

    expect(wrapper.text()).toContain('annual_return')
    expect(wrapper.text()).toContain('sharpe_ratio')
  })
})
