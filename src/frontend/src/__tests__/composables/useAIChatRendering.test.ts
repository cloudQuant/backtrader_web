import { describe, expect, it } from 'vitest'

import type { KBStrategyDraft } from '@/api/kbChat'
import { getStrategyDraftIssue } from '@/composables/useAIChatRendering'

const COMPLETE_STRATEGY_CODE = [
  'import backtrader as bt',
  '',
  'class Demo(bt.Strategy):',
  '    params = (("fast_period", 10), ("slow_period", 30))',
  '',
  '    def __init__(self):',
  '        self.fast_ma = bt.ind.SMA(self.datas[0].close, period=self.p.fast_period)',
  '        self.slow_ma = bt.ind.SMA(self.datas[0].close, period=self.p.slow_period)',
  '        self.cross = bt.ind.CrossOver(self.fast_ma, self.slow_ma)',
  '',
  '    def next(self):',
  '        if not self.position and self.cross > 0:',
  '            self.buy()',
  '        elif self.position and self.cross < 0:',
  '            self.close()',
].join('\n')

function buildDraft(code: string): KBStrategyDraft {
  return {
    name: 'AI策略 - 双均线',
    description: '一个测试策略草案',
    code,
    params: {
      fast_period: { type: 'int', default: 10 },
      slow_period: { type: 'int', default: 30 },
    },
    category: 'trend',
    assumptions: ['默认使用 OHLCV 数据'],
    risk_points: ['需要验证样本外稳定性'],
    data_source: {
      type: 'csv',
      symbol: null,
      symbol_name: null,
      timeframe: '1d',
      timeframe_n: 1,
      start_date: null,
      end_date: null,
      adjustment: null,
    },
    backtest_defaults: {
      initial_cash: 100000,
      commission: 0.001,
      annual_days: 252,
      calc_method: 'simple',
      weight_mode: 'equal',
    },
    execution_plan: {
      workspace_type: 'research',
      group_name: 'AI策略 - 双均线',
      run_parallel: false,
    },
    rationale: '用于测试',
    next_steps: ['回测验证', '策略审查'],
    suggested_symbol: null,
    suggested_timeframe: '1d',
  }
}

describe('getStrategyDraftIssue', () => {
  it('allows complete runnable code even if a comment mentions pass', () => {
    const code = `${COMPLETE_STRATEGY_CODE}\n        # death cross branch does not use pass`

    expect(getStrategyDraftIssue(buildDraft(code))).toBeNull()
  })

  it('rejects a real pass statement in strategy code', () => {
    const code = COMPLETE_STRATEGY_CODE.replace('            self.buy()', '            pass')

    expect(getStrategyDraftIssue(buildDraft(code))).not.toBeNull()
  })

  it('rejects strategy code without an actual trading action', () => {
    const code = COMPLETE_STRATEGY_CODE
      .replace('            self.buy()', '            signal = True')
      .replace('            self.close()', '            signal = False')

    expect(getStrategyDraftIssue(buildDraft(code))).not.toBeNull()
  })
})
