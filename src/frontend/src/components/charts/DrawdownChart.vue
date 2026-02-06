<template>
  <div class="drawdown-chart">
    <h4 class="text-md font-medium mb-4">回撤曲线</h4>
    <div ref="chartRef" :style="{ height: height + 'px' }"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import type { DrawdownPoint } from '@/types/analytics'

const props = withDefaults(defineProps<{
  data: DrawdownPoint[]
  height?: number
}>(), {
  data: () => [],
  height: 200,
})

const chartRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null

onMounted(() => {
  if (chartRef.value) {
    chartInstance = echarts.init(chartRef.value)
    renderChart()
    window.addEventListener('resize', handleResize)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
})

watch(() => props.data, () => {
  renderChart()
}, { deep: true })

function handleResize() {
  chartInstance?.resize()
}

function renderChart() {
  if (!chartInstance || !props.data.length) return

  const dates = props.data.map(d => d.date)
  const drawdowns = props.data.map(d => (d.drawdown * 100).toFixed(2))
  
  // 找到最大回撤点
  let maxDdIndex = 0
  let maxDd = 0
  props.data.forEach((d, i) => {
    if (d.drawdown < maxDd) {
      maxDd = d.drawdown
      maxDdIndex = i
    }
  })

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = params[0]
        return `${p.axisValue}<br/>回撤: ${p.value}%`
      },
    },
    grid: {
      left: '10%',
      right: '5%',
      top: '10%',
      bottom: '15%',
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { show: false },
      axisLine: { lineStyle: { color: '#ddd' } },
    },
    yAxis: {
      type: 'value',
      max: 0,
      axisLabel: {
        formatter: '{value}%',
      },
      splitLine: { lineStyle: { type: 'dashed' } },
    },
    series: [
      {
        name: '回撤',
        type: 'line',
        data: drawdowns,
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(255, 77, 79, 0.8)' },
            { offset: 1, color: 'rgba(255, 77, 79, 0.1)' },
          ]),
        },
        lineStyle: { color: '#ff4d4f', width: 1 },
        showSymbol: false,
        markPoint: {
          data: [
            {
              name: '最大回撤',
              coord: [dates[maxDdIndex], drawdowns[maxDdIndex]],
              value: `${drawdowns[maxDdIndex]}%`,
              itemStyle: { color: '#ff4d4f' },
            },
          ],
          label: {
            formatter: '{c}',
            position: 'bottom',
          },
        },
      },
    ],
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100,
      },
    ],
  }

  chartInstance.setOption(option, true)
}
</script>
