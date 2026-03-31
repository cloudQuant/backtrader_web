import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import OptimizationTable from '@/components/charts/OptimizationTable.vue'
import { elStubs } from '@/test/stubs'
import type { OptimizationResultItem } from '@/types/analytics'

type OptimizationTableProps = {
  results: OptimizationResultItem[]
  best: OptimizationResultItem | null
}

describe('OptimizationTable', () => {
  it('mounts with data', () => {
    const props: OptimizationTableProps = { results: [], best: null }
    const wrapper = mount(OptimizationTable, {
      props,
      global: { stubs: elStubs },
    })
    expect(wrapper.exists()).toBe(true)
  })
})
