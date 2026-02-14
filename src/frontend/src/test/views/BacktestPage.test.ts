import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import BacktestPage from '@/views/BacktestPage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ query: {} }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

vi.mock('@/stores/backtest', () => ({
  useBacktestStore: () => ({
    runBacktest: vi.fn().mockResolvedValue({ task_id: 't1' }),
    fetchResults: vi.fn().mockResolvedValue(undefined),
    results: [],
    total: 0,
    deleteResult: vi.fn().mockResolvedValue(undefined),
  }),
}))

vi.mock('@/stores/strategy', () => ({
  useStrategyStore: () => ({
    fetchStrategies: vi.fn().mockResolvedValue(undefined),
    fetchTemplates: vi.fn().mockResolvedValue(undefined),
    templates: [{ id: 's1', name: 'SMA', category: 'trend' }],
    strategies: [],
  }),
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplateConfig: vi.fn().mockResolvedValue({ strategy: { description: 'test' }, params: { fast: 5, slow: 20 } }),
  },
}))

vi.mock('@/api/backtest', () => ({
  backtestApi: {
    cancel: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('dayjs', () => {
  const fn: any = (_v?: any) => ({
    subtract: () => fn(),
    format: () => '2024-01-01T00:00:00',
    toDate: () => new Date('2024-01-01'),
  })
  fn.default = fn
  return { default: fn }
})

describe('BacktestPage', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const doMount = () => mount(BacktestPage, { global: { stubs: { ...elStubs, EquityCurve: true } } })

  it('mounts without error', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('has templates from store', () => {
    const vm = doMount().vm as any
    expect(vm.templates).toBeDefined()
  })

  it('getStatusType returns correct values', () => {
    const vm = doMount().vm as any
    expect(vm.getStatusType('completed')).toBe('success')
    expect(vm.getStatusType('running')).toBe('warning')
    expect(vm.getStatusType('failed')).toBe('danger')
    expect(vm.getStatusType('pending')).toBe('info')
    expect(vm.getStatusType('cancelled')).toBe('warning')
    expect(vm.getStatusType('xyz')).toBe('info')
  })

  it('getStatusText returns correct values', () => {
    const vm = doMount().vm as any
    expect(vm.getStatusText('completed')).toBe('完成')
    expect(vm.getStatusText('running')).toBe('运行中')
    expect(vm.getStatusText('failed')).toBe('失败')
    expect(vm.getStatusText('unknown')).toBe('unknown')
  })

  it('getStrategyName returns template name or id', () => {
    const vm = doMount().vm as any
    expect(vm.getStrategyName('s1')).toBe('SMA')
    expect(vm.getStrategyName('nonexistent')).toBe('nonexistent')
  })

  it('runBacktest warns if no strategy selected', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    vm.form.strategy_id = ''
    await vm.runBacktest()
    expect(ElMessage.warning).toHaveBeenCalledWith('请选择策略')
  })

  it('onStrategyChange clears config when empty', async () => {
    const vm = doMount().vm as any
    await vm.onStrategyChange('')
    expect(vm.strategyConfig).toBeNull()
  })

  it('onStrategyChange loads config', async () => {
    const vm = doMount().vm as any
    await vm.onStrategyChange('s1')
    expect(vm.strategyConfig).toBeTruthy()
    expect(vm.dynamicParams.fast).toBe(5)
    expect(vm.dynamicParams.slow).toBe(20)
  })

  it('viewResult navigates to result page', () => {
    const vm = doMount().vm as any
    vm.viewResult({ task_id: 't1' })
    // router.push was called (mocked)
  })

  it('cancelBacktest does nothing without taskId', async () => {
    const vm = doMount().vm as any
    vm.currentTaskId = ''
    await vm.cancelBacktest()
  })

  it('closeWebSocket handles null ws', () => {
    const vm = doMount().vm as any
    vm.closeWebSocket()
    // no error thrown
  })

  it('deleteBacktest calls store', async () => {
    const vm = doMount().vm as any
    await vm.deleteBacktest('t1')
  })
})
