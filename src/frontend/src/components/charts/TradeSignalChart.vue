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
    <div ref="chartRef" :style="{ height: computedHeight + 'px' }"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
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
const subChartCount = ref(0)

// 动态计算图表高度：每个副图增加 120px
const computedHeight = computed(() => {
  const base = props.height
  return base + subChartCount.value * 120
})

// 指标可见性状态（由 legend 点击驱动）
const indicatorVisibility: Record<string, boolean> = {}

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

/**
 * 去除指标前导的 warm-up 阶段（值为 0 或 null）以避免从 0 跳到实际值的大跳跃
 */
function stripWarmup(values: (number | null)[]): (number | null)[] {
  const result = [...values]
  for (let i = 0; i < result.length; i++) {
    const v = result[i]
    if (v === null || v === undefined || isNaN(v as number) || v === 0) {
      result[i] = null
    } else {
      break
    }
  }
  return result
}

/**
 * 将指标按值域分类：与价格同量级的画在主图，差异大的画在独立副图
 */
function classifyIndicators(): {
  mainIndicators: Record<string, (number | null)[]>
  subGroups: { name: string; values: (number | null)[] }[]
  hiddenSubNames: string[]
} {
  const mainIndicators: Record<string, (number | null)[]> = {}
  const subGroups: { name: string; values: (number | null)[] }[] = []
  const hiddenSubNames: string[] = []
  if (!props.indicators || !props.klines.length) {
    return { mainIndicators, subGroups, hiddenSubNames }
  }

  const closes = props.klines.map(k => k.close)
  const priceMin = Math.min(...closes)
  const priceMax = Math.max(...closes)
  const priceMid = (priceMin + priceMax) / 2

  for (const [name, rawValues] of Object.entries(props.indicators)) {
    if (!rawValues || rawValues.length === 0) continue
    const values = stripWarmup(rawValues)
    const nonNull = values.filter((v): v is number => v !== null && v !== undefined && !isNaN(v))
    if (nonNull.length === 0) continue

    const indMin = Math.min(...nonNull)
    const indMax = Math.max(...nonNull)
    const indMid = (indMin + indMax) / 2

    const overlapMin = Math.max(priceMin, indMin)
    const overlapMax = Math.min(priceMax, indMax)
    const hasOverlap = overlapMax > overlapMin
    const midpointClose = indMid >= priceMid * 0.15 && indMid <= priceMid * 8

    // 首次看到的指标默认可见
    if (!(name in indicatorVisibility)) {
      indicatorVisibility[name] = true
    }

    if (hasOverlap && midpointClose) {
      mainIndicators[name] = values
    } else {
      if (indicatorVisibility[name] !== false) {
        subGroups.push({ name, values })
      } else {
        hiddenSubNames.push(name)
      }
    }
  }

  return { mainIndicators, subGroups, hiddenSubNames }
}

function renderChart() {
  if (!chartInstance || !props.klines.length) return

  const dates = props.klines.map(k => k.date)
  const ohlc = props.klines.map(k => [k.open, k.close, k.low, k.high])
  const volumes = props.klines.map((k, i) => {
    const isUp = k.close >= k.open
    return [i, k.volume, isUp ? 1 : -1]
  })

  const { mainIndicators, subGroups, hiddenSubNames } = classifyIndicators()
  const numSub = subGroups.length
  subChartCount.value = numSub

  // ---------- 动态布局 ----------
  // 百分比布局，预留足够的空间给 legend、dataZoom 和副图标题
  const legendH = 4       // 顶部 legend 预留
  const sliderH = 8       // 底部 dataZoom slider 预留
  const gap = 3            // 网格间距
  const subTitleH = 2.5    // 每个副图标题行预留
  const totalGaps = (1 + numSub) * gap
  const totalSubTitles = numSub * subTitleH
  const available = 100 - legendH - sliderH - totalGaps - totalSubTitles

  let mainH: number, volH: number, subH: number
  if (numSub === 0) { mainH = available * 0.78; volH = available * 0.22; subH = 0 }
  else if (numSub === 1) { mainH = available * 0.55; volH = available * 0.15; subH = available * 0.30 }
  else if (numSub === 2) { mainH = available * 0.48; volH = available * 0.12; subH = available * 0.40 / 2 }
  else { mainH = available * 0.40; volH = available * 0.10; subH = (available * 0.50) / numSub }

  const grids: any[] = []
  const xAxes: any[] = []
  const yAxes: any[] = []
  const titles: any[] = []
  let curTop = legendH

  // Grid 0 — 主图（K线 + 同量级指标）
  grids.push({ left: '10%', right: '8%', top: `${curTop}%`, height: `${mainH}%` })
  xAxes.push({ type: 'category', data: dates, boundaryGap: false, axisLine: { onZero: false }, splitLine: { show: false }, axisLabel: { show: false }, min: 'dataMin', max: 'dataMax' })
  yAxes.push({ scale: true, splitArea: { show: true } })
  curTop += mainH + gap

  // Grid 1 — 成交量
  titles.push({ text: '成交量', left: '10%', top: `${curTop - 0.5}%`, textStyle: { fontSize: 11, color: '#999', fontWeight: 'normal' } })
  curTop += 1.5
  grids.push({ left: '10%', right: '8%', top: `${curTop}%`, height: `${volH}%` })
  xAxes.push({ type: 'category', gridIndex: 1, data: dates, boundaryGap: false, axisLine: { onZero: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: numSub === 0 }, min: 'dataMin', max: 'dataMax' })
  yAxes.push({ scale: true, gridIndex: 1, splitNumber: 2, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false } })
  curTop += volH + gap

  // Grid 2+ — 副图指标（每个副图前加标题）
  for (let i = 0; i < numSub; i++) {
    const gi = 2 + i
    titles.push({ text: subGroups[i].name, left: '10%', top: `${curTop - 0.5}%`, textStyle: { fontSize: 11, color: '#666', fontWeight: 'normal' } })
    curTop += subTitleH
    grids.push({ left: '10%', right: '8%', top: `${curTop}%`, height: `${subH}%` })
    xAxes.push({ type: 'category', gridIndex: gi, data: dates, boundaryGap: false, axisLine: { onZero: false }, axisTick: { show: i === numSub - 1 }, splitLine: { show: false }, axisLabel: { show: i === numSub - 1 }, min: 'dataMin', max: 'dataMax' })
    yAxes.push({ scale: true, gridIndex: gi, splitNumber: 3 })
    curTop += subH + gap
  }

  // ---------- 系列 ----------
  const series: any[] = []
  const legendData: string[] = ['日K']
  const legendSelected: Record<string, boolean> = {}
  const maColors = ['#f5a623', '#7b68ee', '#20b2aa', '#ff6347', '#9370db', '#e6550d']

  // 买卖点标记
  const buyPoints = props.signals
    .filter(s => s.type === 'buy')
    .map(s => ({ coord: [s.date, s.price * 0.98], value: s.price, itemStyle: { color: '#ec0000' }, symbol: 'triangle', symbolSize: 15 }))
  const sellPoints = props.signals
    .filter(s => s.type === 'sell')
    .map(s => ({ coord: [s.date, s.price * 1.02], value: s.price, itemStyle: { color: '#00da3c' }, symbol: 'triangle', symbolSize: 15, symbolRotate: 180 }))

  series.push({
    name: '日K', type: 'candlestick', data: ohlc,
    itemStyle: { color: '#ec0000', color0: '#00da3c', borderColor: '#ec0000', borderColor0: '#00da3c' },
    markPoint: { data: [...buyPoints, ...sellPoints], label: { show: false } },
  })

  // 主图叠加指标
  let ci = 0
  for (const [name, values] of Object.entries(mainIndicators)) {
    legendData.push(name)
    series.push({ name, type: 'line', data: values, smooth: true, lineStyle: { width: 1.5, opacity: 0.8 }, showSymbol: false, connectNulls: false, itemStyle: { color: maColors[ci % maColors.length] } })
    ci++
  }

  // 成交量（记住其 seriesIndex 用于 visualMap）
  const volSeriesIdx = series.length
  series.push({
    name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: volumes,
    itemStyle: { color: (params: any) => params.data[2] === 1 ? '#ec0000' : '#00da3c' },
  })

  // 副图指标
  const subColors = ['#1890ff', '#722ed1', '#13c2c2', '#eb2f96', '#fa8c16', '#52c41a']
  for (let i = 0; i < numSub; i++) {
    const gi = 2 + i
    const { name, values } = subGroups[i]
    legendData.push(name)
    legendSelected[name] = true
    series.push({ name, type: 'line', xAxisIndex: gi, yAxisIndex: gi, data: values, smooth: true, lineStyle: { width: 1.5 }, showSymbol: false, connectNulls: false, itemStyle: { color: subColors[i % subColors.length] } })
  }

  // 隐藏的副图指标：添加空系列挂在主图上，保证 legend 不消失
  for (const name of hiddenSubNames) {
    legendData.push(name)
    legendSelected[name] = false
    series.push({ name, type: 'line', data: [], showSymbol: false })
  }

  // ---------- 组装 option ----------
  const allXIdx = Array.from({ length: 2 + numSub }, (_, i) => i)

  // dataZoom slider 放在图表底部
  const sliderTop = `${100 - sliderH + 1}%`

  const option: echarts.EChartsOption = {
    animation: false,
    title: titles,
    legend: { top: 0, left: 'center', data: legendData, selected: legendSelected, textStyle: { fontSize: 11 } },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(255, 255, 255, 0.9)', borderWidth: 1, borderColor: '#ccc', padding: 10, textStyle: { color: '#333' },
    },
    axisPointer: { link: [{ xAxisIndex: 'all' as any }], label: { backgroundColor: '#777' } },
    visualMap: { show: false, seriesIndex: volSeriesIdx, dimension: 2, pieces: [{ value: 1, color: '#ec0000' }, { value: -1, color: '#00da3c' }] },
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    dataZoom: [
      { type: 'inside', xAxisIndex: allXIdx, start: 70, end: 100 },
      { show: true, xAxisIndex: allXIdx, type: 'slider', top: sliderTop, start: 70, end: 100 },
    ],
    series,
  }

  chartInstance.setOption(option, true)

  // 记录所有副图指标名（用于判断 legend 点击是否需要重绘）
  const subIndicatorNames = new Set([...subGroups.map(g => g.name), ...hiddenSubNames])

  // 监听 legend 点击事件，仅副图指标切换时重绘布局（移除/添加网格）
  chartInstance.off('legendselectchanged')
  chartInstance.on('legendselectchanged', (params: any) => {
    const selected: Record<string, boolean> = params.selected
    let needRerender = false
    for (const [name, visible] of Object.entries(selected)) {
      if (!subIndicatorNames.has(name)) continue
      if (indicatorVisibility[name] !== visible) {
        indicatorVisibility[name] = visible
        needRerender = true
      }
    }
    if (needRerender) {
      renderChart()
    }
  })

  // 布局变化后 resize
  chartInstance.resize()
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
