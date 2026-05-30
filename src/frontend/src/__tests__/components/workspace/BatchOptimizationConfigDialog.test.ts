import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/api/workspace', () => ({
  workspaceApi: {
    submitUnitOptimization: vi.fn().mockResolvedValue({ task_id: 't-1' }),
    updateUnit: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

import BatchOptimizationConfigDialog from '@/components/workspace/BatchOptimizationConfigDialog.vue'
import { elStubs } from '@/test/stubs'

const units = [
  { id: 'u-1', optimization_config: { objective: 'max_return', n_workers: 8 }, params: { fast: 5 } },
  { id: 'u-2', params: { slow: 20, label: 'x' } },
] as never[]

function doMount(props: Record<string, unknown> = {}) {
  return mount(BatchOptimizationConfigDialog, {
    props: { modelValue: true, workspaceId: 'ws-1', unitIds: ['u-1'], units, ...props },
    global: { stubs: elStubs },
  })
}

describe('BatchOptimizationConfigDialog', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('mounts cleanly', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('calcCount counts equal_diff steps and returns 0 for invalid ranges', () => {
    const vm = doMount().vm as any
    expect(vm.calcCount({ opt_type: 'equal_diff', start: 0, end: 10, step: 5 })).toBe(3)
    expect(vm.calcCount({ opt_type: 'equal_diff', start: 5, end: 5, step: 1 })).toBe(0)
    expect(vm.calcCount({ opt_type: 'none', start: 0, end: 10, step: 1 })).toBe(0)
  })

  it('totalCombinations multiplies enabled layer counts', () => {
    const vm = doMount().vm as any
    vm.form.param_layers = [
      { param_name: 'a', opt_type: 'equal_diff', start: 0, end: 10, step: 5 }, // 3
      { param_name: 'b', opt_type: 'equal_diff', start: 0, end: 2, step: 1 }, // 3
    ]
    expect(vm.totalCombinations).toBe(9)
  })

  it('initForm pre-fills from the first unit with optimization_config', () => {
    const vm = doMount({ unitIds: ['u-1'] }).vm as any
    vm.initForm()
    expect(vm.form.objective).toBe('max_return')
    expect(vm.form.n_workers).toBe(8)
  })

  it('initForm builds layers from numeric params when no config', () => {
    const vm = doMount({ unitIds: ['u-2'] }).vm as any
    vm.initForm()
    const names = vm.form.param_layers.map((l: any) => l.param_name)
    expect(names).toContain('slow')
    expect(names).not.toContain('label')
  })

  it('addParamLayer appends a blank layer', () => {
    const vm = doMount().vm as any
    const before = vm.form.param_layers.length
    vm.addParamLayer()
    expect(vm.form.param_layers.length).toBe(before + 1)
  })
})
