<template>
  <div class="workspace-optimization-tab">
    <teleport to="#page-header-actions" :disabled="!props.toolbarInHeader || !props.active">
      <div
        class="flex items-center justify-between flex-wrap gap-2"
        :class="props.toolbarInHeader && props.active ? 'mb-0' : 'mb-4'"
      >
        <div class="flex items-center gap-2 flex-wrap">
        <el-select v-model="selectedUnitId" placeholder="选择单元查看优化结果" style="width: 300px" size="small" @change="loadResults">
          <el-option
            v-for="u in units"
            :key="u.id"
            :label="`${u.strategy_name || u.strategy_id} @ ${u.symbol}_${u.timeframe}`"
            :value="u.id"
          />
        </el-select>

        <!-- Group 1: Open / Save -->
        <el-button-group>
          <el-tooltip content="打开" placement="top">
            <el-button size="small" @click="handleOpenFile">
              <el-icon><FolderOpened /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="保存" placement="top">
            <el-button :disabled="!hasResults" size="small" @click="handleSaveResults">
              <el-icon><Download /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <!-- Group 2: Apply best params -->
        <el-button-group>
          <el-tooltip content="应用最佳参数" placement="top">
            <el-button :disabled="!hasResults" size="small" type="primary" @click="handleApplyBest">
              <el-icon><Check /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="应用最佳参数到图表和策略单元" placement="top">
            <el-button :disabled="!hasResults" size="small" type="success" @click="handleApplyBestAndOpen">
              <el-icon><Position /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="参数优化测试报告" placement="top">
            <el-button :disabled="!hasResults" size="small" @click="handleTestReport">
              <el-icon><Document /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <!-- Group 3: View mode -->
        <el-button-group>
          <el-tooltip content="表格" placement="top">
            <el-button size="small" :type="viewMode === 'table' ? 'primary' : ''" @click="viewMode = 'table'">
              <el-icon><Grid /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="折线图" placement="top">
            <el-button size="small" :type="viewMode === 'line' ? 'primary' : ''" @click="viewMode = 'line'">
              <el-icon><TrendCharts /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="面积图" placement="top">
            <el-button size="small" :type="viewMode === 'area' ? 'primary' : ''" @click="viewMode = 'area'">
              <el-icon><DataLine /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <!-- Group 4: Filter / Sort / Reset -->
        <el-button-group>
          <el-tooltip content="显示筛选" placement="top">
            <el-button size="small" @click="showFilter = !showFilter">
              <el-icon><Filter /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="还原" placement="top">
            <el-button size="small" @click="handleReset">
              <el-icon><RefreshLeft /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <!-- Group 5: Config -->
        <el-button-group>
          <el-tooltip content="统计时间" placement="top">
            <el-button size="small" @click="showStatTimeDialog = true">
              <el-icon><Timer /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="计算方式" placement="top">
            <el-button size="small" @click="showCalcMethodDialog = true">
              <el-icon><Operation /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="自定义字段" placement="top">
            <el-button size="small" @click="showCustomFieldsDialog = true">
              <el-icon><SetUp /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <!-- Group 6: Actions -->
        <el-button-group>
          <el-tooltip content="重新计算" placement="top">
            <el-button size="small" @click="loadResults">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="设为默认" placement="top">
            <el-button size="small" @click="handleSetDefault">
              <el-icon><Star /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <el-button v-if="selectedUnitId && optimizationStatus === 'running'" type="danger" size="small" @click="handleCancel">
          取消优化
        </el-button>
        </div>
      </div>
    </teleport>

    <!-- Stat Time Dialog -->
    <el-dialog v-model="showStatTimeDialog" title="统计时间" width="400px" destroy-on-close>
      <el-form label-width="100px" size="small">
        <el-form-item label="起始时间">
          <el-date-picker v-model="statTimeRange[0]" type="date" placeholder="选择起始日期" style="width: 100%" />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker v-model="statTimeRange[1]" type="date" placeholder="选择结束日期" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showStatTimeDialog = false">取消</el-button>
        <el-button type="primary" @click="showStatTimeDialog = false; loadResults()">确定</el-button>
      </template>
    </el-dialog>

    <!-- Calc Method Dialog -->
    <el-dialog v-model="showCalcMethodDialog" title="计算方式" width="400px" destroy-on-close>
      <el-form label-width="100px" size="small">
        <el-form-item label="收益计算">
          <el-radio-group v-model="calcMethod">
            <el-radio value="simple">简单收益</el-radio>
            <el-radio value="compound">复合收益</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="年化基准">
          <el-input-number v-model="annualDays" :min="200" :max="365" />
          <span class="ml-2 text-xs text-gray-400">天</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCalcMethodDialog = false">取消</el-button>
        <el-button type="primary" @click="showCalcMethodDialog = false; ElMessage.success('计算方式已更新')">确定</el-button>
      </template>
    </el-dialog>

    <!-- Custom Fields Dialog -->
    <el-dialog v-model="showCustomFieldsDialog" title="自定义字段" width="500px" destroy-on-close>
      <el-checkbox-group v-model="visibleFields">
        <div class="grid grid-cols-3 gap-2">
          <el-checkbox v-for="f in allFields" :key="f.key" :value="f.key">{{ f.label }}</el-checkbox>
        </div>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="visibleFields = allFields.map(f => f.key)">全选</el-button>
        <el-button @click="showCustomFieldsDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- Filter row -->
    <div v-if="showFilter" class="mb-3 flex gap-3 items-center">
      <span class="text-xs text-gray-400">排序:</span>
      <el-select v-model="sortKey" size="small" style="width: 140px" @change="applySort">
        <el-option label="夏普比率" value="sharpe_ratio" />
        <el-option label="年化收益" value="annual_return" />
        <el-option label="总收益率" value="total_return" />
        <el-option label="最大回撤" value="max_drawdown" />
        <el-option label="胜率" value="win_rate" />
        <el-option label="盈利因子" value="profit_factor" />
      </el-select>
      <el-radio-group v-model="sortDir" size="small" @change="applySort">
        <el-radio-button value="desc">降序</el-radio-button>
        <el-radio-button value="asc">升序</el-radio-button>
      </el-radio-group>
    </div>

    <!-- No unit selected -->
    <el-empty v-if="!selectedUnitId" description="请选择一个策略单元查看其优化结果" />

    <!-- Loading -->
    <div v-else-if="loading" class="flex justify-center py-10">
      <el-icon class="is-loading text-2xl text-blue-500"><Loading /></el-icon>
    </div>

    <!-- No results -->
    <el-empty v-else-if="!hasResults" description="该单元暂无优化结果。请先在策略单元工具栏中设置优化参数并提交优化。" />

    <!-- Results -->
    <template v-else>
      <!-- Progress bar if running -->
      <div v-if="optimizationStatus === 'running'" class="mb-4">
        <el-progress :percentage="progressPct" :format="() => `${completed}/${total}`" />
      </div>

      <!-- Summary cards -->
      <div class="grid grid-cols-4 gap-4 mb-4">
        <el-card shadow="never" class="text-center">
          <div class="text-sm text-gray-400">总组合数</div>
          <div class="text-xl font-bold">{{ total }}</div>
        </el-card>
        <el-card shadow="never" class="text-center">
          <div class="text-sm text-gray-400">已完成</div>
          <div class="text-xl font-bold text-green-600">{{ completed }}</div>
        </el-card>
        <el-card shadow="never" class="text-center">
          <div class="text-sm text-gray-400">最佳参数</div>
          <div class="text-lg font-medium">{{ bestParamsStr }}</div>
        </el-card>
        <el-card shadow="never" class="text-center">
          <div class="text-sm text-gray-400">最佳夏普</div>
          <div class="text-xl font-bold text-blue-600">{{ bestSharpe }}</div>
        </el-card>
      </div>

      <!-- Table view -->
      <el-table v-if="viewMode === 'table'" :data="displayRows" border stripe size="small" max-height="500" style="width: 100%">
        <el-table-column label="#" width="55" align="center" fixed>
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="参数值" min-width="150" fixed>
          <template #default="{ row }">{{ formatParams(row.params) }}</template>
        </el-table-column>
        <template v-for="col in activeColumns" :key="col.key">
          <el-table-column
            :label="col.label"
            :width="col.width"
            :align="col.align || 'right'"
            :sortable="col.sortable"
          >
            <template #default="{ row }">{{ col.money ? fmtMoney(row[col.key]) : col.int ? (row[col.key] ?? '-') : fmtVal(row[col.key]) }}</template>
          </el-table-column>
        </template>
      </el-table>

      <!-- Line chart (real ECharts) -->
      <div v-else-if="viewMode === 'line'">
        <el-card shadow="never" class="mb-4">
          <div class="text-sm text-gray-500 mb-2">折线图 - 按 {{ sortLabel }} 排序的前 {{ Math.min(displayRows.length, 200) }} 条优化结果</div>
          <v-chart v-if="displayRows.length" :option="lineChartOption" style="height: 360px; width: 100%" autoresize />
          <div v-else class="text-center text-gray-400 py-10">暂无数据</div>
        </el-card>
      </div>

      <!-- Area chart (real ECharts) -->
      <div v-else-if="viewMode === 'area'">
        <el-card shadow="never" class="mb-4">
          <div class="text-sm text-gray-500 mb-2">面积图 - 按 {{ sortLabel }} 排序的前 {{ Math.min(displayRows.length, 200) }} 条优化结果</div>
          <v-chart v-if="displayRows.length" :option="areaChartOption" style="height: 360px; width: 100%" autoresize />
          <div v-else class="text-center text-gray-400 py-10">暂无数据</div>
        </el-card>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import VChart from 'vue-echarts'
import {
  Loading, Check, Document, Filter, Refresh, Download,
  FolderOpened, Position, Grid, TrendCharts, DataLine,
  RefreshLeft, Timer, Operation, SetUp, Star,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { workspaceApi } from '@/api/workspace'
import { useWorkspaceStore } from '@/stores/workspace'
import { getErrorMessage } from '@/api/index'

const props = defineProps<{
  workspaceId: string
  active?: boolean
  toolbarInHeader?: boolean
}>()

const store = useWorkspaceStore()
const units = computed(() => store.units)

const selectedUnitId = ref('')
const loading = ref(false)
const optimizationStatus = ref('')
const total = ref(0)
const completed = ref(0)
const resultRows = ref<Record<string, unknown>[]>([])
// Original rows as returned by backend (sorted by objective) — used to map apply-best index
const backendRows = ref<Record<string, unknown>[]>([])
const showFilter = ref(false)
const sortKey = ref('sharpe_ratio')
const sortDir = ref<'asc' | 'desc'>('desc')
const viewMode = ref<'table' | 'line' | 'area'>('table')

const showStatTimeDialog = ref(false)
const showCalcMethodDialog = ref(false)
const showCustomFieldsDialog = ref(false)
const statTimeRange = ref<[string | null, string | null]>([null, null])
const calcMethod = ref('simple')
const annualDays = ref(252)

interface ColDef {
  key: string; label: string; width?: number; align?: string;
  sortable?: boolean; money?: boolean; int?: boolean;
}
const allColumnDefs: ColDef[] = [
  { key: 'initial_cash', label: '初始资金', width: 100, money: true },
  { key: 'net_value', label: '净值', width: 80 },
  { key: 'net_profit', label: '净利润', width: 100, money: true },
  { key: 'annual_return', label: '年化收益率%', width: 100, sortable: true },
  { key: 'max_leverage', label: '最大杠杆', width: 80 },
  { key: 'max_market_value', label: '最大市值', width: 100, money: true },
  { key: 'max_drawdown_value', label: '最大回撤值', width: 100, money: true },
  { key: 'max_drawdown', label: '最大回撤%', width: 90, sortable: true },
  { key: 'sharpe_ratio', label: '夏普比率', width: 85, sortable: true },
  { key: 'adjusted_return_risk', label: '收益风险比', width: 90 },
  { key: 'total_trades', label: '交易次数', width: 80, align: 'center', int: true },
  { key: 'win_rate', label: '胜率%', width: 70, sortable: true },
  { key: 'avg_profit', label: '平均利润', width: 90, money: true },
  { key: 'avg_profit_rate', label: '平均利润率%', width: 100 },
  { key: 'total_win_amount', label: '总盈利', width: 100, money: true },
  { key: 'total_loss_amount', label: '总亏损', width: 100, money: true },
  { key: 'profit_loss_ratio', label: '盈亏比', width: 80 },
  { key: 'profit_factor', label: '盈利因子', width: 80, sortable: true },
  { key: 'profit_rate_factor', label: '盈利率因子', width: 90 },
  { key: 'profit_loss_rate_ratio', label: '盈亏率比', width: 80 },
  { key: 'odds', label: '胜算率%', width: 80 },
  { key: 'daily_avg_return', label: '日均收益%', width: 90 },
  { key: 'daily_max_loss', label: '日最大亏损%', width: 100 },
  { key: 'daily_max_profit', label: '日最大盈利%', width: 100 },
  { key: 'weekly_avg_return', label: '周均收益%', width: 90 },
  { key: 'weekly_max_loss', label: '周最大亏损%', width: 100 },
  { key: 'weekly_max_profit', label: '周最大盈利%', width: 100 },
  { key: 'monthly_avg_return', label: '月均收益%', width: 90 },
  { key: 'monthly_max_loss', label: '月最大亏损%', width: 100 },
  { key: 'monthly_max_profit', label: '月最大盈利%', width: 100 },
  { key: 'trading_cost', label: '交易成本', width: 90, money: true },
  { key: 'trading_days', label: '交易日数', width: 80, align: 'center', int: true },
]
const allFields = allColumnDefs.map(c => ({ key: c.key, label: c.label }))
const visibleFields = ref(allFields.map(f => f.key))

const activeColumns = computed(() =>
  allColumnDefs.filter(c => visibleFields.value.includes(c.key))
)
const openFileInput = ref<HTMLInputElement | null>(null)

const hasResults = computed(() => resultRows.value.length > 0 || optimizationStatus.value === 'running')
const progressPct = computed(() => total.value > 0 ? Math.round((completed.value / total.value) * 100) : 0)

// Recalculate annual_return based on user's calcMethod + annualDays settings
function _recalcAnnual(row: Record<string, unknown>): number | null {
  const tr = row.total_return as number | undefined
  const td = row.trading_days as number | undefined
  if (tr == null || !td || td <= 0) return (row.annual_return as number) ?? null
  if (calcMethod.value === 'compound') {
    try { return Math.pow(1 + tr, annualDays.value / td) - 1 } catch { return (row.annual_return as number) ?? null }
  }
  return tr * (annualDays.value / td)
}

const displayRows = computed(() => {
  const rows = resultRows.value.map(r => {
    const recalced = _recalcAnnual(r)
    return recalced != null && recalced !== r.annual_return
      ? { ...r, annual_return: recalced }
      : r
  })
  const key = sortKey.value
  const dir = sortDir.value === 'desc' ? -1 : 1
  rows.sort((a, b) => {
    const va = (a[key] as number) ?? 0
    const vb = (b[key] as number) ?? 0
    return (va - vb) * dir
  })
  return rows
})

const bestParamsStr = computed(() => {
  if (!displayRows.value.length) return '-'
  const best = displayRows.value[0]
  const params = best.params as Record<string, number> | undefined
  if (!params) return '-'
  return Object.entries(params).map(([k, v]) => `${k}=${v}`).join(', ')
})

const bestSharpe = computed(() => {
  if (!displayRows.value.length) return '-'
  const val = displayRows.value[0].sharpe_ratio
  return typeof val === 'number' ? val.toFixed(4) : '-'
})

// --- Bug-11 fix: restore saved optimization display config on mount ---
function _restoreOptDefaults() {
  const oc = (store.currentWorkspace?.settings as Record<string, any>)?.optimization_config
  if (!oc) return
  if (oc.sort_key) sortKey.value = oc.sort_key
  if (oc.sort_dir) sortDir.value = oc.sort_dir
  if (oc.view_mode) viewMode.value = oc.view_mode
  if (oc.calc_method) calcMethod.value = oc.calc_method
  if (oc.annual_days) annualDays.value = oc.annual_days
  if (oc.stat_time_range) statTimeRange.value = oc.stat_time_range
  if (oc.visible_fields) visibleFields.value = oc.visible_fields
}

onMounted(() => {
  _restoreOptDefaults()
  if (!store.units.length) {
    store.fetchUnits(props.workspaceId)
  }
})

async function loadResults() {
  if (!selectedUnitId.value) return
  loading.value = true
  try {
    const progress = await workspaceApi.getOptimizationProgress(props.workspaceId, selectedUnitId.value).catch(() => null)
    if (progress) {
      optimizationStatus.value = (progress.status as string) || ''
      total.value = (progress.total as number) || 0
      completed.value = (progress.completed as number) || 0
    }

    const results = await workspaceApi.getOptimizationResults(props.workspaceId, selectedUnitId.value).catch(() => null)
    // Backend returns `rows`; also tolerate legacy `results` key
    const rowsData = results?.rows ?? results?.results
    if (results && rowsData) {
      const rows = rowsData as Record<string, unknown>[]
      resultRows.value = rows
      backendRows.value = [...rows]  // snapshot of backend sort order
      optimizationStatus.value = (results.status as string) || optimizationStatus.value
      total.value = (results.total as number) || total.value
      completed.value = (results.completed as number) || completed.value
      // Sync default sort to backend's objective
      if (results.objective && typeof results.objective === 'string') {
        sortKey.value = results.objective
        sortDir.value = results.objective === 'max_drawdown' ? 'asc' : 'desc'
      }
    } else {
      resultRows.value = []
      backendRows.value = []
    }
  } catch {
    resultRows.value = []
  } finally {
    loading.value = false
  }
}

function applySort() {
  // displayRows is a computed that auto-sorts
}

// --- Auto-polling for optimization progress (Bug-8 fix) ---
let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (!selectedUnitId.value) return
    try {
      const progress = await workspaceApi.getOptimizationProgress(props.workspaceId, selectedUnitId.value).catch(() => null)
      if (progress) {
        optimizationStatus.value = (progress.status as string) || ''
        total.value = (progress.total as number) || 0
        completed.value = (progress.completed as number) || 0
      }
      // If terminal state, load final results and stop polling
      if (['completed', 'failed', 'cancelled'].includes(optimizationStatus.value)) {
        stopPolling()
        await loadResults()
      }
    } catch { /* ignore polling errors */ }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

watch(optimizationStatus, (val) => {
  if (val === 'running') {
    startPolling()
  } else {
    stopPolling()
  }
})

onBeforeUnmount(() => stopPolling())

// --- Open / Save ---
function handleOpenFile() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      if (data.results && Array.isArray(data.results)) {
        resultRows.value = data.results
        ElMessage.success(`已加载 ${data.results.length} 条优化结果`)
      } else {
        ElMessage.warning('文件格式不正确')
      }
    } catch {
      ElMessage.error('读取文件失败')
    }
  }
  input.click()
}

function handleSaveResults() {
  if (!resultRows.value.length) return
  const data = {
    unit_id: selectedUnitId.value,
    exported_at: new Date().toISOString(),
    results: resultRows.value,
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `opt_results_${selectedUnitId.value.slice(0, 8)}_${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('优化结果已保存')
}

// --- Apply best + open chart ---
async function handleApplyBestAndOpen() {
  await handleApplyBest()
  const unit = units.value.find(u => u.id === selectedUnitId.value)
  if (unit) {
    window.open(`/backtest/legacy?symbol=${unit.symbol}&timeframe=${unit.timeframe}`, '_blank')
  }
}

// --- Test report ---
function handleTestReport() {
  if (!displayRows.value.length) return
  const best = displayRows.value[0]
  const lines = [
    '=== 参数优化测试报告 ===',
    `单元: ${selectedUnitId.value}`,
    `总组合: ${total.value}`,
    `最佳参数: ${formatParams(best.params)}`,
    `夏普比率: ${fmtVal(best.sharpe_ratio)}`,
    `年化收益: ${fmtVal(best.annual_return)}`,
    `最大回撤: ${fmtVal(best.max_drawdown)}`,
    `胜率: ${fmtVal(best.win_rate)}`,
    `盈利因子: ${fmtVal(best.profit_factor)}`,
    `交易次数: ${best.total_trades ?? '-'}`,
  ]
  ElMessageBox.alert(lines.join('\n'), '参数优化测试报告', {
    confirmButtonText: '关闭',
    customStyle: { whiteSpace: 'pre-wrap', fontFamily: 'monospace' } as any,
  })
}

// --- Reset ---
function handleReset() {
  sortKey.value = 'sharpe_ratio'
  sortDir.value = 'desc'
  showFilter.value = false
  viewMode.value = 'table'
  visibleFields.value = allFields.map(f => f.key)
  ElMessage.success('已还原默认设置')
}

// --- Set as default (Bug-9 fix: persist to workspace.settings) ---
async function handleSetDefault() {
  try {
    await workspaceApi.update(props.workspaceId, {
      settings: {
        optimization_config: {
          sort_key: sortKey.value,
          sort_dir: sortDir.value,
          view_mode: viewMode.value,
          calc_method: calcMethod.value,
          annual_days: annualDays.value,
          stat_time_range: statTimeRange.value,
          visible_fields: visibleFields.value,
        },
      },
    })
    ElMessage.success('已保存为默认优化结果配置')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '保存默认配置失败'))
  }
}

async function handleCancel() {
  if (!selectedUnitId.value) return
  try {
    await workspaceApi.cancelOptimization(props.workspaceId, selectedUnitId.value)
    ElMessage.success('优化任务已取消')
    await loadResults()
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '取消失败'))
  }
}

async function handleApplyBest() {
  if (!selectedUnitId.value || !displayRows.value.length) return
  const unit = units.value.find(u => u.id === selectedUnitId.value)
  const taskId = unit?.last_optimization_task_id
  if (!taskId) {
    ElMessage.warning('未找到优化任务ID')
    return
  }
  // The displayed best row (index 0 after local sort)
  const bestRow = displayRows.value[0]
  // Find the matching index in the backend's sorted rows
  let backendIdx = backendRows.value.indexOf(bestRow)
  if (backendIdx < 0) backendIdx = 0
  try {
    await ElMessageBox.confirm('确认将最佳参数应用到该策略单元？', '应用最佳参数', { type: 'info' })
    await workspaceApi.applyBestParams(props.workspaceId, {
      unit_id: selectedUnitId.value,
      optimization_task_id: taskId,
      result_index: backendIdx,
    })
    ElMessage.success('最佳参数已应用')
    store.fetchUnits(props.workspaceId)
  } catch (e: unknown) {
    if (e !== 'cancel' && (e as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(e, '应用失败'))
    }
  }
}

function formatParams(params: unknown) {
  if (!params || typeof params !== 'object') return '-'
  return Object.entries(params as Record<string, number>)
    .map(([k, v]) => `${k}=${v}`)
    .join(', ')
}

function fmtVal(val: unknown) {
  if (val == null) return '-'
  return typeof val === 'number' ? val.toFixed(4) : String(val)
}

function fmtMoney(val: unknown) {
  if (val == null) return '-'
  return typeof val === 'number' ? val.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : String(val)
}

function getBarHeight(row: Record<string, unknown>): number {
  const val = row[sortKey.value]
  if (typeof val !== 'number') return 5
  const rows = displayRows.value
  const vals = rows.map(r => (typeof r[sortKey.value] === 'number' ? r[sortKey.value] as number : 0))
  const maxV = Math.max(...vals.map(Math.abs), 1)
  return Math.max(5, Math.round((Math.abs(val) / maxV) * 180))
}

// --- ECharts options (Bug-9 fix) ---
const chartData = computed(() => {
  const rows = displayRows.value.slice(0, 200)
  const labels = rows.map((_, i) => `#${i + 1}`)
  const values = rows.map(r => {
    const v = r[sortKey.value]
    return typeof v === 'number' ? v : 0
  })
  return { labels, values }
})

const sortLabel = computed(() => {
  const col = allColumnDefs.find(c => c.key === sortKey.value)
  return col ? col.label : sortKey.value
})

const lineChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: chartData.value.labels, axisLabel: { show: false } },
  yAxis: { type: 'value', name: sortLabel.value },
  grid: { left: 60, right: 20, top: 30, bottom: 30 },
  series: [{
    name: sortLabel.value,
    type: 'line',
    data: chartData.value.values,
    smooth: true,
    lineStyle: { width: 2, color: '#3b82f6' },
    itemStyle: { color: '#3b82f6' },
    symbolSize: 0,
  }],
}))

const areaChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: chartData.value.labels, axisLabel: { show: false } },
  yAxis: { type: 'value', name: sortLabel.value },
  grid: { left: 60, right: 20, top: 30, bottom: 30 },
  series: [{
    name: sortLabel.value,
    type: 'line',
    data: chartData.value.values,
    smooth: true,
    areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(16,185,129,0.4)' }, { offset: 1, color: 'rgba(16,185,129,0.05)' }] } },
    lineStyle: { width: 2, color: '#10b981' },
    itemStyle: { color: '#10b981' },
    symbolSize: 0,
  }],
}))
</script>
