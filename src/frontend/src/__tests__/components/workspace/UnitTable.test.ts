import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import UnitTable from '@/components/workspace/UnitTable.vue'
import { elStubs } from '@/test/stubs'

const units = [
  {
    id: 'u-1',
    strategy_name: 'Alpha',
    symbol: '000001.SZ',
    run_status: 'completed',
    last_task_id: 't-1',
  },
  {
    id: 'u-2',
    strategy_name: 'Beta',
    symbol: '600000.SH',
    run_status: 'idle',
    last_task_id: '',
  },
] as never[]

function doMount() {
  return mount(UnitTable, {
    props: { units },
    global: { stubs: elStubs },
  })
}

describe('UnitTable', () => {
  it('mounts and renders without error for a set of units', () => {
    const wrapper = doMount()
    expect(wrapper.exists()).toBe(true)
  })

  it('exposes clearSelection and toggleRowSelection that delegate to the inner table', () => {
    const wrapper = doMount()
    const vm = wrapper.vm as any
    const inner = { clearSelection: vi.fn(), toggleRowSelection: vi.fn() }
    vm.tableRef = inner
    vm.clearSelection()
    vm.toggleRowSelection(units[0], true)
    expect(inner.clearSelection).toHaveBeenCalled()
    expect(inner.toggleRowSelection).toHaveBeenCalledWith(units[0], true)
  })

  it('tolerates a null inner table ref (no throw)', () => {
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.tableRef = null
    expect(() => vm.clearSelection()).not.toThrow()
    expect(() => vm.toggleRowSelection(units[0])).not.toThrow()
  })
})
