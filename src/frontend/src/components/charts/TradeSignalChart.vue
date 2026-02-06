<template>
  <div class="trade-signal-chart">
    <div class="flex justify-between items-center mb-4">
      <h4 class="text-md font-medium">K线图与交易信号</h4>
      <div class="flex gap-2">
        <el-button-group size="small">
          <el-button 
            v-for="p in periods" 
            :key="p.value"
            :type="selectedPeriod === p.value ? 'primary' : ''"
            @click="handlePeriodChange(p.value)"
          >
            {{ p.label }}
          </el-button>
        </el-button-group>
        <el-button size="small" @click="handleExport">
          <el-icon><Download /></el-icon>
        </el-button>
      </div>
    </div>
    <div ref="chartRef" :style="{ height: height + 'px' }"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import { Download } from '@element-plus/icons-vue'
import type { KlineData, TradeSignal } from '@/types/analytics'

const props = withDefaults(defineProps<{
  klines: KlineData[]
  signals: TradeSignal[]
  indicators?: Record<string, (number | null)[]>
  height?: number
}>(), {
  klines: () => [],
  signals: () => [],
  height: 600,
})

const chartRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null

const periods = [
  { label: '1月', value: '1m' },
  { label: '3月', value: '3m' },
  { label: '6月', value: '6m' },
  { label: '1年', value: '1y' },
  { label: '全部', value: 'all' },
]
const selectedPeriod = ref('all')

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

watch(() => [props.klines, props.signals, props.indicators], () => {
  renderChart()
}, { deep: true })

function handleResize() {
  chartInstance?.resize()
}

function renderChart() {
  if (!chartInstance || !props.klines.length) return

  const dates = props.klines.map(k => k.date)
  const ohlc = props.klines.map(k => [k.open, k.close, k.low, k.high])
  const volumes = props.klines.map((k, i) => {
    const isUp = k.close >= k.open
    return [i, k.volume, isUp ? 1 : -1]
  })

  // 买卖点标记
  const buyPoints = props.signals
    .filter(s => s.type === 'buy')
    .map(s => ({
      coord: [s.date, s.price * 0.98],
      value: s.price,
      itemStyle: { color: '#ec0000' },
      symbol: 'triangle',
      symbolSize: 15,
    }))

  const sellPoints = props.signals
    .filter(s => s.type === 'sell')
    .map(s => ({
      coord: [s.date, s.price * 1.02],
      value: s.price,
      itemStyle: { color: '#00da3c' },
      symbol: 'triangle',
      symbolSize: 15,
      symbolRotate: 180,
    }))

  const series: any[] = [
    {
      name: '日K',
      type: 'candlestick',
      data: ohlc,
      itemStyle: {
        color: '#ec0000',
        color0: '#00da3c',
        borderColor: '#ec0000',
        borderColor0: '#00da3c',
      },
      markPoint: {
        data: [...buyPoints, ...sellPoints],
        label: { show: false },
      },
    },
  ]

  // 添加均线
  if (props.indicators) {
    const maColors = ['#f5a623', '#7b68ee', '#20b2aa', '#ff6347']
    let colorIndex = 0
    for (const [name, values] of Object.entries(props.indicators)) {
      if (values && values.length > 0) {
        series.push({
          name: name.toUpperCase(),
          type: 'line',
          data: values,
          smooth: true,
          lineStyle: { width: 1.5, opacity: 0.8 },
          showSymbol: false,
          itemStyle: { color: maColors[colorIndex % maColors.length] },
        })
        colorIndex++
      }
    }
  }

  // 成交量
  series.push({
    name: '成交量',
    type: 'bar',
    xAxisIndex: 1,
    yAxisIndex: 1,
    data: volumes,
    itemStyle: {
      color: (params: any) => params.data[2] === 1 ? '#ec0000' : '#00da3c',
    },
  })

  const option: echarts.EChartsOption = {
    animation: false,
    legend: {
      bottom: 10,
      left: 'center',
      data: ['日K', ...(props.indicators ? Object.keys(props.indicators).map(k => k.toUpperCase()) : [])],
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(255, 255, 255, 0.9)',
      borderWidth: 1,
      borderColor: '#ccc',
      padding: 10,
      textStyle: { color: '#333' },
    },
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
      label: { backgroundColor: '#777' },
    },
    visualMap: {
      show: false,
      seriesIndex: series.length - 1,
      dimension: 2,
      pieces: [
        { value: 1, color: '#ec0000' },
        { value: -1, color: '#00da3c' },
      ],
    },
    grid: [
      { left: '10%', right: '8%', height: '50%' },
      { left: '10%', right: '8%', top: '68%', height: '16%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLine: { onZero: false },
        splitLine: { show: false },
        min: 'dataMin',
        max: 'dataMax',
      },
      {
        type: 'category',
        gridIndex: 1,
        data: dates,
        boundaryGap: false,
        axisLine: { onZero: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        min: 'dataMin',
        max: 'dataMax',
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
      {
        type: 'inside',
        xAxisIndex: [0, 1],
        start: 70,
        end: 100,
      },
      {
        show: true,
        xAxisIndex: [0, 1],
        type: 'slider',
        top: '90%',
        start: 70,
        end: 100,
      },
    ],
    series,
  }

  chartInstance.setOption(option, true)
}

function handlePeriodChange(period: string) {
  selectedPeriod.value = period
  // 根据周期调整dataZoom范围
  const total = props.klines.length
  let start = 0
  
  switch (period) {
    case '1m': start = Math.max(0, 100 - (22 / total) * 100); break
    case '3m': start = Math.max(0, 100 - (66 / total) * 100); break
    case '6m': start = Math.max(0, 100 - (132 / total) * 100); break
    case '1y': start = Math.max(0, 100 - (252 / total) * 100); break
    default: start = 0
  }
  
  chartInstance?.setOption({
    dataZoom: [
      { start, end: 100 },
      { start, end: 100 },
    ],
  })
}

function handleExport() {
  if (chartInstance) {
    const url = chartInstance.getDataURL({
      type: 'png',
      pixelRatio: 2,
      backgroundColor: '#fff',
    })
    const link = document.createElement('a')
    link.href = url
    link.download = 'kline-chart.png'
    link.click()
  }
}
</script>
