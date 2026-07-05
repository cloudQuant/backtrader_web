import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/api/workspace', () => ({
  workspaceApi: {
    runUnits: vi.fn().mockResolvedValue(undefined),
    stopUnits: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

const storeState = {
  units: [] as any[],
  selectedUnitIds: [] as string[],
  startPolling: vi.fn(),
  stopPolling: vi.fn(),
  setSelectedUnitIds: vi.fn((ids: string[]) => {
    storeState.selectedUnitIds = ids
  }),
  clearSelection: vi.fn(),
  fetchUnits: vi.fn().mockResolvedValue(undefined),
  pollStatus: vi.fn().mockResolvedValue(undefined),
}

vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => storeState,
}))

import WorkspaceUnitsTab from '@/components/workspace/WorkspaceUnitsTab.vue'
import { elStubs } from '@/test/stubs'

const childStubs = {
  CreateUnitDialog: true,
  DataSourceDialog: true,
  UnitSettingsDialog: true,
  StrategyParamsDialog: true,
  OptimizationConfigDialog: true,
  OptimizationThreadDialog: true,
  BatchOptimizationConfigDialog: true,
  ChangeSymbolDialog: true,
  GroupRenameDialog: true,
  UnitRenameDialog: true,
  UnitTable: true,
  UnitsActionsBar: true,
  WorkspaceUnitRuntimeDialog: true,
}

function doMount(props: Record<string, unknown> = {}) {
  return mount(WorkspaceUnitsTab, {
    props: { workspaceId: 'ws-1', ...props },
    global: { stubs: { ...elStubs, ...childStubs } },
  })
}

describe('WorkspaceUnitsTab', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    storeState.units = []
    storeState.selectedUnitIds = []
    vi.clearAllMocks()
  })

  it('mounts cleanly', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('inferBatchParamType returns int for integer ranges and float otherwise', () => {
    const vm = doMount().vm as any
    expect(vm.inferBatchParamType({ start: 1, end: 10, step: 1 })).toBe('int')
    expect(vm.inferBatchParamType({ start: 0.1, end: 1, step: 0.1 })).toBe('float')
  })

  it('calculateBatchTotalCombinations multiplies per-param counts', () => {
    const vm = doMount().vm as any
    expect(vm.calculateBatchTotalCombinations({})).toBe(0)
    expect(
      vm.calculateBatchTotalCombinations({
        a: { start: 0, end: 10, step: 5, type: 'int' }, // 3 values: 0,5,10
        b: { start: 1, end: 3, step: 1, type: 'int' }, // 3 values: 1,2,3
      }),
    ).toBe(9)
    expect(
      vm.calculateBatchTotalCombinations({ a: { start: 5, end: 5, step: 1, type: 'int' } }),
    ).toBe(0)
  })

  it('optimization status predicates classify states', () => {
    const vm = doMount().vm as any
    expect(vm.isOptimizationActiveStatus('running')).toBe(true)
    expect(vm.isOptimizationActiveStatus('completed')).toBe(false)
    expect(vm.isOptimizationPendingStatus('queued')).toBe(true)
    expect(vm.isOptimizationPendingStatus('running')).toBe(false)
    expect(vm.isOptimizationTerminalStatus('failed')).toBe(true)
    expect(vm.isOptimizationTerminalStatus('running')).toBe(false)
  })

  it('getOptimizationTotal/Completed clamp to >= 0', () => {
    const vm = doMount().vm as any
    expect(vm.getOptimizationTotal({ opt_total: 5 })).toBe(5)
    expect(vm.getOptimizationTotal({ opt_total: -3 })).toBe(0)
    expect(vm.getOptimizationCompleted({ opt_completed: 2 })).toBe(2)
    expect(vm.getOptimizationCompleted({})).toBe(0)
  })

  it('shouldShowOptimizationProgress reflects active vs terminal state', () => {
    const vm = doMount().vm as any
    expect(vm.shouldShowOptimizationProgress({ opt_status: 'running' })).toBe(true)
    expect(vm.shouldShowOptimizationProgress({ opt_status: 'completed' })).toBe(false)
    expect(
      vm.shouldShowOptimizationProgress({ opt_status: null, opt_total: 10, opt_completed: 3 }),
    ).toBe(true)
  })

  it('runStatusTagType and runStatusLabel map known statuses', () => {
    const vm = doMount().vm as any
    expect(vm.runStatusTagType('running')).toBe('primary')
    expect(vm.runStatusTagType('completed')).toBe('success')
    expect(vm.runStatusTagType('unknown')).toBe('info')
    expect(vm.runStatusLabel('idle')).toBe('units.statusIdle')
    expect(vm.runStatusLabel('weird')).toBe('weird')
  })

  it('optimizationStatusTagType/Label handle null', () => {
    const vm = doMount().vm as any
    expect(vm.optimizationStatusTagType('completed')).toBe('success')
    expect(vm.optimizationStatusTagType(null)).toBe('info')
    expect(vm.optimizationStatusLabel(null)).toBe('-')
    expect(vm.optimizationStatusLabel('failed')).toBe('units.statusFail')
  })

  it('objectiveLabel maps known objectives', () => {
    const vm = doMount().vm as any
    expect(vm.objectiveLabel('sharpe_max')).toBe('units.bestSharpe')
    expect(vm.objectiveLabel(undefined)).toBe('-')
    expect(vm.objectiveLabel('custom')).toBe('custom')
  })

  it('formatOptimizationCount renders completed/total or dash', () => {
    const vm = doMount().vm as any
    expect(vm.formatOptimizationCount({ opt_total: 0 })).toBe('-')
    expect(vm.formatOptimizationCount({ opt_total: 10, opt_completed: 4 })).toBe('4/10')
  })

  it('unitResultSummary renders metrics and failure reasons', () => {
    const vm = doMount().vm as any
    expect(
      vm.unitResultSummary({
        run_status: 'completed',
        metrics_snapshot: { total_return: 0.1234, sharpe_ratio: 1.234, total_trades: 8 },
      }),
    ).toBe('收益 12.34% · Sharpe 1.23 · 交易 8')
    expect(
      vm.unitResultSummary({
        run_status: 'failed',
        error_message: 'No CSV file found for symbol=sa',
        metrics_snapshot: {},
      }),
    ).toBe('失败：No CSV file found for symbol=sa')
  })

  it('canOpenReport requires completed status and a task id', () => {
    const vm = doMount().vm as any
    expect(vm.canOpenReport({ run_status: 'completed', last_task_id: 't-1' })).toBe(true)
    expect(vm.canOpenReport({ run_status: 'completed', last_task_id: '' })).toBe(false)
    expect(vm.canOpenReport({ run_status: 'idle', last_task_id: 't-1' })).toBe(false)
  })

  it('selection computeds reflect store state', async () => {
    storeState.units = [{ id: 'u-1' }, { id: 'u-2' }]
    storeState.selectedUnitIds = ['u-1']
    const vm = doMount().vm as any
    expect(vm.hasSelection).toBe(true)
    expect(vm.hasSingleSelection).toBe(true)
    expect(vm.selectedUnit?.id).toBe('u-1')
  })
})
