<template>
  <div class="workspace-units-tab trading-workspace-tab">
    <teleport
      to="#page-header-actions"
      :disabled="!props.toolbarInHeader || !props.active"
    >
      <UnitActionsBar
        :active="props.active"
        :toolbar-in-header="props.toolbarInHeader"
        :has-selection="hasSelection"
        :has-single-selection="hasSingleSelection"
        :running="store.running"
        :auto-trading-enabled="autoTradingEnabled"
        :auto-trading-loading="autoTradingLoading"
        :auto-trading-schedule-summary="autoTradingScheduleSummary"
        :selected-count="store.selectedUnitIds.length"
        :unit-count="store.units.length"
        @select-all="handleSelectAll"
        @enable-auto-trading="handleEnableAutoTrading"
        @disable-auto-trading="handleDisableAutoTrading"
        @lock-trading="handleLockTrading"
        @lock-running="handleLockRunning"
        @unlock="handleUnlock"
        @start-selected="handleStartSelected"
        @stop-selected="handleStopSelected"
        @create-unit="showCreateUnit = true"
        @bulk-delete="handleBulkDelete"
        @import-units="handleImportUnits"
        @export-units="handleExportUnits"
        @open-data-source="showDataSource = true"
        @open-unit-settings="showUnitSettings = true"
        @open-strategy-params="showStrategyParams = true"
        @open-position-manager="showPositionManager = true"
        @open-kline="handleOpenKline"
        @open-report="emit('switch-tab', 'report', store.selectedUnitIds[0], [...store.selectedUnitIds])"
        @open-auto-trading-config="showAutoTradingConfig = true"
        @create-optimization-task="handleCreateOptimizationTask"
        @open-optimization="emit('switch-tab', 'optimization', store.selectedUnitIds[0])"
        @open-scheduled-optimization="showScheduledOptimization = true"
        @open-trading-day-stats="showTradingDayStats = true"
        @open-group-link="showGroupLink = true"
      />
    </teleport>

    <div class="trading-overview-grid">
      <div class="overview-card">
        <span class="overview-card__label">策略单元</span>
        <strong class="overview-card__value">{{ store.units.length }}</strong>
        <span class="overview-card__meta">当前工作区总量</span>
      </div>
      <div class="overview-card is-success">
        <span class="overview-card__label">运行中</span>
        <strong class="overview-card__value">{{ runningUnitCount }}</strong>
        <span class="overview-card__meta">含运行与排队状态</span>
      </div>
      <div class="overview-card is-warning">
        <span class="overview-card__label">实盘 / 模拟</span>
        <strong class="overview-card__value">{{ liveUnitCount }} / {{ paperUnitCount }}</strong>
        <span class="overview-card__meta">交易模式分布</span>
      </div>
      <div class="overview-card is-danger">
        <span class="overview-card__label">锁定单元</span>
        <strong class="overview-card__value">{{ lockedUnitCount }}</strong>
        <span class="overview-card__meta">交易或运行锁定</span>
      </div>
    </div>

    <div class="trading-schedule-bar">
      <div class="trading-schedule-bar__item">
        <span class="label">自动交易</span>
        <span class="value">{{ autoTradingScheduleSummary || '未配置交易时段' }}</span>
      </div>
      <div class="trading-schedule-bar__item">
        <span class="label">当日盈利单元</span>
        <span class="value">{{ profitableUnitCount }}</span>
      </div>
      <div class="trading-schedule-bar__item">
        <span class="label">最近更新</span>
        <span class="value">{{ lastUpdatedLabel }}</span>
      </div>
    </div>

    <UnitTable
      ref="tableRef"
      :units="store.units"
      @selection-change="onSelectionChange"
      @row-dblclick="openDetail"
      @open-detail="openDetail"
    />

    <CreateUnitDialog
      v-model="showCreateUnit"
      :workspace-id="props.workspaceId"
      workspace-type="trading"
      @created="onUnitCreated"
    />

    <DataSourceDialog
      v-model="showDataSource"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      workspace-type="trading"
      @saved="onUnitUpdated"
    />

    <UnitSettingsDialog
      v-model="showUnitSettings"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      workspace-type="trading"
      @saved="onUnitUpdated"
    />

    <StrategyParamsDialog
      v-model="showStrategyParams"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      workspace-type="trading"
      @saved="onUnitUpdated"
    />

    <AutoTradingConfigDialog
      v-model="showAutoTradingConfig"
      :workspace-id="props.workspaceId"
      @saved="handleAutoTradingSaved"
    />

    <OptimizationConfigDialog
      v-model="showOptConfig"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      @saved="onUnitUpdated"
    />

    <BatchOptimizationConfigDialog
      v-model="showBatchOptConfig"
      :workspace-id="props.workspaceId"
      :unit-ids="store.selectedUnitIds"
      :units="store.units"
      @saved="onUnitUpdated"
    />

    <PositionManagerDialog
      v-model="showPositionManager"
      :workspace-id="props.workspaceId"
      :unit-ids="store.selectedUnitIds.length ? [...store.selectedUnitIds] : undefined"
    />

    <TradingDayStatsDialog
      v-model="showTradingDayStats"
      :workspace-id="props.workspaceId"
    />

    <ScheduledOptimizationDialog
      v-model="showScheduledOptimization"
      :workspace-id="props.workspaceId"
    />

    <GroupLinkDialog
      v-model="showGroupLink"
      :workspace-id="props.workspaceId"
      :unit-ids="[...store.selectedUnitIds]"
    />

    <ImportTradingUnitsDialog
      v-model="showImportDialog"
      :workspace-id="props.workspaceId"
      @imported="handleUnitsImported"
    />

    <ExportTradingUnitsDialog
      v-model="showExportDialog"
      :units="selectedUnits"
      @exported="handleUnitsExported"
    />

    <el-dialog
      v-model="showDetailDialog"
      title="策略单元详情"
      width="980px"
    >
      <div
        v-if="detailUnit"
        class="space-y-4 text-sm"
      >
        <div class="flex flex-wrap items-center justify-end gap-2">
          <el-button
            size="small"
            @click="handleOpenRuntimeDialog(detailUnit)"
          >
            查看运行文件
          </el-button>
          <el-button
            type="primary"
            size="small"
            @click="handleOpenRuntimeDirectory(detailUnit)"
          >
            打开策略单元
          </el-button>
        </div>

        <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              单元
            </div>
            <div class="mt-1 font-semibold text-slate-700">
              {{ detailUnit.strategy_name || detailUnit.strategy_id }}
            </div>
            <div class="text-xs text-slate-400">
              {{ detailUnit.symbol }} / {{ detailUnit.timeframe }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              交易模式
            </div>
            <div class="mt-1 font-semibold text-slate-700">
              {{ detailUnit.trading_mode === 'live' ? '实盘交易' : '模拟交易' }}
            </div>
            <div class="text-xs text-slate-400">
              {{ statusLabel(detailUnit) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              网关
            </div>
            <div class="mt-1 font-semibold text-slate-700">
              {{ detailUnit.trading_snapshot?.gateway_summary || '-' }}
            </div>
            <div class="text-xs text-slate-400">
              实例 {{ detailUnit.trading_instance_id || '-' }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              最近更新
            </div>
            <div class="mt-1 font-semibold text-slate-700">
              {{ detailUnit.trading_snapshot?.updated_at || formatTime(detailUnit.updated_at) }}
            </div>
            <div class="text-xs text-slate-400">
              交易日 {{ detailUnit.trading_snapshot?.trading_day || '-' }}
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
          <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div class="text-xs text-slate-500">
              多仓 / 空仓
            </div>
            <div class="mt-1 text-lg font-semibold text-slate-700">
              {{ formatNumber(detailUnit.trading_snapshot?.long_position, 0, false) }}
              /
              {{ formatNumber(detailUnit.trading_snapshot?.short_position, 0, false) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div class="text-xs text-slate-500">
              当日盈亏
            </div>
            <div
              class="mt-1 text-lg font-semibold"
              :class="numberClass(detailUnit.trading_snapshot?.today_pnl)"
            >
              {{ formatSignedNumber(detailUnit.trading_snapshot?.today_pnl, 2, false) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div class="text-xs text-slate-500">
              累计盈亏
            </div>
            <div
              class="mt-1 text-lg font-semibold"
              :class="numberClass(detailUnit.trading_snapshot?.cumulative_pnl)"
            >
              {{ formatSignedNumber(detailUnit.trading_snapshot?.cumulative_pnl, 2, false) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div class="text-xs text-slate-500">
              杠杆 / 最新价
            </div>
            <div class="mt-1 text-lg font-semibold text-slate-700">
              {{ formatNumber(detailUnit.trading_snapshot?.leverage, 2, false) }}
              /
              {{ formatPrice(detailUnit.trading_snapshot?.latest_price) }}
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-3 text-sm font-medium text-slate-700">
            运行信息
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div><span class="text-gray-500">启动时间：</span>{{ detailUnit.trading_snapshot?.started_at || '-' }}</div>
            <div><span class="text-gray-500">停止时间：</span>{{ detailUnit.trading_snapshot?.stopped_at || '-' }}</div>
            <div class="md:col-span-2">
              <span class="text-gray-500">错误信息：</span>{{ detailUnit.trading_snapshot?.error || '-' }}
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-3 text-sm font-medium text-slate-700">
            头寸明细
          </div>
          <el-table
            :data="detailUnit.trading_snapshot?.positions || []"
            size="small"
            border
            class="detail-positions-table"
            empty-text="暂无持仓明细"
          >
            <el-table-column
              prop="data_name"
              label="合约"
              min-width="150"
              show-overflow-tooltip
            />
            <el-table-column
              label="方向"
              width="90"
              align="center"
            >
              <template #default="{ row }">
                {{ directionLabel(row.direction) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="size"
              label="数量"
              width="90"
              align="right"
            />
            <el-table-column
              label="开仓价"
              width="110"
              align="right"
            >
              <template #default="{ row }">
                {{ formatPrice(row.price) }}
              </template>
            </el-table-column>
            <el-table-column
              label="现价"
              width="110"
              align="right"
            >
              <template #default="{ row }">
                {{ formatPrice(row.current_price) }}
              </template>
            </el-table-column>
            <el-table-column
              label="市值"
              width="120"
              align="right"
            >
              <template #default="{ row }">
                {{ formatAmountCompact(row.market_value) }}
              </template>
            </el-table-column>
            <el-table-column
              label="盈亏"
              width="110"
              align="right"
            >
              <template #default="{ row }">
                <span :class="numberClass(row.pnl)">
                  {{ formatSignedNumber(row.pnl, 2, false) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </el-dialog>
    <UnitRuntimeDialog
      v-model="showRuntimeDialog"
      :workspace-id="workspaceId"
      :unit="runtimeUnit"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getErrorMessage } from '@/api/index'
import { workspaceApi } from '@/api/workspace'
import { useWorkspaceStore } from '@/stores/workspace'
import type {
  StrategyUnit,
  TradingAutoConfig,
  TradingAutoScheduleItem,
} from '@/types/workspace'
import {
  directionLabel,
  formatAmountCompact,
  formatNumber,
  formatPrice,
  formatSignedNumber,
  formatTime,
  numberClass,
  statusLabel,
} from '@/composables/useUnitTableRendering'
import AutoTradingConfigDialog from './AutoTradingConfigDialog.vue'
import BatchOptimizationConfigDialog from './BatchOptimizationConfigDialog.vue'
import CreateUnitDialog from './CreateUnitDialog.vue'
import DataSourceDialog from './DataSourceDialog.vue'
import ExportTradingUnitsDialog from './ExportTradingUnitsDialog.vue'
import GroupLinkDialog from './GroupLinkDialog.vue'
import ImportTradingUnitsDialog from './ImportTradingUnitsDialog.vue'
import OptimizationConfigDialog from './OptimizationConfigDialog.vue'
import PositionManagerDialog from './PositionManagerDialog.vue'
import ScheduledOptimizationDialog from './ScheduledOptimizationDialog.vue'
import StrategyParamsDialog from './StrategyParamsDialog.vue'
import TradingDayStatsDialog from './TradingDayStatsDialog.vue'
import UnitActionsBar from './UnitActionsBar.vue'
import UnitRuntimeDialog from './UnitRuntimeDialog.vue'
import UnitTable from './UnitTable.vue'
import UnitSettingsDialog from './UnitSettingsDialog.vue'

const props = defineProps<{
  workspaceId: string
  active?: boolean
  toolbarInHeader?: boolean
}>()

const emit = defineEmits<{
  'switch-tab': [tab: string, unitId?: string, unitIds?: string[]]
}>()

const store = useWorkspaceStore()
const tableRef = ref<{
  clearSelection: () => void
  toggleRowSelection: (row: StrategyUnit, selected?: boolean) => void
} | null>(null)

const showCreateUnit = ref(false)
const showDataSource = ref(false)
const showUnitSettings = ref(false)
const showStrategyParams = ref(false)
const showAutoTradingConfig = ref(false)
const showOptConfig = ref(false)
const showBatchOptConfig = ref(false)
const showPositionManager = ref(false)
const showTradingDayStats = ref(false)
const showScheduledOptimization = ref(false)
const showGroupLink = ref(false)
const showImportDialog = ref(false)
const showExportDialog = ref(false)
const showDetailDialog = ref(false)
const showRuntimeDialog = ref(false)
const detailUnit = ref<StrategyUnit | null>(null)
const runtimeUnit = ref<StrategyUnit | null>(null)
const autoTradingEnabled = ref(false)
const autoTradingLoading = ref(false)
const autoTradingSchedule = ref<TradingAutoScheduleItem[]>([])

const hasSelection = computed(() => store.selectedUnitIds.length > 0)
const hasSingleSelection = computed(() => store.selectedUnitIds.length === 1)
const selectedUnits = computed(() =>
  store.units.filter(unit => store.selectedUnitIds.includes(unit.id))
)
const selectedUnit = computed<StrategyUnit | null>(() => {
  if (!hasSingleSelection.value) return null
  return store.units.find(unit => unit.id === store.selectedUnitIds[0]) ?? null
})
const runningUnitCount = computed(() =>
  store.units.filter(unit => ['running', 'queued'].includes(unit.trading_snapshot?.instance_status || unit.run_status)).length
)
const lockedUnitCount = computed(() =>
  store.units.filter(unit => unit.lock_trading || unit.lock_running).length
)
const liveUnitCount = computed(() =>
  store.units.filter(unit => unit.trading_mode === 'live').length
)
const paperUnitCount = computed(() =>
  store.units.filter(unit => unit.trading_mode !== 'live').length
)
const profitableUnitCount = computed(() =>
  store.units.filter(unit => Number(unit.trading_snapshot?.today_pnl || 0) > 0).length
)
const autoTradingScheduleSummary = computed(() => {
  if (!autoTradingSchedule.value.length) {
    return ''
  }
  return autoTradingSchedule.value
    .map(item => `${item.session} ${item.start}-${item.stop}`)
    .join(' / ')
})
const lastUpdatedLabel = computed(() => {
  const timestamps = store.units
    .map(unit => unit.trading_snapshot?.updated_at || unit.updated_at)
    .filter(Boolean)
    .map(value => new Date(String(value)).getTime())
    .filter(value => !Number.isNaN(value))
  if (!timestamps.length) {
    return '-'
  }
  return new Date(Math.max(...timestamps)).toLocaleString('zh-CN')
})

onMounted(() => {
  store.clearSelection()
  store.startPolling(props.workspaceId)
  void loadAutoTradingState()
})

onUnmounted(() => {
  store.stopPolling()
})

function onSelectionChange(rows: StrategyUnit[]) {
  store.setSelectedUnitIds(rows.map(row => row.id))
}

function handleSelectAll() {
  if (!tableRef.value) return
  if (store.selectedUnitIds.length === store.units.length) {
    tableRef.value.clearSelection()
    store.clearSelection()
    return
  }
  tableRef.value.clearSelection()
  for (const unit of store.units) {
    tableRef.value.toggleRowSelection(unit, true)
  }
}

function onUnitCreated() {
  void store.fetchUnits(props.workspaceId)
}

async function onUnitUpdated() {
  await store.fetchUnits(props.workspaceId)
  await store.pollStatus(props.workspaceId)
}

async function loadAutoTradingState() {
  try {
    const [config, scheduleResponse] = await Promise.all([
      workspaceApi.getTradingAutoConfig(props.workspaceId),
      workspaceApi.getTradingAutoSchedule(props.workspaceId),
    ])
    autoTradingEnabled.value = config.enabled
    autoTradingSchedule.value = scheduleResponse
  } catch {
    autoTradingEnabled.value = false
    autoTradingSchedule.value = []
  }
}

async function updateAutoTradingEnabled(enabled: boolean) {
  autoTradingLoading.value = true
  try {
    const updated = await workspaceApi.updateTradingAutoConfig(props.workspaceId, { enabled })
    const scheduleResponse = await workspaceApi.getTradingAutoSchedule(props.workspaceId)
    autoTradingEnabled.value = updated.enabled
    autoTradingSchedule.value = scheduleResponse
    ElMessage.success(updated.enabled ? '自动交易已启用' : '自动交易已关闭')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '更新自动交易配置失败'))
  } finally {
    autoTradingLoading.value = false
  }
}

function handleEnableAutoTrading() {
  void updateAutoTradingEnabled(true)
}

function handleDisableAutoTrading() {
  void updateAutoTradingEnabled(false)
}

function handleAutoTradingSaved(payload: { config: TradingAutoConfig; schedule: TradingAutoScheduleItem[] }) {
  autoTradingEnabled.value = payload.config.enabled
  autoTradingSchedule.value = payload.schedule
}

function handleCreateOptimizationTask() {
  if (!store.selectedUnitIds.length) {
    ElMessage.warning('请先选择要创建优化任务的策略单元')
    return
  }
  if (hasSingleSelection.value) {
    showOptConfig.value = true
    return
  }
  showBatchOptConfig.value = true
}

async function handleStartSelected() {
  if (!store.selectedUnitIds.length) return
  const liveUnits = store.units.filter(unit =>
    store.selectedUnitIds.includes(unit.id) && unit.trading_mode === 'live'
  )
  try {
    if (liveUnits.length > 0) {
      await ElMessageBox.confirm(
        `将启动 ${liveUnits.length} 个实盘策略单元。请确认网关状态和交易参数无误。`,
        '实盘启动确认',
        {
          type: 'warning',
          confirmButtonText: '确认启动',
          cancelButtonText: '取消',
        }
      )
    }
    const results = await store.runSelectedUnits(props.workspaceId, false)
    const failed = (results ?? []).filter(result => result.status === 'failed')
    if (failed.length > 0) {
      ElMessage.warning(`已提交启动请求，${failed.length} 个单元启动失败`)
    } else {
      ElMessage.success('启动请求已提交')
    }
    await onUnitUpdated()
  } catch (error: unknown) {
    if (error !== 'cancel' && (error as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(error, '启动失败'))
    }
  }
}

async function handleStopSelected() {
  if (!store.selectedUnitIds.length) return
  try {
    await store.stopSelectedUnits(props.workspaceId)
    ElMessage.success('停止指令已发送')
    await onUnitUpdated()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '停止失败'))
  }
}

async function applyLockPatch(
  patch: Partial<Pick<StrategyUnit, 'lock_trading' | 'lock_running'>>,
  successMessage: string,
) {
  if (!store.selectedUnitIds.length) return
  try {
    await store.patchUnits(props.workspaceId, [...store.selectedUnitIds], patch)
    ElMessage.success(successMessage)
    await onUnitUpdated()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '更新锁定状态失败'))
  }
}

function handleLockTrading() {
  void applyLockPatch({ lock_trading: true }, '已锁定交易')
}

function handleLockRunning() {
  void applyLockPatch({ lock_running: true }, '已锁定运行')
}

function handleUnlock() {
  void applyLockPatch({ lock_trading: false, lock_running: false }, '已解除锁定')
}

async function handleBulkDelete() {
  if (!store.selectedUnitIds.length) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${store.selectedUnitIds.length} 个策略单元？`, '删除确认', {
      type: 'warning',
    })
    await store.bulkDeleteUnits(props.workspaceId, [...store.selectedUnitIds])
    ElMessage.success('策略单元已删除')
  } catch (error: unknown) {
    if (error !== 'cancel' && (error as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(error, '删除失败'))
    }
  }
}

function handleImportUnits() {
  showImportDialog.value = true
}

function handleExportUnits() {
  if (!selectedUnits.value.length) {
    ElMessage.warning('请先选择要导出的策略单元')
    return
  }
  showExportDialog.value = true
}

async function handleUnitsImported() {
  await onUnitUpdated()
}

function handleUnitsExported() {
  ElMessage.success('导出操作已完成')
}

function handleOpenKline() {
  if (!selectedUnit.value) return
  const query = new URLSearchParams({
    symbol: selectedUnit.value.symbol,
    timeframe: selectedUnit.value.timeframe,
  })
  window.open(`/backtest/legacy?${query.toString()}`, '_blank')
}

function openDetail(unit: StrategyUnit) {
  detailUnit.value = unit
  showDetailDialog.value = true
}

async function handleOpenRuntimeDirectory(unit: StrategyUnit) {
  try {
    const result = await workspaceApi.openUnitRuntimeDir(props.workspaceId, unit.id)
    ElMessage.success(result.message || '策略单元目录已打开')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '打开策略单元失败'))
  }
}

function handleOpenRuntimeDialog(unit: StrategyUnit) {
  runtimeUnit.value = unit
  showRuntimeDialog.value = true
}

</script>

<style scoped>
.trading-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.overview-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  border: 1px solid #dbeafe;
  border-radius: 12px;
  background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%);
}

.overview-card.is-success {
  border-color: #bbf7d0;
  background: linear-gradient(135deg, #ffffff 0%, #f0fdf4 100%);
}

.overview-card.is-warning {
  border-color: #fde68a;
  background: linear-gradient(135deg, #ffffff 0%, #fffbeb 100%);
}

.overview-card.is-danger {
  border-color: #fecaca;
  background: linear-gradient(135deg, #ffffff 0%, #fef2f2 100%);
}

.overview-card__label {
  font-size: 12px;
  color: #64748b;
}

.overview-card__value {
  font-size: 24px;
  line-height: 1.1;
  color: #0f172a;
}

.overview-card__meta {
  font-size: 12px;
  color: #94a3b8;
}

.trading-schedule-bar {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
}

.trading-schedule-bar__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.trading-schedule-bar__item .label {
  font-size: 12px;
  color: #94a3b8;
}

.trading-schedule-bar__item .value {
  font-size: 13px;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.detail-positions-table :deep(.el-table__header th) {
  background: #f8fafc;
  color: #475569;
  font-weight: 600;
}

@media (max-width: 1200px) {
  .trading-overview-grid,
  .trading-schedule-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .trading-overview-grid,
  .trading-schedule-bar {
    grid-template-columns: 1fr;
  }
}
</style>
