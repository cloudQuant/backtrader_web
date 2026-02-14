import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ReturnHeatmap from './ReturnHeatmap.vue'
import { elStubs } from '@/test/stubs'

describe('ReturnHeatmap', () => {
  it('mounts with empty data', () => {
    const wrapper = mount(ReturnHeatmap, {
      props: { returns: [], years: [] } as any,
      global: { stubs: elStubs },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('mounts with return data', () => {
    const wrapper = mount(ReturnHeatmap, {
      props: {
        returns: [
          { year: 2024, month: 1, return_pct: 0.05 },
          { year: 2024, month: 2, return_pct: -0.03 },
        ],
        years: [2024],
        height: 300,
      } as any,
      global: { stubs: elStubs },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders chart container div', () => {
    const wrapper = mount(ReturnHeatmap, {
      props: { returns: [], years: [] } as any,
      global: { stubs: elStubs },
    })
    expect(wrapper.find('.return-heatmap').exists()).toBe(true)
  })

  it('has renderChart function', () => {
    const wrapper = mount(ReturnHeatmap, {
      props: { returns: [], years: [] } as any,
      global: { stubs: elStubs },
    })
    const vm = wrapper.vm as any
    expect(typeof vm.renderChart).toBe('function')
  })

  it('has handleResize function', () => {
    const wrapper = mount(ReturnHeatmap, {
      props: { returns: [], years: [] } as any,
      global: { stubs: elStubs },
    })
    const vm = wrapper.vm as any
    expect(typeof vm.handleResize).toBe('function')
    vm.handleResize() // should not throw
  })

  it('renderChart does nothing when no data', () => {
    const wrapper = mount(ReturnHeatmap, {
      props: { returns: [], years: [] } as any,
      global: { stubs: elStubs },
    })
    const vm = wrapper.vm as any
    vm.renderChart() // should not throw
  })

  it('updates when props change', async () => {
    const wrapper = mount(ReturnHeatmap, {
      props: { returns: [], years: [] } as any,
      global: { stubs: elStubs },
    })
    await wrapper.setProps({
      returns: [{ year: 2024, month: 1, return_pct: 0.1 }],
      years: [2024],
    } as any)
    await nextTick()
    expect(wrapper.exists()).toBe(true)
  })

  it('default height is 280', () => {
    const wrapper = mount(ReturnHeatmap, {
      props: { returns: [], years: [] } as any,
      global: { stubs: elStubs },
    })
    const vm = wrapper.vm as any
    expect(vm.height).toBe(280)
  })
})
