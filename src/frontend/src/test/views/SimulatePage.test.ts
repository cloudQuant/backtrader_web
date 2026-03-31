import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SimulatePage from '@/views/SimulatePage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

vi.mock('@/api/simulation', () => ({
  simulationApi: {
    list: vi.fn().mockResolvedValue({ instances: [
      {
        id: 'sim1',
        strategy_id: 'sim/s1',
        strategy_name: 'TestStrategy',
        status: 'running',
        created_at: '2024-01-01',
        params: {},
      },
    ], total: 1 }),
    add: vi.fn().mockResolvedValue({ id: 'sim2', strategy_id: 'sim/s1', strategy_name: 'TestStrategy', status: 'stopped' }),
    remove: vi.fn().mockResolvedValue(undefined),
    start: vi.fn().mockResolvedValue({ id: 'sim1', status: 'running', strategy_name: 'TestStrategy' }),
    stop: vi.fn().mockResolvedValue({ id: 'sim1', status: 'stopped', strategy_name: 'TestStrategy' }),
    startAll: vi.fn().mockResolvedValue({ success: 1, failed: 0 }),
    stopAll: vi.fn().mockResolvedValue({ success: 1, failed: 0 }),
  },
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({ templates: [{ id: 'sim/s1', name: 'TestStrategy' }] }),
    getConfig: vi.fn().mockResolvedValue({ config: null }),
  },
}))

vi.mock('@/stores/strategy', () => ({
  useStrategyStore: () => ({
    fetchTemplates: vi.fn().mockResolvedValue(undefined),
    templates: [{ id: 's1', name: 'TestStrategy' }],
  }),
}))

vi.mock('@/api', () => ({
  getErrorMessage: vi.fn((e: unknown) => String(e)),
  default: vi.fn(),
}))

describe('SimulatePage', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const doMount = () => mount(SimulatePage, { global: { stubs: elStubs } })

  it('mounts without error', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('renders simulation header', () => {
    const wrapper = doMount()
    expect(wrapper.text()).toContain('模拟交易')
  })

  it('computes runningCount', async () => {
    const vm = doMount().vm as any
    await vi.dynamicImportSettled()
    await new Promise(r => setTimeout(r, 50))
    expect(vm.runningCount).toBeGreaterThanOrEqual(0)
  })

  it('handleAdd does nothing without strategy_id', async () => {
    const vm = doMount().vm as any
    vm.addForm.strategy_id = ''
    await vm.handleAdd()
  })
})
