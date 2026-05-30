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
    getUnitOptimizationResults: vi.fn().mockResolvedValue({ rows: [], status: 'idle' }),
    getUnitOptimizationProgress: vi.fn().mockResolvedValue({ status: 'idle' }),
    cancelUnitOptimization: vi.fn().mockResolvedValue(undefined),
    applyBestParams: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => ({
    units: [{ id: 'u-1', strategy_name: 'Alpha' }],
    currentWorkspace: { settings: {} },
  }),
}))

import WorkspaceOptimizationTab from '@/components/workspace/WorkspaceOptimizationTab.vue'
import { elStubs } from '@/test/stubs'

function doMount(props: Record<string, unknown> = {}) {
  return mount(WorkspaceOptimizationTab, {
    props: { workspaceId: 'ws-1', ...props },
    global: { stubs: elStubs },
  })
}

describe('WorkspaceOptimizationTab', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('mounts cleanly', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('formatParams renders key=value pairs and handles non-objects', () => {
    const vm = doMount().vm as any
    expect(vm.formatParams({ fast: 5, slow: 20 })).toBe('fast=5, slow=20')
    expect(vm.formatParams(null)).toBe('-')
    expect(vm.formatParams('x')).toBe('-')
  })

  it('fmtVal formats numbers to 4 decimals', () => {
    const vm = doMount().vm as any
    expect(vm.fmtVal(1.23456)).toBe('1.2346')
    expect(vm.fmtVal(null)).toBe('-')
    expect(vm.fmtVal('abc')).toBe('abc')
  })

  it('fmtMoney formats numbers and passes strings', () => {
    const vm = doMount().vm as any
    expect(vm.fmtMoney(null)).toBe('-')
    expect(vm.fmtMoney('x')).toBe('x')
    expect(typeof vm.fmtMoney(1000)).toBe('string')
  })

  it('progressPct computes percentage from completed/total', () => {
    const vm = doMount().vm as any
    expect(vm.progressPct).toBe(0)
    vm.total = 4
    vm.completed = 1
    expect(vm.progressPct).toBe(25)
  })

  it('hasResults reflects rows or running state', () => {
    const vm = doMount().vm as any
    expect(vm.hasResults).toBe(false)
    vm.resultRows = [{ params: {}, sharpe_ratio: 1 }]
    expect(vm.hasResults).toBe(true)
  })

  it('bestParamsStr and bestSharpe reflect the top display row', () => {
    const vm = doMount().vm as any
    expect(vm.bestParamsStr).toBe('-')
    expect(vm.bestSharpe).toBe('-')
    vm.resultRows = [{ params: { fast: 5 }, sharpe_ratio: 2.5 }]
    expect(vm.bestParamsStr).toBe('fast=5')
    expect(vm.bestSharpe).toBe('2.5000')
  })

  it('displayRows sorts by the active sort key descending by default', () => {
    const vm = doMount().vm as any
    vm.resultRows = [
      { params: {}, sharpe_ratio: 1 },
      { params: {}, sharpe_ratio: 3 },
      { params: {}, sharpe_ratio: 2 },
    ]
    vm.sortKey = 'sharpe_ratio'
    vm.sortDir = 'desc'
    const sharpes = vm.displayRows.map((r: any) => r.sharpe_ratio)
    expect(sharpes).toEqual([3, 2, 1])
  })

  it('emptyStateDescription varies by optimization status', () => {
    const vm = doMount().vm as any
    vm.optimizationStatus = 'cancelled'
    expect(vm.emptyStateDescription).toContain('optimization.taskCancelled')
    vm.optimizationStatus = 'failed'
    expect(vm.emptyStateDescription).toContain('optimization.taskFailed')
  })
})
