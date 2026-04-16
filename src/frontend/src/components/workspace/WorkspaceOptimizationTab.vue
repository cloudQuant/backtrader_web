<template>
  <div class="workspace-optimization-tab">
    <teleport
      to="#page-header-actions"
      :disabled="!props.toolbarInHeader || !props.active"
    >
      <div
        class="flex items-center justify-between flex-wrap gap-2"
        :class="props.toolbarInHeader && props.active ? 'mb-0' : 'mb-4'"
      >
        <div class="flex items-center gap-2 flex-wrap">
          <el-select
            v-model="selectedUnitId"
            placeholder="选择单元查看优化结果"
            style="width: 300px"
            size="small"
            @change="loadResults"
          >
            <el-option
              v-for="u in units"
              :key="u.id"
              :label="`${u.strategy_name || u.strategy_id} @ ${u.symbol}_${u.timeframe}`"
              :value="u.id"
            />
          </el-select>

          <!-- Group 1: Open / Save -->
          <el-button-group>
            <el-tooltip
              content="打开"
              placement="top"
            >
              <el-button
                size="small"
                @click="handleOpenFile"
              >
                <el-icon><FolderOpened /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="保存"
              placement="top"
            >
              <el-button
                :disabled="!hasResults"
                size="small"
                @click="handleSaveResults"
              >
                <el-icon><Download /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <!-- Group 2: Apply best params -->
          <el-button-group>
            <el-tooltip
              content="应用最佳参数"
              placement="top"
            >
              <el-button
                :disabled="!hasResults"
                size="small"
                type="primary"
                @click="handleApplyBest"
              >
                <el-icon><Check /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="应用最佳参数到图表和策略单元"
              placement="top"
            >
              <el-button
                :disabled="!hasResults"
                size="small"
                type="success"
                @click="handleApplyBestAndOpen"
              >
                <el-icon><Position /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="参数优化测试报告"
              placement="top"
            >
              <el-button
                :disabled="!hasResults"
                size="small"
                @click="handleTestReport"
              >
                <el-icon><Document /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <!-- Group 3: View mode -->
          <el-button-group>
            <el-tooltip
              content="表格"
              placement="top"
            >
              <el-button
                size="small"
                :type="viewMode === 'table' ? 'primary' : ''"
                @click="viewMode = 'table'"
              >
                <el-icon><Grid /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="参数分析"
              placement="top"
            >
              <el-button
                size="small"
                :type="viewMode === 'analysis' ? 'primary' : ''"
                @click="viewMode = 'analysis'"
              >
                <el-icon><Operation /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <!-- Group 4: Filter / Sort / Reset -->
          <el-button-group>
            <el-tooltip
              content="显示筛选"
              placement="top"
            >
              <el-button
                size="small"
                @click="showFilter = !showFilter"
              >
                <el-icon><Filter /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="还原"
              placement="top"
            >
              <el-button
                size="small"
                @click="handleReset"
              >
                <el-icon><RefreshLeft /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <!-- Group 5: Config -->
          <el-button-group>
            <el-tooltip
              content="统计时间"
              placement="top"
            >
              <el-button
                size="small"
                @click="showStatTimeDialog = true"
              >
                <el-icon><Timer /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="计算方式"
              placement="top"
            >
              <el-button
                size="small"
                @click="showCalcMethodDialog = true"
              >
                <el-icon><Operation /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="自定义字段"
              placement="top"
            >
              <el-button
                size="small"
                @click="showCustomFieldsDialog = true"
              >
                <el-icon><SetUp /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <!-- Group 6: Actions -->
          <el-button-group>
            <el-tooltip
              content="重新计算"
              placement="top"
            >
              <el-button
                size="small"
                @click="loadResults"
              >
                <el-icon><Refresh /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="设为默认"
              placement="top"
            >
              <el-button
                size="small"
                @click="handleSetDefault"
              >
                <el-icon><Star /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <el-button
            v-if="selectedUnitId && optimizationStatus === 'running'"
            type="danger"
            size="small"
            @click="handleCancel"
          >
            取消优化
          </el-button>
        </div>
      </div>
    </teleport>

    <!-- Stat Time Dialog -->
    <el-dialog
      v-model="showStatTimeDialog"
      title="统计时间"
      width="400px"
      destroy-on-close
    >
      <el-form
        label-width="100px"
        size="small"
      >
        <el-form-item label="起始时间">
          <el-date-picker
            v-model="statTimeRange[0]"
            type="date"
            placeholder="选择起始日期"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker
            v-model="statTimeRange[1]"
            type="date"
            placeholder="选择结束日期"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showStatTimeDialog = false">
          取消
        </el-button>
        <el-button
          type="primary"
          @click="showStatTimeDialog = false; loadResults()"
        >
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- Calc Method Dialog -->
    <el-dialog
      v-model="showCalcMethodDialog"
      title="计算方式"
      width="400px"
      destroy-on-close
    >
      <el-form
        label-width="100px"
        size="small"
      >
        <el-form-item label="收益计算">
          <el-radio-group v-model="calcMethod">
            <el-radio value="simple">
              简单收益
            </el-radio>
            <el-radio value="compound">
              复合收益
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="年化基准">
          <el-input-number
            v-model="annualDays"
            :min="200"
            :max="365"
          />
          <span class="ml-2 text-xs text-gray-400">天</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCalcMethodDialog = false">
          取消
        </el-button>
        <el-button
          type="primary"
          @click="showCalcMethodDialog = false; ElMessage.success('计算方式已更新')"
        >
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- Custom Fields Dialog -->
    <el-dialog
      v-model="showCustomFieldsDialog"
      title="自定义字段"
      width="500px"
      destroy-on-close
    >
      <el-checkbox-group v-model="visibleFields">
        <div class="grid grid-cols-3 gap-2">
          <el-checkbox
            v-for="f in allFields"
            :key="f.key"
            :value="f.key"
          >
            {{ f.label }}
          </el-checkbox>
        </div>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="visibleFields = allFields.map(f => f.key)">
          全选
        </el-button>
        <el-button @click="showCustomFieldsDialog = false">
          关闭
        </el-button>
      </template>
    </el-dialog>

    <!-- Filter row -->
    <div
      v-if="showFilter"
      class="mb-3 flex gap-3 items-center"
    >
      <span class="text-xs text-gray-400">排序:</span>
      <el-select
        v-model="sortKey"
        size="small"
        style="width: 140px"
        @change="applySort"
      >
        <el-option
          label="夏普比率"
          value="sharpe_ratio"
        />
        <el-option
          label="年化收益"
          value="annual_return"
        />
        <el-option
          label="总收益率"
          value="total_return"
        />
        <el-option
          label="最大回撤"
          value="max_drawdown"
        />
        <el-option
          label="胜率"
          value="win_rate"
        />
        <el-option
          label="盈利因子"
          value="profit_factor"
        />
      </el-select>
      <el-radio-group
        v-model="sortDir"
        size="small"
        @change="applySort"
      >
        <el-radio-button value="desc">
          降序
        </el-radio-button>
        <el-radio-button value="asc">
          升序
        </el-radio-button>
      </el-radio-group>
    </div>

    <!-- No unit selected -->
    <el-empty
      v-if="!selectedUnitId"
      description="请选择一个策略单元查看其优化结果"
    />

    <!-- Loading -->
    <div
      v-else-if="loading"
      class="flex justify-center py-10"
    >
      <el-icon class="is-loading text-2xl text-blue-500">
        <Loading />
      </el-icon>
    </div>

    <!-- No results -->
    <el-empty
      v-else-if="!hasResults"
      :description="emptyStateDescription"
    />

    <!-- Results -->
    <template v-else>
      <!-- Progress bar if running -->
      <div
        v-if="optimizationStatus === 'running'"
        class="mb-4"
      >
        <el-progress
          :percentage="progressPct"
          :format="() => `${completed}/${total}`"
        />
      </div>

      <!-- Summary cards -->
      <div class="grid grid-cols-4 gap-4 mb-4">
        <el-card
          shadow="never"
          class="text-center"
        >
          <div class="text-sm text-gray-400">
            总组合数
          </div>
          <div class="text-xl font-bold">
            {{ total }}
          </div>
        </el-card>
        <el-card
          shadow="never"
          class="text-center"
        >
          <div class="text-sm text-gray-400">
            已完成
          </div>
          <div class="text-xl font-bold text-green-600">
            {{ completed }}
          </div>
        </el-card>
        <el-card
          shadow="never"
          class="text-center"
        >
          <div class="text-sm text-gray-400">
            最佳参数
          </div>
          <div class="text-lg font-medium">
            {{ bestParamsStr }}
          </div>
        </el-card>
        <el-card
          shadow="never"
          class="text-center"
        >
          <div class="text-sm text-gray-400">
            最佳夏普
          </div>
          <div class="text-xl font-bold text-blue-600">
            {{ bestSharpe }}
          </div>
        </el-card>
      </div>

      <!-- Table view -->
      <el-table
        v-if="viewMode === 'table'"
        :data="displayRows"
        border
        stripe
        size="small"
        max-height="500"
        style="width: 100%"
      >
        <el-table-column
          label="#"
          width="55"
          align="center"
          fixed
        >
          <template #default="{ $index }">
            {{ $index + 1 }}
          </template>
        </el-table-column>
        <template
          v-for="paramName in paramNames"
          :key="`param-${paramName}`"
        >
          <el-table-column
            :label="paramName"
            min-width="110"
            align="center"
          >
            <template #default="{ row }">
              {{ row[paramName] ?? '-' }}
            </template>
          </el-table-column>
        </template>
        <template
          v-for="col in activeColumns"
          :key="col.key"
        >
          <el-table-column
            :label="col.label"
            :width="col.width"
            :align="col.align || 'right'"
            :sortable="col.sortable"
          >
            <template #default="{ row }">
              {{ col.money ? fmtMoney(row[col.key]) : col.int ? (row[col.key] ?? '-') : fmtVal(row[col.key]) }}
            </template>
          </el-table-column>
        </template>
        <el-table-column
          label="操作"
          width="120"
          align="center"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              size="small"
              :loading="runningRow === row"
              @click="handleRunWithParams(row)"
            >
              回测详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Analysis view -->
      <div v-else-if="viewMode === 'analysis'">
        <el-card
          shadow="never"
          class="mb-4"
        >
          <div class="flex flex-wrap items-center gap-3 mb-4">
            <span class="text-sm text-gray-500">参数</span>
            <el-select
              v-model="selectedAnalysisParams"
              multiple
              collapse-tags
              collapse-tags-tooltip
              :multiple-limit="3"
              placeholder="选择 1-3 个参数"
              size="small"
              style="width: 360px"
            >
              <el-option
                v-for="paramName in paramNames"
                :key="`analysis-param-${paramName}`"
                :label="paramName"
                :value="paramName"
              />
            </el-select>
            <span class="text-sm text-gray-500">目标值</span>
            <el-select
              v-model="analysisMetric"
              placeholder="选择目标值"
              size="small"
              style="width: 220px"
            >
              <el-option
                v-for="option in metricOptions"
                :key="`analysis-metric-${option.value}`"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </div>
          <div class="text-sm text-gray-500 mb-3">
            {{ analysisDescription }}
          </div>
          <div
            v-if="selectedAnalysisMode"
            ref="analysisChartRef"
            :style="{ height: selectedAnalysisMode === 'scatter3d' ? '520px' : '420px', width: '100%' }"
          />
          <div
            v-else
            class="text-center text-gray-400 py-12"
          >
            请选择 1-3 个参数进行分析
          </div>
        </el-card>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import 'echarts-gl'
import { useRouter } from 'vue-router'
import {
  Loading, Check, Document, Filter, Refresh, Download,
  FolderOpened, Position, Grid,
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
  initialUnitId?: string
}>()

const store = useWorkspaceStore()
const router = useRouter()
const units = computed(() => store.units)

const selectedUnitId = ref('')
const loading = ref(false)
const optimizationStatus = ref('')
const total = ref(0)
const completed = ref(0)
const failed = ref(0)
const resultRows = ref<Record<string, unknown>[]>([])
const paramNames = ref<string[]>([])
const optimizationTaskId = ref('')
const showFilter = ref(false)
const sortKey = ref('sharpe_ratio')
const sortDir = ref<'asc' | 'desc'>('desc')
const viewMode = ref<'table' | 'analysis'>('table')

const showStatTimeDialog = ref(false)
const showCalcMethodDialog = ref(false)
const showCustomFieldsDialog = ref(false)
const statTimeRange = ref<[string | null, string | null]>([null, null])
const calcMethod = ref('simple')
const annualDays = ref(252)
const selectedAnalysisParams = ref<string[]>([])
const analysisMetric = ref('sharpe_ratio')
const analysisChartRef = ref<HTMLElement | null>(null)
let analysisChart: echarts.ECharts | null = null

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

const hasResults = computed(() => resultRows.value.length > 0 || optimizationStatus.value === 'running')
const progressPct = computed(() => total.value > 0 ? Math.round((completed.value / total.value) * 100) : 0)
const emptyStateDescription = computed(() => {
  if (optimizationStatus.value === 'cancelled') {
    return '该优化任务已取消。'
  }
  if (optimizationStatus.value === 'failed') {
    return '该优化任务执行失败，请检查参数范围、数据配置或后端日志。'
  }
  if (optimizationStatus.value === 'completed' && failed.value > 0 && completed.value === 0) {
    return `该单元优化已结束，但 ${failed.value} 组参数全部失败，因此没有可展示的优化结果。`
  }
  if (optimizationStatus.value === 'completed' && failed.value > 0) {
    return `该单元优化已结束，但仅部分组合成功。当前无可展示结果，请检查失败任务日志。`
  }
  return '该单元暂无优化结果。请先在策略单元工具栏中设置优化参数并提交优化。'
})

// Recalculate annual_return based on user's calcMethod + annualDays settings
function _recalcAnnual(row: Record<string, unknown>): number | null {
  const tr = row.total_return as number | undefined
  const td = row.trading_days as number | undefined
  if (tr == null || !td || td <= 0) return (row.annual_return as number) ?? null
  if (calcMethod.value === 'compound') {
    try { return (Math.pow(1 + tr / 100, annualDays.value / td) - 1) * 100 } catch { return (row.annual_return as number) ?? null }
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
  if (oc.view_mode === 'analysis' || oc.view_mode === 'table') viewMode.value = oc.view_mode
  if (oc.calc_method) calcMethod.value = oc.calc_method
  if (oc.annual_days) annualDays.value = oc.annual_days
  if (oc.stat_time_range) statTimeRange.value = oc.stat_time_range
  if (oc.visible_fields) visibleFields.value = oc.visible_fields
  if (Array.isArray(oc.analysis_params)) selectedAnalysisParams.value = oc.analysis_params.slice(0, 3)
  if (oc.analysis_metric) analysisMetric.value = oc.analysis_metric
}

onMounted(async () => {
  _restoreOptDefaults()
  if (!store.units.length) {
    await store.fetchUnits(props.workspaceId)
  }
  window.addEventListener('resize', handleResize)
  // Auto-select initial unit if provided
  if (props.initialUnitId) {
    selectedUnitId.value = props.initialUnitId
    await loadResults()
  }
})

watch(() => props.initialUnitId, async (newId) => {
  if (newId && newId !== selectedUnitId.value) {
    selectedUnitId.value = newId
    await loadResults()
  }
})

watch(() => props.active, async (isActive) => {
  if (isActive && selectedUnitId.value) {
    await loadResults()
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
      failed.value = (progress.failed as number) || 0
    }

    const results = await workspaceApi.getOptimizationResults(props.workspaceId, selectedUnitId.value).catch(() => null)
    // Backend returns `rows`; also tolerate legacy `results` key
    const rowsData = results?.rows ?? results?.results
    if (results && rowsData) {
      const rows = rowsData as Record<string, unknown>[]
      resultRows.value = rows
      paramNames.value = Array.isArray(results.param_names) ? (results.param_names as string[]) : deriveParamNames(rows)
      optimizationTaskId.value = typeof results.task_id === 'string' ? results.task_id : ''
      optimizationStatus.value = (results.status as string) || optimizationStatus.value
      total.value = (results.total as number) || total.value
      completed.value = (results.completed as number) || completed.value
      failed.value = (results.failed as number) || failed.value
      // Sync default sort to backend's objective
      if (results.objective && typeof results.objective === 'string') {
        sortKey.value = results.objective
        sortDir.value = results.objective === 'max_drawdown' ? 'asc' : 'desc'
      }
      initializeAnalysisControls(typeof results.objective === 'string' ? results.objective : sortKey.value)
    } else {
      resultRows.value = []
      paramNames.value = []
      optimizationTaskId.value = ''
      selectedAnalysisParams.value = []
    }
  } catch {
    resultRows.value = []
    paramNames.value = []
    optimizationTaskId.value = ''
    selectedAnalysisParams.value = []
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
        failed.value = (progress.failed as number) || 0
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
       paramNames.value = Array.isArray(data.param_names) ? (data.param_names as string[]) : deriveParamNames(data.results)
       initializeAnalysisControls(typeof data.objective === 'string' ? data.objective : sortKey.value)
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
     param_names: paramNames.value,
     objective: sortKey.value,
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
           analysis_params: selectedAnalysisParams.value,
           analysis_metric: analysisMetric.value,
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
  const bestRow = displayRows.value[0]
  const backendIdx = typeof bestRow.result_index === 'number' ? bestRow.result_index : 0
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

const runningRow = ref<Record<string, unknown> | null>(null)

async function handleRunWithParams(row: Record<string, unknown>) {
  if (!selectedUnitId.value) return
  const resultIndex = typeof row.result_index === 'number' ? row.result_index : null
  const artifactPath = typeof row.artifact_path === 'string' ? row.artifact_path : ''
  if (optimizationTaskId.value && resultIndex !== null && artifactPath) {
    router.push({
      name: 'BacktestResult',
      params: { id: optimizationTaskId.value },
      query: {
        workspaceId: props.workspaceId,
        optimizationUnitId: selectedUnitId.value,
        optimizationResultIndex: String(resultIndex),
      },
    })
    return
  }
  const unit = units.value.find(u => u.id === selectedUnitId.value)
  if (!unit) return
  const params = row.params as Record<string, number> | undefined
  if (!params) {
    ElMessage.warning('该行无参数信息')
    return
  }
  runningRow.value = row
  let pollStarted = false
  try {
    // 1. Apply params to unit, preserving non-optimized params
    await workspaceApi.updateUnit(props.workspaceId, unit.id, {
      params: {
        ...(unit.params || {}),
        ...params,
      },
    })
    // 2. Run the unit
    const res = await workspaceApi.runUnits(props.workspaceId, [unit.id], false)
    const result = res.results?.[0]
    if (result?.task_id) {
      pollStarted = true
      ElMessage.success('回测已提交，待完成后自动跳转')
      // 3. Poll until done, then navigate
      const pollId = setInterval(async () => {
        try {
          const statuses = await workspaceApi.getUnitsStatus(props.workspaceId)
          const s = statuses.find(x => x.id === unit.id)
          if (s && (s.run_status === 'completed' || s.run_status === 'failed')) {
            clearInterval(pollId)
            runningRow.value = null
            if (s.run_status === 'completed' && s.last_task_id) {
              router.push({
                name: 'BacktestResult',
                params: { id: s.last_task_id as string },
                query: { workspaceId: props.workspaceId },
              })
            } else {
              ElMessage.error('回测失败')
            }
          }
        } catch { /* ignore */ }
      }, 2000)
      // Safety timeout: stop polling after 10 minutes
      setTimeout(() => { clearInterval(pollId); runningRow.value = null }, 600000)
    } else {
      ElMessage.warning('回测提交未返回任务ID')
    }
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '提交回测失败'))
  } finally {
    if (!pollStarted && runningRow.value === row) runningRow.value = null
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
  return typeof val === 'number'
    ? val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
    : String(val)
}

function formatMetricValue(metricKey: string, value: number | null) {
  if (value == null || !Number.isFinite(value)) return '-'
  const col = allColumnDefs.find(item => item.key === metricKey)
  if (col?.money) {
    return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  }
  if (col?.int) {
    return String(Math.round(value))
  }
  return value.toFixed(4)
}

const metricOptions = computed(() =>
  allColumnDefs
    .filter(col => displayRows.value.some(row => toNumber(row[col.key]) !== null))
    .map(col => ({ label: col.label, value: col.key }))
)

const selectedAnalysisMode = computed<'boxplot' | 'heatmap' | 'scatter3d' | ''>(() => {
  if (selectedAnalysisParams.value.length === 1) return 'boxplot'
  if (selectedAnalysisParams.value.length === 2) return 'heatmap'
  if (selectedAnalysisParams.value.length === 3) return 'scatter3d'
  return ''
})

const analysisDescription = computed(() => {
  if (selectedAnalysisMode.value === 'boxplot') {
    return `已选择 1 个参数，将展示 ${getMetricLabel(analysisMetric.value)} 在 ${selectedAnalysisParams.value[0]} 各取值下的分布。`
  }
  if (selectedAnalysisMode.value === 'heatmap') {
    return `已选择 2 个参数，将展示 ${getMetricLabel(analysisMetric.value)} 在参数组合上的热力分布。`
  }
  if (selectedAnalysisMode.value === 'scatter3d') {
    return `已选择 3 个参数，将展示三维参数空间中 ${getMetricLabel(analysisMetric.value)} 的分布。`
  }
  return '选择 1 个参数显示箱体图，选择 2 个参数显示热力图，选择 3 个参数显示立体三维图。'
})

function deriveParamNames(rows: Record<string, unknown>[]): string[] {
  const row = rows.find(item => item.params && typeof item.params === 'object')
  if (!row || !row.params || typeof row.params !== 'object') return []
  return Object.keys(row.params as Record<string, unknown>)
}

function initializeAnalysisControls(preferredMetric?: string) {
  const allowed = new Set(paramNames.value)
  const filtered = selectedAnalysisParams.value.filter(name => allowed.has(name)).slice(0, 3)
  if (filtered.length > 0) {
    selectedAnalysisParams.value = filtered
  } else if (paramNames.value.length >= 2) {
    selectedAnalysisParams.value = paramNames.value.slice(0, 2)
  } else {
    selectedAnalysisParams.value = paramNames.value.slice(0, 1)
  }

  const availableMetricKeys = new Set(metricOptions.value.map(option => option.value))
  const nextMetric = preferredMetric && availableMetricKeys.has(preferredMetric)
    ? preferredMetric
    : availableMetricKeys.has(analysisMetric.value)
      ? analysisMetric.value
      : metricOptions.value[0]?.value

  if (nextMetric) {
    analysisMetric.value = nextMetric
  }
}

function getMetricLabel(metricKey: string) {
  return allColumnDefs.find(col => col.key === metricKey)?.label || metricKey
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function compareAxisValues(a: unknown, b: unknown) {
  const numA = toNumber(a)
  const numB = toNumber(b)
  if (numA !== null && numB !== null) return numA - numB
  return String(a).localeCompare(String(b), 'zh-CN', { numeric: true })
}

function getAxisCategories(key: string): string[] {
  return [...new Set(displayRows.value.map(row => row[key]).filter(value => value != null))]
    .sort(compareAxisValues)
    .map(value => String(value))
}

function quantile(sortedValues: number[], ratio: number): number {
  if (!sortedValues.length) return 0
  const position = (sortedValues.length - 1) * ratio
  const base = Math.floor(position)
  const rest = position - base
  const next = sortedValues[base + 1]
  if (next == null) return sortedValues[base]
  return sortedValues[base] + rest * (next - sortedValues[base])
}

function renderAnalysisChart() {
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

function disposeAnalysisChart() {
  if (!analysisChart) return
  analysisChart.dispose()
  analysisChart = null
}

function renderBoxplotChart() {
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
      itemStyle: { color: '#5470c6', borderColor: '#1f2937' },
    }],
  }, true)
}

function renderHeatmapChart() {
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
      inRange: { color: ['#313695', '#4575b4', '#74add1', '#fee090', '#f46d43', '#d73027', '#a50026'] },
    },
    series: [{
      type: 'heatmap',
      data,
      label: { show: data.length <= 100 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.35)' } },
    }],
  }, true)
}

function renderScatter3dChart() {
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
      inRange: { color: ['#313695', '#4575b4', '#74add1', '#fee090', '#f46d43', '#d73027', '#a50026'] },
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
      emphasis: { itemStyle: { borderColor: '#111827', borderWidth: 1 } },
    }],
  }, true)
}

function handleResize() {
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
</script>
