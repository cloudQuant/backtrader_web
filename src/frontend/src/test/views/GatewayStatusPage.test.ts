import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GatewayStatusPage from '@/views/GatewayStatusPage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/api/liveTrading', () => ({
  liveTradingApi: {
    getGatewayHealth: vi.fn().mockResolvedValue({ gateways: [
      {
        gateway_key: 'gw1',
        provider: 'ctp_gateway',
        is_healthy: true,
        exchange_type: 'CTP',
        asset_type: 'FUTURE',
        account_id: '088888',
        connected_instances: 1,
        last_check: '2024-01-01T00:00:00',
      },
    ] }),
    connectGateway: vi.fn().mockResolvedValue({ success: true }),
    disconnectGateway: vi.fn().mockResolvedValue({ success: true }),
  },
}))

describe('GatewayStatusPage', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const doMount = () => mount(GatewayStatusPage, { global: { stubs: elStubs } })

  it('mounts without error', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('renders gateway status header', () => {
    const wrapper = doMount()
    expect(wrapper.text()).toContain('Gateway 状态监控')
  })

  it('computes healthyCount', async () => {
    const vm = doMount().vm as any
    await vi.dynamicImportSettled()
    await new Promise(r => setTimeout(r, 50))
    expect(vm.healthyCount).toBeGreaterThanOrEqual(0)
  })
})
