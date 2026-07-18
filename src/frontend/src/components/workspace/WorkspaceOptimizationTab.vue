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
                <el-icon aria-hidden="true"><FolderOpened /></el-icon>
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
                <el-icon aria-hidden="true"><Download /></el-icon>
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
                <el-icon aria-hidden="true"><Check /></el-icon>
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
                <el-icon aria-hidden="true"><Position /></el-icon>
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
                <el-icon aria-hidden="true"><Document /></el-icon>
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
                <el-icon aria-hidden="true"><Grid /></el-icon>
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
                <el-icon aria-hidden="true"><Operation /></el-icon>
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
                <el-icon aria-hidden="true"><Filter /></el-icon>
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
                <el-icon aria-hidden="true"><RefreshLeft /></el-icon>
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
                <el-icon aria-hidden="true"><Timer /></el-icon>
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
                <el-icon aria-hidden="true"><Operation /></el-icon>
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
                <el-icon aria-hidden="true"><SetUp /></el-icon>
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
                <el-icon aria-hidden="true"><Refresh /></el-icon>
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
                <el-icon aria-hidden="true"><Star /></el-icon>
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
      <el-icon class="is-loading text-2xl text-blue-500" aria-hidden="true">
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
import { ElMessage } from 'element-plus'
import {
  Loading, Check, Document, Filter, Refresh, Download,
  FolderOpened, Position, Grid, RefreshLeft, Timer, Operation, SetUp, Star,
} from '@element-plus/icons-vue'
import { useWorkspaceOptimizationTab, type WorkspaceOptimizationTabProps } from './optimization/useWorkspaceOptimizationTab'

const props = defineProps<WorkspaceOptimizationTabProps>()
const optimizationPage = useWorkspaceOptimizationTab(props)

const {
  t,
  units,
  selectedUnitId,
  loading,
  optimizationStatus,
  total,
  completed,
  paramNames,
  showFilter,
  sortKey,
  sortDir,
  viewMode,
  showStatTimeDialog,
  showCalcMethodDialog,
  showCustomFieldsDialog,
  statTimeRange,
  calcMethod,
  annualDays,
  selectedAnalysisParams,
  analysisMetric,
  analysisChartRef,
  allFields,
  visibleFields,
  activeColumns,
  hasResults,
  progressPct,
  emptyStateDescription,
  displayRows,
  bestParamsStr,
  bestSharpe,
  loadResults,
  applySort,
  handleOpenFile,
  handleSaveResults,
  handleApplyBestAndOpen,
  handleTestReport,
  handleReset,
  handleSetDefault,
  handleCancel,
  handleApplyBest,
  runningRow,
  handleRunWithParams,
  fmtVal,
  fmtMoney,
  metricOptions,
  selectedAnalysisMode,
  analysisDescription,
} = optimizationPage

defineExpose(optimizationPage)
</script>
