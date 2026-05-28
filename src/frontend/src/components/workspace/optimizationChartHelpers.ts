/**
 * Optimization chart rendering helpers.
 * Extracted from WorkspaceOptimizationTab.vue (iteration 174).
 */

import * as echarts from "echarts"
import "echarts-gl"
import { CHART_BORDER_DARK, CHART_EMPHASIS_BORDER, OPTIMIZATION_BOXPLOT_COLOR, OPTIMIZATION_HEATMAP_COLORS } from "@/constants/chartColors"

export function renderAnalysisChart() {
  if (!analysisChartRef.value || !selectedAnalysisMode.value) return
  if (!analysisChart) analysisChart = echarts.init(analysisChartRef.value)

  if (selectedAnalysisMode.value === 'boxplot') {
    renderBoxplotChart()
    return
  }
  if (selectedAnalysisMode.value === 'heatmap') {
    renderHeatmapChart()
    return
  }
  renderScatter3dChart()
}

export function disposeAnalysisChart() {
  if (!analysisChart) return
  analysisChart.dispose()
  analysisChart = null
}

export function renderBoxplotChart() {
  if (!analysisChart || selectedAnalysisParams.value.length !== 1) return
  const paramKey = selectedAnalysisParams.value[0]
  const metricKey = analysisMetric.value
  const groups = new Map<string, number[]>()

  for (const row of displayRows.value) {
    const metricValue = toNumber(row[metricKey])
    const paramValue = row[paramKey]
    if (metricValue === null || paramValue == null) continue
    const key = String(paramValue)
    const current = groups.get(key) || []
    current.push(metricValue)
    groups.set(key, current)
  }

  const categories = getAxisCategories(paramKey).filter(label => groups.has(label))
  const boxData = categories.map(category => {
    const values = [...(groups.get(category) || [])].sort((a, b) => a - b)
    return [
      values[0] ?? 0,
      quantile(values, 0.25),
      quantile(values, 0.5),
      quantile(values, 0.75),
      values[values.length - 1] ?? 0,
    ]
  })

  analysisChart.setOption({
    tooltip: { trigger: 'item' },
    grid: { left: 70, right: 30, top: 30, bottom: 60 },
    xAxis: { type: 'category', data: categories, name: paramKey },
    yAxis: { type: 'value', name: getMetricLabel(metricKey) },
    series: [{
      type: 'boxplot',
      data: boxData,
      itemStyle: { color: OPTIMIZATION_BOXPLOT_COLOR, borderColor: CHART_BORDER_DARK },
    }],
  }, true)
}

export function renderHeatmapChart() {
  if (!analysisChart || selectedAnalysisParams.value.length !== 2) return
  const [xKey, yKey] = selectedAnalysisParams.value
  const metricKey = analysisMetric.value
  const tooltipMetricKeys = ['net_profit', 'max_drawdown', 'annual_return', 'total_trades', 'win_rate']
  const summaryMetricKeys = [...new Set([metricKey, ...tooltipMetricKeys])]
  const xCategories = getAxisCategories(xKey)
  const yCategories = getAxisCategories(yKey)
  const xIndexMap = new Map(xCategories.map((label, index) => [label, index]))
  const yIndexMap = new Map(yCategories.map((label, index) => [label, index]))

  interface MetricAccumulator {
    sum: number
    count: number
  }

  interface HeatmapCellAccumulator {
    targetSum: number
    targetCount: number
    metrics: Record<string, MetricAccumulator>
  }

  interface HeatmapPoint {
    value: [number, number, number]
    sampleCount: number
    metrics: Record<string, number | null>
  }

  const cellMap = new Map<string, HeatmapCellAccumulator>()

  for (const row of displayRows.value) {
    const metricValue = toNumber(row[metricKey])
    const xValue = row[xKey]
    const yValue = row[yKey]
    if (metricValue === null || xValue == null || yValue == null) continue
    const cellKey = `${String(xValue)}__${String(yValue)}`
    const current = cellMap.get(cellKey) || {
      targetSum: 0,
      targetCount: 0,
      metrics: {},
    }
    current.targetSum += metricValue
    current.targetCount += 1
    for (const summaryKey of summaryMetricKeys) {
      const summaryValue = toNumber(row[summaryKey])
      if (summaryValue === null) continue
      const accumulator = current.metrics[summaryKey] || { sum: 0, count: 0 }
      accumulator.sum += summaryValue
      accumulator.count += 1
      current.metrics[summaryKey] = accumulator
    }
    cellMap.set(cellKey, current)
  }

  const data: HeatmapPoint[] = []
  let minValue = Number.POSITIVE_INFINITY
  let maxValue = Number.NEGATIVE_INFINITY

  for (const [cellKey, current] of cellMap.entries()) {
    const [xValue, yValue] = cellKey.split('__')
    const xIndex = xIndexMap.get(xValue)
    const yIndex = yIndexMap.get(yValue)
    if (xIndex == null || yIndex == null || current.targetCount === 0) continue
    const avgValue = current.targetSum / current.targetCount
    const metrics: Record<string, number | null> = {}
    for (const summaryKey of summaryMetricKeys) {
      const accumulator = current.metrics[summaryKey]
      metrics[summaryKey] = accumulator && accumulator.count > 0
        ? accumulator.sum / accumulator.count
        : null
    }
    data.push({
      value: [xIndex, yIndex, avgValue],
      sampleCount: current.targetCount,
      metrics,
    })
    minValue = Math.min(minValue, avgValue)
    maxValue = Math.max(maxValue, avgValue)
  }

  const safeMin = Number.isFinite(minValue) ? minValue : 0
  const safeMax = Number.isFinite(maxValue) ? maxValue : 0

  analysisChart.setOption({
    tooltip: {
      position: 'top',
      formatter: (params: { data: HeatmapPoint }) => {
        const point = params.data
        const [xIndex, yIndex] = point.value
        const metricLabel = getMetricLabel(metricKey)
        const lines = [
          `${xKey}: ${xCategories[xIndex]}`,
          `${yKey}: ${yCategories[yIndex]}`,
          `目标值（${metricLabel}）: ${formatMetricValue(metricKey, point.metrics[metricKey] ?? point.value[2])}`,
        ]
        for (const summaryKey of tooltipMetricKeys) {
          if (summaryKey === metricKey) continue
          lines.push(`${getMetricLabel(summaryKey)}: ${formatMetricValue(summaryKey, point.metrics[summaryKey] ?? null)}`)
        }
        lines.push(`样本数: ${point.sampleCount}`)
        return lines.join('<br/>')
      },
    },
    grid: { left: 80, right: 110, top: 30, bottom: 60 },
    xAxis: { type: 'category', data: xCategories, name: xKey },
    yAxis: { type: 'category', data: yCategories, name: yKey },
    visualMap: {
      min: safeMin,
      max: safeMax,
      calculable: true,
      orient: 'vertical',
      right: 10,
      top: 'center',
      inRange: { color: [...OPTIMIZATION_HEATMAP_COLORS] },
    },
    series: [{
      type: 'heatmap',
      data,
      label: { show: data.length <= 100 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.35)' } },
    }],
  }, true)
}

export function renderScatter3dChart() {
  if (!analysisChart || selectedAnalysisParams.value.length !== 3) return
  const [xKey, yKey, zKey] = selectedAnalysisParams.value
  const metricKey = analysisMetric.value
  const xCategories = getAxisCategories(xKey)
  const yCategories = getAxisCategories(yKey)
  const zCategories = getAxisCategories(zKey)
  const xIndexMap = new Map(xCategories.map((label, index) => [label, index]))
  const yIndexMap = new Map(yCategories.map((label, index) => [label, index]))
  const zIndexMap = new Map(zCategories.map((label, index) => [label, index]))
  const data = displayRows.value
    .map(row => {
      const metricValue = toNumber(row[metricKey])
      const xValue = row[xKey]
      const yValue = row[yKey]
      const zValue = row[zKey]
      if (metricValue === null || xValue == null || yValue == null || zValue == null) return null
      return [
        xIndexMap.get(String(xValue)) ?? 0,
        yIndexMap.get(String(yValue)) ?? 0,
        zIndexMap.get(String(zValue)) ?? 0,
        metricValue,
      ]
    })
    .filter((item): item is [number, number, number, number] => item !== null)

  const metricValues = data.map(item => item[3])
  const minValue = metricValues.length ? Math.min(...metricValues) : 0
  const maxValue = metricValues.length ? Math.max(...metricValues) : 0

  analysisChart.setOption({
    tooltip: {
      formatter: (params: { data: [number, number, number, number] }) => (
        `${xKey}=${xCategories[params.data[0]]}<br/>${yKey}=${yCategories[params.data[1]]}<br/>${zKey}=${zCategories[params.data[2]]}<br/>${getMetricLabel(metricKey)}: ${params.data[3].toFixed(4)}`
      ),
    },
    visualMap: {
      min: minValue,
      max: maxValue,
      dimension: 3,
      orient: 'vertical',
      right: 10,
      top: 'center',
      inRange: { color: [...OPTIMIZATION_HEATMAP_COLORS] },
    },
    xAxis3D: { type: 'category', data: xCategories, name: xKey },
    yAxis3D: { type: 'category', data: yCategories, name: yKey },
    zAxis3D: { type: 'category', data: zCategories, name: zKey },
    grid3D: {
      viewControl: { autoRotate: false, distance: 180 },
      light: { main: { intensity: 1.2 }, ambient: { intensity: 0.4 } },
    },
    series: [{
      type: 'scatter3D',
      data,
      symbolSize: 10,
      itemStyle: { opacity: 0.85 },
      emphasis: { itemStyle: { borderColor: CHART_EMPHASIS_BORDER, borderWidth: 1 } },
    }],
  }, true)
}

export function handleResize() {
  analysisChart?.resize()
}

watch(selectedAnalysisParams, (value) => {
  if (value.length > 3) {
    selectedAnalysisParams.value = value.slice(0, 3)
  }
})

watch([selectedAnalysisParams, analysisMetric, displayRows, viewMode], () => {
  if (viewMode.value === 'analysis' && selectedAnalysisMode.value) {
    nextTick(() => {
      renderAnalysisChart()
    })
  } else {
    disposeAnalysisChart()
  }
}, { deep: true })

onBeforeUnmount(() => {
  stopPolling()
  window.removeEventListener('resize', handleResize)
  disposeAnalysisChart()
})
