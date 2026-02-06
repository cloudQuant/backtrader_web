<template>
  <div class="equity-curve">
    <h4 class="text-md font-medium mb-4">资金曲线</h4>
    <div ref="chartRef" :style="{ height: height + 'px' }"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import type { EquityPoint } from '@/types/analytics'

const props = withDefaults(defineProps<{
  data: EquityPoint[]
  height?: number
}>(), {
  data: () => [],
  height: 350,
})

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function initChart() {
  if (!chartRef.value || !props.data?.length) return
  
  if (chart) {
    chart.dispose()
  }
  
  chart = echarts.init(chartRef.value)
  
  const dates = props.data.map(d => d.date)
  const totalAssets = props.data.map(d => d.total_assets)
  const cash = props.data.map(d => d.cash)
  const positionValue = props.data.map(d => d.position_value)
  
  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (params: any) => {
        const date = params[0].axisValue
        let html = `<strong>${date}</strong><br/>`
        params.forEach((p: any) => {
          html += `${p.marker} ${p.seriesName}: ¥${p.value.toLocaleString()}<br/>`
        })
        return html
      },
    },
    legend: {
      data: ['总资产', '现金', '持仓市值'],
      top: 0,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      top: '12%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      name: '金额',
      axisLabel: {
        formatter: (value: number) => `¥${(value / 1000).toFixed(0)}K`,
      },
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { show: true, type: 'slider', bottom: '2%' },
    ],
    series: [
      {
        name: '总资产',
        type: 'line',
        data: totalAssets,
        smooth: true,
        lineStyle: { width: 2, color: '#3b82f6' },
        areaStyle: {
          opacity: 0.2,
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(59, 130, 246, 0.4)' },
            { offset: 1, color: 'rgba(59, 130, 246, 0.05)' },
          ]),
        },
        showSymbol: false,
      },
      {
        name: '现金',
        type: 'line',
        data: cash,
        smooth: true,
        lineStyle: { width: 1.5, type: 'dashed', color: '#10b981' },
        showSymbol: false,
      },
      {
        name: '持仓市值',
        type: 'line',
        data: positionValue,
        smooth: true,
        lineStyle: { width: 1.5, type: 'dotted', color: '#f59e0b' },
        showSymbol: false,
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
