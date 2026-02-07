<template>
  <div class="return-heatmap">
    <h4 class="text-md font-medium mb-4">月度收益热力图</h4>
    <div ref="chartRef" :style="{ height: height + 'px' }"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { MonthlyReturn } from '@/types/analytics'

const props = withDefaults(defineProps<{
  returns: MonthlyReturn[]
  years: number[]
  height?: number
}>(), {
  returns: () => [],
  years: () => [],
  height: 280,
})

const chartRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null

const months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

onMounted(() => {
  nextTick(() => {
    if (chartRef.value) {
      chartInstance = echarts.init(chartRef.value)
      renderChart()
    }
  })
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
})

watch(() => [props.returns, props.years], () => {
  renderChart()
}, { deep: true })

function handleResize() {
  chartInstance?.resize()
}

function renderChart() {
  if (!chartInstance || !props.returns.length) return

  // 转换数据为热力图格式 [monthIndex, yearIndex, value]
  const data = props.returns.map(r => {
    const yearIndex = props.years.indexOf(r.year)
    return [r.month - 1, yearIndex, (r.return_pct * 100).toFixed(2)]
  })

  const values = data.map(d => Math.abs(parseFloat(d[2] as string)))
  const max = Math.max(...values, 10)

  const option: echarts.EChartsOption = {
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        const year = props.years[params.data[1]]
        const month = months[params.data[0]]
        const value = params.data[2]
        return `${year}年${month}: ${value}%`
      },
    },
    grid: {
      height: '60%',
      top: '10%',
      left: '15%',
      right: '10%',
    },
    xAxis: {
      type: 'category',
      data: months,
      splitArea: { show: true },
      axisLabel: { fontSize: 10 },
    },
    yAxis: {
      type: 'category',
      data: props.years.map(String),
      splitArea: { show: true },
    },
    visualMap: {
      min: -max,
      max: max,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '5%',
      inRange: {
        color: ['#00da3c', '#ffffff', '#ec0000'],
      },
    },
    series: [
      {
        type: 'heatmap',
        data: data,
        label: {
          show: true,
          formatter: (params: any) => `${params.data[2]}%`,
          fontSize: 9,
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
      },
    ],
  }

  chartInstance.setOption(option, true)
}
</script>
