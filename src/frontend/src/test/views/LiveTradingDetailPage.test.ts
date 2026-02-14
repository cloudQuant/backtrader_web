import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LiveTradingDetailPage from '@/views/LiveTradingDetailPage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  useRoute: () => ({ params: { id: 'i1' } }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/api/liveTrading', () => ({
  liveTradingApi: {
    get: vi.fn().mockResolvedValue({
      id: 'i1', strategy_id: 's1', strategy_name: 'SMA', status: 'running',
      pid: 1234, error: null, params: {}, created_at: '2024-01-01',
      started_at: '2024-01-01', stopped_at: null, log_dir: null,
    }),
    start: vi.fn().mockResolvedValue({ id: 'i1', status: 'running' }),
    stop: vi.fn().mockResolvedValue({ id: 'i1', status: 'stopped' }),
  },
}))

describe('LiveTradingDetailPage', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('mounts without error', () => {
    const wrapper = mount(LiveTradingDetailPage, { global: { stubs: elStubs } })
    expect(wrapper.exists()).toBe(true)
  })
})
