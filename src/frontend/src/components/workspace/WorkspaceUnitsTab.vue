<template>
  <div class="workspace-units-tab">
    <teleport to="#page-header-actions" :disabled="!props.toolbarInHeader || !props.active">
      <div
        class="flex items-center justify-between flex-wrap gap-2"
        :class="props.toolbarInHeader && props.active ? 'mb-0' : 'mb-4'"
      >
        <div class="flex items-center gap-2 flex-wrap">
        <!-- Group 1: Run operations -->
        <el-button-group>
          <el-tooltip content="顺序运行选中" placement="top">
            <el-button :disabled="!hasSelection || store.running" size="small" @click="handleRunSelected(false)">
              <el-icon><VideoPlay /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="并行运行选中" placement="top">
            <el-button :disabled="!hasSelection || store.running" size="small" @click="handleRunSelected(true)">
              <el-icon><VideoPause /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="停止选中" placement="top">
            <el-button :disabled="!hasSelection" size="small" type="danger" plain @click="handleStopSelected">
              <el-icon><SwitchButton /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <!-- Group 2: Unit management -->
        <el-button-group>
          <el-tooltip content="策略重新加载" placement="top">
            <el-button size="small" @click="handleReloadStrategy">
              <el-icon><RefreshRight /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="新建单元" placement="top">
            <el-button size="small" type="primary" @click="showCreateUnit = true">
              <el-icon><Plus /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="删除单元" placement="top">
            <el-button :disabled="!hasSelection" size="small" @click="handleBulkDelete">
              <el-icon><Delete /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="导入策略单元" placement="top">
            <el-button size="small" @click="handleImportUnits">
              <el-icon><Upload /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="导出策略单元" placement="top">
            <el-button :disabled="!hasSelection" size="small" @click="handleExportUnits">
              <el-icon><Download /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <!-- Group 3: Config dialogs -->
        <el-button-group>
          <el-tooltip content="数据源" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="showDataSource = true">
              <el-icon><DataLine /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="单元设置" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="showUnitSettings = true">
              <el-icon><Setting /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="策略参数" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="showStrategyParams = true">
              <el-icon><Document /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="切换商品" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="showChangeSymbol = true">
              <el-icon><Switch /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="打开K线" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="handleOpenKline">
              <el-icon><TrendCharts /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <!-- Group 4: Optimization -->
        <el-button-group>
          <el-tooltip content="优化参数设置" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="showOptConfig = true">
              <el-icon><Aim /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="优化线程设置" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="showOptThread = true">
              <el-icon><Cpu /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="批量优化参数设置" placement="top">
            <el-button :disabled="!hasSelection" size="small" @click="showBatchOptConfig = true">
              <el-icon><Operation /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="批量提交优化" placement="top">
            <el-button :disabled="!hasSelection || batchSubmittingOptimization" :loading="batchSubmittingOptimization" size="small" type="success" @click="handleBatchSubmitOpt">
              <el-icon><Promotion /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="优化参数复制" placement="top">
            <el-button :disabled="!hasSingleSelection || !hasSelection" size="small" @click="handleCopyOptParams">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="优化任务结果" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="emit('switch-tab', 'optimization', store.selectedUnitIds[0])">
              <el-icon><Odometer /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="多任务组合报告" placement="top">
            <el-button :disabled="!hasSelection" size="small" @click="emit('switch-tab', 'report', store.selectedUnitIds[0], [...store.selectedUnitIds])">
              <el-icon><Notebook /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <!-- Group 5: Rename & Sort -->
        <el-button-group>
          <el-tooltip content="组名重命名" placement="top">
            <el-button :disabled="!hasSelection" size="small" @click="showGroupRename = true">
              <el-icon><EditPen /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="单元重命名" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="showUnitRename = true">
              <el-icon><Edit /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>

        <el-button-group>
          <el-tooltip content="上移" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="handleMove('up')">
              <el-icon><Top /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="下移" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="handleMove('down')">
              <el-icon><Bottom /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="移到顶部" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="handleMove('top')">
              <el-icon><Upload /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="移到底部" placement="top">
            <el-button :disabled="!hasSingleSelection" size="small" @click="handleMove('bottom')">
              <el-icon><Download /></el-icon>
            </el-button>
          </el-tooltip>
        </el-button-group>
        </div>

        <span class="text-sm text-gray-400">共 {{ store.units.length }} 个单元</span>
      </div>
    </teleport>

    <!-- Strategy Unit Table -->
    <el-table
      :data="store.units"
      @selection-change="onSelectionChange"
      @row-dblclick="handleRowDblClick"
      stripe
      border
      size="small"
      empty-text="暂无策略单元，点击 + 新建"
    >
      <el-table-column type="selection" width="40" />
      <el-table-column label="#" width="50" align="center">
        <template #default="{ row }">{{ row.sort_order + 1 }}</template>
      </el-table-column>
      <el-table-column prop="group_name" label="组名" min-width="120" show-overflow-tooltip />
      <el-table-column prop="strategy_name" label="策略名" min-width="120" show-overflow-tooltip />
      <el-table-column prop="symbol" label="代码" width="80" />
      <el-table-column prop="symbol_name" label="名称" width="100" show-overflow-tooltip />
      <el-table-column prop="timeframe" label="周期" width="70" align="center" />
      <el-table-column prop="category" label="分类" width="80" show-overflow-tooltip />
      <el-table-column label="起始日期" width="150">
        <template #default="{ row }">{{ formatDate(row.data_config?.start_date) }}</template>
      </el-table-column>
      <el-table-column label="结束日期" width="150">
        <template #default="{ row }">{{ row.data_config?.use_end_date ? formatDate(row.data_config?.end_date) : '-' }}</template>
      </el-table-column>
      <el-table-column label="bar数" width="70" align="center">
        <template #default="{ row }">{{ row.bar_count ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="策略目标" width="100" align="center">
        <template #default="{ row }">{{ objectiveLabel(row.optimization_config?.objective) }}</template>
      </el-table-column>
      <el-table-column label="运行状态" width="120" align="center">
        <template #default="{ row }">
          <!--
            Bug8 follow-up: show "completed/total" from initialization so the
            column always reflects optimization task cardinality.
          -->
          <template v-if="shouldShowOptimizationProgress(row)">
            {{ formatOptimizationCount(row) }}
          </template>
          <template v-else-if="shouldShowOptimizationTerminal(row)">
            <el-tag :type="optimizationStatusTagType(row.opt_status)" size="small">
              {{ optimizationStatusLabel(row.opt_status) }}
            </el-tag>
          </template>
          <template v-else>
            <el-tag :type="runStatusTagType(row.run_status)" size="small">
              {{ runStatusLabel(row.run_status) }}
            </el-tag>
          </template>
        </template>
      </el-table-column>
      <el-table-column prop="run_count" label="运行次数" width="80" align="center" />
      <el-table-column label="已用时间" width="90" align="center">
        <template #default="{ row }">
          {{ formatElapsedTime(row) }}
        </template>
      </el-table-column>
      <el-table-column label="剩余时间" width="130" align="center">
        <template #default="{ row }">
          {{ formatRemainingTime(row) }}
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="150">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <!-- Create Unit Dialog -->
    <CreateUnitDialog
      v-model="showCreateUnit"
      :workspace-id="props.workspaceId"
      @created="onUnitCreated"
    />

    <!-- Data Source Dialog -->
    <DataSourceDialog
      v-model="showDataSource"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      workspace-type="research"
      @saved="onUnitUpdated"
    />

    <!-- Unit Settings Dialog -->
    <UnitSettingsDialog
      v-model="showUnitSettings"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      workspace-type="research"
      @saved="onUnitUpdated"
    />

    <!-- Strategy Params Dialog -->
    <StrategyParamsDialog
      v-model="showStrategyParams"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      workspace-type="research"
      @saved="onUnitUpdated"
    />

    <!-- Optimization Config Dialog -->
    <OptimizationConfigDialog
      v-model="showOptConfig"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      @saved="onUnitUpdated"
    />

    <!-- Optimization Thread Dialog -->
    <OptimizationThreadDialog
      v-model="showOptThread"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      @saved="onUnitUpdated"
    />

    <!-- Batch Optimization Config Dialog -->
    <BatchOptimizationConfigDialog
      v-model="showBatchOptConfig"
      :workspace-id="props.workspaceId"
      :unit-ids="store.selectedUnitIds"
      :units="store.units"
      @saved="onUnitUpdated"
    />

    <!-- Change Symbol Dialog -->
    <ChangeSymbolDialog
      v-model="showChangeSymbol"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      :selected-unit-ids="store.selectedUnitIds"
      @saved="onUnitsRefresh"
    />

    <!-- Hidden file input for import -->
    <input
      ref="importFileInput"
      type="file"
      accept=".json"
      style="display: none"
      @change="onImportFileSelected"
    />

    <!-- Group Rename Dialog -->
    <GroupRenameDialog
      v-model="showGroupRename"
      :workspace-id="props.workspaceId"
      :unit-ids="store.selectedUnitIds"
      @saved="onUnitsRefresh"
    />

    <!-- Unit Rename Dialog -->
    <UnitRenameDialog
      v-model="showUnitRename"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      @saved="onUnitsRefresh"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import {
  Plus, Delete, VideoPlay, VideoPause, SwitchButton,
  DataLine, Setting, Document, Aim, EditPen, Edit,
  Top, Bottom, Upload, Download, RefreshRight,
  Switch, TrendCharts, Cpu, CopyDocument, Odometer, Notebook,
  Operation, Promotion,
} from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { workspaceApi } from '@/api/workspace'
import { getErrorMessage } from '@/api/index'
import type { StrategyUnit } from '@/types/workspace'
import CreateUnitDialog from './CreateUnitDialog.vue'
import DataSourceDialog from './DataSourceDialog.vue'
import UnitSettingsDialog from './UnitSettingsDialog.vue'
import StrategyParamsDialog from './StrategyParamsDialog.vue'
import OptimizationConfigDialog from './OptimizationConfigDialog.vue'
import OptimizationThreadDialog from './OptimizationThreadDialog.vue'
import BatchOptimizationConfigDialog from './BatchOptimizationConfigDialog.vue'
import ChangeSymbolDialog from './ChangeSymbolDialog.vue'
import GroupRenameDialog from './GroupRenameDialog.vue'
import UnitRenameDialog from './UnitRenameDialog.vue'

const props = defineProps<{
  workspaceId: string
  active?: boolean
  toolbarInHeader?: boolean
}>()

const emit = defineEmits<{
  'switch-tab': [tab: string, unitId?: string, unitIds?: string[]]
}>()

const store = useWorkspaceStore()
const router = useRouter()

const hasSelection = computed(() => store.selectedUnitIds.length > 0)
const hasSingleSelection = computed(() => store.selectedUnitIds.length === 1)
const selectedUnit = computed<StrategyUnit | null>(() => {
  if (!hasSingleSelection.value) return null
  return store.units.find(u => u.id === store.selectedUnitIds[0]) ?? null
})

// Dialog visibility flags
const showCreateUnit = ref(false)
const showDataSource = ref(false)
const showUnitSettings = ref(false)
const showStrategyParams = ref(false)
const showOptConfig = ref(false)
const showOptThread = ref(false)
const showBatchOptConfig = ref(false)
const showChangeSymbol = ref(false)
const showGroupRename = ref(false)
const showUnitRename = ref(false)
const importFileInput = ref<HTMLInputElement | null>(null)
const batchSubmittingOptimization = ref(false)
const nowMs = ref(Date.now())
let clockTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  store.startPolling(props.workspaceId)
  clockTimer = setInterval(() => {
    nowMs.value = Date.now()
  }, 1000)
})
onUnmounted(() => {
  store.stopPolling()
  if (clockTimer) {
    clearInterval(clockTimer)
    clockTimer = null
  }
})

function onSelectionChange(rows: StrategyUnit[]) {
  store.setSelectedUnitIds(rows.map(r => r.id))
}

function canOpenReport(unit: StrategyUnit): boolean {
  return unit.run_status === 'completed' && !!unit.last_task_id
}

function handleRowDblClick(row: StrategyUnit, column?: { type?: string }, event?: Event) {
  if (!canOpenReport(row)) return
  if (column?.type === 'selection') return
  const target = event?.target as HTMLElement | null
  if (target?.closest('button, a, .el-checkbox')) return
  router.push({
    name: 'BacktestResult',
    params: { id: row.last_task_id as string },
    query: { workspaceId: props.workspaceId },
  })
}

function onUnitCreated() {
  store.fetchUnits(props.workspaceId)
}
async function onUnitUpdated() {
  await store.fetchUnits(props.workspaceId)
  await store.pollStatus(props.workspaceId)
}
async function onUnitsRefresh() {
  await store.fetchUnits(props.workspaceId)
  await store.pollStatus(props.workspaceId)
}

// --- Bulk delete ---
async function handleBulkDelete() {
  if (!store.selectedUnitIds.length) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${store.selectedUnitIds.length} 个单元？`, '删除确认', { type: 'warning' })
    await store.bulkDeleteUnits(props.workspaceId, [...store.selectedUnitIds])
    ElMessage.success('已删除')
  } catch (e: unknown) {
    if (e !== 'cancel' && (e as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(e, '删除失败'))
    }
  }
}

// --- Run / Stop ---
async function handleRunSelected(parallel = false) {
  if (!store.selectedUnitIds.length) return
  try {
    await store.runSelectedUnits(props.workspaceId, parallel)
    ElMessage.success(parallel ? '并行运行已启动' : '顺序运行已启动')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '运行失败'))
  }
}

async function handleStopSelected() {
  if (!store.selectedUnitIds.length) return
  try {
    await store.stopSelectedUnits(props.workspaceId)
    ElMessage.success('已发送停止指令')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '停止失败'))
  }
}

// --- Move / Reorder ---
async function handleMove(direction: 'up' | 'down' | 'top' | 'bottom') {
  if (!hasSingleSelection.value) return
  const unitId = store.selectedUnitIds[0]
  const ids = store.units.map(u => u.id)
  const idx = ids.indexOf(unitId)
  if (idx < 0) return

  const newIds = [...ids]
  newIds.splice(idx, 1)
  let insertAt = idx
  if (direction === 'up' && idx > 0) insertAt = idx - 1
  else if (direction === 'down' && idx < ids.length - 1) insertAt = idx + 1
  else if (direction === 'top') insertAt = 0
  else if (direction === 'bottom') insertAt = newIds.length
  else return

  newIds.splice(insertAt, 0, unitId)
  try {
    await store.reorderUnits(props.workspaceId, newIds)
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '排序失败'))
  }
}

// --- Reload strategy ---
function handleReloadStrategy() {
  store.fetchUnits(props.workspaceId)
  ElMessage.success('策略已重新加载')
}

// --- Import / Export ---
function handleImportUnits() {
  importFileInput.value?.click()
}

async function onImportFileSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    const data = JSON.parse(text)
    const units = Array.isArray(data) ? data : (data.units ?? [])
    if (!units.length) {
      ElMessage.warning('文件中未找到策略单元数据')
      return
    }
    await store.batchCreateUnits(props.workspaceId, units)
    ElMessage.success(`成功导入 ${units.length} 个策略单元`)
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '导入失败'))
  } finally {
    if (importFileInput.value) importFileInput.value.value = ''
  }
}

function handleExportUnits() {
  const selected = store.units.filter(u => store.selectedUnitIds.includes(u.id))
  if (!selected.length) return
  const exportData = selected.map(u => ({
    strategy_name: u.strategy_name,
    strategy_id: u.strategy_id,
    symbol: u.symbol,
    symbol_name: u.symbol_name,
    timeframe: u.timeframe,
    group_name: u.group_name,
    category: u.category,
    data_config: u.data_config,
    unit_settings: u.unit_settings,
    params: u.params,
    optimization_config: u.optimization_config,
  }))
  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `units_export_${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success(`已导出 ${selected.length} 个策略单元`)
}

// --- Open K-line ---
function handleOpenKline() {
  if (!selectedUnit.value) return
  const u = selectedUnit.value
  const url = `/backtest/legacy?symbol=${u.symbol}&timeframe=${u.timeframe}`
  window.open(url, '_blank')
}

function inferBatchParamType(layer: { start: number; end: number; step: number }): 'int' | 'float' {
  const values = [layer.start, layer.end, layer.step]
  return values.every(v => Number.isInteger(v)) ? 'int' : 'float'
}

function calculateBatchTotalCombinations(
  paramRanges: Record<string, { start: number; end: number; step: number; type: string }>,
): number {
  const counts = Object.values(paramRanges).map(spec => {
    const distance = spec.end - spec.start
    if (distance <= 0 || spec.step <= 0) {
      return 0
    }
    return Math.floor(distance / spec.step) + 1
  })
  if (!counts.length) {
    return 0
  }
  return counts.reduce((product, count) => product * count, 1)
}

function initializeUnitOptimizationState(
  unit: StrategyUnit,
  totalCombinations: number | null,
  taskId?: string,
) {
  const now = Date.now()
  if (taskId) {
    unit.last_optimization_task_id = taskId
  }
  unit.opt_status = 'pending'
  unit.opt_elapsed_time = 0
  unit.opt_remaining_time = 0
  unit.opt_total = totalCombinations
  unit.opt_completed = totalCombinations == null ? null : 0
  unit.opt_progress = 0
  unit.opt_started_at_ms = now
  unit.opt_last_sync_at_ms = now
}

function sleep(ms: number) {
  return new Promise(resolve => window.setTimeout(resolve, ms))
}

function isOptimizationActiveStatus(status: string | null | undefined) {
  return status === 'pending' || status === 'queued' || status === 'running'
}

function isOptimizationPendingStatus(status: string | null | undefined) {
  return status === 'pending' || status === 'queued'
}

function isOptimizationTerminalStatus(status: string | null | undefined) {
  return status === 'completed' || status === 'failed' || status === 'cancelled'
}

function getOptimizationTotal(row: StrategyUnit): number {
  return Math.max(0, Number(row.opt_total ?? 0))
}

function getOptimizationCompleted(row: StrategyUnit): number {
  return Math.max(0, Number(row.opt_completed ?? 0))
}

function hasOptimizationInProgressSnapshot(row: StrategyUnit): boolean {
  const total = getOptimizationTotal(row)
  if (total <= 0) return false
  return getOptimizationCompleted(row) < total
}

function shouldShowOptimizationProgress(row: StrategyUnit): boolean {
  if (isOptimizationActiveStatus(row.opt_status)) {
    return true
  }
  if (isOptimizationTerminalStatus(row.opt_status)) {
    return false
  }
  return hasOptimizationInProgressSnapshot(row)
}

function shouldShowOptimizationTerminal(row: StrategyUnit): boolean {
  if (!isOptimizationTerminalStatus(row.opt_status)) {
    return false
  }
  if (row.opt_status !== 'completed') {
    return true
  }
  const total = getOptimizationTotal(row)
  return total <= 0 || getOptimizationCompleted(row) >= total
}

async function waitForUnitOptimizationCompletion(unitId: string, pendingUnitIds: string[] = [], timeoutMs = 12 * 60 * 60 * 1000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    // Refresh protection window for units still queued in the batch
    const nowTs = Date.now()
    for (const pid of pendingUnitIds) {
      const pu = store.units.find(item => item.id === pid)
      if (pu && isOptimizationPendingStatus(pu.opt_status)) {
        pu.opt_started_at_ms = nowTs
      }
    }
    await store.pollStatus(props.workspaceId)
    const unit = store.units.find(item => item.id === unitId)
    if (unit && shouldShowOptimizationTerminal(unit)) {
      return unit.opt_status
    }

    const progress = await workspaceApi.getOptimizationProgress(props.workspaceId, unitId).catch(() => null)
    if (unit && progress) {
      const status = typeof progress.status === 'string' ? progress.status : unit.opt_status ?? null
      const completed = Number(progress.completed ?? 0)
      const failed = Number(progress.failed ?? 0)
      const total = Number(progress.total ?? unit.opt_total ?? 0)
      const elapsed = Number(progress.elapsed_time ?? unit.opt_elapsed_time ?? 0)
      const remaining = Number(progress.remaining_time ?? unit.opt_remaining_time ?? 0)
      const done = completed + failed
      const prematureCompleted = status === 'completed' && total > 0 && done < total
      if (!prematureCompleted) {
        unit.opt_status = status
      }
      unit.opt_total = Number.isFinite(total) ? total : unit.opt_total
      unit.opt_completed = Number.isFinite(done) ? done : unit.opt_completed
      unit.opt_progress = Number(progress.progress ?? unit.opt_progress ?? 0)
      unit.opt_elapsed_time = Number.isFinite(elapsed) ? elapsed : unit.opt_elapsed_time
      unit.opt_remaining_time = Number.isFinite(remaining) ? remaining : unit.opt_remaining_time
      unit.opt_last_sync_at_ms = nowTs
      if (unit.opt_status === 'running') {
        unit.opt_started_at_ms = nowTs - Math.round(Math.max(0, unit.opt_elapsed_time ?? 0) * 1000)
      } else if (unit.opt_status === 'pending' || unit.opt_status === 'queued') {
        unit.opt_started_at_ms = nowTs
        unit.opt_elapsed_time = 0
        unit.opt_remaining_time = 0
      } else if (unit.opt_status) {
        unit.opt_started_at_ms = null
        unit.opt_last_sync_at_ms = null
        unit.opt_remaining_time = 0
      }
      if (shouldShowOptimizationTerminal(unit)) {
        return unit.opt_status
      }
    }
    if (unit && shouldShowOptimizationTerminal(unit)) {
      return unit.opt_status
    }
    await sleep(3000)
  }
  throw new Error('等待优化任务完成超时')
}

// --- Batch submit optimization ---
async function handleBatchSubmitOpt() {
  const ids = store.selectedUnitIds
  if (!ids.length) return

  batchSubmittingOptimization.value = true
  try {
    await store.fetchUnits(props.workspaceId)

    const unitsWithConfig = store.units.filter(
      u => ids.includes(u.id) && u.optimization_config && (u.optimization_config as Record<string, unknown>).param_layers
    )
    if (!unitsWithConfig.length) {
      ElMessage.warning('选中的单元尚未设置优化参数（param_layers），请先通过"批量优化参数设置"配置')
      return
    }

    let validCount = 0
    const invalidNames: string[] = []
    for (const u of unitsWithConfig) {
      const oc = u.optimization_config as Record<string, unknown>
      const layers = (oc.param_layers || []) as Array<{ param_name: string; opt_type: string; start: number; end: number; step: number }>
      const hasValid = layers.some(l => l.param_name && l.opt_type === 'equal_diff' && l.step > 0 && l.end > l.start)
      if (hasValid) {
        validCount++
      } else {
        invalidNames.push(u.strategy_name || u.strategy_id || u.id)
      }
    }
    if (validCount === 0) {
      ElMessage.warning('所有选中单元的优化参数范围无效（请确保 结束值 > 起始值 且 步长 > 0）')
      return
    }

    const invalidHint = invalidNames.length > 0 ? `\n（${invalidNames.length} 个单元参数范围无效将被跳过）` : ''
    try {
      await ElMessageBox.confirm(
        `确认顺序为 ${validCount} 个单元串行提交优化任务？${invalidHint}`,
        '批量提交优化',
        { type: 'info' },
      )
    } catch { return }

    // Bug8 fix: Pre-initialize optimization status / elapsed / remaining for ALL
    // selected units so the UI immediately shows a fresh 0/N progress state and
    // zeroed timers, instead of keeping the previous completed task snapshot.
    for (const u of unitsWithConfig) {
      const localUnit = store.units.find(item => item.id === u.id)
      if (!localUnit) continue
      const oc = u.optimization_config as Record<string, unknown>
      const layers = (oc.param_layers || []) as Array<{ param_name: string; opt_type: string; start: number; end: number; step: number }>
      const ranges: Record<string, { start: number; end: number; step: number; type: string }> = {}
      for (const l of layers) {
        if (!l.param_name || l.opt_type !== 'equal_diff' || l.step <= 0 || l.end <= l.start) continue
        ranges[l.param_name] = {
          start: l.start,
          end: l.end,
          step: l.step,
          type: inferBatchParamType(l),
        }
      }
      const total = Object.keys(ranges).length ? calculateBatchTotalCombinations(ranges) : 0
      initializeUnitOptimizationState(localUnit, total || null)
    }

    const remainingQueue = unitsWithConfig.map(u => u.id)

    let completed = 0
    let failed = 0
    let submitFailed = 0
    const errors: string[] = []

    for (const u of unitsWithConfig) {
      const name = u.strategy_name || u.id
      const localUnit = store.units.find(item => item.id === u.id)
      const qIdx = remainingQueue.indexOf(u.id)
      if (qIdx >= 0) remainingQueue.splice(qIdx, 1)
      try {
        const oc = u.optimization_config as Record<string, unknown>
        const layers = (oc.param_layers || []) as Array<{ param_name: string; opt_type: string; start: number; end: number; step: number }>
        const paramRanges: Record<string, { start: number; end: number; step: number; type: string }> = {}
        for (const l of layers) {
          if (!l.param_name || l.opt_type !== 'equal_diff' || l.step <= 0 || l.end <= l.start) continue
          paramRanges[l.param_name] = {
            start: l.start,
            end: l.end,
            step: l.step,
            type: inferBatchParamType(l),
          }
        }
        if (!Object.keys(paramRanges).length) {
          errors.push(`${name}: 无有效参数范围`)
          submitFailed++
          continue
        }

        const totalCombinations = calculateBatchTotalCombinations(paramRanges)
        if (localUnit) {
          initializeUnitOptimizationState(localUnit, totalCombinations || null)
        }

        const nWorkers = (oc.n_workers as number) || 4
        const mode = (oc.mode as string) || 'grid'
        const timeout = (oc.timeout as number) || 0
        const result = await workspaceApi.submitOptimization(props.workspaceId, {
          unit_id: u.id,
          param_ranges: paramRanges,
          n_workers: nWorkers,
          mode,
          timeout,
        })

        if (localUnit) {
          initializeUnitOptimizationState(localUnit, result.total_combinations, result.task_id)
        }

        await store.pollStatus(props.workspaceId)

        const terminalStatus = await waitForUnitOptimizationCompletion(u.id, [...remainingQueue])
        if (terminalStatus === 'completed') {
          completed++
        } else {
          failed++
          errors.push(`${name}: 优化结束状态 ${terminalStatus}`)
        }
      } catch (e: unknown) {
        errors.push(`${name}: ${getErrorMessage(e, '提交失败')}`)
        submitFailed++
      }
    }

    if (failed > 0 || submitFailed > 0) {
      ElMessage.warning(`串行优化完成：${completed} 个完成，${failed} 个运行失败，${submitFailed} 个提交失败\n${errors.slice(0, 3).join('; ')}`)
    } else {
      ElMessage.success(`串行优化完成：${completed} 个单元已依次执行完成`)
    }
  } finally {
    batchSubmittingOptimization.value = false
    await store.fetchUnits(props.workspaceId)
  }
}

// --- Copy optimization params ---
async function handleCopyOptParams() {
  if (!selectedUnit.value) return
  const source = selectedUnit.value
  if (!source.optimization_config) {
    ElMessage.warning('当前单元没有优化参数设置')
    return
  }
  const targets = store.selectedUnitIds.filter(id => id !== source.id)
  if (!targets.length) {
    ElMessage.warning('请额外选中要复制到的目标单元')
    return
  }
  try {
    for (const id of targets) {
      await workspaceApi.updateUnit(props.workspaceId, id, {
        optimization_config: { ...source.optimization_config },
      })
    }
    ElMessage.success(`优化参数已复制到 ${targets.length} 个单元`)
    store.fetchUnits(props.workspaceId)
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '复制失败'))
  }
}

// --- Formatters ---
function runStatusTagType(status: string) {
  const map: Record<string, string> = {
    idle: 'info', queued: 'warning', running: '', completed: 'success', failed: 'danger', cancelled: 'warning',
  }
  return map[status] || 'info'
}

function runStatusLabel(status: string) {
  const map: Record<string, string> = {
    idle: '空闲', queued: '排队中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消',
  }
  return map[status] || status
}

function optimizationStatusTagType(status: string | null | undefined) {
  const map: Record<string, string> = {
    completed: 'success', failed: 'danger', cancelled: 'warning',
  }
  return map[status || ''] || 'info'
}

function optimizationStatusLabel(status: string | null | undefined) {
  const map: Record<string, string> = {
    completed: '已完成', failed: '失败', cancelled: '已取消',
  }
  return map[status || ''] || '-'
}

function objectiveLabel(obj: string | undefined) {
  if (!obj) return '-'
  const map: Record<string, string> = {
    sharpe_max: '夏普最大', max_return: '最大收益', min_drawdown: '最小回撤',
  }
  return map[obj] || obj
}

function formatOptimizationCount(row: StrategyUnit): string {
  const total = getOptimizationTotal(row)
  if (total <= 0) return '-'
  return `${getOptimizationCompleted(row)}/${total}`
}

function getLiveOptimizationElapsedSeconds(row: StrategyUnit): number {
  const syncedElapsed = Math.max(0, row.opt_elapsed_time ?? 0)
  if (row.opt_status !== 'running') {
    return syncedElapsed
  }
  const startedAt = row.opt_started_at_ms
  if (!startedAt) {
    return syncedElapsed
  }
  const liveElapsed = Math.max(0, (nowMs.value - startedAt) / 1000)
  return Math.max(syncedElapsed, liveElapsed)
}

function getLiveOptimizationRemainingSeconds(row: StrategyUnit): number {
  return Math.max(0, row.opt_remaining_time ?? 0)
}

function formatElapsedTime(row: StrategyUnit): string {
  if (row.opt_status === 'running') {
    return `${getLiveOptimizationElapsedSeconds(row).toFixed(1)}s`
  }
  if (shouldShowOptimizationTerminal(row) && row.opt_elapsed_time != null) {
    return `${row.opt_elapsed_time.toFixed(1)}s`
  }
  if (shouldShowOptimizationProgress(row) && row.opt_elapsed_time != null) {
    return `${Math.max(0, row.opt_elapsed_time).toFixed(1)}s`
  }
  return row.last_run_time != null ? `${row.last_run_time.toFixed(1)}s` : '-'
}

function formatRemainingTime(row: StrategyUnit): string {
  if (row.opt_status === 'running') {
    return `${getLiveOptimizationRemainingSeconds(row).toFixed(1)}s`
  }
  if (row.opt_status === 'pending' || row.opt_status === 'queued') {
    return '0.0s'
  }
  if (shouldShowOptimizationTerminal(row)) {
    return '0.0s'
  }
  if (shouldShowOptimizationProgress(row)) {
    return `${Math.max(0, row.opt_remaining_time ?? 0).toFixed(1)}s`
  }
  return estimateRemaining(row)
}

function estimateRemaining(row: StrategyUnit): string {
  if (row.run_status !== 'running') return '-'
  // Estimate based on average run time from previous runs
  if (row.run_count && row.run_count > 0 && row.last_run_time && row.last_run_time > 0) {
    // Simple heuristic: average previous run time as estimate
    const avgTime = row.last_run_time
    // We don't track elapsed of current run, so show estimated total
    return `~${avgTime.toFixed(0)}s`
  }
  return '...'
}

function formatDate(dateStr: string | undefined) {
  if (!dateStr) return '-'
  return dateStr.slice(0, 10)
}

function formatTime(iso: string) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN')
}
</script>
