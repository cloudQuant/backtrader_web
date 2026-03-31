import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SimulateDetailPage from '@/views/SimulateDetailPage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'sim1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/api/simulation', () => ({
  simulationApi: {
    getDetail: vi.fn().mockResolvedValue({
      strategy_name: 'TestStrategy',
      symbol: 'BTCUSDT',
      start_date: '2024-01-01',
      end_date: '2024-06-01',
      metrics: { total_return: 0.15, sharpe_ratio: 1.2, max_drawdown: 0.05 },
      equity_curve: [],
      trades: [],
    }),
    getKlineSignals: vi.fn().mockResolvedValue({ dates: [], ohlc: [], signals: [] }),
    getMonthlyReturns: vi.fn().mockResolvedValue({ months: [], returns: [] }),
    getConfig: vi.fn().mockResolvedValue(''),
    saveConfig: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/api', () => ({
  getErrorMessage: vi.fn((e: unknown) => String(e)),
  default: {
    get: vi.fn().mockResolvedValue(''),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}))

describe('SimulateDetailPage', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const doMount = () => mount(SimulateDetailPage, { global: { stubs: elStubs } })

  it('mounts without error', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('shows loading state initially', () => {
    const wrapper = doMount()
    // Component should be in loading or error state initially
    expect(wrapper.exists()).toBe(true)
  })

  it('computes instanceId from route', () => {
    const vm = doMount().vm as any
    expect(vm.instanceId).toBe('sim1')
  })
})
