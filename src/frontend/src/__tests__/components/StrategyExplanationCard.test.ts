import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StrategyExplanationCard from '@/components/backtest/StrategyExplanationCard.vue'
import { elStubs } from '@/test/stubs'
import type { StrategyExplanation } from '@/api/strategy'

const explanation: StrategyExplanation = {
  code_hash: 'abc123',
  strategy_name: '双均线策略',
  summary: '双均线策略通过快慢均线交叉识别趋势。',
  indicators_explanation: '使用 SMA 和 CrossOver 判断趋势。',
  entry_explanation: '快线上穿慢线时买入。',
  exit_explanation: '快线下穿慢线时卖出。',
  params_explanation: 'fast_period 控制快线周期。',
  market_fit: '适合趋势市场。',
  risk_notes: ['震荡市场可能频繁假信号'],
  ast: {
    parsable: true,
    indicators: [{ name: 'SMA', alias: 'fast_ma', params: { period: 'self.p.fast_period' } }],
    entry_signals: [{ condition: 'self.crossover[0] > 0', side: 'buy' }],
    exit_signals: [{ condition: 'self.crossover[0] < 0', side: 'sell' }],
    risk_controls: [{ type: 'position_size', value: 10, source: '10' }],
    params: [{ name: 'fast_period', default: 5 }],
    data_sources: ['close'],
    raw_code: null,
    parse_error: null,
  },
  reason_code: 'static_fallback',
  model_id: null,
  cached: false,
  disclaimer: '解释仅供研究参考，不构成投资建议。',
}

describe('StrategyExplanationCard', () => {
  it('renders six explanation sections and static analysis evidence', () => {
    const wrapper = mount(StrategyExplanationCard, {
      props: { explanation },
      global: { stubs: elStubs },
    })

    const text = wrapper.text()
    expect(text).toContain('策略解释')
    expect(text).toContain('双均线策略通过快慢均线交叉识别趋势')
    expect(text).toContain('指标说明')
    expect(text).toContain('买入逻辑')
    expect(text).toContain('卖出逻辑')
    expect(text).toContain('参数说明')
    expect(text).toContain('市场适配')
    expect(text).toContain('SMA')
    expect(text).toContain('信号示意')
    expect(text).toContain('self.crossover[0] > 0')
    expect(text).toContain('仓位/风控')
    expect(text).toContain('position_size')
    expect(text).toContain('震荡市场可能频繁假信号')
  })
})
