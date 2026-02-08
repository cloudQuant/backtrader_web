<template>
  <div class="equity-curve">
    <h4 class="text-md font-medium mb-4">资金曲线</h4>
    <div ref="chartRef" :style="{ height: height + 'px' }"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { EquityPoint } from '@/types/analytics'

interface TradeSignal {
  date: string
  type: 'buy' | 'sell'
  price: number
}

const props = withDefaults(defineProps<{
  data?: EquityPoint[]
  equity?: number[]
  dates?: string[]
  drawdown?: number[]
  trades?: TradeSignal[]
  height?: number
}>(), {
  data: () => [],
  equity: () => [],
  dates: () => [],
  drawdown: () => [],
  trades: () => [],
  height: 350,
})

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

const chartDates = computed(() => {
  if (props.dates?.length) return props.dates
  return props.data?.map(d => d.date) || []
})

const chartEquity = computed(() => {
  if (props.equity?.length) return props.equity
  return props.data?.map(d => d.total_assets) || []
})

const chartDrawdown = computed(() => {
  if (props.drawdown?.length) return props.drawdown
  return []
})

function initChart() {
  if (!chartRef.value || !chartDates.value.length) return
  
  if (chart) {
    chart.dispose()
  }
  
  chart = echarts.init(chartRef.value)
  
  const hasDrawdown = chartDrawdown.value.length > 0
  const hasDetailData = props.data?.length > 0 && props.data[0].cash !== undefined
  
  const legendData = ['总资产']
  if (hasDetailData) {
    legendData.push('现金', '持仓市值')
  }
  if (hasDrawdown) {
    legendData.push('回撤')
  }
  
  const grids: echarts.EChartsOption['grid'] = hasDrawdown
    ? [
        { left: '3%', right: '4%', bottom: '30%', top: '12%', containLabel: true },
        { left: '3%', right: '4%', bottom: '12%', height: '15%', containLabel: true },
      ]
    : [{ left: '3%', right: '4%', bottom: '15%', top: '12%', containLabel: true }]
  
  const xAxes: any[] = [
    { type: 'category', data: chartDates.value, boundaryGap: false },
  ]
  const yAxes: any[] = [
    {
      type: 'value', name: '金额',
      axisLabel: { formatter: (v: number) => {
        if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(1) + '亿'
        if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(1) + '万'
        return v.toFixed(0)
      }},
    },
  ]
  
  if (hasDrawdown) {
    xAxes.push({
      type: 'category', gridIndex: 1, data: chartDates.value,
      boundaryGap: false, axisLabel: { show: false }, axisTick: { show: false },
    })
    yAxes.push({
      type: 'value', gridIndex: 1, name: '回撤%', inverse: true,
      axisLabel: { formatter: (v: number) => `${v.toFixed(0)}%` },
      splitNumber: 2,
    })
  }
  
  const series: any[] = [
    {
      name: '总资产', type: 'line', data: chartEquity.value,
      smooth: true, showSymbol: false,
      lineStyle: { width: 2, color: '#3b82f6' },
      areaStyle: {
        opacity: 0.15,
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(59, 130, 246, 0.4)' },
          { offset: 1, color: 'rgba(59, 130, 246, 0.02)' },
        ]),
      },
    },
  ]
  
  if (hasDetailData) {
    series.push(
      {
        name: '现金', type: 'line',
        data: props.data.map(d => d.cash),
        smooth: true, showSymbol: false,
        lineStyle: { width: 1.5, type: 'dashed', color: '#10b981' },
      },
      {
        name: '持仓市值', type: 'line',
        data: props.data.map(d => d.position_value),
        smooth: true, showSymbol: false,
        lineStyle: { width: 1.5, type: 'dotted', color: '#f59e0b' },
      },
    )
  }
  
  if (hasDrawdown) {
    series.push({
      name: '回撤', type: 'line',
      xAxisIndex: 1, yAxisIndex: 1,
      data: chartDrawdown.value,
      smooth: true, showSymbol: false,
      lineStyle: { width: 1, color: '#ef4444' },
      areaStyle: {
        opacity: 0.3,
        color: 'rgba(239, 68, 68, 0.3)',
      },
    })
  }
  
  // 买卖点标记
  if (props.trades?.length) {
    const buyData: any[] = []
    const sellData: any[] = []
    const dateSet = new Set(chartDates.value)
    
    props.trades.forEach(t => {
      if (!dateSet.has(t.date)) return
      const idx = chartDates.value.indexOf(t.date)
      if (idx < 0) return
      const equity = chartEquity.value[idx]
      if (t.type === 'buy') {
        buyData.push({ value: [t.date, equity], symbol: 'triangle', symbolSize: 12 })
      } else {
        sellData.push({ value: [t.date, equity], symbol: 'diamond', symbolSize: 12 })
      }
    })
    
    if (buyData.length) {
      series.push({
        name: '买入', type: 'scatter', data: buyData,
        itemStyle: { color: '#ef4444' },
        z: 10,
      })
      legendData.push('买入')
    }
    if (sellData.length) {
      series.push({
        name: '卖出', type: 'scatter', data: sellData,
        itemStyle: { color: '#10b981' },
        z: 10,
      })
      legendData.push('卖出')
    }
  }
  
  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (params: any) => {
        const date = params[0].axisValue
        let html = `<strong>${date}</strong><br/>`
        params.forEach((p: any) => {
          if (p.seriesName === '回撤') {
            html += `${p.marker} ${p.seriesName}: ${p.value.toFixed(2)}%<br/>`
          } else {
            html += `${p.marker} ${p.seriesName}: ¥${Number(p.value).toLocaleString()}<br/>`
          }
        })
        return html
      },
    },
    legend: { data: legendData, top: 0 },
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    dataZoom: [
      { type: 'inside', xAxisIndex: hasDrawdown ? [0, 1] : [0], start: 0, end: 100 },
      { show: true, type: 'slider', bottom: '2%', xAxisIndex: hasDrawdown ? [0, 1] : [0] },
    ],
    series,
  }
  
  chart.setOption(option)
}

function handleResize() {
  chart?.resize()
}

onMounted(() => {
  nextTick(() => initChart())
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  chart?.dispose()
  window.removeEventListener('resize', handleResize)
})

watch([() => props.data, () => props.equity, () => props.drawdown, () => props.trades], initChart, { deep: true })
</script>
