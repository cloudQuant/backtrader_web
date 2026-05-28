import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import BrokerProfilesPage from '@/views/BrokerProfilesPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  listProfiles: vi.fn(),
  createProfile: vi.fn(),
  getHealth: vi.fn(),
  getAccounts: vi.fn(),
  getPositions: vi.fn(),
  getOrders: vi.fn(),
  getQuote: vi.fn(),
  enableWrite: vi.fn(),
}))

const authStoreState = vi.hoisted(() => ({
  user: { is_admin: true },
}))

vi.mock('@/api/brokerProfiles', () => ({
  brokerProfilesApi: apiMocks,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => authStoreState,
}))

describe('BrokerProfilesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authStoreState.user = { is_admin: true }
    apiMocks.listProfiles.mockResolvedValue({
      items: [
        {
          id: 'profile-1',
          broker_id: 'gateway_bridge',
          account_alias: 'sim-account',
          capabilities: ['health', 'accounts', 'quotes'],
          credentials_ref: { api_key_env: '***_KEY' },
          enabled: true,
          last_health: null,
          created_by: 'user-1',
          is_destructive_enabled: false,
          credentials_rotated_at: '2026-05-26T00:00:00+00:00',
          rotation_warning: 'credentials_rotation_overdue',
          runtime_gateway_key: 'manual:IB_WEB:DU123456',
          runtime_account_id: 'DU123456',
          runtime_binding: {
            gateway_key: 'manual:IB_WEB:DU123456',
            exchange_type: 'IB_WEB',
            account_id: 'DU123456',
            has_runtime: true,
          },
          created_at: '2026-05-26T00:00:00+00:00',
          updated_at: '2026-05-26T00:00:00+00:00',
        },
      ],
      total: 1,
    })
    apiMocks.createProfile.mockResolvedValue({ id: 'profile-1' })
    apiMocks.getHealth.mockResolvedValue({ adapter: 'gateway_bridge', connected: true })
    apiMocks.getAccounts.mockResolvedValue({ items: [{ account_id: 'sim-account', cash: 0 }], total: 1 })
    apiMocks.getPositions.mockResolvedValue({ items: [], total: 0 })
    apiMocks.getOrders.mockResolvedValue({ items: [], total: 0 })
    apiMocks.getQuote.mockResolvedValue({ symbol: 'RB2510', price: 0, provider: 'gateway_bridge' })
    apiMocks.enableWrite.mockResolvedValue({ id: 'profile-1', is_destructive_enabled: true })
  })

  it('loads profiles and inspects selected profile runtime data', async () => {
    const wrapper = mountWithPlugins(BrokerProfilesPage)
    expect(wrapper.text()).toContain('Broker Profiles')

    await flushPromises()
    await (wrapper.vm as any).createDemoProfile()
    await flushPromises()
    await (wrapper.vm as any).inspectProfile('profile-1')
    await flushPromises()

    expect(apiMocks.listProfiles).toHaveBeenCalled()
    expect(apiMocks.createProfile).toHaveBeenCalled()
    expect(apiMocks.getHealth).toHaveBeenCalledWith('profile-1')
    expect(apiMocks.getAccounts).toHaveBeenCalledWith('profile-1')
    expect(apiMocks.getPositions).toHaveBeenCalledWith('profile-1')
    expect(apiMocks.getOrders).toHaveBeenCalledWith('profile-1')
    expect(apiMocks.getQuote).toHaveBeenCalledWith('profile-1', 'RB2510')
    expect(wrapper.text()).toContain('sim-account')
    expect(wrapper.text()).toContain('RB2510')
  })

  it('only admin users can enable live write', async () => {
    const wrapper = mountWithPlugins(BrokerProfilesPage)
    await flushPromises()

    ;(wrapper.vm as any).enableWriteForm.confirmationText = 'ENABLE sim-account'
    await (wrapper.vm as any).enableLiveWrite('profile-1')
    await flushPromises()
    expect(apiMocks.enableWrite).toHaveBeenCalledWith('profile-1', {
      confirmation_text: 'ENABLE sim-account',
      idempotency_key: expect.any(String),
    })

    authStoreState.user = { is_admin: false }
    const nonAdminWrapper = mountWithPlugins(BrokerProfilesPage)
    await flushPromises()
    await (nonAdminWrapper.vm as any).enableLiveWrite('profile-1')
    await flushPromises()
    expect(apiMocks.enableWrite).toHaveBeenCalledTimes(1)
  })

  it('submits manual profile form payload and renders runtime binding warning state', async () => {
    const wrapper = mountWithPlugins(BrokerProfilesPage)
    await flushPromises()

    ;(wrapper.vm as any).form.broker_id = 'gateway_bridge'
    ;(wrapper.vm as any).form.account_alias = 'DU123456'
    ;(wrapper.vm as any).form.capabilitiesText = 'health, accounts, positions, orders, quotes'
    ;(wrapper.vm as any).form.apiKeyEnv = 'BT_BROKER_SIM_KEY'
    ;(wrapper.vm as any).form.apiSecretEnv = 'BT_BROKER_SIM_SECRET'
    ;(wrapper.vm as any).form.credentialsRotatedAt = '2026-02-01T00:00:00+00:00'
    ;(wrapper.vm as any).form.runtimeGatewayKey = 'manual:IB_WEB:DU123456'
    ;(wrapper.vm as any).form.runtimeAccountId = 'DU123456'

    await (wrapper.vm as any).submitCreateProfile()
    await flushPromises()

    expect(apiMocks.createProfile).toHaveBeenCalledWith({
      broker_id: 'gateway_bridge',
      account_alias: 'DU123456',
      capabilities: ['health', 'accounts', 'positions', 'orders', 'quotes'],
      credentials_ref: {
        api_key_env: 'BT_BROKER_SIM_KEY',
        api_secret_env: 'BT_BROKER_SIM_SECRET',
      },
      credentials_rotated_at: '2026-02-01T00:00:00+00:00',
      runtime_gateway_key: 'manual:IB_WEB:DU123456',
      runtime_account_id: 'DU123456',
    })
    expect(wrapper.text()).toContain('manual:IB_WEB:DU123456')
    expect(wrapper.text()).toContain('credentials_rotation_overdue')
  })

  it('requires matching confirmation phrase before enabling live write', async () => {
    const wrapper = mountWithPlugins(BrokerProfilesPage)
    await flushPromises()

    ;(wrapper.vm as any).enableWriteForm.confirmationText = 'WRONG'
    await (wrapper.vm as any).enableLiveWrite('profile-1')
    await flushPromises()

    expect(apiMocks.enableWrite).not.toHaveBeenCalled()
    expect((wrapper.vm as any).enableWriteError).toContain('ENABLE sim-account')
    expect(wrapper.text()).toContain('ENABLE sim-account')
  })
})
