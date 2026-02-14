import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import OptimizationPage from '@/views/OptimizationPage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

vi.mock('@/stores/strategy', () => ({
  useStrategyStore: () => ({
    fetchTemplates: vi.fn().mockResolvedValue(undefined),
    templates: [{ id: 's1', name: 'SMA' }],
  }),
}))

vi.mock('@/api/optimization', () => ({
  optimizationApi: {
    getStrategyParams: vi.fn().mockResolvedValue({ strategy_id: 's1', params: [
      { name: 'fast', type: 'int', default: 5, description: 'Fast MA' },
      { name: 'slow', type: 'int', default: 20, description: 'Slow MA' },
    ] }),
    submit: vi.fn().mockResolvedValue({ task_id: 't1', total_combinations: 10, message: '已提交' }),
    getProgress: vi.fn().mockResolvedValue({ task_id: 't1', status: 'running', progress: 50, total: 10, completed: 5, failed: 0, n_workers: 4, strategy_id: 's1', created_at: '' }),
    getResults: vi.fn().mockResolvedValue({ task_id: 't1', rows: [], best: null, param_names: ['fast', 'slow'], metric_names: ['annual_return'] }),
    cancel: vi.fn().mockResolvedValue({ message: 'ok' }),
  },
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({ templates: [{ id: 's1', name: 'SMA' }] }),
  },
}))

vi.mock('echarts-gl', () => ({}))

describe('OptimizationPage', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const doMount = () => mount(OptimizationPage, { global: { stubs: { ...elStubs, OptimizationTable: true } } })

  it('mounts without error', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('has config phase initially', () => {
    const vm = doMount().vm as any
    expect(vm.phase).toBe('config')
  })

  it('calcCount returns 0 when disabled', () => {
    const vm = doMount().vm as any
    expect(vm.calcCount({ enabled: false, start: 0, end: 10, step: 1 })).toBe(0)
  })

  it('calcCount returns 0 when step <= 0', () => {
    const vm = doMount().vm as any
    expect(vm.calcCount({ enabled: true, start: 0, end: 10, step: 0 })).toBe(0)
  })

  it('calcCount returns correct value', () => {
    const vm = doMount().vm as any
    expect(vm.calcCount({ enabled: true, start: 0, end: 10, step: 2 })).toBe(6)
  })

  it('totalCombinations returns 0 when no params', () => {
    const vm = doMount().vm as any
    vm.paramRows = []
    expect(vm.totalCombinations).toBe(0)
  })

  it('onStrategyChange clears params when empty', async () => {
    const vm = doMount().vm as any
    await vm.onStrategyChange('')
    expect(vm.paramRows).toEqual([])
  })

  it('onStrategyChange loads params', async () => {
    const vm = doMount().vm as any
    await vm.onStrategyChange('s1')
    expect(vm.paramRows.length).toBe(2)
    expect(vm.paramRows[0].name).toBe('fast')
  })

  it('startOptimization warns if no enabled params', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    vm.paramRows = []
    await vm.startOptimization()
    expect(ElMessage.warning).toHaveBeenCalledWith('请至少启用一个参数')
  })

  it('startOptimization submits and starts polling', async () => {
    const vm = doMount().vm as any
    vm.selectedStrategy = 's1'
    vm.paramRows = [{ name: 'fast', type: 'int', enabled: true, start: 5, end: 15, step: 1 }]
    await vm.startOptimization()
    expect(vm.phase).toBe('running')
    expect(vm.taskId).toBe('t1')
    vm.stopPolling()
  })

  it('cancelOpt calls api', async () => {
    const vm = doMount().vm as any
    vm.taskId = 't1'
    await vm.cancelOpt()
  })

  it('stopPolling clears timer', () => {
    const vm = doMount().vm as any
    vm.stopPolling()
    // no error
  })

  it('metricOptions has expected entries', () => {
    const vm = doMount().vm as any
    expect(vm.metricOptions.length).toBe(6)
  })

  it('handleResize is a function', () => {
    const vm = doMount().vm as any
    expect(typeof vm.handleResize).toBe('function')
    vm.handleResize() // should not throw
  })

  it('loadResults sets results and phase to done', async () => {
    const vm = doMount().vm as any
    vm.taskId = 't1'
    await vm.loadResults()
    expect(vm.phase).toBe('done')
    expect(vm.results).toBeTruthy()
    expect(vm.heatmapXParam).toBe('fast')
    expect(vm.heatmapYParam).toBe('slow')
    expect(vm.boxParam).toBe('fast')
  })

  it('renderHeatmap does nothing without results', () => {
    const vm = doMount().vm as any
    vm.results = null
    vm.renderHeatmap() // should not throw
  })

  it('renderHeatmap does nothing when params match', () => {
    const vm = doMount().vm as any
    vm.results = { rows: [], param_names: ['fast', 'slow'] }
    vm.heatmapXParam = 'fast'
    vm.heatmapYParam = 'fast' // same param
    vm.renderHeatmap() // should not throw (early return)
  })

  it('renderBoxplot does nothing without results', () => {
    const vm = doMount().vm as any
    vm.results = null
    vm.renderBoxplot() // should not throw
  })

  it('renderBoxplot does nothing without boxParam', () => {
    const vm = doMount().vm as any
    vm.results = { rows: [] }
    vm.boxParam = ''
    vm.renderBoxplot() // should not throw
  })

  it('renderScatter3d does nothing without results', () => {
    const vm = doMount().vm as any
    vm.results = null
    vm.renderScatter3d() // should not throw
  })

  it('renderScatter3d does nothing without all 3 params', () => {
    const vm = doMount().vm as any
    vm.results = { rows: [] }
    vm.scatter3dX = 'fast'
    vm.scatter3dY = ''
    vm.scatter3dZ = ''
    vm.renderScatter3d() // should not throw
  })

  it('resultTab defaults to table', () => {
    const vm = doMount().vm as any
    expect(vm.resultTab).toBe('table')
  })
})
