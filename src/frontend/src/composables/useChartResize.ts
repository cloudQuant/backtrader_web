import { ref, onMounted, onUnmounted, nextTick, type Ref } from 'vue'
import * as echarts from 'echarts'

/**
 * Composable for managing ECharts instance lifecycle and resize handling.
 *
 * @param renderFn - Optional render function called after chart init and on data changes.
 * @returns chartRef, chartInstance, initChart, disposeChart
 */
export function useChartResize(renderFn?: () => void) {
  const chartRef = ref<HTMLElement>() as Ref<HTMLElement | undefined>
  let chartInstance: echarts.ECharts | null = null

  function getChart(): echarts.ECharts | null {
    return chartInstance
  }

  function initChart(): echarts.ECharts | null {
    if (!chartRef.value) return null

    if (chartInstance) {
      chartInstance.dispose()
    }

    chartInstance = echarts.init(chartRef.value)

    if (renderFn) {
      renderFn()
    }

    return chartInstance
  }

  function handleResize() {
    chartInstance?.resize()
  }

  function disposeChart() {
    chartInstance?.dispose()
    chartInstance = null
  }

  onMounted(() => {
    nextTick(() => {
      if (chartRef.value) {
        chartInstance = echarts.init(chartRef.value)
        if (renderFn) {
          renderFn()
        }
      }
    })
    window.addEventListener('resize', handleResize)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    disposeChart()
  })

  return {
    chartRef,
    getChart,
    initChart,
    disposeChart,
  }
}
