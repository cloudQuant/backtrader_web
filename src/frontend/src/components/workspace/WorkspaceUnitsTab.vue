<template>
  <div class="workspace-units-tab">
    <teleport
      to="#page-header-actions"
      :disabled="!props.toolbarInHeader || !props.active"
    >
      <div
        class="flex items-center justify-between flex-wrap gap-2"
        :class="props.toolbarInHeader && props.active ? 'mb-0' : 'mb-4'"
      >
        <div class="flex items-center gap-2 flex-wrap">
          <!-- Group 1: Run operations -->
          <el-button-group>
            <el-tooltip
              :content="t('units.runSerial')"
              placement="top"
            >
              <el-button
                :disabled="!hasSelection || store.running"
                size="small"
                @click="handleRunSelected(false)"
              >
                <el-icon aria-hidden="true"><VideoPlay /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.runParallel')"
              placement="top"
            >
              <el-button
                :disabled="!hasSelection || store.running"
                size="small"
                @click="handleRunSelected(true)"
              >
                <el-icon aria-hidden="true"><VideoPause /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.stopSelected')"
              placement="top"
            >
              <el-button
                :disabled="!hasSelection"
                size="small"
                type="danger"
                plain
                @click="handleStopSelected"
              >
                <el-icon aria-hidden="true"><SwitchButton /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <!-- Group 2: Unit management -->
          <el-button-group>
            <el-tooltip
              :content="t('units.reloadStrategy')"
              placement="top"
            >
              <el-button
                size="small"
                @click="handleReloadStrategy"
              >
                <el-icon aria-hidden="true"><RefreshRight /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.createUnit')"
              placement="top"
            >
              <el-button
                size="small"
                type="primary"
                @click="showCreateUnit = true"
              >
                <el-icon aria-hidden="true"><Plus /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.deleteUnit')"
              placement="top"
            >
              <el-button
                :disabled="!hasSelection"
                size="small"
                @click="handleBulkDelete"
              >
                <el-icon aria-hidden="true"><Delete /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.importUnits')"
              placement="top"
            >
              <el-button
                size="small"
                @click="handleImportUnits"
              >
                <el-icon aria-hidden="true"><Upload /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.exportUnits')"
              placement="top"
            >
              <el-button
                :disabled="!hasSelection"
                size="small"
                @click="handleExportUnits"
              >
                <el-icon aria-hidden="true"><Download /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <!-- Group 3: Config dialogs -->
          <el-button-group>
            <el-tooltip
              :content="t('units.dataSource')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="showDataSource = true"
              >
                <el-icon aria-hidden="true"><DataLine /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.unitSettings')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="showUnitSettings = true"
              >
                <el-icon aria-hidden="true"><Setting /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.strategyParams')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="showStrategyParams = true"
              >
                <el-icon aria-hidden="true"><Document /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.switchSymbol')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="showChangeSymbol = true"
              >
                <el-icon aria-hidden="true"><Switch /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.open') + ' K'"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="handleOpenKline"
              >
                <el-icon aria-hidden="true"><TrendCharts /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="查看回测结果"
              placement="top"
            >
              <el-button
                :disabled="!hasOpenableSelectedReport"
                size="small"
                @click="handleOpenSelectedReport"
              >
                <el-icon aria-hidden="true"><View /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <!-- Group 4: Optimization -->
          <el-button-group>
            <el-tooltip
              :content="t('units.paramOpt')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="showOptConfig = true"
              >
                <el-icon aria-hidden="true"><Aim /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.threadOpt')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="showOptThread = true"
              >
                <el-icon aria-hidden="true"><Cpu /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.batchParamOpt')"
              placement="top"
            >
              <el-button
                :disabled="!hasSelection"
                size="small"
                @click="showBatchOptConfig = true"
              >
                <el-icon aria-hidden="true"><Operation /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.submitBatchOpt')"
              placement="top"
            >
              <el-button
                :disabled="!hasSelection || batchSubmittingOptimization"
                :loading="batchSubmittingOptimization"
                size="small"
                type="success"
                @click="handleBatchSubmitOpt"
              >
                <el-icon aria-hidden="true"><Promotion /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.paramOptCopy')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection || !hasSelection"
                size="small"
                @click="handleCopyOptParams"
              >
                <el-icon aria-hidden="true"><CopyDocument /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.optResults')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="emit('switch-tab', 'optimization', store.selectedUnitIds[0])"
              >
                <el-icon aria-hidden="true"><Odometer /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.multiTaskReport')"
              placement="top"
            >
              <el-button
                :disabled="!hasSelection"
                size="small"
                @click="emit('switch-tab', 'report', store.selectedUnitIds[0], [...store.selectedUnitIds])"
              >
                <el-icon aria-hidden="true"><Notebook /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <!-- Group 5: Rename & Sort -->
          <el-button-group>
            <el-tooltip
              :content="t('units.groupRename')"
              placement="top"
            >
              <el-button
                :disabled="!hasSelection"
                size="small"
                @click="showGroupRename = true"
              >
                <el-icon aria-hidden="true"><EditPen /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.renameUnit')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="showUnitRename = true"
              >
                <el-icon aria-hidden="true"><Edit /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <el-button-group>
            <el-tooltip
              :content="t('units.moveUp')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="handleMove('up')"
              >
                <el-icon aria-hidden="true"><Top /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.moveDown')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="handleMove('down')"
              >
                <el-icon aria-hidden="true"><Bottom /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.moveTop')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="handleMove('top')"
              >
                <el-icon aria-hidden="true"><Upload /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('units.moveBottom')"
              placement="top"
            >
              <el-button
                :disabled="!hasSingleSelection"
                size="small"
                @click="handleMove('bottom')"
              >
                <el-icon aria-hidden="true"><Download /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>
        </div>

        <span class="text-sm text-gray-400">{{ t('units.total') }} {{ store.units.length }} {{ t('units.nUnitsSuffix') }}</span>
      </div>
    </teleport>

    <!-- Strategy Unit Table -->
    <el-table
      :data="store.units"
      stripe
      border
      size="small"
      :empty-text="t('units.emptyUnits') + '，' + t('units.clickToCreate') + ' + ' + t('units.create')"
      @selection-change="onSelectionChange"
      @row-dblclick="handleRowDblClick"
    >
      <el-table-column
        type="selection"
        width="40"
      />
      <el-table-column
        label="#"
        width="50"
        align="center"
      >
        <template #default="{ row }">
          {{ row.sort_order + 1 }}
        </template>
      </el-table-column>
      <el-table-column
        prop="group_name"
        :label="t('units.groupName')"
        min-width="120"
        show-overflow-tooltip
      />
      <el-table-column
        prop="strategy_name"
        :label="t('units.strategyName')"
        min-width="120"
        show-overflow-tooltip
      />
      <el-table-column
        prop="symbol"
        :label="t('units.code')"
        width="80"
      />
      <el-table-column
        prop="symbol_name"
        :label="t('units.name')"
        width="100"
        show-overflow-tooltip
      />
      <el-table-column
        prop="timeframe"
        :label="t('units.timeframe')"
        width="70"
        align="center"
      />
      <el-table-column
        prop="category"
        :label="t('units.category')"
        width="80"
        show-overflow-tooltip
      />
      <el-table-column
        :label="t('units.rangeStartDate')"
        width="150"
      >
        <template #default="{ row }">
          {{ formatDate(row.data_config?.start_date) }}
        </template>
      </el-table-column>
      <el-table-column
        :label="t('units.rangeEndDate')"
        width="150"
      >
        <template #default="{ row }">
          {{ row.data_config?.use_end_date ? formatDate(row.data_config?.end_date) : '-' }}
        </template>
      </el-table-column>
      <el-table-column
        :label="'bar ' + t('units.countSuffix')"
        width="70"
        align="center"
      >
        <template #default="{ row }">
          {{ row.bar_count ?? '-' }}
        </template>
      </el-table-column>
      <el-table-column
        :label="t('units.strategyTarget')"
        width="100"
        align="center"
      >
        <template #default="{ row }">
          {{ objectiveLabel(row.optimization_config?.objective) }}
        </template>
      </el-table-column>
      <el-table-column
        :label="t('units.runStatus')"
        width="120"
        align="center"
      >
        <template #default="{ row }">
          <div class="unit-status-cell">
            <template v-if="shouldShowOptimizationProgress(row)">
              <span class="unit-status-count">{{ formatOptimizationCount(row) }}</span>
              <el-progress
                class="unit-status-progress"
                :percentage="optimizationProgressPercent(row)"
                :stroke-width="6"
                :show-text="false"
              />
            </template>
            <template v-else-if="shouldShowOptimizationTerminal(row)">
              <el-tag
                :type="optimizationStatusTagType(row.opt_status)"
                size="small"
              >
                {{ optimizationStatusLabel(row.opt_status) }}
              </el-tag>
            </template>
            <template v-else>
              <el-tag
                :type="runStatusTagType(row.run_status)"
                size="small"
              >
                {{ runStatusLabel(row.run_status) }}
              </el-tag>
              <template v-if="shouldShowRunProgress(row)">
                <span class="unit-status-count">{{ runProgressLabel(row) }}</span>
                <el-progress
                  class="unit-status-progress"
                  :percentage="runProgressPercent(row)"
                  :status="runProgressStatus(row)"
                  :stroke-width="6"
                  :show-text="false"
                />
                <span
                  v-if="row.run_message"
                  class="unit-status-message"
                >
                  {{ row.run_message }}
                </span>
              </template>
            </template>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        label="结果"
        min-width="280"
      >
        <template #default="{ row }">
          <div class="unit-result-cell">
            <span
              class="unit-result-summary"
              :class="{ 'unit-result-summary--error': row.run_status === 'failed' }"
            >
              {{ unitResultSummary(row) }}
            </span>
            <el-button
              v-if="canOpenReport(row)"
              class="unit-result-action"
              size="small"
              link
              type="primary"
              @click.stop="openBacktestResult(row)"
            >
              <el-icon aria-hidden="true"><View /></el-icon>
              查看
            </el-button>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        prop="run_count"
        :label="t('units.runCount')"
        width="80"
        align="center"
      />
      <el-table-column
        :label="t('units.elapsed')"
        width="90"
        align="center"
      >
        <template #default="{ row }">
          {{ formatElapsedTime(row) }}
        </template>
      </el-table-column>
      <el-table-column
        :label="t('units.remaining')"
        width="130"
        align="center"
      >
        <template #default="{ row }">
          {{ formatRemainingTime(row) }}
        </template>
      </el-table-column>
      <el-table-column
        :label="t('units.createdAt')"
        width="150"
      >
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
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
    >

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
import {
  Plus, Delete, VideoPlay, VideoPause, SwitchButton,
  DataLine, Setting, Document, Aim, EditPen, Edit,
  Top, Bottom, Upload, Download, RefreshRight,
  Switch, TrendCharts, Cpu, CopyDocument, Odometer, Notebook,
  Operation, Promotion, View,
} from '@element-plus/icons-vue'
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
import {
  useWorkspaceUnitsTab,
  type WorkspaceUnitsTabProps,
} from './units/useWorkspaceUnitsTab'

const props = defineProps<WorkspaceUnitsTabProps>()
const emit = defineEmits<{
  'switch-tab': [tab: string, unitId?: string, unitIds?: string[]]
}>()
const unitsPage = useWorkspaceUnitsTab(props)
const {
  batchSubmittingOptimization,
  canOpenReport,
  formatDate,
  formatElapsedTime,
  formatOptimizationCount,
  formatRemainingTime,
  formatTime,
  handleBatchSubmitOpt,
  handleBulkDelete,
  handleCopyOptParams,
  handleExportUnits,
  handleImportUnits,
  handleMove,
  handleOpenKline,
  handleOpenSelectedReport,
  handleReloadStrategy,
  handleRowDblClick,
  handleRunSelected,
  handleStopSelected,
  hasOpenableSelectedReport,
  hasSelection,
  hasSingleSelection,
  objectiveLabel,
  onImportFileSelected,
  onSelectionChange,
  onUnitCreated,
  onUnitUpdated,
  onUnitsRefresh,
  openBacktestResult,
  optimizationProgressPercent,
  optimizationStatusLabel,
  optimizationStatusTagType,
  runProgressLabel,
  runProgressPercent,
  runProgressStatus,
  runStatusLabel,
  runStatusTagType,
  selectedUnit,
  shouldShowOptimizationProgress,
  shouldShowOptimizationTerminal,
  shouldShowRunProgress,
  showBatchOptConfig,
  showChangeSymbol,
  showCreateUnit,
  showDataSource,
  showGroupRename,
  showOptConfig,
  showOptThread,
  showStrategyParams,
  showUnitRename,
  showUnitSettings,
  store,
  t,
  unitResultSummary,
} = unitsPage

defineExpose(unitsPage)
</script>

<style scoped>
.unit-status-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.unit-status-count {
  font-size: 12px;
  line-height: 1;
  color: var(--el-text-color-secondary);
}

.unit-status-progress {
  width: 84px;
}

.unit-status-message {
  max-width: 108px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  line-height: 1.2;
  color: var(--el-text-color-placeholder);
}

.unit-result-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.unit-result-summary {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--el-text-color-regular);
  font-size: 12px;
  line-height: 1.4;
}

.unit-result-summary--error {
  color: var(--el-color-danger);
}

.unit-result-action {
  flex: 0 0 auto;
}
</style>
