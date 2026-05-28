import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import GatewayStatusPage from '@/views/GatewayStatusPage.vue'
import { elStubs } from '@/test/stubs'

const liveTradingApiMocks = vi.hoisted(() => ({
  listGatewayHealth: vi.fn(),
  getGatewayCredentials: vi.fn(),
  connectGateway: vi.fn(),
  disconnectGateway: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@element-plus/icons-vue', () => ({
  Refresh: { template: '<span />' },
  Loading: { template: '<span />' },
  CircleCheckFilled: { template: '<span />' },
  CircleCloseFilled: { template: '<span />' },
  Connection: { template: '<span />' },
  Grid: { template: '<span />' },
  List: { template: '<span />' },
}))

vi.mock('@/api/liveTrading', () => ({
  liveTradingApi: {
    listGatewayHealth: liveTradingApiMocks.listGatewayHealth,
    getGatewayCredentials: liveTradingApiMocks.getGatewayCredentials,
    connectGateway: liveTradingApiMocks.connectGateway,
    disconnectGateway: liveTradingApiMocks.disconnectGateway,
  },
}))

function makeGateway(overrides: Record<string, unknown> = {}) {
  return {
    gateway_key: 'manual:CTP:088888',
    state: 'running',
    is_healthy: true,
    market_connection: 'connected',
    trade_connection: 'connected',
    uptime_sec: 120,
    last_heartbeat: Math.floor(Date.parse('2026-04-02T00:00:05.000Z') / 1000),
    heartbeat_age_sec: 5,
    last_tick_time: null,
    last_order_time: null,
    strategy_count: 1,
    symbol_count: 2,
    tick_count: 10,
    order_count: 1,
    recent_errors: [],
    ref_count: 1,
    instances: ['inst-1'],
    exchange: 'CTP',
    asset_type: 'FUTURE',
    account_id: '088888',
    ...overrides,
  }
}

async function flushUi() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

describe('GatewayStatusPage', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-02T00:00:10.000Z'))
    setActivePinia(createPinia())
    vi.clearAllMocks()
    document.body.innerHTML = '<div id="page-header-actions"></div>'
    liveTradingApiMocks.listGatewayHealth.mockResolvedValue({ total: 1, gateways: [makeGateway()] })
    liveTradingApiMocks.getGatewayCredentials.mockResolvedValue({})
    liveTradingApiMocks.connectGateway.mockResolvedValue({ message: 'ok' })
    liveTradingApiMocks.disconnectGateway.mockResolvedValue({ message: 'ok' })
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  const doMount = () => mount(GatewayStatusPage, { attachTo: document.body, global: { stubs: elStubs } })

  it('mounts without error', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('renders gateway status header actions into page header target', async () => {
    const wrapper = doMount()
    await flushUi()
    const headerActions = document.getElementById('page-header-actions')
    expect(headerActions?.textContent || '').toContain('连接 Gateway')
    expect(headerActions?.textContent || '').toContain('刷新')
    expect(wrapper.text()).not.toContain('连接 Gateway')
  })

  it('computes healthyCount', async () => {
    const vm = doMount().vm as any
    await flushUi()
    expect(vm.healthyCount).toBeGreaterThanOrEqual(0)
  })

  it('updates heartbeat latency locally between backend polls', async () => {
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await vm.fetchHealth()
    await flushUi()
    expect(vm.gateways).toHaveLength(1)
    expect(vm.formatHeartbeatAge(vm.gateways[0])).toBe('5s')

    liveTradingApiMocks.listGatewayHealth.mockClear()

    await vi.advanceTimersByTimeAsync(3_000)
    await flushUi()

    expect(vm.formatHeartbeatAge(vm.gateways[0])).toBe('8s')
    expect(liveTradingApiMocks.listGatewayHealth).not.toHaveBeenCalled()
  })
})
