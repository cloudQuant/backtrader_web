import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PaperTradingDetailPage from '@/views/PaperTradingDetailPage.vue'
import { elStubs } from '@/test/stubs'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  getEquity: vi.fn(),
  getAlerts: vi.fn(),
  listRules: vi.fn(),
  pause: vi.fn(),
  decideHandoff: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { instanceId: 'paper-1' } }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

vi.mock('@/api', () => ({
  getErrorMessage: (reason: unknown, fallback: string) => (
    reason instanceof Error ? reason.message : fallback
  ),
}))

vi.mock('@/api/paperRuntime', () => ({
  paperRuntimeApi: apiMocks,
}))

describe('PaperTradingDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.get.mockResolvedValue({
      instance_id: 'paper-1',
      workspace_id: 'workspace-1',
      unit_id: 'unit-1',
      workspace_name: 'Paper workspace',
      unit_name: 'RB strategy',
      symbol: 'RB0',
      status: 'running',
      paused: false,
      positions: [{ data_name: 'RB0', size: 1 }],
      orders: [{ order_id: 'order-1', status: 'submitted' }],
      trades: [{ id: 'trade-1', pnlcomm: 10 }],
      signals: [{ symbol: 'RB0', signal: 'buy' }],
      latest_equity: { total_equity: 100000, cash: 90000 },
    })
    apiMocks.getEquity.mockResolvedValue({ points: [], sampled: false, sampling: 'none' })
    apiMocks.getAlerts.mockResolvedValue([])
    apiMocks.listRules.mockResolvedValue([])
  })

  it('shows loading first, then loads canonical detail and all runtime sections', async () => {
    const wrapper = mount(PaperTradingDetailPage, { global: { stubs: elStubs } })
    expect(wrapper.text()).toContain('查询中')

    await flushPromises()

    expect(apiMocks.get).toHaveBeenCalledWith('paper-1')
    expect(apiMocks.getEquity).toHaveBeenCalledWith('paper-1')
    expect(apiMocks.getAlerts).toHaveBeenCalledWith('paper-1')
    expect(apiMocks.listRules).toHaveBeenCalledWith('paper-1')
    expect(wrapper.text()).toContain('RB strategy')
    expect(wrapper.text()).toContain('当前持仓')
    expect(wrapper.text()).toContain('订单')
    expect(wrapper.text()).toContain('成交记录')
    expect(wrapper.text()).toContain('策略信号')
    expect(wrapper.text()).toContain('运行告警')
  })

  it('shows retryable error state when canonical detail is unavailable', async () => {
    apiMocks.get.mockRejectedValueOnce(new Error('runtime unavailable'))
    const wrapper = mount(PaperTradingDetailPage, { global: { stubs: elStubs } })

    await flushPromises()

    expect(wrapper.find('.el-result').exists()).toBe(true)
    expect((wrapper.vm as any).error).toBe('runtime unavailable')
  })
})
