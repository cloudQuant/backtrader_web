import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import KlineChart from './KlineChart.vue'
import { elStubs } from '@/test/stubs'

describe('KlineChart', () => {
  it('mounts with data prop', () => {
    const wrapper = mount(KlineChart, {
      props: { data: { dates: ['2024-01-01'], ohlc: [[10, 11, 9, 10.5]], volumes: [1000] } } as any,
      global: { stubs: elStubs },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('mounts without data', () => {
    const wrapper = mount(KlineChart, { global: { stubs: elStubs } })
    expect(wrapper.exists()).toBe(true)
  })
})
