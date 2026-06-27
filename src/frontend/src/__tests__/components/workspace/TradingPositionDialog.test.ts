import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import TradingPositionDialog from '@/components/workspace/TradingPositionDialog.vue'
import { elStubs } from '@/test/stubs'
import type { StrategyUnit, TradingSnapshot } from '@/types/workspace'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: ref('zh-CN') }),
}))

describe('TradingPositionDialog', () => {
  const snapshot: TradingSnapshot = {
    instance_id: null,
    instance_status: 'running',
    mode: 'live',
    error: null,
    started_at: null,
    stopped_at: null,
    gateway_summary: null,
    long_position: 0.00004,
    short_position: 0,
    today_pnl: null,
    position_pnl: 0.0004,
    latest_price: 60010,
    change_pct: null,
    long_market_value: 0.0056649,
    short_market_value: 0,
    leverage: null,
    cumulative_pnl: null,
    max_drawdown_rate: null,
    trading_day: null,
    updated_at: null,
    detail_route: null,
    positions: [
      {
        data_name: 'BTC-USDT-SWAP',
        direction: 'long',
        size: 0.00004,
        price: 60000,
        current_price: 60010,
        market_value: 0.0056649,
        pnl: null,
        position_pnl: 0.0004,
      },
    ],
    trades: [],
  }

  const unit: StrategyUnit = {
    id: 'unit-1',
    workspace_id: 'workspace-1',
    group_name: 'default',
    strategy_id: null,
    strategy_name: 'Micro Unit',
    symbol: 'BTC-USDT-SWAP',
    symbol_name: 'BTC swap',
    timeframe: '1m',
    timeframe_n: 1,
    category: 'test',
    sort_order: 0,
    data_config: {},
    unit_settings: {},
    params: {},
    optimization_config: {},
    trading_mode: 'live',
    gateway_config: {},
    lock_trading: false,
    lock_running: false,
    trading_instance_id: null,
    trading_snapshot: snapshot,
    run_status: 'running',
    run_count: 0,
    last_run_time: null,
    last_task_id: null,
    last_optimization_task_id: null,
    bar_count: null,
    metrics_snapshot: {},
    created_at: '2026-06-26T00:00:00Z',
    updated_at: '2026-06-26T00:00:00Z',
  }

  const mountDialog = (dialogUnit: StrategyUnit = unit) => mount(TradingPositionDialog, {
    props: {
      modelValue: true,
      unit: dialogUnit,
    },
    global: { stubs: elStubs },
  })

  it('preserves micro quantities and small valuation values', () => {
    const vm = mountDialog().vm as any

    expect(vm.formatQuantity(0.00004)).toBe('0.00004')
    expect(vm.formatAmount(0.0056649)).toBe('0.005665')
    expect(vm.formatSignedAmount(0.0004)).toBe('+0.0004')
  })

  it('falls back across common position PnL fields', () => {
    const vm = mountDialog().vm as any

    expect(vm.positionPnl({ pnlcomm: 1.2, pnl: 2.3, position_pnl: 3.4 })).toBe(1.2)
    expect(vm.positionPnl({ net_pnl: 3.5, position_pnl: 3.4, pnl: 2.3 })).toBe(3.5)
    expect(vm.positionPnl({ pnl: 2.3, position_pnl: 3.4 })).toBe(3.4)
    expect(vm.positionPnl({ pnl: 2.3, net_pnl: 3.5 })).toBe(3.5)
    expect(vm.positionPnl({ position_pnl: 3.4 })).toBe(3.4)
    expect(vm.positionPnl({ gross_pnl: 4.5 })).toBe(4.5)
  })

  it('filters flat exchange alias rows and keeps nonzero alias positions', () => {
    const aliasedSnapshot = {
      ...snapshot,
      positions: [
        {
          data_name: 'BTC-USDT-SWAP',
          direction: 'long',
          size: 0,
          price: 60000,
          current_price: 60010,
          market_value: 0,
          pnl: null,
          position_pnl: 999,
          long_position: 0,
          short_position: 0,
        },
        {
          data_name: 'ETH-USDT-SWAP',
          direction: 'long',
          size: 0,
          price: 3000,
          current_price: 3001,
          market_value: 0,
          pnl: null,
          position_pnl: 888,
          positionAmt: '0',
        },
        {
          data_name: 'IF2609',
          direction: 'long',
          size: 0,
          price: 5000,
          current_price: 5001,
          market_value: 1500300,
          pnl: null,
          position_pnl: 265.5,
          Position: '1',
        },
      ] as any,
    }
    const wrapper = mountDialog({
      ...unit,
      trading_snapshot: aliasedSnapshot,
    })
    const vm = wrapper.vm as any

    expect(vm.positions).toHaveLength(1)
    expect(vm.positions[0].data_name).toBe('IF2609')
  })
})
