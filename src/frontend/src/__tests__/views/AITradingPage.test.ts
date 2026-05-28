import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

import AITradingPage from '@/views/AITradingPage.vue'
import { mountWithPlugins } from '@/test/mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  executeTrade: vi.fn(),
  confirmTrade: vi.fn(),
  getTradingConfig: vi.fn(),
  getTradingHistory: vi.fn(),
}))

const messageMocks = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}))

const confirmMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/aiTrading', () => ({
  executeTrade: apiMocks.executeTrade,
  confirmTrade: apiMocks.confirmTrade,
  getTradingConfig: apiMocks.getTradingConfig,
  getTradingHistory: apiMocks.getTradingHistory,
}))

vi.mock('element-plus', () => ({
  ElMessage: messageMocks,
  ElMessageBox: {
    confirm: confirmMock,
  },
}))

function buildResponse(overrides: Record<string, unknown> = {}) {
  return {
    trade_id: 'trade-1',
    intent: {
      action: 'buy',
      symbol: 'RB2510',
      exchange: 'SHFE',
      quantity: 1,
      price: 3500,
      order_type: 'limit',
      stop_loss: null,
      take_profit: null,
      reason: 'test',
      confidence: 0.82,
      risk_level: 'medium',
      raw_input: '买入1手螺纹钢主力合约',
    },
    risk_assessment: {
      approved: true,
      risk_level: 'medium',
      warnings: ['注意滑点'],
      blocked_reasons: [],
      requires_confirmation: false,
      max_loss_estimate: 200,
      position_impact: 'small',
    },
    status: 'pending_confirmation',
    message: '解析完成',
    execution_result: null,
    ai_reasoning: '基于策略建议执行',
    suggestions: ['建议分批成交'],
    requires_confirmation: false,
    degraded: false,
    diagnostic_message: null,
    ...overrides,
  }
}

describe('AITradingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.getTradingConfig.mockResolvedValue({
      enabled: true,
      default_mode: 'paper',
      max_single_trade_amount: 100000,
      max_daily_trades: 20,
      max_position_ratio: 0.2,
      require_confirmation_above: 0.7,
      blocked_symbols: [],
      available_gateways: [
        {
          gateway_id: 'gw-1',
          exchange_type: 'binance',
          account_id: 'live-1',
          connected: true,
        },
      ],
      available_accounts: [
        {
          account_id: 'paper-1',
          name: '模拟账户A',
          total_equity: 100000,
          current_cash: 80000,
          is_active: true,
        },
      ],
    })
    apiMocks.getTradingHistory.mockResolvedValue({
      total: 1,
      items: [
        {
          trade_id: 'history-1',
          user_input: '买入 1 手 RB2510',
          action: 'buy',
          symbol: 'RB2510',
          quantity: 1,
          price: 3500,
          status: 'confirmed',
          confidence: 0.75,
          risk_level: 'medium',
          ai_reasoning: '已有成交记录',
          dry_run: true,
          created_at: '2026-01-01T08:00:00Z',
          executed_at: '2026-01-01T08:01:00Z',
        },
      ],
    })
    apiMocks.executeTrade.mockResolvedValue(buildResponse())
    apiMocks.confirmTrade.mockResolvedValue({
      trade_id: 'trade-1',
      status: 'confirmed',
      message: '已确认执行',
    })
    confirmMock.mockResolvedValue(undefined)
  })

  it('loads config and history, then executes a dry-run trade', async () => {
    const wrapper = mountWithPlugins(AITradingPage, {
      customStubs: {
        Promotion: true,
        Warning: true,
        Document: true,
      },
    })

    await flushPromises()

    expect(apiMocks.getTradingConfig).toHaveBeenCalledTimes(1)
    expect(apiMocks.getTradingHistory).toHaveBeenCalledWith(20)
    expect(wrapper.text()).toContain('自然语言交易')
    expect(wrapper.text()).toContain('买入 1 手 RB2510')

    const vm = wrapper.vm as any
    vm.message = '买入1手螺纹钢主力合约'

    await vm.handleSend()
    await flushPromises()

    expect(apiMocks.executeTrade).toHaveBeenCalledWith({
      message: '买入1手螺纹钢主力合约',
      gateway_id: undefined,
      account_id: 'paper-1',
      dry_run: true,
      auto_confirm: false,
    })
    expect(vm.currentResponse.trade_id).toBe('trade-1')
    expect(vm.responses).toHaveLength(1)
  })

  it('confirms and cancels pending trades through the dialog flow', async () => {
    const wrapper = mountWithPlugins(AITradingPage, {
      customStubs: {
        Promotion: true,
        Warning: true,
        Document: true,
      },
    })

    await flushPromises()

    const vm = wrapper.vm as any
    const response = buildResponse({ trade_id: 'trade-2', requires_confirmation: true })

    await vm.handleConfirmDialog(response)
    await flushPromises()

    expect(apiMocks.confirmTrade).toHaveBeenCalledWith({
      trade_id: 'trade-2',
      confirmed: true,
    })
    expect(messageMocks.success).toHaveBeenCalledWith('已确认执行')

    confirmMock.mockRejectedValueOnce('cancel')
    await vm.handleConfirmDialog(response)
    await flushPromises()

    expect(apiMocks.confirmTrade).toHaveBeenLastCalledWith({
      trade_id: 'trade-2',
      confirmed: false,
    })
    expect(messageMocks.info).toHaveBeenCalledWith('交易已取消')
  })
})
