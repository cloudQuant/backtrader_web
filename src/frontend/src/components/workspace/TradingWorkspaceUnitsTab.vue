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
        <span class="overview-card__label">{{ t('units.nStrategyUnits') }}</span>
        <strong class="overview-card__value">{{ store.units.length }}</strong>
        <span class="overview-card__meta">{{ t('tradingUnits.workspaceTotal') }}</span>
      </div>
      <div class="overview-card is-success">
        <span class="overview-card__label">{{ t('tradingUnits.runStatus') }}</span>
        <strong class="overview-card__value">{{ runningUnitCount }}</strong>
        <span class="overview-card__meta">{{ t('tradingUnits.runningQueued') }}</span>
      </div>
      <div class="overview-card is-warning">
        <span class="overview-card__label">{{ t('tradingUnits.liveTradingShort') }} / {{ t('tradingUnits.paperTradingShort') }}</span>
        <strong class="overview-card__value">{{ liveUnitCount }} / {{ paperUnitCount }}</strong>
        <span class="overview-card__meta">{{ t('tradingUnits.tradingModeDist') }}</span>
      </div>
      <div class="overview-card is-danger">
        <span class="overview-card__label">{{ t('tradingUnits.lockUnit') }}</span>
        <strong class="overview-card__value">{{ lockedUnitCount }}</strong>
        <span class="overview-card__meta">{{ t('tradingUnits.tradingOrLocked') }}</span>
      </div>
    </div>

    <div class="trading-schedule-bar">
      <div class="trading-schedule-bar__item">
        <span class="label">{{ t('tradingUnits.autoTrading') }}</span>
        <span class="value">{{ autoTradingScheduleSummary || t('tradingUnits.noTradingSession') }}</span>
      </div>
      <div class="trading-schedule-bar__item">
        <span class="label">{{ t('tradingUnits.todayProfitUnits') }}</span>
        <span class="value">{{ profitableUnitCount }}</span>
      </div>
      <div class="trading-schedule-bar__item">
        <span class="label">{{ t('tradingUnits.lastUpdate') }}</span>
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

    <TradingUnitDetailDialog
      v-model:visible="showDetailDialog"
      :detail-unit="detailUnit"
      @open-runtime-dialog="handleOpenRuntimeDialog"
      @open-runtime-directory="handleOpenRuntimeDirectory"
    />
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
import { useI18n } from 'vue-i18n'
import { getErrorMessage } from '@/api/index'
import { workspaceApi } from '@/api/workspace'
import { useWorkspaceStore } from '@/stores/workspace'
import { useAutoTradingControls } from '@/composables/useAutoTradingControls'
import type { StrategyUnit } from '@/types/workspace'
import AutoTradingConfigDialog from './AutoTradingConfigDialog.vue'
import TradingUnitDetailDialog from './TradingUnitDetailDialog.vue'
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

const { t } = useI18n()
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

const {
  autoTradingEnabled,
  autoTradingLoading,
  autoTradingScheduleSummary,
  loadAutoTradingState,
  handleEnableAutoTrading,
  handleDisableAutoTrading,
  handleAutoTradingSaved,
} = useAutoTradingControls(() => props.workspaceId)

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

function handleCreateOptimizationTask() {
  if (!store.selectedUnitIds.length) {
    ElMessage.warning(t('tradingUnits.selectUnitForOpt'))
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
        `${t('tradingUnits.willStart')} ${liveUnits.length} ${t('tradingUnits.nLiveUnits')}。${t('tradingUnits.confirmGateway')}。`,
        t('tradingUnits.liveStartConfirm'),
        {
          type: 'warning',
          confirmButtonText: t('tradingUnits.confirmStart'),
          cancelButtonText: t('tradingUnits.cancel'),
        }
      )
    }
    const results = await store.runSelectedUnits(props.workspaceId, false)
    const failed = (results ?? []).filter(result => result.status === 'failed')
    if (failed.length > 0) {
      ElMessage.warning(`${t('tradingUnits.startSubmitted')}，${failed.length} ${t('tradingUnits.nUnitsLaunchFailed')}`)
    } else {
      ElMessage.success(t('tradingUnits.startRequestSubmitted'))
    }
    await onUnitUpdated()
  } catch (error: unknown) {
    if (error !== 'cancel' && (error as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(error, t('tradingUnits.startFailed')))
    }
  }
}

async function handleStopSelected() {
  if (!store.selectedUnitIds.length) return
  try {
    await store.stopSelectedUnits(props.workspaceId)
    ElMessage.success(t('tradingUnits.stopSent'))
    await onUnitUpdated()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, t('tradingUnits.stopFailed')))
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
    ElMessage.error(getErrorMessage(error, t('tradingUnits.updateLockFailed')))
  }
}

function handleLockTrading() {
  void applyLockPatch({ lock_trading: true }, t('tradingUnits.lockedTrading'))
}

function handleLockRunning() {
  void applyLockPatch({ lock_running: true }, t('tradingUnits.lockedRunning'))
}

function handleUnlock() {
  void applyLockPatch({ lock_trading: false, lock_running: false }, t('tradingUnits.unlocked'))
}

async function handleBulkDelete() {
  if (!store.selectedUnitIds.length) return
  try {
    await ElMessageBox.confirm(`${t('tradingUnits.confirmDeleteSelected')} ${store.selectedUnitIds.length} ${t('tradingUnits.nUnits')}？`, t('tradingUnits.deleteConfirm'), {
      type: 'warning',
    })
    await store.bulkDeleteUnits(props.workspaceId, [...store.selectedUnitIds])
    ElMessage.success(t('tradingUnits.unitDeleted'))
  } catch (error: unknown) {
    if (error !== 'cancel' && (error as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(error, t('tradingUnits.deleteFailed')))
    }
  }
}

function handleImportUnits() {
  showImportDialog.value = true
}

function handleExportUnits() {
  if (!selectedUnits.value.length) {
    ElMessage.warning(t('tradingUnits.selectUnitForExport'))
    return
  }
  showExportDialog.value = true
}

async function handleUnitsImported() {
  await onUnitUpdated()
}

function handleUnitsExported() {
  ElMessage.success(t('tradingUnits.exportDone'))
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
    ElMessage.success(result.message || t('tradingUnits.unitDirOpened'))
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, t('tradingUnits.openUnitFailed')))
  }
}

function handleOpenRuntimeDialog(unit: StrategyUnit) {
  runtimeUnit.value = unit
  showRuntimeDialog.value = true
}

</script>

<style scoped src="./TradingWorkspaceUnitsTab.styles.css"></style>
