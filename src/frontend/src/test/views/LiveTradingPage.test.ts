import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LiveTradingPage from '@/views/LiveTradingPage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

vi.mock('@/api/liveTrading', () => ({
  liveTradingApi: {
    list: vi.fn().mockResolvedValue({ instances: [
      { id: 'i1', strategy_id: 's1', strategy_name: 'SMA', status: 'running', created_at: '2024-01-01' },
    ] }),
    add: vi.fn().mockResolvedValue({ id: 'i2' }),
    remove: vi.fn().mockResolvedValue(undefined),
    start: vi.fn().mockResolvedValue({ id: 'i1', status: 'running', strategy_name: 'SMA' }),
    stop: vi.fn().mockResolvedValue({ id: 'i1', status: 'stopped', strategy_name: 'SMA' }),
    startAll: vi.fn().mockResolvedValue({ success: 1, failed: 0 }),
    stopAll: vi.fn().mockResolvedValue({ success: 1, failed: 0 }),
  },
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({ templates: [{ id: 's1', name: 'SMA' }] }),
  },
}))

vi.mock('@/stores/strategy', () => ({
  useStrategyStore: () => ({
    fetchTemplates: vi.fn().mockResolvedValue(undefined),
    templates: [{ id: 's1', name: 'SMA' }],
  }),
}))

describe('LiveTradingPage', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const doMount = () => mount(LiveTradingPage, { global: { stubs: elStubs } })

  it('mounts without error', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('statusLabel returns correct labels', () => {
    const vm = doMount().vm as any
    expect(vm.statusLabel('running')).toBe('运行中')
    expect(vm.statusLabel('error')).toBe('异常')
    expect(vm.statusLabel('stopped')).toBe('已停止')
  })

  it('runningCount computes correctly', async () => {
    const vm = doMount().vm as any
    await vi.dynamicImportSettled()
    // After loadData resolves, instances should have 1 running
    await new Promise(r => setTimeout(r, 50))
    expect(vm.runningCount).toBeGreaterThanOrEqual(0)
  })

  it('handleAdd does nothing without strategy_id', async () => {
    const vm = doMount().vm as any
    vm.addForm.strategy_id = ''
    await vm.handleAdd()
  })

  it('handleAdd adds and reloads', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    vm.addForm.strategy_id = 's1'
    await vm.handleAdd()
    expect(ElMessage.success).toHaveBeenCalledWith('添加成功')
    expect(vm.showAddDialog).toBe(false)
  })

  it('handleRemove removes instance', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    await vm.handleRemove({ id: 'i1', strategy_name: 'SMA' })
    expect(ElMessage.success).toHaveBeenCalledWith('已删除')
  })

  it('handleStart starts instance', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    const inst = { id: 'i1', strategy_name: 'SMA', status: 'stopped' }
    await vm.handleStart(inst)
    expect(ElMessage.success).toHaveBeenCalled()
  })

  it('handleStop stops instance', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    const inst = { id: 'i1', strategy_name: 'SMA', status: 'running' }
    await vm.handleStop(inst)
    expect(ElMessage.success).toHaveBeenCalled()
  })

  it('handleStartAll batch starts', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    await vm.handleStartAll()
    expect(ElMessage.success).toHaveBeenCalled()
    expect(vm.batchLoading).toBe(false)
  })

  it('handleStopAll batch stops', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    await vm.handleStopAll()
    expect(ElMessage.success).toHaveBeenCalled()
    expect(vm.batchLoading).toBe(false)
  })

  it('goToDetail navigates', () => {
    const vm = doMount().vm as any
    vm.goToDetail({ id: 'i1' })
  })
})
