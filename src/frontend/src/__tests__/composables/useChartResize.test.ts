import { defineComponent, h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import * as echarts from 'echarts'
import { useChartResize } from '@/composables/useChartResize'

describe('useChartResize', () => {
  it('rerenders and resizes the chart when the theme changes', async () => {
    const renderChart = vi.fn()
    const Host = defineComponent({
      setup() {
        const { chartRef } = useChartResize(renderChart)
        return () => h('div', { ref: chartRef })
      },
    })
    const wrapper = mount(Host)
    await nextTick()

    const chart = vi.mocked(echarts.init).mock.results.at(-1)?.value
    expect(renderChart).toHaveBeenCalledTimes(1)

    window.dispatchEvent(new Event('themechange'))

    expect(renderChart).toHaveBeenCalledTimes(2)
    expect(chart?.resize).toHaveBeenCalled()

    wrapper.unmount()
    window.dispatchEvent(new Event('themechange'))
    expect(renderChart).toHaveBeenCalledTimes(2)
  })
})
