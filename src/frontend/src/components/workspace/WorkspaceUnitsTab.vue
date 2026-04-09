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
          <el-tooltip content="优化参数复制" placement="top">
            <el-button :disabled="!hasSingleSelection || !hasSelection" size="small" @click="handleCopyOptParams">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="优化任务结果" placement="top">
            <el-button size="small" @click="emit('switch-tab', 'optimization')">
              <el-icon><Odometer /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="多任务组合报告" placement="top">
            <el-button size="small" @click="emit('switch-tab', 'report')">
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
      @row-click="handleRowClick"
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
      <el-table-column label="运行状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="runStatusTagType(row.run_status)" size="small">
            {{ runStatusLabel(row.run_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="run_count" label="运行次数" width="80" align="center" />
      <el-table-column label="已用时间" width="90" align="center">
        <template #default="{ row }">
          {{ row.last_run_time != null ? row.last_run_time.toFixed(1) + 's' : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="剩余时间" width="90" align="center">
        <template #default="{ row }">
          {{ estimateRemaining(row) }}
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
      @saved="onUnitUpdated"
    />

    <!-- Unit Settings Dialog -->
    <UnitSettingsDialog
      v-model="showUnitSettings"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      @saved="onUnitUpdated"
    />

    <!-- Strategy Params Dialog -->
    <StrategyParamsDialog
      v-model="showStrategyParams"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
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
import ChangeSymbolDialog from './ChangeSymbolDialog.vue'
import GroupRenameDialog from './GroupRenameDialog.vue'
import UnitRenameDialog from './UnitRenameDialog.vue'

const props = defineProps<{
  workspaceId: string
  active?: boolean
  toolbarInHeader?: boolean
}>()

const emit = defineEmits<{
  'switch-tab': [tab: string]
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
const showChangeSymbol = ref(false)
const showGroupRename = ref(false)
const showUnitRename = ref(false)
const importFileInput = ref<HTMLInputElement | null>(null)

onMounted(() => {
  store.startPolling(props.workspaceId)
})
onUnmounted(() => {
  store.stopPolling()
})

function onSelectionChange(rows: StrategyUnit[]) {
  store.setSelectedUnitIds(rows.map(r => r.id))
}

function canOpenReport(unit: StrategyUnit): boolean {
  return unit.run_status === 'completed' && !!unit.last_task_id
}

function handleRowClick(row: StrategyUnit, column?: { type?: string }, event?: Event) {
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
function onUnitUpdated() {
  store.fetchUnits(props.workspaceId)
}
function onUnitsRefresh() {
  store.fetchUnits(props.workspaceId)
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

function objectiveLabel(obj: string | undefined) {
  if (!obj) return '-'
  const map: Record<string, string> = {
    sharpe_max: '夏普最大', max_return: '最大收益', min_drawdown: '最小回撤',
  }
  return map[obj] || obj
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
