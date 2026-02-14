import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DrawdownChart from './DrawdownChart.vue'
import { elStubs } from '@/test/stubs'

describe('DrawdownChart', () => {
  it('mounts with data prop', () => {
    const wrapper = mount(DrawdownChart, {
      props: { data: [{ date: '2024-01-01', drawdown: -5, maxDrawdown: -5 }] } as any,
      global: { stubs: elStubs },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('mounts with empty data', () => {
    const wrapper = mount(DrawdownChart, {
      props: { data: [] } as any,
      global: { stubs: elStubs },
    })
    expect(wrapper.exists()).toBe(true)
  })
})
