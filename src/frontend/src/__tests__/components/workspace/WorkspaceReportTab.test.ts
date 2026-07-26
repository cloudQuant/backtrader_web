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
    getWorkspaceReport: vi.fn().mockResolvedValue({ units: [], summary: {} }),
    recalcWorkspaceReport: vi.fn().mockResolvedValue({ units: [], summary: {} }),
    deleteWorkspaceReport: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

const units = [
  { id: 'u-1', strategy_name: 'Alpha', strategy_id: 's-1' },
  { id: 'u-2', strategy_name: '', strategy_id: 's-2' },
]

vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => ({
    units,
    currentWorkspace: { settings: {} },
  }),
}))

import WorkspaceReportTab from '@/components/workspace/WorkspaceReportTab.vue'
import { elStubs } from '@/test/stubs'

function doMount(props: Record<string, unknown> = {}) {
  return mount(WorkspaceReportTab, {
    props: { workspaceId: 'ws-1', ...props },
    global: { stubs: elStubs },
  })
}

describe('WorkspaceReportTab', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('mounts cleanly', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('fmtPct formats percentages and handles null', () => {
    const vm = doMount().vm as any
    expect(vm.fmtPct(12.345)).toBe('12.35%')
    expect(vm.fmtPct(null)).toBe('-')
    expect(vm.fmtPct(undefined)).toBe('-')
  })

  it('fmtNum formats to 2 decimals and handles null', () => {
    const vm = doMount().vm as any
    expect(vm.fmtNum(3.14159)).toBe('3.14')
    expect(vm.fmtNum(null)).toBe('-')
  })

  it('fmtVal formats numbers to 4 decimals, passes strings through', () => {
    const vm = doMount().vm as any
    expect(vm.fmtVal(1.23456)).toBe('1.2346')
    expect(vm.fmtVal('abc')).toBe('abc')
    expect(vm.fmtVal(null)).toBe('-')
  })

  it('fmtMoney formats numbers with locale and passes strings', () => {
    const vm = doMount().vm as any
    expect(vm.fmtMoney(null)).toBe('-')
    expect(vm.fmtMoney('n/a')).toBe('n/a')
    expect(typeof vm.fmtMoney(1234567.89)).toBe('string')
  })

  it('returnColor maps sign to a tailwind class', () => {
    const vm = doMount().vm as any
    expect(vm.returnColor(1)).toBe('text-green-500')
    expect(vm.returnColor(-1)).toBe('text-red-500')
    expect(vm.returnColor(0)).toBe('text-green-500')
    expect(vm.returnColor(null)).toBe('')
  })

  it('weightModeLabel reflects the weight mode', () => {
    const vm = doMount().vm as any
    expect(vm.weightModeLabel).toBe('report.weightEqual')
    vm.weightMode = 'custom'
    expect(vm.weightModeLabel).toBe('report.weightCustom')
  })

  it('formatRangeValue slices ISO dates and stringifies others', () => {
    const vm = doMount().vm as any
    expect(vm.formatRangeValue('')).toBe('')
    expect(vm.formatRangeValue('2024-01-15T09:00:00')).toBe('2024-01-15')
    expect(vm.formatRangeValue('plain')).toBe('plain')
  })

  it('statRangeLabel uses fullRange when no range set', () => {
    const vm = doMount().vm as any
    expect(vm.statRangeLabel).toBe('report.fullRange')
    vm.reportStatRange = ['2024-01-01', '2024-02-01']
    expect(vm.statRangeLabel).toContain('~')
  })

  it('selectedUnitNames maps ids to names with fallback', () => {
    const vm = doMount().vm as any
    vm.selectedReportUnitIds = ['u-1', 'u-2', 'u-x']
    const names = vm.selectedUnitNames
    expect(names).toContain('Alpha')
    expect(names).toContain('s-2') // u-2 has empty strategy_name -> strategy_id
    expect(names).toContain('u-x') // unknown id -> itself
  })

  it('filteredUnits returns all when no selection, subset otherwise', () => {
    const vm = doMount().vm as any
    vm.report = { units: [{ id: 'u-1' }, { id: 'u-2' }], summary: {} }
    expect(vm.filteredUnits).toHaveLength(2)
    vm.selectedReportUnitIds = ['u-1']
    expect(vm.filteredUnits).toHaveLength(1)
  })
})
