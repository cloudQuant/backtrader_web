<template>
  <div ref="chartRef" class="w-full h-full"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import type { KlineData } from '@/types'

interface Props {
  data: KlineData
  indicators?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  indicators: () => ['MA5', 'MA20'],
})

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function calculateMA(data: number[][], period: number) {
  const result: (number | '-')[] = []
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push('-')
    } else {
      let sum = 0
      for (let j = 0; j < period; j++) {
        sum += data[i - j][1]
      }
      result.push(+(sum / period).toFixed(2))
    }
  }
  return result
}

function initChart() {
  if (!chartRef.value || !props.data) return
  
  if (chart) {
    chart.dispose()
  }
  
  chart = echarts.init(chartRef.value)
  
  const option: echarts.EChartsOption = {
    animation: false,
    legend: {
      data: ['K线', ...props.indicators],
      top: 10,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
    },
    grid: [
      { left: '10%', right: '8%', height: '50%' },
      { left: '10%', right: '8%', top: '68%', height: '16%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: props.data.dates,
        boundaryGap: false,
        axisLine: { onZero: false },
        splitLine: { show: false },
        axisPointer: { z: 100 },
      },
      {
        type: 'category',
        gridIndex: 1,
        data: props.data.dates,
        boundaryGap: false,
        axisLine: { onZero: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
      },
    ],
    yAxis: [
      {
        scale: true,
        splitArea: { show: true },
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 70, end: 100 },
      { show: true, xAxisIndex: [0, 1], type: 'slider', top: '88%', start: 70, end: 100 },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: props.data.ohlc,
        itemStyle: {
          color: '#ec0000',
          color0: '#00da3c',
          borderColor: '#ec0000',
          borderColor0: '#00da3c',
        },
      },
      ...props.indicators.map((ind) => {
        const period = parseInt(ind.replace('MA', ''))
        return {
          name: ind,
          type: 'line' as const,
          data: calculateMA(props.data.ohlc, period),
          smooth: true,
          lineStyle: { opacity: 0.6, width: 2 },
        }
      }),
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: props.data.volumes,
        itemStyle: { color: '#7fbe23' },
      },
    ],
  }
  
  chart.setOption(option)
}

function handleResize() {
  chart?.resize()
}

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  chart?.dispose()
  window.removeEventListener('resize', handleResize)
})

watch(() => props.data, initChart, { deep: true })
</script>
