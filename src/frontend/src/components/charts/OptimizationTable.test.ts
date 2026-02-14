import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import OptimizationTable from './OptimizationTable.vue'
import { elStubs } from '@/test/stubs'

describe('OptimizationTable', () => {
  it('mounts with data', () => {
    const wrapper = mount(OptimizationTable, {
      props: { results: [], best: null } as any,
      global: { stubs: elStubs },
    })
    expect(wrapper.exists()).toBe(true)
  })
})
