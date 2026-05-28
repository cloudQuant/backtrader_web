import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import BacktestPage from '@/views/BacktestPage.vue'
import { elStubs } from '@/test/stubs'
import { getStatusType, getStatusText } from '@/constants/strategy'
import type { BacktestResponse, BacktestStatusResponse, StrategyConfig } from '@/types'

type BacktestPageVm = {
  templates: unknown[]
  form: { strategy_id: string }
  strategyConfig: Record<string, unknown> | null
  dynamicParams: Record<string, number>
  currentTaskId: string
  runBacktest: () => Promise<void>
  onStrategyChange: (strategyId: string) => Promise<void>
  viewResult: (result: { task_id: string }) => void
  cancelBacktest: () => Promise<void>
  closeWebSocket: () => void
  deleteBacktest: (taskId: string) => Promise<void>
  connectWebSocket: (taskId: string) => void
}

type MockDayjsInstance = {
  subtract: () => MockDayjsInstance
  format: () => string
  toDate: () => Date
}

type MockDayjsFactory = {
  (_value?: unknown): MockDayjsInstance
  default?: MockDayjsFactory
}

const mocks = vi.hoisted(() => {
  const backtestResponse: BacktestResponse = { task_id: 't1', status: 'pending' }
  const templateConfig: StrategyConfig = {
    strategy_id: 's1',
    strategy: { description: 'test' },
    params: { fast: 5, slow: 20 },
    data: { symbol: '000001.SZ' },
    backtest: { initial_cash: 100000, commission: 0.001 },
  }
  const backtestStatus: BacktestStatusResponse = { task_id: 't1', status: 'running' }

  return {
    routerPush: vi.fn(),
    runBacktest: vi.fn().mockResolvedValue(backtestResponse),
    fetchResult: vi.fn().mockResolvedValue(null),
    fetchResults: vi.fn().mockResolvedValue(undefined),
    deleteResult: vi.fn().mockResolvedValue(undefined),
    fetchStrategies: vi.fn().mockResolvedValue(undefined),
    fetchTemplates: vi.fn().mockResolvedValue(undefined),
    getTemplateConfig: vi.fn().mockResolvedValue(templateConfig),
    getStatus: vi.fn().mockResolvedValue(backtestStatus),
    cancel: vi.fn().mockResolvedValue(undefined),
  }
})

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.routerPush }),
  useRoute: () => ({ query: {} }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

vi.mock('@/stores/backtest', () => ({
  useBacktestStore: () => ({
    runBacktest: mocks.runBacktest,
    fetchResult: mocks.fetchResult,
    fetchResults: mocks.fetchResults,
    results: [],
    total: 0,
    deleteResult: mocks.deleteResult,
  }),
}))

vi.mock('@/stores/strategy', () => ({
  useStrategyStore: () => ({
    fetchStrategies: mocks.fetchStrategies,
    fetchTemplates: mocks.fetchTemplates,
    templates: [{ id: 's1', name: 'SMA', category: 'trend' }],
    strategies: [],
  }),
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplateConfig: mocks.getTemplateConfig,
  },
}))

vi.mock('@/api/backtest', () => ({
  backtestApi: {
    getStatus: mocks.getStatus,
    cancel: mocks.cancel,
  },
}))

vi.mock('dayjs', () => {
  const fn: MockDayjsFactory = (_v?: unknown) => ({
    subtract: () => fn(),
    format: () => '2024-01-01T00:00:00',
    toDate: () => new Date('2024-01-01'),
  })
  fn.default = fn
  return { default: fn }
})

const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key]
    }),
    clear: vi.fn(() => {
      store = {}
    }),
  }
})()

Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock })

describe('BacktestPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorageMock.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  const doMount = () => mount(BacktestPage, { global: { stubs: { ...elStubs, EquityCurve: true } } })
  const getVm = () => doMount().vm as unknown as BacktestPageVm

  it('mounts without error', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('has templates from store', () => {
    const vm = getVm()
    expect(vm.templates).toBeDefined()
  })

  it('getStatusType returns correct values (shared constants)', () => {
    expect(getStatusType('completed')).toBe('success')
    expect(getStatusType('running')).toBe('warning')
    expect(getStatusType('failed')).toBe('danger')
    expect(getStatusType('pending')).toBe('info')
    expect(getStatusType('cancelled')).toBe('warning')
    expect(getStatusType('xyz')).toBe('info')
  })

  it('getStatusText returns correct values (shared constants)', () => {
    expect(getStatusText('completed')).toBe('完成')
    expect(getStatusText('running')).toBe('运行中')
    expect(getStatusText('failed')).toBe('失败')
    expect(getStatusText('unknown')).toBe('unknown')
  })

  it('runBacktest warns if no strategy selected', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = getVm()
    vm.form.strategy_id = ''
    await vm.runBacktest()
    expect(ElMessage.warning).toHaveBeenCalledWith('请选择策略')
  })

  it('onStrategyChange clears config when empty', async () => {
    const vm = getVm()
    await vm.onStrategyChange('')
    expect(vm.strategyConfig).toBeNull()
  })

  it('onStrategyChange loads config', async () => {
    const vm = getVm()
    await vm.onStrategyChange('s1')
    expect(vm.strategyConfig).toBeTruthy()
    expect(vm.dynamicParams.fast).toBe(5)
    expect(vm.dynamicParams.slow).toBe(20)
  })

  it('viewResult navigates to result page', () => {
    const vm = getVm()
    vm.viewResult({ task_id: 't1' })
    expect(mocks.routerPush).toHaveBeenCalledWith('/backtest/result/t1')
  })

  it('cancelBacktest does nothing without taskId', async () => {
    const vm = getVm()
    vm.currentTaskId = ''
    await vm.cancelBacktest()
  })

  it('closeWebSocket handles null ws', () => {
    const vm = getVm()
    vm.closeWebSocket()
    expect(vm).toBeTruthy()
  })

  it('deleteBacktest calls store', async () => {
    const vm = getVm()
    await vm.deleteBacktest('t1')
    expect(mocks.deleteResult).toHaveBeenCalledWith('t1')
  })

  it('connectWebSocket uses subprotocol token instead of query param', () => {
    vi.useFakeTimers()
    localStorageMock.setItem('token', 'token-123')

    const wsInstance = {
      readyState: 1,
      send: vi.fn(),
      close: vi.fn(),
      onmessage: null,
      onerror: null,
      onclose: null,
    }
    const webSocketMock = vi.fn().mockImplementation(() => wsInstance)
    Object.assign(webSocketMock, { OPEN: 1 })
    vi.stubGlobal('WebSocket', webSocketMock)

    const vm = getVm()
    vm.connectWebSocket('task-1')

    expect(webSocketMock).toHaveBeenCalledTimes(1)
    const [url, protocols] = webSocketMock.mock.calls[0]
    expect(String(url)).toContain('/ws/backtest/task-1')
    expect(String(url)).not.toContain('?token=')
    expect(protocols).toEqual(['access-token', 'token-123'])

    vm.closeWebSocket()
  })

  it('runBacktest surfaces submission errors', async () => {
    const { ElMessage } = await import('element-plus')
    mocks.runBacktest.mockRejectedValueOnce(new Error('提交失败'))

    const vm = getVm()
    vm.form.strategy_id = 's1'

    await vm.runBacktest()

    expect(ElMessage.error).toHaveBeenCalledWith('提交失败')
  })
})
