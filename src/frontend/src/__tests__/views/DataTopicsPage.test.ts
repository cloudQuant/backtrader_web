import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DataTopicsPage from '@/views/data/DataTopicsPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  listTopics: vi.fn(),
  refreshTopic: vi.fn(),
  getStats: vi.fn(),
  buildTopicStreamUrl: vi.fn((topic: string) => `ws://test/${topic}`),
  buildPatternStreamUrl: vi.fn((pattern: string) => `ws://test?pattern=${pattern}`),
  getWebSocketProtocols: vi.fn(() => ['access-token', 'token']),
}))

const authStoreState = vi.hoisted(() => ({
  user: { is_admin: true },
}))

vi.mock('@/api/dataTopics', () => ({
  dataTopicsApi: apiMocks,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => authStoreState,
}))

describe('DataTopicsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authStoreState.user = { is_admin: true }
    apiMocks.listTopics.mockResolvedValue({
      items: [
        {
          topic: 'market:quote:RB2510',
          has_value: true,
          updated_at_ms: 123,
          policy: { ttl_ms: 200 },
          subscription_count: 1,
          last_error: null,
        },
      ],
      total: 1,
    })
    apiMocks.refreshTopic.mockResolvedValue({ topic: 'market:quote:RB2510', value: { symbol: 'RB2510', price: 101 } })
    apiMocks.getStats.mockResolvedValue({
      total_topics: 1,
      topics_with_value: 1,
      subscription_count: 1,
      error_count: 0,
      ws_gateway: { connection_count: 1, subscription_count: 1 },
    })
  })

  it('loads topics, stats, and refreshes selected topic', async () => {
    const wrapper = mountWithPlugins(DataTopicsPage)
    expect(wrapper.text()).toContain('Data Topic Hub')

    await flushPromises()
    await (wrapper.vm as any).refreshSelectedTopic()
    await flushPromises()

    expect(apiMocks.listTopics).toHaveBeenCalled()
    expect(apiMocks.getStats).toHaveBeenCalled()
    expect(apiMocks.refreshTopic).toHaveBeenCalledWith('market:quote:RB2510')
    expect(wrapper.text()).toContain('market:quote:RB2510')
    expect(wrapper.text()).toContain('RB2510')
  })

  it('skips admin stats for non-admin users', async () => {
    authStoreState.user = { is_admin: false }

    mountWithPlugins(DataTopicsPage)
    await flushPromises()

    expect(apiMocks.listTopics).toHaveBeenCalled()
    expect(apiMocks.getStats).not.toHaveBeenCalled()
  })
})
