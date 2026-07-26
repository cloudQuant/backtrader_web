<template>
  <div class="return-heatmap">
    <h4 class="text-md font-medium mb-4">
      {{ t('charts.heatmapTitle') }}
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
import type * as echarts from 'echarts'
import type { MonthlyReturn } from '@/types/analytics'
import { useChartResize } from '@/composables/useChartResize'
import { RETURN_HEATMAP_COLORS } from '@/constants/chartColors'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  returns: MonthlyReturn[]
  years: number[]
  height?: number
}>(), {
  returns: () => [],
  years: () => [],
  height: 280,
})

const { chartRef, getChart } = useChartResize(renderChart)

const months = computed(() => [
  t('charts.heatmapMonth1'),
  t('charts.heatmapMonth2'),
  t('charts.heatmapMonth3'),
  t('charts.heatmapMonth4'),
  t('charts.heatmapMonth5'),
  t('charts.heatmapMonth6'),
  t('charts.heatmapMonth7'),
  t('charts.heatmapMonth8'),
  t('charts.heatmapMonth9'),
  t('charts.heatmapMonth10'),
  t('charts.heatmapMonth11'),
  t('charts.heatmapMonth12'),
])

watch(
  () => `${props.returns?.length}:${props.years?.length}`,
  () => { renderChart() },
)

function renderChart() {
  const chartInstance = getChart()
  if (!chartInstance || !props.returns.length) return

  // 转换数据为热力图格式 [monthIndex, yearIndex, value]
  const data = props.returns.map(r => {
    const yearIndex = props.years.indexOf(r.year)
    return [r.month - 1, yearIndex, (r.return_pct * 100).toFixed(2)]
  })

  const numericValues = data.map(d => parseFloat(d[2] as string))
  const dataMin = Math.min(...numericValues)
  const dataMax = Math.max(...numericValues)
  const absMax = Math.max(Math.abs(dataMin), Math.abs(dataMax), 0.01)

  const option: echarts.EChartsOption = {
    tooltip: {
      position: 'top',
      formatter: (params: unknown) => {
        const p = params as { data?: [number, number, number | string] }
        const year = props.years[p.data?.[1] ?? 0]
        const month = months.value[p.data?.[0] ?? 0]
        const value = p.data?.[2]
        return t('charts.yearMonth', { year, month, value: value ?? '' })
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
      data: months.value,
      splitArea: { show: true },
      axisLabel: { fontSize: 10 },
    },
    yAxis: {
      type: 'category',
      data: props.years.map(String),
      splitArea: { show: true },
    },
    visualMap: {
      min: -absMax,
      max: absMax,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '5%',
      inRange: {
        color: [...RETURN_HEATMAP_COLORS],
      },
    },
    series: [
      {
        type: 'heatmap',
        data: data,
        label: {
          show: true,
          formatter: (params: unknown) => `${(params as { data?: [number, number, number | string] }).data?.[2]}%`,
          fontSize: 9,
          color: '#333',
        },
        itemStyle: {
          borderWidth: 1,
          borderColor: '#fff',
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
      } as unknown as echarts.SeriesOption,
    ],
  }

  chartInstance.setOption(option, true)
}
</script>
