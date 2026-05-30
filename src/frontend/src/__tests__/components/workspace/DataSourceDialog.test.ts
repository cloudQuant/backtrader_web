import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const updateUnit = vi.fn().mockResolvedValue(undefined)
vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => ({ updateUnit }),
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

import DataSourceDialog from '@/components/workspace/DataSourceDialog.vue'
import { elStubs } from '@/test/stubs'

const unit = {
  id: 'u-1',
  timeframe: '1h',
  timeframe_n: 2,
  data_config: {
    range_type: 'sample',
    sample_count: 500,
    start_date: '2021-01-01',
    end_date: '2022-01-01',
    adjust_type: 'forward',
  },
} as never

function doMount(props: Record<string, unknown> = {}) {
  return mount(DataSourceDialog, {
    props: { modelValue: true, workspaceId: 'ws-1', unit, ...props },
    global: { stubs: elStubs },
  })
}

describe('DataSourceDialog', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('mounts cleanly', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('dialogTitle differs for research vs trading workspaces', () => {
    expect((doMount({ workspaceType: 'research' }).vm as any).dialogTitle).toContain(
      'workspaceDialogs.strategyResearch',
    )
    expect((doMount({ workspaceType: 'trading' }).vm as any).dialogTitle).toContain(
      'workspaceDialogs.strategyTrading',
    )
  })

  it('toPickerDate parses dates, strings and falls back', () => {
    const vm = doMount().vm as any
    const fallback = new Date('2000-01-01')
    const d = new Date('2021-06-01')
    expect(vm.toPickerDate(d, fallback)).toBe(d)
    expect(vm.toPickerDate('2021-06-01', fallback) instanceof Date).toBe(true)
    expect(vm.toPickerDate('not-a-date', fallback)).toBe(fallback)
    expect(vm.toPickerDate(null, fallback)).toBe(fallback)
  })

  it('initForm hydrates the form from the unit data_config', () => {
    const vm = doMount().vm as any
    vm.initForm()
    expect(vm.form.timeframe).toBe('1h')
    expect(vm.form.timeframe_n).toBe(2)
    expect(vm.form.range_type).toBe('sample')
    expect(vm.form.sample_count).toBe(500)
    expect(vm.form.adjust_type).toBe('forward')
  })

  it('initForm uses defaults when unit has no data_config', () => {
    const vm = doMount({ unit: { id: 'u-2', data_config: {} } }).vm as any
    vm.initForm()
    expect(vm.form.range_type).toBe('date')
    expect(vm.form.sample_count).toBe(1000)
    expect(vm.form.adjust_type).toBe('none')
  })
})
