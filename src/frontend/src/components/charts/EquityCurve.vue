<template>
  <div class="equity-curve">
    <h4 class="text-md font-medium mb-4">
      {{ t('charts.equityTitle') }}
    </h4>
    <div
      ref="chartRef"
      :style="{ height: height + 'px' }"
    />
  </div>
</template>

<script setup lang="ts">
import { watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts'
import type { EquityPoint } from '@/types/analytics'
import { useChartResize } from '@/composables/useChartResize'
import {
  EQUITY_BUY_SIGNAL_COLOR,
  EQUITY_CASH_COLOR,
  EQUITY_CURVE_AREA_END,
  EQUITY_CURVE_AREA_START,
  EQUITY_CURVE_COLOR,
  EQUITY_DRAWDOWN_AREA_COLOR,
  EQUITY_DRAWDOWN_COLOR,
  EQUITY_POSITION_COLOR,
  EQUITY_SELL_SIGNAL_COLOR,
} from '@/constants/chartColors'

const { t } = useI18n()

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

const { chartRef, getChart } = useChartResize(renderChart)

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

function renderChart() {
  const chart = getChart()
  if (!chart || !chartDates.value.length) return
  
  const hasDrawdown = chartDrawdown.value.length > 0
  const hasDetailData = props.data?.length > 0 && props.data[0].cash !== undefined
  
  const legendData = [t('charts.equityTotal')]
  if (hasDetailData) {
    legendData.push(t('charts.equityCash'), t('charts.equityPosition'))
  }
  if (hasDrawdown) {
    legendData.push(t('charts.equityDrawdown'))
  }
  
  const grids: echarts.EChartsOption['grid'] = hasDrawdown
    ? [
        { left: '3%', right: '4%', bottom: '30%', top: '12%', containLabel: true },
        { left: '3%', right: '4%', bottom: '12%', height: '15%', containLabel: true },
      ]
    : [{ left: '3%', right: '4%', bottom: '15%', top: '12%', containLabel: true }]
  
  const xAxes: echarts.XAXisComponentOption[] = [
    { type: 'category', data: chartDates.value, boundaryGap: false },
  ]
  const equityNumbers = chartEquity.value.filter((v): v is number => typeof v === 'number' && isFinite(v))
  const equityMin = equityNumbers.length ? Math.min(...equityNumbers) : 0
  const equityMax = equityNumbers.length ? Math.max(...equityNumbers) : 0
  const equityRange = equityMax - equityMin || equityMax * 0.1 || 1
  const yMin = equityMin - equityRange * 0.05
  const yMax = equityMax + equityRange * 0.02

  const yAxes: echarts.YAXisComponentOption[] = [
    {
      type: 'value', name: t('charts.equityAmount'),
      min: Math.floor(yMin),
      max: Math.ceil(yMax),
      axisLabel: { formatter: (v: number) => {
        if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(1) + t('charts.yi')
        if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(1) + t('charts.wan')
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
      type: 'value', gridIndex: 1, name: t('charts.equityDrawdownPct'), inverse: true,
      axisLabel: { formatter: (v: number) => `${v.toFixed(0)}%` },
      splitNumber: 2,
    })
  }
  
  const series: echarts.SeriesOption[] = [
    {
      name: t('charts.equityTotal'), type: 'line', data: chartEquity.value,
      smooth: true, showSymbol: false,
      lineStyle: { width: 2, color: EQUITY_CURVE_COLOR },
      areaStyle: {
        opacity: 0.15,
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: EQUITY_CURVE_AREA_START },
          { offset: 1, color: EQUITY_CURVE_AREA_END },
        ]),
      },
    },
  ]
  
  if (hasDetailData) {
    series.push(
      {
        name: t('charts.equityCash'), type: 'line',
        data: props.data.map(d => d.cash),
        smooth: true, showSymbol: false,
        lineStyle: { width: 1.5, type: 'dashed', color: EQUITY_CASH_COLOR },
      },
      {
        name: t('charts.equityPosition'), type: 'line',
        data: props.data.map(d => d.position_value),
        smooth: true, showSymbol: false,
        lineStyle: { width: 1.5, type: 'dotted', color: EQUITY_POSITION_COLOR },
      },
    )
  }
  
  if (hasDrawdown) {
    series.push({
      name: t('charts.equityDrawdown'), type: 'line',
      xAxisIndex: 1, yAxisIndex: 1,
      data: chartDrawdown.value,
      smooth: true, showSymbol: false,
      lineStyle: { width: 1, color: EQUITY_DRAWDOWN_COLOR },
      areaStyle: {
        opacity: 0.3,
        color: EQUITY_DRAWDOWN_AREA_COLOR,
      },
    })
  }
  
  // 买卖点标记
  if (props.trades?.length) {
    const buyData: Array<{ value: [string, number]; symbol: string; symbolSize: number }> = []
    const sellData: Array<{ value: [string, number]; symbol: string; symbolSize: number }> = []
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
        name: t('charts.equityBuy'), type: 'scatter', data: buyData,
        itemStyle: { color: EQUITY_BUY_SIGNAL_COLOR },
        z: 10,
      })
      legendData.push(t('charts.equityBuy'))
    }
    if (sellData.length) {
      series.push({
        name: t('charts.equitySell'), type: 'scatter', data: sellData,
        itemStyle: { color: EQUITY_SELL_SIGNAL_COLOR },
        z: 10,
      })
      legendData.push(t('charts.equitySell'))
    }
  }
  
  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (params: unknown) => {
        if (typeof params === 'string') return params
        const arr = Array.isArray(params) ? params : []
        const date = (arr[0] as { axisValue?: string })?.axisValue ?? ''
        let html = `<strong>${date}</strong><br/>`
        arr.forEach((p: { seriesName?: string; value?: number; marker?: string }) => {
          const numericValue = Number(p.value ?? 0)
          if (p.seriesName === t('charts.equityDrawdown')) {
            html += `${p.marker} ${p.seriesName}: ${numericValue.toFixed(2)}%<br/>`
          } else {
            html += `${p.marker} ${p.seriesName}: ¥${numericValue.toLocaleString()}<br/>`
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
  
  chart.setOption(option, true)
}

// Use data identity instead of deep watch for performance
watch(
  () => `${props.data?.length}:${props.equity?.length}:${props.drawdown?.length}:${props.trades?.length}`,
  renderChart,
)
</script>
