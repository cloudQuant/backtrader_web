<template>
  <div class="workspace-report-tab">
    <teleport to="#page-header-actions" :disabled="!props.toolbarInHeader || !props.active">
      <div
        class="flex items-center justify-between flex-wrap gap-2"
        :class="props.toolbarInHeader && props.active ? 'mb-0' : 'mb-4'"
      >
        <div class="flex items-center gap-2 flex-wrap">
        <!-- Group 1: Open / Delete / Clear / Save -->
        <el-button-group>
          <el-tooltip content="打开" placement="top">
            <el-button size="small" @click="handleOpenReport">
              <el-icon><FolderOpened /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="删除" placement="top">
            <el-button size="small" :disabled="!report" @click="handleDeleteReport">
              <el-icon><Delete /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="清空" placement="top">
            <el-button size="small" :disabled="!report" @click="handleClearReport">
              <el-icon><Close /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="保存" placement="top">
            <el-button size="small" :disabled="!report" @click="handleSaveReport">
              <el-icon><Download /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <!-- Group 2: Config -->
        <el-button-group>
          <el-tooltip content="统计时间" placement="top">
            <el-button size="small" @click="showStatTimeDialog = true">
              <el-icon><Timer /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="组合最大投入资金" placement="top">
            <el-button size="small" @click="showMaxCashDialog = true">
              <el-icon><Wallet /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="计算方式" placement="top">
            <el-button size="small" @click="showCalcMethodDialog = true">
              <el-icon><Operation /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="报告权重" placement="top">
            <el-button size="small" @click="showWeightDialog = true">
              <el-icon><Histogram /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="自定义字段" placement="top">
            <el-button size="small" @click="showCustomFieldsDialog = true">
              <el-icon><SetUp /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <!-- Group 3: Actions -->
        <el-button-group>
          <el-tooltip content="报告计算(按配置重算)" placement="top">
            <el-button size="small" type="primary" :loading="loading" @click="recalculateReport">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="设为默认" placement="top">
            <el-button size="small" @click="handleSetDefault">
              <el-icon><Star /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>
        </div>
      </div>
    </teleport>

    <!-- Stat Time Dialog -->
    <el-dialog v-model="showStatTimeDialog" title="统计时间" width="400px" destroy-on-close>
      <el-form label-width="100px" size="small">
        <el-form-item label="起始时间">
          <el-date-picker v-model="reportStatRange[0]" type="date" placeholder="选择起始日期" style="width: 100%" />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker v-model="reportStatRange[1]" type="date" placeholder="选择结束日期" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showStatTimeDialog = false">取消</el-button>
        <el-button type="primary" @click="showStatTimeDialog = false; recalculateReport()">确定</el-button>
      </template>
    </el-dialog>

    <!-- Max Cash Dialog -->
    <el-dialog v-model="showMaxCashDialog" title="组合最大投入资金" width="400px" destroy-on-close>
      <el-form label-width="120px" size="small">
        <el-form-item label="最大投入资金">
          <el-input-number v-model="maxCash" :min="0" :step="100000" style="width: 200px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showMaxCashDialog = false">取消</el-button>
        <el-button type="primary" @click="showMaxCashDialog = false; recalculateReport()">确定</el-button>
      </template>
    </el-dialog>

    <!-- Calc Method Dialog -->
    <el-dialog v-model="showCalcMethodDialog" title="计算方式" width="400px" destroy-on-close>
      <el-form label-width="100px" size="small">
        <el-form-item label="收益计算">
          <el-radio-group v-model="reportCalcMethod">
            <el-radio value="simple">简单收益</el-radio>
            <el-radio value="compound">复合收益</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="年化基准">
          <el-input-number v-model="reportAnnualDays" :min="200" :max="365" />
          <span class="ml-2 text-xs text-gray-400">天</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCalcMethodDialog = false">取消</el-button>
        <el-button type="primary" @click="showCalcMethodDialog = false; recalculateReport()">确定</el-button>
      </template>
    </el-dialog>

    <!-- Weight Dialog -->
    <el-dialog v-model="showWeightDialog" title="报告权重" width="400px" destroy-on-close>
      <el-form label-width="100px" size="small">
        <el-form-item label="权重模式">
          <el-radio-group v-model="weightMode">
            <el-radio value="equal">等权</el-radio>
            <el-radio value="custom">自定义</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="weightMode === 'custom'" label="自定义权重">
          <div class="text-xs text-gray-400">各单元权重由资金占比自动计算</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showWeightDialog = false">取消</el-button>
        <el-button type="primary" @click="showWeightDialog = false; recalculateReport()">确定</el-button>
      </template>
    </el-dialog>

    <!-- Custom Fields Dialog -->
    <el-dialog v-model="showCustomFieldsDialog" title="自定义字段" width="500px" destroy-on-close>
      <el-checkbox-group v-model="reportVisibleFields">
        <div class="grid grid-cols-3 gap-2">
          <el-checkbox v-for="f in reportAllFields" :key="f.key" :value="f.key">{{ f.label }}</el-checkbox>
        </div>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="reportVisibleFields = reportAllFields.map(f => f.key)">全选</el-button>
        <el-button @click="showCustomFieldsDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-skeleton :rows="6" :loading="loading" animated>
      <template #default>
        <!-- Summary cards -->
        <div v-if="report" class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <el-card shadow="hover" class="text-center">
            <div class="text-2xl font-bold">{{ filteredSummary.total_units ?? 0 }}</div>
            <div class="text-xs text-gray-400 mt-1">总单元数</div>
          </el-card>
          <el-card shadow="hover" class="text-center">
            <div class="text-2xl font-bold">{{ filteredSummary.completed_units ?? 0 }}</div>
            <div class="text-xs text-gray-400 mt-1">已完成</div>
          </el-card>
          <el-card shadow="hover" class="text-center">
            <div class="text-2xl font-bold" :class="returnColor(filteredSummary.avg_total_return)">
              {{ fmtPct(filteredSummary.avg_total_return) }}
            </div>
            <div class="text-xs text-gray-400 mt-1">平均收益率</div>
          </el-card>
          <el-card shadow="hover" class="text-center">
            <div class="text-2xl font-bold" :class="returnColor(filteredSummary.avg_sharpe_ratio)">
              {{ fmtNum(filteredSummary.avg_sharpe_ratio) }}
            </div>
            <div class="text-xs text-gray-400 mt-1">平均夏普比</div>
          </el-card>
          <el-card shadow="hover" class="text-center">
            <div class="text-2xl font-bold text-red-500">
              {{ fmtPct(filteredSummary.avg_max_drawdown) }}
            </div>
            <div class="text-xs text-gray-400 mt-1">平均最大回撤</div>
          </el-card>
          <el-card shadow="hover" class="text-center">
            <div class="text-2xl font-bold">{{ fmtPct(filteredSummary.avg_win_rate) }}</div>
            <div class="text-xs text-gray-400 mt-1">平均胜率</div>
          </el-card>
          <el-card shadow="hover" class="text-center">
            <div class="text-2xl font-bold">{{ filteredSummary.total_trades ?? '-' }}</div>
            <div class="text-xs text-gray-400 mt-1">总交易次数</div>
          </el-card>
          <el-card shadow="hover" class="text-center">
            <div class="text-2xl font-bold" :class="returnColor(filteredSummary.avg_annual_return)">
              {{ fmtPct(filteredSummary.avg_annual_return) }}
            </div>
            <div class="text-xs text-gray-400 mt-1">平均年化收益</div>
          </el-card>
        </div>

        <!-- Highlights -->
        <div v-if="filteredSummary.best_return_unit || filteredSummary.worst_drawdown_unit" class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <el-card v-if="filteredSummary.best_return_unit" shadow="hover">
            <template #header><span class="text-sm font-medium">最佳收益单元</span></template>
            <div class="flex justify-between items-center">
              <span>{{ filteredSummary.best_return_unit.strategy_name }} / {{ filteredSummary.best_return_unit.symbol }}</span>
              <span class="text-green-500 font-bold">{{ fmtPct(filteredSummary.best_return_unit.value) }}</span>
            </div>
          </el-card>
          <el-card v-if="filteredSummary.worst_drawdown_unit" shadow="hover">
            <template #header><span class="text-sm font-medium">最大回撤单元</span></template>
            <div class="flex justify-between items-center">
              <span>{{ filteredSummary.worst_drawdown_unit.strategy_name }} / {{ filteredSummary.worst_drawdown_unit.symbol }}</span>
              <span class="text-red-500 font-bold">{{ fmtPct(filteredSummary.worst_drawdown_unit.value) }}</span>
            </div>
          </el-card>
        </div>

        <!-- Per-unit table with dynamic columns -->
        <el-table v-if="filteredUnits.length" :data="filteredUnits" stripe border size="small" class="w-full" max-height="500">
          <el-table-column label="#" width="50" align="center" fixed>
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="strategy_name" label="报告单元" min-width="120" fixed />
          <el-table-column prop="group_name" label="来源" width="100" />
          <el-table-column prop="data_source" label="数据源" width="120" />
          <el-table-column prop="start_date" label="起始时间" width="100" />
          <template v-for="col in reportActiveColumns" :key="col.key">
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

        <el-empty v-if="report && !filteredUnits.length" description="当前选中范围暂无单元数据" />
        <el-empty v-if="!report && !loading" description="点击刷新加载报告" />
      </template>
    </el-skeleton>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  Refresh, FolderOpened, Delete, Close, Download,
  Timer, Wallet, Operation, Histogram, SetUp, Star,
} from '@element-plus/icons-vue'
import { workspaceApi } from '@/api/workspace'
import { useWorkspaceStore } from '@/stores/workspace'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getErrorMessage } from '@/api/index'

const props = defineProps<{
  workspaceId: string
  active?: boolean
  toolbarInHeader?: boolean
  initialUnitId?: string
  initialUnitIds?: string[]
}>()

const store = useWorkspaceStore()
const loading = ref(false)
const report = ref<Record<string, any> | null>(null)
const selectedReportUnitIds = ref<string[]>([])

const showStatTimeDialog = ref(false)
const showMaxCashDialog = ref(false)
const showCalcMethodDialog = ref(false)
const showWeightDialog = ref(false)
const showCustomFieldsDialog = ref(false)
const reportStatRange = ref<[string | null, string | null]>([null, null])
const maxCash = ref(1000000)
const reportCalcMethod = ref('simple')
const reportAnnualDays = ref(252)
const weightMode = ref('equal')

function _restoreDefaults() {
  const rc = (store.currentWorkspace?.settings as Record<string, any>)?.report_config
  if (!rc) return
  if (rc.calc_method) reportCalcMethod.value = rc.calc_method
  if (rc.annual_days) reportAnnualDays.value = rc.annual_days
  if (rc.weight_mode) weightMode.value = rc.weight_mode
  if (rc.max_cash != null) maxCash.value = rc.max_cash
  if (rc.stat_range) {
    reportStatRange.value = [rc.stat_range[0] ?? null, rc.stat_range[1] ?? null]
  }
}

interface RptColDef {
  key: string; label: string; width?: number; align?: string;
  sortable?: boolean; money?: boolean; int?: boolean;
}

const reportColumnDefs: RptColDef[] = [
  { key: 'initial_cash', label: '最大投入资金', width: 110, money: true },
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
const reportAllFields = reportColumnDefs.map(c => ({ key: c.key, label: c.label }))
const reportVisibleFields = ref(reportAllFields.map(f => f.key))

const reportActiveColumns = computed(() =>
  reportColumnDefs.filter(c => reportVisibleFields.value.includes(c.key))
)

const filteredUnits = computed(() => {
  const rows = Array.isArray(report.value?.units) ? report.value.units : []
  if (!selectedReportUnitIds.value.length) return rows
  return rows.filter((row: Record<string, unknown>) => selectedReportUnitIds.value.includes(String(row.id || '')))
})

const filteredSummary = computed(() => {
  const rows = filteredUnits.value as Array<Record<string, any>>
  if (!rows.length) {
    return {
      total_units: 0,
      completed_units: 0,
      avg_total_return: null,
      avg_annual_return: null,
      avg_sharpe_ratio: null,
      avg_max_drawdown: null,
      avg_win_rate: null,
      total_trades: null,
      best_return_unit: null,
      worst_drawdown_unit: null,
    }
  }
  const avg = (key: string) => {
    const values = rows.map(r => r[key]).filter((v: unknown) => typeof v === 'number') as number[]
    if (!values.length) return null
    return values.reduce((sum, v) => sum + v, 0) / values.length
  }
  const totalTrades = rows
    .map(r => r.total_trades)
    .filter((v: unknown) => typeof v === 'number')
    .reduce((sum: number, v: number) => sum + v, 0)
  const bestReturnUnit = rows.reduce((best: Record<string, any> | null, row) => {
    if (!best) return row
    return (row.total_return ?? Number.NEGATIVE_INFINITY) > (best.total_return ?? Number.NEGATIVE_INFINITY) ? row : best
  }, null)
  const worstDrawdownUnit = rows.reduce((worst: Record<string, any> | null, row) => {
    if (!worst) return row
    return Math.abs(row.max_drawdown ?? 0) > Math.abs(worst.max_drawdown ?? 0) ? row : worst
  }, null)
  return {
    total_units: rows.length,
    completed_units: rows.filter(r => r.run_status === 'completed' || r.last_task_id).length,
    avg_total_return: avg('total_return'),
    avg_annual_return: avg('annual_return'),
    avg_sharpe_ratio: avg('sharpe_ratio'),
    avg_max_drawdown: avg('max_drawdown'),
    avg_win_rate: avg('win_rate'),
    total_trades: totalTrades || null,
    best_return_unit: bestReturnUnit ? {
      strategy_name: bestReturnUnit.strategy_name,
      symbol: bestReturnUnit.symbol,
      value: bestReturnUnit.total_return,
    } : null,
    worst_drawdown_unit: worstDrawdownUnit ? {
      strategy_name: worstDrawdownUnit.strategy_name,
      symbol: worstDrawdownUnit.symbol,
      value: worstDrawdownUnit.max_drawdown,
    } : null,
  }
})

async function fetchReport() {
  loading.value = true
  try {
    report.value = await workspaceApi.getReport(props.workspaceId)
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '加载报告失败'))
  } finally {
    loading.value = false
  }
}

async function recalculateReport() {
  loading.value = true
  try {
    const config: Record<string, unknown> = {
      calc_method: reportCalcMethod.value,
      annual_days: reportAnnualDays.value,
      weight_mode: weightMode.value,
      max_cash: maxCash.value,
    }
    if (reportStatRange.value[0]) config.start_date = reportStatRange.value[0]
    if (reportStatRange.value[1]) config.end_date = reportStatRange.value[1]
    report.value = await workspaceApi.createReport(props.workspaceId, config)
    ElMessage.success('报告已按配置重新计算')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '重新计算失败'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  _restoreDefaults()
  selectedReportUnitIds.value = props.initialUnitIds?.length ? [...props.initialUnitIds] : (props.initialUnitId ? [props.initialUnitId] : [])
  fetchReport()
})

watch(() => props.initialUnitIds, (newIds) => {
  selectedReportUnitIds.value = newIds?.length ? [...newIds] : (props.initialUnitId ? [props.initialUnitId] : [])
}, { deep: true })

watch(() => props.active, async (isActive) => {
  if (isActive) {
    selectedReportUnitIds.value = props.initialUnitIds?.length ? [...props.initialUnitIds] : (props.initialUnitId ? [props.initialUnitId] : [])
    await fetchReport()
  }
})

function handleOpenReport() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      if (data.summary || data.units) {
        report.value = data
        ElMessage.success('报告已加载')
      } else {
        ElMessage.warning('文件格式不正确')
      }
    } catch {
      ElMessage.error('读取文件失败')
    }
  }
  input.click()
}

// --- Delete report config (Bug-5 v2: safe semantics, only clears config not metrics) ---
async function handleDeleteReport() {
  try {
    await ElMessageBox.confirm('确认清除报告配置缓存？此操作不会影响单元运行指标数据。', '清除报告配置', { type: 'info' })
    await workspaceApi.deleteReport(props.workspaceId)
    report.value = null
    // Reset local config to defaults
    reportCalcMethod.value = 'simple'
    reportAnnualDays.value = 252
    weightMode.value = 'equal'
    maxCash.value = 1000000
    reportStatRange.value = [null, null]
    ElMessage.success('报告配置已清除')
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error(getErrorMessage(e, '清除失败'))
  }
}

// --- Clear (local view reset) ---
function handleClearReport() {
  report.value = null
  ElMessage.info('本地视图已清空，可点击刷新重新加载')
}

// --- Save ---
function handleSaveReport() {
  if (!report.value) return
  const blob = new Blob([JSON.stringify(report.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `report_${props.workspaceId.slice(0, 8)}_${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('报告已保存')
}

// --- Set default (save config to workspace settings) ---
async function handleSetDefault() {
  try {
    await workspaceApi.update(props.workspaceId, {
      settings: {
        report_config: {
          calc_method: reportCalcMethod.value,
          annual_days: reportAnnualDays.value,
          weight_mode: weightMode.value,
          max_cash: maxCash.value,
          stat_range: reportStatRange.value,
        },
      },
    })
    ElMessage.success('已保存为默认报告配置')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '保存默认配置失败'))
  }
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '-'
  return `${v.toFixed(2)}%`
}

function fmtNum(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toFixed(2)
}

function fmtVal(val: unknown) {
  if (val == null) return '-'
  return typeof val === 'number' ? val.toFixed(4) : String(val)
}

function fmtMoney(val: unknown) {
  if (val == null) return '-'
  return typeof val === 'number' ? val.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : String(val)
}

function returnColor(v: number | null | undefined): string {
  if (v == null) return ''
  return v >= 0 ? 'text-green-500' : 'text-red-500'
}
</script>
