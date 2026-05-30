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

vi.mock('@/api/workspace', () => ({
  workspaceApi: {
    submitUnitOptimization: vi.fn().mockResolvedValue({ task_id: 't-1' }),
  },
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => ({ updateUnit: vi.fn().mockResolvedValue(undefined) }),
}))

import OptimizationConfigDialog from '@/components/workspace/OptimizationConfigDialog.vue'
import { elStubs } from '@/test/stubs'

const unit = {
  id: 'u-1',
  optimization_config: {},
  params: { fast: 5, slow: 20, label: 'x' },
} as never

function doMount(props: Record<string, unknown> = {}) {
  return mount(OptimizationConfigDialog, {
    props: { modelValue: true, workspaceId: 'ws-1', unit, ...props },
    global: { stubs: elStubs },
  })
}

describe('OptimizationConfigDialog', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('mounts cleanly', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('inferParamType returns int for integer layers and float otherwise', () => {
    const vm = doMount().vm as any
    expect(vm.inferParamType({ current_value: 1, start: 0, end: 10, step: 1 })).toBe('int')
    expect(vm.inferParamType({ current_value: 1, start: 0, end: 1, step: 0.5 })).toBe('float')
  })

  it('calculateTotalCombinations multiplies per-param counts', () => {
    const vm = doMount().vm as any
    expect(vm.calculateTotalCombinations({})).toBe(0)
    expect(
      vm.calculateTotalCombinations({
        a: { start: 0, end: 10, step: 5, type: 'int' },
        b: { start: 1, end: 2, step: 1, type: 'int' },
      }),
    ).toBe(6)
  })

  it('initForm builds param layers from numeric unit params', () => {
    const vm = doMount().vm as any
    vm.initForm()
    const names = vm.form.param_layers.map((l: any) => l.param_name)
    expect(names).toContain('fast')
    expect(names).toContain('slow')
    expect(names).not.toContain('label') // non-numeric excluded
  })

  it('addParamLayer appends a blank layer', () => {
    const vm = doMount().vm as any
    const before = vm.form.param_layers.length
    vm.addParamLayer()
    expect(vm.form.param_layers.length).toBe(before + 1)
    expect(vm.form.param_layers.at(-1).param_name).toBe('')
  })

  it('initForm reads existing optimization_config objective', () => {
    const vm = doMount({
      unit: { id: 'u-2', optimization_config: { objective: 'max_return' }, params: {} },
    }).vm as any
    vm.initForm()
    expect(vm.form.objective).toBe('max_return')
  })
})
