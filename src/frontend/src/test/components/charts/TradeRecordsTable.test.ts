import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TradeRecordsTable from '@/components/charts/TradeRecordsTable.vue'
import { elStubs } from '@/test/stubs'

describe('TradeRecordsTable', () => {
  it('mounts with trades prop', () => {
    const wrapper = mount(TradeRecordsTable, {
      props: { trades: [] } as any,
      global: { stubs: elStubs },
    })
    expect(wrapper.exists()).toBe(true)
  })
})
