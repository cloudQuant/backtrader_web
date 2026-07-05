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
            :placeholder="t('optimization.selectUnitToView')"
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
              :content="t('optimization.open')"
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
              :content="t('optimization.save')"
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
              :content="t('optimization.applyBestParams')"
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
              :content="t('optimization.applyBestToUnit')"
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
              :content="t('optimization.paramReportTitle')"
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
              :content="t('optimization.table')"
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
              :content="t('optimization.paramAnalysis')"
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
              :content="t('optimization.showFilter')"
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
              :content="t('optimization.restoreDefault')"
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
              :content="t('optimization.timeRange')"
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
              :content="t('optimization.calcMethod')"
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
              :content="t('optimization.customField')"
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
              :content="t('optimization.recalculate')"
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
              :content="t('optimization.setDefault')"
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
            {{ t('optimization.cancelOptimization') }}
          </el-button>
        </div>
      </div>
    </teleport>

    <!-- Stat Time Dialog -->
    <el-dialog
      v-model="showStatTimeDialog"
      :title="t('optimization.timeRange')"
      width="400px"
      destroy-on-close
    >
      <el-form
        label-width="100px"
        size="small"
      >
        <el-form-item :label="t('optimization.timeStart')">
          <el-date-picker
            v-model="statTimeRange[0]"
            type="date"
            :placeholder="t('optimization.selectStart')"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="t('optimization.timeEnd')">
          <el-date-picker
            v-model="statTimeRange[1]"
            type="date"
            :placeholder="t('optimization.selectEnd')"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showStatTimeDialog = false">
          {{ t('optimization.cancel') }}
        </el-button>
        <el-button
          type="primary"
          @click="showStatTimeDialog = false; loadResults()"
        >
          {{ t('optimization.confirm') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Calc Method Dialog -->
    <el-dialog
      v-model="showCalcMethodDialog"
      :title="t('optimization.calcMethod')"
      width="400px"
      destroy-on-close
    >
      <el-form
        label-width="100px"
        size="small"
      >
        <el-form-item :label="t('optimization.returnCalc')">
          <el-radio-group v-model="calcMethod">
            <el-radio value="simple">
              {{ t('optimization.simpleReturn') }}
            </el-radio>
            <el-radio value="compound">
              {{ t('optimization.compoundReturn') }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="t('optimization.annualBenchmark')">
          <el-input-number
            v-model="annualDays"
            :min="200"
            :max="365"
          />
          <span class="ml-2 text-xs text-gray-400">{{ t('optimization.days') }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCalcMethodDialog = false">
          {{ t('optimization.cancel') }}
        </el-button>
        <el-button
          type="primary"
          @click="showCalcMethodDialog = false; ElMessage.success(t('optimization.calcMethodUpdated'))"
        >
          {{ t('optimization.confirm') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Custom Fields Dialog -->
    <el-dialog
      v-model="showCustomFieldsDialog"
      :title="t('optimization.customField')"
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
          {{ t('optimization.selectAll') }}
        </el-button>
        <el-button @click="showCustomFieldsDialog = false">
          {{ t('optimization.close') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Filter row -->
    <div
      v-if="showFilter"
      class="mb-3 flex gap-3 items-center"
    >
      <span class="text-xs text-gray-400">{{ t('optimization.sortLabel') }}:</span>
      <el-select
        v-model="sortKey"
        size="small"
        style="width: 140px"
        @change="applySort"
      >
        <el-option
          :label="t('optimization.sharpe')"
          value="sharpe_ratio"
        />
        <el-option
          :label="t('optimization.annualReturn')"
          value="annual_return"
        />
        <el-option
          :label="t('optimization.totalReturn')"
          value="total_return"
        />
        <el-option
          :label="t('optimization.maxDrawdown')"
          value="max_drawdown"
        />
        <el-option
          :label="t('optimization.winRate')"
          value="win_rate"
        />
        <el-option
          :label="t('optimization.profitFactor')"
          value="profit_factor"
        />
      </el-select>
      <el-radio-group
        v-model="sortDir"
        size="small"
        @change="applySort"
      >
        <el-radio-button value="desc">
          {{ t('optimization.sortDesc') }}
        </el-radio-button>
        <el-radio-button value="asc">
          {{ t('optimization.sortAsc') }}
        </el-radio-button>
      </el-radio-group>
    </div>

    <!-- No unit selected -->
    <el-empty
      v-if="!selectedUnitId"
      :description="t('optimization.selectUnitToViewLong')"
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
            {{ t('optimization.totalCombosCount') }}
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
            {{ t('optimization.completed') }}
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
            {{ t('optimization.paramAtBestParam') }}
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
            {{ t('optimization.bestSharpe') }}
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
          :label="t('optimization.actions')"
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
              {{ t('optimization.backtestDetail') }}
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
            <span class="text-sm text-gray-500">{{ t('optimization.paramHeader') }}</span>
            <el-select
              v-model="selectedAnalysisParams"
              multiple
              collapse-tags
              collapse-tags-tooltip
              :multiple-limit="3"
              :placeholder="t('optimization.forNParams', { n: '1-3' })"
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
            <span class="text-sm text-gray-500">{{ t('optimization.targetValue') }}</span>
            <el-select
              v-model="analysisMetric"
              :placeholder="t('optimization.selectGoal')"
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
            {{ t('optimization.forNParams', { n: '1-3' }) }}
          </div>
        </el-card>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, type CSSProperties } from 'vue'
import 'echarts-gl'
import { useRouter } from 'vue-router'
import {
  Loading, Check, Document, Filter, Refresh, Download,
  FolderOpened, Position, Grid,
  RefreshLeft, Timer, Operation, SetUp, Star,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { workspaceApi } from '@/api/workspace'
import { useWorkspaceStore } from '@/stores/workspace'
import { getErrorMessage } from '@/api/index'

const { t } = useI18n()

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

interface ColDef {
  key: string; label: string; width?: number; align?: string;
  sortable?: boolean; money?: boolean; int?: boolean;
}

interface OptimizationDisplayConfig {
  sort_key?: string
  sort_dir?: 'asc' | 'desc'
  view_mode?: 'analysis' | 'table'
  calc_method?: string
  annual_days?: number
  stat_time_range?: [string | null, string | null]
  visible_fields?: string[]
  analysis_params?: string[]
  analysis_metric?: string
}

interface WorkspaceSettingsWithOptimization {
  optimization_config?: OptimizationDisplayConfig
}

const allColumnDefs: ColDef[] = [
  { key: 'initial_cash', label: t('optimization.initialCash'), width: 100, money: true },
  { key: 'net_value', label: t('optimization.netValue'), width: 80 },
  { key: 'net_profit', label: t('optimization.netProfit'), width: 100, money: true },
  { key: 'annual_return', label: t('optimization.annualizedReturn') + '%', width: 100, sortable: true },
  { key: 'max_leverage', label: t('optimization.maxLeverage'), width: 80 },
  { key: 'max_market_value', label: t('optimization.maxMarketValue'), width: 100, money: true },
  { key: 'max_drawdown_value', label: t('optimization.maxDrawdownVal'), width: 100, money: true },
  { key: 'max_drawdown', label: t('optimization.maxDrawdown') + '%', width: 90, sortable: true },
  { key: 'sharpe_ratio', label: t('optimization.sharpe'), width: 85, sortable: true },
  { key: 'adjusted_return_risk', label: t('optimization.riskReturnRatio'), width: 90 },
  { key: 'total_trades', label: t('optimization.tradeCount'), width: 80, align: 'center', int: true },
  { key: 'win_rate', label: t('optimization.winRate') + '%', width: 70, sortable: true },
  { key: 'avg_profit', label: t('optimization.avgProfit'), width: 90, money: true },
  { key: 'avg_profit_rate', label: t('optimization.avgProfitRate') + '%', width: 100 },
  { key: 'total_win_amount', label: t('optimization.totalProfit'), width: 100, money: true },
  { key: 'total_loss_amount', label: t('optimization.totalLoss'), width: 100, money: true },
  { key: 'profit_loss_ratio', label: t('optimization.profitLossRatio'), width: 80 },
  { key: 'profit_factor', label: t('optimization.profitFactor'), width: 80, sortable: true },
  { key: 'profit_rate_factor', label: t('optimization.profitRateFactor'), width: 90 },
  { key: 'profit_loss_rate_ratio', label: t('optimization.profitRateRatio'), width: 80 },
  { key: 'odds', label: t('optimization.winChance') + '%', width: 80 },
  { key: 'daily_avg_return', label: t('optimization.daily') + '%', width: 90 },
  { key: 'daily_max_loss', label: t('optimization.dailyMaxLoss') + '%', width: 100 },
  { key: 'daily_max_profit', label: t('optimization.dailyMaxProfit') + '%', width: 100 },
  { key: 'weekly_avg_return', label: t('optimization.weekly') + '%', width: 90 },
  { key: 'weekly_max_loss', label: t('optimization.weeklyMaxLoss') + '%', width: 100 },
  { key: 'weekly_max_profit', label: t('optimization.weeklyMaxProfit') + '%', width: 100 },
  { key: 'monthly_avg_return', label: t('optimization.monthly') + '%', width: 90 },
  { key: 'monthly_max_loss', label: t('optimization.monthlyMaxLoss') + '%', width: 100 },
  { key: 'monthly_max_profit', label: t('optimization.monthlyMaxProfit') + '%', width: 100 },
  { key: 'trading_cost', label: t('optimization.tradeCost'), width: 90, money: true },
  { key: 'trading_days', label: t('optimization.tradeDays'), width: 80, align: 'center', int: true },
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
    return t('optimization.taskCancelled') + '。'
  }
  if (optimizationStatus.value === 'failed') {
    return t('optimization.taskFailed') + '，' + t('optimization.pleaseCheckRange') + '、' + t('optimization.pleaseCheckLogs') + '。'
  }
  if (optimizationStatus.value === 'completed' && failed.value > 0 && completed.value === 0) {
    return t('optimization.taskCompleted') + '，' + t('optimization.butSuffix') + ` ${failed.value} ` + t('optimization.allFailed') + '，' + t('optimization.causeNoResults') + '。'
  }
  if (optimizationStatus.value === 'completed' && failed.value > 0) {
    return t('optimization.taskCompleted') + '，' + t('optimization.butSomeFailed') + '。' + t('optimization.noResult') + '，' + t('optimization.taskFailedCheckLogs') + '。'
  }
  return t('optimization.noResultForUnit') + '。' + t('optimization.noResultDetail') + '。'
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
  const settings = store.currentWorkspace?.settings as WorkspaceSettingsWithOptimization | undefined
  const oc = settings?.optimization_config
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
       ElMessage.success(t('optimization.loaded') + ` ${data.results.length} ` + t('optimization.nResultsCount', { n: '' }))
     } else {
       ElMessage.warning(t('optimization.fileFormatErr'))
     }
    } catch {
      ElMessage.error(t('optimization.readFileFailed'))
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
  ElMessage.success(t('optimization.optimizationSaved'))
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
  const reportDialogStyle: CSSProperties = { whiteSpace: 'pre-wrap', fontFamily: 'monospace' }
  const lines = [
    '=== ' + t('optimization.paramReportTitle') + ' ===',
    t('optimization.parameterUnit') + `: ${selectedUnitId.value}`,
    t('optimization.totalCombos') + `: ${total.value}`,
    t('optimization.bestParams') + `: ${formatParams(best.params)}`,
    t('optimization.sharpe') + `: ${fmtVal(best.sharpe_ratio)}`,
    t('optimization.annualReturn') + `: ${fmtVal(best.annual_return)}`,
    t('optimization.maxDrawdown') + `: ${fmtVal(best.max_drawdown)}`,
    t('optimization.winRate') + `: ${fmtVal(best.win_rate)}`,
    t('optimization.profitFactor') + `: ${fmtVal(best.profit_factor)}`,
    t('optimization.tradeCount') + `: ${best.total_trades ?? '-'}`,
  ]
  ElMessageBox.alert(lines.join('\n'), t('optimization.paramReportTitle'), {
    confirmButtonText: t('optimization.close'),
    customStyle: reportDialogStyle,
  })
}

// --- Reset ---
function handleReset() {
  sortKey.value = 'sharpe_ratio'
  sortDir.value = 'desc'
  showFilter.value = false
  viewMode.value = 'table'
  visibleFields.value = allFields.map(f => f.key)
  ElMessage.success(t('optimization.restoredDefault'))
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
     ElMessage.success(t('optimization.savedAsDefault'))
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('optimization.saveDefaultFailed')))
  }
}

async function handleCancel() {
  if (!selectedUnitId.value) return
  try {
    await workspaceApi.cancelOptimization(props.workspaceId, selectedUnitId.value)
    ElMessage.success(t('optimization.optimizationCancelled'))
    await loadResults()
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('optimization.cancelFailed')))
  }
}

async function handleApplyBest() {
  if (!selectedUnitId.value || !displayRows.value.length) return
  const unit = units.value.find(u => u.id === selectedUnitId.value)
  const taskId = unit?.last_optimization_task_id
  if (!taskId) {
    ElMessage.warning(t('optimization.noTaskFound'))
    return
  }
  const bestRow = displayRows.value[0]
  const backendIdx = typeof bestRow.result_index === 'number' ? bestRow.result_index : 0
  try {
    await ElMessageBox.confirm(t('optimization.confirmApplyBest') + '?', t('optimization.applyBestParams'), { type: 'info' })
    await workspaceApi.applyBestParams(props.workspaceId, {
      unit_id: selectedUnitId.value,
      optimization_task_id: taskId,
      result_index: backendIdx,
    })
    ElMessage.success(t('optimization.bestParamsApplied'))
    store.fetchUnits(props.workspaceId)
  } catch (e: unknown) {
    if (e !== 'cancel' && (e as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(e, t('optimization.applyFailed')))
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
    ElMessage.warning(t('optimization.rowNoParam'))
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
      ElMessage.success(t('optimization.backtestSubmitted') + '，' + t('optimization.waitingNavigate'))
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
                query: {
                  workspaceId: props.workspaceId,
                  unitId: unit.id,
                  strategyName: unit.strategy_name || unit.group_name || unit.strategy_id || '',
                },
              })
            } else {
              ElMessage.error(t('optimization.backtestFailed'))
            }
          }
        } catch { /* ignore */ }
      }, 2000)
      // Safety timeout: stop polling after 10 minutes
      setTimeout(() => { clearInterval(pollId); runningRow.value = null }, 600000)
    } else {
      ElMessage.warning(t('optimization.backtestNoTask'))
    }
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('optimization.submitBacktestFailed')))
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
    return t('optimization.selected') + ' 1 ' + t('optimization.paramHeader') + '，' + t('optimization.willShow') + ` ${getMetricLabel(analysisMetric.value)} ` + t('optimization.in') + ` ${selectedAnalysisParams.value[0]} ` + t('optimization.distribution') + '。'
  }
  if (selectedAnalysisMode.value === 'heatmap') {
    return t('optimization.selected') + ' 2 ' + t('optimization.paramHeader') + '，' + t('optimization.willShow') + ` ${getMetricLabel(analysisMetric.value)} ` + t('optimization.onCombinations') + '。'
  }
  if (selectedAnalysisMode.value === 'scatter3d') {
    return t('optimization.selected') + ' 3 ' + t('optimization.paramHeader') + '，' + t('optimization.in3DSpace') + ` ${getMetricLabel(analysisMetric.value)} ` + t('optimization.distributionOf') + '。'
  }
  return t('optimization.selectGeneric') + ' 1 ' + t('optimization.showBoxplot', { n: '' }) + '，' + t('optimization.selectGeneric') + ' 2 ' + t('optimization.showHeatmap', { n: '' }) + '，' + t('optimization.selectGeneric') + ' 3 ' + t('optimization.show3D', { n: '' }) + '。'
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

</script>
