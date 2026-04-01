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
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    document.body.innerHTML = '<div id="page-header-actions"></div>'
  })

  const doMount = () => mount(GatewayStatusPage, { attachTo: document.body, global: { stubs: elStubs } })

  it('mounts without error', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('renders gateway status header actions into page header target', async () => {
    const wrapper = doMount()
    await vi.dynamicImportSettled()
    await new Promise(r => setTimeout(r, 50))
    const headerActions = document.getElementById('page-header-actions')
    expect(headerActions?.textContent || '').toContain('连接 Gateway')
    expect(headerActions?.textContent || '').toContain('刷新')
    expect(wrapper.text()).not.toContain('连接 Gateway')
  })

  it('computes healthyCount', async () => {
    const vm = doMount().vm as any
    await vi.dynamicImportSettled()
    await new Promise(r => setTimeout(r, 50))
    expect(vm.healthyCount).toBeGreaterThanOrEqual(0)
  })
})
