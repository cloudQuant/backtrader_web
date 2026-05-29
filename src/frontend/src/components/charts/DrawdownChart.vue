<template>
  <div class="drawdown-chart">
    <h4 class="text-md font-medium mb-4">
      {{ t('charts.drawdownTitle') }}
    </h4>
    <div
      ref="chartRef"
      :style="{ height: height + 'px' }"
    />
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts'
import type { DrawdownPoint } from '@/types/analytics'
import { useChartResize } from '@/composables/useChartResize'
import { DRAWDOWN_AREA_END, DRAWDOWN_AREA_START, DRAWDOWN_COLOR } from '@/constants/chartColors'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  data: DrawdownPoint[]
  height?: number
}>(), {
  data: () => [],
  height: 200,
})

const { chartRef, getChart } = useChartResize(renderChart)

watch(
  () => props.data?.length,
  () => { renderChart() },
)

function renderChart() {
  const chartInstance = getChart()
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
      formatter: (params: unknown) => {
        if (typeof params === 'string') return params
        const arr = Array.isArray(params) ? params : []
        const p = arr[0] as { axisValue?: string; value?: number } | undefined
        return p ? `${p.axisValue}<br/>${t('charts.drawdownTooltip', { value: p.value })}` : ''
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
        name: t('charts.drawdownSeries'),
        type: 'line',
        data: drawdowns,
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: DRAWDOWN_AREA_START },
            { offset: 1, color: DRAWDOWN_AREA_END },
          ]),
        },
        lineStyle: { color: DRAWDOWN_COLOR, width: 1 },
        showSymbol: false,
        markPoint: {
          data: [
            {
              name: t('charts.drawdownMaxLabel'),
              coord: [dates[maxDdIndex], drawdowns[maxDdIndex]],
              value: `${drawdowns[maxDdIndex]}%`,
              itemStyle: { color: DRAWDOWN_COLOR },
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
