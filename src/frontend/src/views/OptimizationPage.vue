<template>
  <div class="space-y-5">
    <!-- Step 1: 策略选择 + 参数配置 -->
    <el-card v-if="phase === 'config'">
      <template #header><span class="font-bold">参数优化配置</span></template>

      <!-- 策略选择 -->
      <el-form label-width="100px" class="mb-4">
        <el-form-item label="选择策略">
          <el-select
            v-model="selectedStrategy"
            filterable
            placeholder="请选择策略"
            class="w-full"
            @change="onStrategyChange"
          >
            <el-option
              v-for="t in templates"
              :key="t.id"
              :label="t.name"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <!-- 参数网格 -->
      <div v-if="paramRows.length > 0">
        <el-table :data="paramRows" border size="small" class="mb-4">
          <el-table-column prop="name" label="参数名" width="140" />
          <el-table-column prop="type" label="类型" width="70" align="center" />
          <el-table-column prop="default" label="默认值" width="90" align="center" />
          <el-table-column label="启用" width="60" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.enabled" />
            </template>
          </el-table-column>
          <el-table-column label="起始值" width="120">
            <template #default="{ row }">
              <el-input-number
                v-model="row.start"
                :disabled="!row.enabled"
                :step="row.type === 'int' ? 1 : 0.1"
                size="small"
                controls-position="right"
                class="w-full"
              />
            </template>
          </el-table-column>
          <el-table-column label="结束值" width="120">
            <template #default="{ row }">
              <el-input-number
                v-model="row.end"
                :disabled="!row.enabled"
                :step="row.type === 'int' ? 1 : 0.1"
                size="small"
                controls-position="right"
                class="w-full"
              />
            </template>
          </el-table-column>
          <el-table-column label="步长" width="120">
            <template #default="{ row }">
              <el-input-number
                v-model="row.step"
                :disabled="!row.enabled"
                :min="row.type === 'int' ? 1 : 0.001"
                :step="row.type === 'int' ? 1 : 0.1"
                size="small"
                controls-position="right"
                class="w-full"
              />
            </template>
          </el-table-column>
          <el-table-column label="组合数" width="80" align="center">
            <template #default="{ row }">
              <span v-if="row.enabled">{{ calcCount(row) }}</span>
              <span v-else class="text-gray-400">—</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 进程数 + 总组合数 -->
        <div class="flex items-center gap-6 mb-4">
          <el-form-item label="进程数" class="mb-0">
            <el-input-number v-model="nWorkers" :min="1" :max="32" size="small" />
          </el-form-item>
          <span class="text-gray-600">
            总参数组合: <strong class="text-blue-600">{{ totalCombinations }}</strong>
          </span>
        </div>

        <el-button type="primary" :disabled="totalCombinations === 0" @click="startOptimization">
          开始优化
        </el-button>
      </div>
    </el-card>

    <!-- Step 2: 优化进行中 -->
    <el-card v-if="phase === 'running'">
      <template #header><span class="font-bold">优化进行中…</span></template>
      <div class="space-y-4">
        <el-progress :percentage="progress.progress" :stroke-width="20" :text-inside="true" />
        <div class="text-sm text-gray-600">
          已完成: {{ progress.completed }} / {{ progress.total }}
          <span v-if="progress.failed > 0" class="text-red-500 ml-2">失败: {{ progress.failed }}</span>
          <span class="ml-4">进程数: {{ progress.n_workers }}</span>
        </div>
        <el-button type="danger" plain size="small" @click="cancelOpt">取消优化</el-button>
      </div>
    </el-card>

    <!-- Step 3: 结果展示 -->
    <template v-if="phase === 'done' && results">
      <!-- 操作栏 -->
      <div class="flex items-center gap-3">
        <el-button size="small" @click="phase = 'config'">返回配置</el-button>
        <span class="text-gray-500 text-sm">
          共 {{ results.completed }} 组成功 / {{ results.total }} 组
          <span v-if="results.failed > 0" class="text-red-500">, {{ results.failed }} 组失败</span>
        </span>
      </div>

      <el-tabs v-model="resultTab">
        <!-- 结果列表 -->
        <el-tab-pane label="结果列表" name="table">
          <el-card>
            <el-table
              :data="results.rows"
              stripe
              size="small"
              max-height="500"
              :default-sort="{ prop: 'annual_return', order: 'descending' }"
              highlight-current-row
            >
              <el-table-column
                v-for="p in results.param_names"
                :key="'p_' + p"
                :prop="p"
                :label="p"
                width="100"
                sortable
                align="center"
              />
              <el-table-column prop="annual_return" label="年化收益率%" width="110" sortable align="right">
                <template #default="{ row }">
                  <span :class="row.annual_return >= 0 ? 'text-green-600' : 'text-red-600'">
                    {{ row.annual_return?.toFixed(2) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="sharpe_ratio" label="夏普率" width="90" sortable align="right">
                <template #default="{ row }">{{ row.sharpe_ratio?.toFixed(4) }}</template>
              </el-table-column>
              <el-table-column prop="max_drawdown" label="最大回撤%" width="100" sortable align="right">
                <template #default="{ row }">{{ row.max_drawdown?.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column prop="total_trades" label="交易次数" width="80" sortable align="center" />
              <el-table-column prop="win_rate" label="胜率%" width="80" sortable align="right">
                <template #default="{ row }">{{ row.win_rate?.toFixed(1) }}</template>
              </el-table-column>
              <el-table-column prop="total_return" label="总收益率%" width="100" sortable align="right">
                <template #default="{ row }">
                  <span :class="row.total_return >= 0 ? 'text-green-600' : 'text-red-600'">
                    {{ row.total_return?.toFixed(2) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="final_value" label="终值" width="110" sortable align="right">
                <template #default="{ row }">{{ row.final_value?.toFixed(2) }}</template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-tab-pane>

        <!-- 热力图 (2 params + 1 metric) -->
        <el-tab-pane label="热力图" name="heatmap">
          <el-card>
            <div class="flex items-center gap-4 mb-4 flex-wrap">
              <el-form-item label="X 轴参数" class="mb-0">
                <el-select v-model="heatmapXParam" size="small" class="w-36">
                  <el-option v-for="p in results.param_names" :key="p" :label="p" :value="p" />
                </el-select>
              </el-form-item>
              <el-form-item label="Y 轴参数" class="mb-0">
                <el-select v-model="heatmapYParam" size="small" class="w-36">
                  <el-option v-for="p in results.param_names" :key="p" :label="p" :value="p" />
                </el-select>
              </el-form-item>
              <el-form-item label="指标" class="mb-0">
                <el-select v-model="heatmapMetric" size="small" class="w-40">
                  <el-option v-for="m in metricOptions" :key="m.value" :label="m.label" :value="m.value" />
                </el-select>
              </el-form-item>
            </div>
            <div ref="heatmapRef" style="width:100%;height:500px"></div>
          </el-card>
        </el-tab-pane>

        <!-- 箱体图 (1 param + 1 metric) -->
        <el-tab-pane label="箱体图" name="boxplot">
          <el-card>
            <div class="flex items-center gap-4 mb-4 flex-wrap">
              <el-form-item label="参数" class="mb-0">
                <el-select v-model="boxParam" size="small" class="w-36">
                  <el-option v-for="p in results.param_names" :key="p" :label="p" :value="p" />
                </el-select>
              </el-form-item>
              <el-form-item label="指标" class="mb-0">
                <el-select v-model="boxMetric" size="small" class="w-40">
                  <el-option v-for="m in metricOptions" :key="m.value" :label="m.label" :value="m.value" />
                </el-select>
              </el-form-item>
            </div>
            <div ref="boxplotRef" style="width:100%;height:500px"></div>
          </el-card>
        </el-tab-pane>

        <!-- 3D 散点图 (3 params + 1 metric) -->
        <el-tab-pane label="3D散点图" name="scatter3d">
          <el-card>
            <div class="flex items-center gap-4 mb-4 flex-wrap">
              <el-form-item label="X 轴" class="mb-0">
                <el-select v-model="scatter3dX" size="small" class="w-36">
                  <el-option v-for="p in results.param_names" :key="p" :label="p" :value="p" />
                </el-select>
              </el-form-item>
              <el-form-item label="Y 轴" class="mb-0">
                <el-select v-model="scatter3dY" size="small" class="w-36">
                  <el-option v-for="p in results.param_names" :key="p" :label="p" :value="p" />
                </el-select>
              </el-form-item>
              <el-form-item label="Z 轴" class="mb-0">
                <el-select v-model="scatter3dZ" size="small" class="w-36">
                  <el-option v-for="p in results.param_names" :key="p" :label="p" :value="p" />
                </el-select>
              </el-form-item>
              <el-form-item label="颜色指标" class="mb-0">
                <el-select v-model="scatter3dMetric" size="small" class="w-40">
                  <el-option v-for="m in metricOptions" :key="m.value" :label="m.label" :value="m.value" />
                </el-select>
              </el-form-item>
            </div>
            <div ref="scatter3dRef" style="width:100%;height:600px"></div>
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onBeforeUnmount, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import 'echarts-gl'
import { strategyApi } from '@/api/strategy'
import { optimizationApi } from '@/api/optimization'
import type { OptimizationProgress, OptimizationResults, StrategyParam } from '@/api/optimization'

// ---- State ----

const phase = ref<'config' | 'running' | 'done'>('config')
const templates = ref<{ id: string; name: string }[]>([])
const selectedStrategy = ref('')
const paramRows = ref<any[]>([])
const nWorkers = ref(4)
const taskId = ref('')
const progress = ref<OptimizationProgress>({
  task_id: '', status: '', strategy_id: '', total: 0, completed: 0, failed: 0,
  progress: 0, n_workers: 0, created_at: '',
})
const results = ref<OptimizationResults | null>(null)
const resultTab = ref('table')

// Chart selectors
const heatmapXParam = ref('')
const heatmapYParam = ref('')
const heatmapMetric = ref('annual_return')
const boxParam = ref('')
const boxMetric = ref('annual_return')
const scatter3dX = ref('')
const scatter3dY = ref('')
const scatter3dZ = ref('')
const scatter3dMetric = ref('annual_return')

const metricOptions = [
  { label: '年化收益率', value: 'annual_return' },
  { label: '夏普率', value: 'sharpe_ratio' },
  { label: '最大回撤', value: 'max_drawdown' },
  { label: '总收益率', value: 'total_return' },
  { label: '交易次数', value: 'total_trades' },
  { label: '胜率', value: 'win_rate' },
]

// Chart refs
const heatmapRef = ref<HTMLElement | null>(null)
const boxplotRef = ref<HTMLElement | null>(null)
const scatter3dRef = ref<HTMLElement | null>(null)
let heatmapChart: echarts.ECharts | null = null
let boxplotChart: echarts.ECharts | null = null
let scatter3dChart: echarts.ECharts | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

// ---- Computed ----

function calcCount(row: any): number {
  if (!row.enabled || row.step <= 0) return 0
  return Math.floor((row.end - row.start) / row.step) + 1
}

const totalCombinations = computed(() => {
  const enabled = paramRows.value.filter(r => r.enabled)
  if (enabled.length === 0) return 0
  return enabled.reduce((acc, r) => acc * Math.max(calcCount(r), 1), 1)
})

// ---- Load templates ----

onMounted(async () => {
  try {
    const res = await strategyApi.getTemplates()
    templates.value = res.templates
  } catch { /* ignore */ }
})

async function onStrategyChange(strategyId: string) {
  if (!strategyId) { paramRows.value = []; return }
  try {
    const res = await optimizationApi.getStrategyParams(strategyId)
    paramRows.value = res.params.map((p: StrategyParam) => ({
      name: p.name,
      type: p.type,
      default: p.default,
      description: p.description,
      enabled: true,
      start: p.default,
      end: p.type === 'int' ? p.default + 10 : p.default * 2 || 1,
      step: p.type === 'int' ? 1 : Math.max(p.default * 0.1, 0.1),
    }))
  } catch (e: any) {
    ElMessage.error(e.message || '获取参数失败')
  }
}

// ---- Submit ----

async function startOptimization() {
  const enabled = paramRows.value.filter(r => r.enabled)
  if (enabled.length === 0) { ElMessage.warning('请至少启用一个参数'); return }

  const paramRanges: Record<string, any> = {}
  for (const r of enabled) {
    paramRanges[r.name] = { start: r.start, end: r.end, step: r.step, type: r.type }
  }

  try {
    const res = await optimizationApi.submit({
      strategy_id: selectedStrategy.value,
      param_ranges: paramRanges,
      n_workers: nWorkers.value,
    })
    taskId.value = res.task_id
    ElMessage.success(res.message)
    phase.value = 'running'
    startPolling()
  } catch (e: any) {
    ElMessage.error(e.message || '提交失败')
  }
}

// ---- Polling ----

function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const p = await optimizationApi.getProgress(taskId.value)
      progress.value = p
      if (p.status === 'completed' || p.status === 'error' || p.status === 'cancelled') {
        stopPolling()
        await loadResults()
      }
    } catch { /* ignore */ }
  }, 1500)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

async function cancelOpt() {
  try {
    await optimizationApi.cancel(taskId.value)
    ElMessage.info('已请求取消')
  } catch { /* ignore */ }
}

async function loadResults() {
  try {
    const r = await optimizationApi.getResults(taskId.value)
    results.value = r
    phase.value = 'done'

    // 初始化图表选择器
    if (r.param_names.length >= 1) {
      heatmapXParam.value = r.param_names[0]
      boxParam.value = r.param_names[0]
      scatter3dX.value = r.param_names[0]
    }
    if (r.param_names.length >= 2) {
      heatmapYParam.value = r.param_names[1]
      scatter3dY.value = r.param_names[1]
    }
    if (r.param_names.length >= 3) {
      scatter3dZ.value = r.param_names[2]
    }
  } catch (e: any) {
    ElMessage.error(e.message || '获取结果失败')
  }
}

// ---- Charts ----

function renderHeatmap() {
  if (!heatmapRef.value || !results.value) return
  if (!heatmapXParam.value || !heatmapYParam.value || heatmapXParam.value === heatmapYParam.value) return
  if (!heatmapChart) heatmapChart = echarts.init(heatmapRef.value)

  const rows = results.value.rows
  const xKey = heatmapXParam.value
  const yKey = heatmapYParam.value
  const mKey = heatmapMetric.value

  const xVals = [...new Set(rows.map(r => r[xKey]))].sort((a, b) => a - b)
  const yVals = [...new Set(rows.map(r => r[yKey]))].sort((a, b) => a - b)

  // Build lookup
  const lookup: Record<string, number> = {}
  for (const r of rows) {
    lookup[`${r[xKey]}_${r[yKey]}`] = r[mKey] ?? 0
  }

  const data: [number, number, number][] = []
  let minVal = Infinity, maxVal = -Infinity
  for (let xi = 0; xi < xVals.length; xi++) {
    for (let yi = 0; yi < yVals.length; yi++) {
      const v = lookup[`${xVals[xi]}_${yVals[yi]}`]
      if (v !== undefined) {
        data.push([xi, yi, v])
        if (v < minVal) minVal = v
        if (v > maxVal) maxVal = v
      }
    }
  }

  const metricLabel = metricOptions.find(m => m.value === mKey)?.label || mKey

  heatmapChart.setOption({
    tooltip: {
      position: 'top',
      formatter: (p: any) => `${xKey}=${xVals[p.data[0]]}, ${yKey}=${yVals[p.data[1]]}<br/>${metricLabel}: ${p.data[2]?.toFixed(4)}`,
    },
    grid: { left: 80, right: 120, top: 30, bottom: 60 },
    xAxis: { type: 'category', data: xVals.map(String), name: xKey },
    yAxis: { type: 'category', data: yVals.map(String), name: yKey },
    visualMap: {
      min: minVal, max: maxVal, calculable: true,
      orient: 'vertical', right: 10, top: 'center',
      inRange: { color: ['#313695', '#4575b4', '#74add1', '#abd9e9', '#fee090', '#fdae61', '#f46d43', '#d73027', '#a50026'] },
    },
    series: [{
      type: 'heatmap', data, label: { show: data.length < 200 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
    }],
  }, true)
}

function renderBoxplot() {
  if (!boxplotRef.value || !results.value) return
  if (!boxParam.value) return
  if (!boxplotChart) boxplotChart = echarts.init(boxplotRef.value)

  const rows = results.value.rows
  const pKey = boxParam.value
  const mKey = boxMetric.value

  // Group by param value
  const groups: Record<string, number[]> = {}
  for (const r of rows) {
    const key = String(r[pKey])
    if (!groups[key]) groups[key] = []
    groups[key].push(r[mKey] ?? 0)
  }

  const cats = Object.keys(groups).sort((a, b) => parseFloat(a) - parseFloat(b))
  const boxData: number[][] = []

  for (const cat of cats) {
    const arr = groups[cat].sort((a, b) => a - b)
    const n = arr.length
    const q1 = arr[Math.floor(n * 0.25)] ?? 0
    const q2 = arr[Math.floor(n * 0.5)] ?? 0
    const q3 = arr[Math.floor(n * 0.75)] ?? 0
    const low = arr[0] ?? 0
    const high = arr[n - 1] ?? 0
    boxData.push([low, q1, q2, q3, high])
  }

  const metricLabel = metricOptions.find(m => m.value === mKey)?.label || mKey

  boxplotChart.setOption({
    tooltip: { trigger: 'item' },
    grid: { left: 80, right: 30, top: 30, bottom: 60 },
    xAxis: { type: 'category', data: cats, name: pKey },
    yAxis: { type: 'value', name: metricLabel },
    series: [{
      type: 'boxplot',
      data: boxData,
      itemStyle: { color: '#5470c6', borderColor: '#333' },
    }],
  }, true)
}

function renderScatter3d() {
  if (!scatter3dRef.value || !results.value) return
  if (!scatter3dX.value || !scatter3dY.value || !scatter3dZ.value) return
  if (!scatter3dChart) scatter3dChart = echarts.init(scatter3dRef.value)

  const rows = results.value.rows
  const xKey = scatter3dX.value
  const yKey = scatter3dY.value
  const zKey = scatter3dZ.value
  const mKey = scatter3dMetric.value
  const metricLabel = metricOptions.find(m => m.value === mKey)?.label || mKey

  const data = rows.map(r => [r[xKey], r[yKey], r[zKey], r[mKey] ?? 0])
  const mVals = data.map(d => d[3])
  const minV = Math.min(...mVals)
  const maxV = Math.max(...mVals)

  scatter3dChart.setOption({
    tooltip: {
      formatter: (p: any) => {
        const d = p.data
        return `${xKey}=${d[0]}, ${yKey}=${d[1]}, ${zKey}=${d[2]}<br/>${metricLabel}: ${d[3]?.toFixed(4)}`
      },
    },
    visualMap: {
      min: minV, max: maxV, dimension: 3, inRange: {
        color: ['#313695', '#4575b4', '#74add1', '#fee090', '#f46d43', '#d73027', '#a50026'],
      },
      right: 10, top: 'center',
    },
    xAxis3D: { type: 'value', name: xKey },
    yAxis3D: { type: 'value', name: yKey },
    zAxis3D: { type: 'value', name: zKey },
    grid3D: {
      viewControl: { autoRotate: false, distance: 200 },
      light: { main: { intensity: 1.2 }, ambient: { intensity: 0.3 } },
    },
    series: [{
      type: 'scatter3D',
      data,
      symbolSize: 8,
      itemStyle: { opacity: 0.8 },
      emphasis: { itemStyle: { borderColor: '#000', borderWidth: 1 } },
    }],
  }, true)
}

// Watch chart selector changes
watch([heatmapXParam, heatmapYParam, heatmapMetric], () => {
  if (resultTab.value === 'heatmap') nextTick(renderHeatmap)
})
watch([boxParam, boxMetric], () => {
  if (resultTab.value === 'boxplot') nextTick(renderBoxplot)
})
watch([scatter3dX, scatter3dY, scatter3dZ, scatter3dMetric], () => {
  if (resultTab.value === 'scatter3d') nextTick(renderScatter3d)
})

watch(resultTab, (tab) => {
  nextTick(() => {
    if (tab === 'heatmap') renderHeatmap()
    else if (tab === 'boxplot') renderBoxplot()
    else if (tab === 'scatter3d') renderScatter3d()
  })
})

// Cleanup
onBeforeUnmount(() => {
  stopPolling()
  heatmapChart?.dispose()
  boxplotChart?.dispose()
  scatter3dChart?.dispose()
})
</script>
