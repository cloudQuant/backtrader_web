<template>
  <div class="workspace-report-tab">
    <teleport
      to="#page-header-actions"
      :disabled="!props.toolbarInHeader || !props.active"
    >
      <div
        class="flex items-center justify-between flex-wrap gap-2"
        :class="props.toolbarInHeader && props.active ? 'mb-0' : 'mb-4'"
      >
        <div class="flex items-center gap-2 flex-wrap">
          <!-- Group 1: Open / Delete / Clear / Save -->
          <el-button-group>
            <el-tooltip
              :content="t('report.open')"
              placement="top"
            >
              <el-button
                size="small"
                @click="handleOpenReport"
              >
                <el-icon><FolderOpened /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('report.delete')"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!report"
                @click="handleDeleteReport"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('report.clearConfig')"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!report"
                @click="handleClearReport"
              >
                <el-icon><Close /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('report.save')"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!report"
                @click="handleSaveReport"
              >
                <el-icon><Download /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <!-- Group 2: Config -->
          <el-button-group>
            <el-tooltip
              :content="t('report.timeRange')"
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
              :content="t('report.portfolioMaxInput')"
              placement="top"
            >
              <el-button
                size="small"
                @click="showMaxCashDialog = true"
              >
                <el-icon><Wallet /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('report.calcMethod')"
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
              :content="t('report.reportWeight')"
              placement="top"
            >
              <el-button
                size="small"
                @click="showWeightDialog = true"
              >
                <el-icon><Histogram /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('report.customField')"
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

          <!-- Group 3: Actions -->
          <el-button-group>
            <el-tooltip
              :content="t('report.reportCalc') + '(' + t('report.recalcWithConfig') + ')'"
              placement="top"
            >
              <el-button
                size="small"
                type="primary"
                :loading="loading"
                @click="recalculateReport"
              >
                <el-icon><Refresh /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="t('report.setDefault')"
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
        </div>
      </div>
    </teleport>

    <!-- Stat Time Dialog -->
    <el-dialog
      v-model="showStatTimeDialog"
      :title="t('report.timeRange')"
      width="560px"
      destroy-on-close
    >
      <div class="space-y-4">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('report.timeStart') }}
            </div>
            <div class="mt-1 text-sm font-semibold text-slate-700">
              {{ formatRangeValue(reportStatRange[0]) || t('report.notSet') }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('report.timeEnd') }}
            </div>
            <div class="mt-1 text-sm font-semibold text-slate-700">
              {{ formatRangeValue(reportStatRange[1]) || t('report.notSet') }}
            </div>
          </div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <el-form
            label-width="100px"
            size="small"
          >
            <el-form-item :label="t('report.timeStart')">
              <el-date-picker
                v-model="reportStatRange[0]"
                type="date"
                :placeholder="t('report.selectStart')"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item :label="t('report.timeEnd')">
              <el-date-picker
                v-model="reportStatRange[1]"
                type="date"
                :placeholder="t('report.selectEnd')"
                style="width: 100%"
              />
            </el-form-item>
          </el-form>
        </div>
      </div>
      <template #footer>
        <el-button @click="showStatTimeDialog = false">
          {{ t('report.cancel') }}
        </el-button>
        <el-button
          type="primary"
          @click="showStatTimeDialog = false; recalculateReport()"
        >
          {{ t('report.confirm') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Max Cash Dialog -->
    <el-dialog
      v-model="showMaxCashDialog"
      :title="t('report.portfolioMaxInput')"
      width="560px"
      destroy-on-close
    >
      <div class="space-y-4">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('report.currentMaxInput') }}
            </div>
            <div class="mt-1 text-sm font-semibold text-slate-700">
              {{ fmtMoney(maxCash) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('report.selectedUnits') }}
            </div>
            <div class="mt-1 text-sm font-semibold text-slate-700">
              {{ selectedReportUnitIds.length || filteredSummary.total_units || 0 }}
            </div>
          </div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <el-form
            label-width="120px"
            size="small"
          >
            <el-form-item :label="t('report.maxInputCash')">
              <el-input-number
                v-model="maxCash"
                :min="0"
                :step="100000"
                style="width: 240px"
              />
            </el-form-item>
          </el-form>
        </div>
      </div>
      <template #footer>
        <el-button @click="showMaxCashDialog = false">
          {{ t('report.cancel') }}
        </el-button>
        <el-button
          type="primary"
          @click="showMaxCashDialog = false; recalculateReport()"
        >
          {{ t('report.confirm') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Calc Method Dialog -->
    <el-dialog
      v-model="showCalcMethodDialog"
      :title="t('report.calcMethod')"
      width="620px"
      destroy-on-close
    >
      <div class="space-y-4">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('report.returnCalc') }}
            </div>
            <div class="mt-1 text-sm font-semibold text-slate-700">
              {{ reportCalcMethod === 'compound' ? t('report.compoundReturn') : t('report.simpleReturn') }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('report.annualBenchmark') }}
            </div>
            <div class="mt-1 text-sm font-semibold text-slate-700">
              {{ reportAnnualDays }} {{ t('report.days') }}
            </div>
          </div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <el-form
            label-width="100px"
            size="small"
          >
            <el-form-item :label="t('report.returnCalc')">
              <el-radio-group v-model="reportCalcMethod">
                <el-radio value="simple">
                  {{ t('report.simpleReturn') }}
                </el-radio>
                <el-radio value="compound">
                  {{ t('report.compoundReturn') }}
                </el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item :label="t('report.annualBenchmark')">
              <el-input-number
                v-model="reportAnnualDays"
                :min="200"
                :max="365"
              />
              <span class="ml-2 text-xs text-gray-400">{{ t('report.days') }}</span>
            </el-form-item>
          </el-form>
        </div>
      </div>
      <template #footer>
        <el-button @click="showCalcMethodDialog = false">
          {{ t('report.cancel') }}
        </el-button>
        <el-button
          type="primary"
          @click="showCalcMethodDialog = false; recalculateReport()"
        >
          {{ t('report.confirm') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Weight Dialog -->
    <el-dialog
      v-model="showWeightDialog"
      :title="t('report.reportWeight')"
      width="620px"
      destroy-on-close
    >
      <div class="space-y-4">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('report.weightMode') }}
            </div>
            <div class="mt-1 text-sm font-semibold text-slate-700">
              {{ weightModeLabel }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('report.affectingUnits') }}
            </div>
            <div class="mt-1 text-sm font-semibold text-slate-700">
              {{ selectedReportUnitIds.length || filteredSummary.total_units || 0 }}
            </div>
          </div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <el-form
            label-width="100px"
            size="small"
          >
            <el-form-item :label="t('report.weightMode')">
              <el-radio-group v-model="weightMode">
                <el-radio value="equal">
                  {{ t('report.weightEqual') }}
                </el-radio>
                <el-radio value="custom">
                  {{ t('report.weightCustom') }}
                </el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item
              v-if="weightMode === 'custom'"
              :label="t('report.weightCustomShort')"
            >
              <div class="text-xs text-gray-400">
                {{ t('report.weightAuto') }}
              </div>
            </el-form-item>
          </el-form>
        </div>
      </div>
      <template #footer>
        <el-button @click="showWeightDialog = false">
          {{ t('report.cancel') }}
        </el-button>
        <el-button
          type="primary"
          @click="showWeightDialog = false; recalculateReport()"
        >
          {{ t('report.confirm') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Custom Fields Dialog -->
    <el-dialog
      v-model="showCustomFieldsDialog"
      :title="t('report.customField')"
      width="720px"
      destroy-on-close
    >
      <div class="space-y-4">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('report.fieldCount') }}
            </div>
            <div class="mt-1 text-sm font-semibold text-slate-700">
              {{ reportAllFields.length }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('report.showing') }}
            </div>
            <div class="mt-1 text-sm font-semibold text-slate-700">
              {{ visibleFieldCount }}
            </div>
          </div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <el-checkbox-group v-model="reportVisibleFields">
            <div class="grid grid-cols-2 gap-2 md:grid-cols-3">
              <el-checkbox
                v-for="f in reportAllFields"
                :key="f.key"
                :value="f.key"
              >
                {{ f.label }}
              </el-checkbox>
            </div>
          </el-checkbox-group>
        </div>
      </div>
      <template #footer>
        <el-button @click="reportVisibleFields = reportAllFields.map(f => f.key)">
          {{ t('report.selectAll') }}
        </el-button>
        <el-button @click="reportVisibleFields = []">
          {{ t('report.clearConfig') }}
        </el-button>
        <el-button @click="showCustomFieldsDialog = false">
          {{ t('report.close') }}
        </el-button>
      </template>
    </el-dialog>

    <el-skeleton
      :rows="6"
      :loading="loading"
      animated
    >
      <template #default>
        <div
          v-if="report"
          class="report-overview-panel"
        >
          <div class="report-overview-panel__main">
            <div class="report-overview-panel__title">
              {{ t('report.sectionTitle') }}
            </div>
            <div class="report-overview-panel__meta">
              <span>{{ t('report.statRange') }} {{ statRangeLabel }}</span>
              <span>{{ t('report.selectedUnits') }} {{ selectedReportUnitIds.length || filteredSummary.total_units || 0 }}</span>
              <span>{{ t('report.calcMethod') }} {{ reportCalcMethod === 'compound' ? t('report.compoundReturn') : t('report.simpleReturn') }}</span>
              <span>{{ t('report.annualBenchmark') }} {{ reportAnnualDays }} {{ t('report.days') }}</span>
              <span>{{ t('report.weightLabel') }} {{ weightMode === 'custom' ? t('report.weightCustom') : t('report.weightEqual') }}</span>
            </div>
          </div>
          <div class="report-overview-panel__tags">
            <el-tag
              size="small"
              effect="plain"
              type="info"
            >
              {{ t('report.maxInput') }} {{ fmtMoney(maxCash) }}
            </el-tag>
            <el-tag
              size="small"
              effect="plain"
              type="success"
            >
              {{ t('report.data') }} {{ filteredUnits.length }} {{ t('report.rowSuffix') }}
            </el-tag>
          </div>
        </div>

        <div
          v-if="report && selectedUnitNames.length"
          class="report-unit-tags"
        >
          <el-tag
            v-for="name in selectedUnitNames"
            :key="name"
            size="small"
            effect="plain"
          >
            {{ name }}
          </el-tag>
        </div>

        <div
          v-if="report"
          class="report-summary-grid mb-6"
        >
          <div class="summary-card">
            <div class="summary-card__value">
              {{ filteredSummary.total_units ?? 0 }}
            </div>
            <div class="summary-card__label">
              {{ t('report.totalUnits') }}
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-card__value">
              {{ filteredSummary.completed_units ?? 0 }}
            </div>
            <div class="summary-card__label">
              {{ t('report.completed') }}
            </div>
          </div>
          <div class="summary-card">
            <div
              class="summary-card__value"
              :class="returnColor(filteredSummary.avg_total_return)"
            >
              {{ fmtPct(filteredSummary.avg_total_return) }}
            </div>
            <div class="summary-card__label">
              {{ t('report.avgReturnRate') }}
            </div>
          </div>
          <div class="summary-card">
            <div
              class="summary-card__value"
              :class="returnColor(filteredSummary.avg_sharpe_ratio)"
            >
              {{ fmtNum(filteredSummary.avg_sharpe_ratio) }}
            </div>
            <div class="summary-card__label">
              {{ t('report.avgSharpe') }}
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-card__value text-red-500">
              {{ fmtPct(filteredSummary.avg_max_drawdown) }}
            </div>
            <div class="summary-card__label">
              {{ t('report.avgMaxDrawdown') }}
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-card__value">
              {{ fmtPct(filteredSummary.avg_win_rate) }}
            </div>
            <div class="summary-card__label">
              {{ t('report.avgWinRate') }}
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-card__value">
              {{ filteredSummary.total_trades ?? '-' }}
            </div>
            <div class="summary-card__label">
              {{ t('report.totalTrades') }}
            </div>
          </div>
          <div class="summary-card">
            <div
              class="summary-card__value"
              :class="returnColor(filteredSummary.avg_annual_return)"
            >
              {{ fmtPct(filteredSummary.avg_annual_return) }}
            </div>
            <div class="summary-card__label">
              {{ t('report.avgAnnualReturn') }}
            </div>
          </div>
        </div>

        <div
          v-if="filteredSummary.best_return_unit || filteredSummary.worst_drawdown_unit"
          class="report-highlight-grid mb-6"
        >
          <div
            v-if="filteredSummary.best_return_unit"
            class="highlight-card is-success"
          >
            <div class="highlight-card__label">
              {{ t('report.bestUnit') }}
            </div>
            <div class="highlight-card__main">
              <span>{{ filteredSummary.best_return_unit.strategy_name }} / {{ filteredSummary.best_return_unit.symbol }}</span>
              <span class="text-green-500 font-bold">{{ fmtPct(filteredSummary.best_return_unit.value) }}</span>
            </div>
          </div>
          <div
            v-if="filteredSummary.worst_drawdown_unit"
            class="highlight-card is-danger"
          >
            <div class="highlight-card__label">
              {{ t('report.worstUnit') }}
            </div>
            <div class="highlight-card__main">
              <span>{{ filteredSummary.worst_drawdown_unit.strategy_name }} / {{ filteredSummary.worst_drawdown_unit.symbol }}</span>
              <span class="text-red-500 font-bold">{{ fmtPct(filteredSummary.worst_drawdown_unit.value) }}</span>
            </div>
          </div>
        </div>

        <el-table
          v-if="filteredUnits.length"
          :data="filteredUnits"
          row-key="id"
          stripe
          border
          size="small"
          class="w-full report-table"
          max-height="500"
        >
          <el-table-column
            label="#"
            width="50"
            align="center"
            fixed
          >
            <template #default="{ $index }">
              {{ $index + 1 }}
            </template>
          </el-table-column>
          <el-table-column
            prop="strategy_name"
            :label="t('report.reportUnits')"
            min-width="120"
            fixed
          />
          <el-table-column
            prop="group_name"
            :label="t('report.sourceFromUnit')"
            width="100"
          />
          <el-table-column
            prop="data_source"
            :label="t('report.dataSource')"
            width="120"
          />
          <el-table-column
            prop="start_date"
            :label="t('report.timeStart')"
            width="100"
          />
          <template
            v-for="col in reportActiveColumns"
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
        </el-table>

        <el-empty
          v-if="report && !filteredUnits.length"
          :description="t('report.noUnitData')"
        />
        <el-empty
          v-if="!report && !loading"
          :description="t('report.clickToRefresh')"
        />
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
import { useI18n } from 'vue-i18n'
import { workspaceApi } from '@/api/workspace'
import { useWorkspaceStore } from '@/stores/workspace'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getErrorMessage } from '@/api/index'
import type { WorkspaceReportConfig, WorkspaceReportResponse, WorkspaceReportUnitRow } from '@/types/workspace'

const { t } = useI18n()

const props = defineProps<{
  workspaceId: string
  active?: boolean
  toolbarInHeader?: boolean
  initialUnitId?: string
  initialUnitIds?: string[]
}>()

const store = useWorkspaceStore()
const loading = ref(false)
const report = ref<WorkspaceReportResponse | null>(null)
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
  const rc: WorkspaceReportConfig | undefined = store.currentWorkspace?.settings.report_config
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
  { key: 'initial_cash', label: t('report.maxInputCash'), width: 110, money: true },
  { key: 'net_value', label: t('report.netValue'), width: 80 },
  { key: 'net_profit', label: t('report.netProfit'), width: 100, money: true },
  { key: 'annual_return', label: t('report.annualizedReturn') + '%', width: 100, sortable: true },
  { key: 'max_leverage', label: t('report.maxLeverage'), width: 80 },
  { key: 'max_market_value', label: t('report.maxMarketValue'), width: 100, money: true },
  { key: 'max_drawdown_value', label: t('report.maxDrawdownVal'), width: 100, money: true },
  { key: 'max_drawdown', label: t('report.maxDrawdown') + '%', width: 90, sortable: true },
  { key: 'sharpe_ratio', label: t('report.sharpe'), width: 85, sortable: true },
  { key: 'adjusted_return_risk', label: t('report.riskReturnRatio'), width: 90 },
  { key: 'total_trades', label: t('report.tradeCount'), width: 80, align: 'center', int: true },
  { key: 'win_rate', label: t('report.winRate') + '%', width: 70, sortable: true },
  { key: 'avg_profit', label: t('report.avgProfit'), width: 90, money: true },
  { key: 'avg_profit_rate', label: t('report.avgProfitRate') + '%', width: 100 },
  { key: 'total_win_amount', label: t('report.totalProfit'), width: 100, money: true },
  { key: 'total_loss_amount', label: t('report.totalLoss'), width: 100, money: true },
  { key: 'profit_loss_ratio', label: t('report.profitLossRatio'), width: 80 },
  { key: 'profit_factor', label: t('report.profitFactor'), width: 80, sortable: true },
  { key: 'profit_rate_factor', label: t('report.profitRateFactor'), width: 90 },
  { key: 'profit_loss_rate_ratio', label: t('report.profitRateRatio'), width: 80 },
  { key: 'odds', label: t('report.winChance') + '%', width: 80 },
  { key: 'daily_avg_return', label: t('report.daily') + '%', width: 90 },
  { key: 'daily_max_loss', label: t('report.dailyMaxLoss') + '%', width: 100 },
  { key: 'daily_max_profit', label: t('report.dailyMaxProfit') + '%', width: 100 },
  { key: 'weekly_avg_return', label: t('report.weekly') + '%', width: 90 },
  { key: 'weekly_max_loss', label: t('report.weeklyMaxLoss') + '%', width: 100 },
  { key: 'weekly_max_profit', label: t('report.weeklyMaxProfit') + '%', width: 100 },
  { key: 'monthly_avg_return', label: t('report.monthly') + '%', width: 90 },
  { key: 'monthly_max_loss', label: t('report.monthlyMaxLoss') + '%', width: 100 },
  { key: 'monthly_max_profit', label: t('report.monthlyMaxProfit') + '%', width: 100 },
  { key: 'trading_cost', label: t('report.tradeCost'), width: 90, money: true },
  { key: 'trading_days', label: t('report.tradeDays'), width: 80, align: 'center', int: true },
]
const reportAllFields = reportColumnDefs.map(c => ({ key: c.key, label: c.label }))
const reportVisibleFields = ref(reportAllFields.map(f => f.key))
const visibleFieldCount = computed(() => reportVisibleFields.value.length)
const weightModeLabel = computed(() => (weightMode.value === 'custom' ? t('report.weightCustom') : t('report.weightEqual')))

const reportActiveColumns = computed(() =>
  reportColumnDefs.filter(c => reportVisibleFields.value.includes(c.key))
)
const selectedUnitNames = computed(() => {
  if (!selectedReportUnitIds.value.length) return []
  const unitMap = new Map(store.units.map(unit => [unit.id, unit.strategy_name || unit.strategy_id || unit.id]))
  return selectedReportUnitIds.value
    .map(id => unitMap.get(id) || id)
    .filter(Boolean)
})
function formatRangeValue(value: unknown) {
  if (!value) return ''
  if (value instanceof Date) {
    return value.toLocaleDateString('zh-CN')
  }
  const text = String(value)
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
    return text.slice(0, 10)
  }
  return text
}
const statRangeLabel = computed(() => {
  if (reportStatRange.value[0] || reportStatRange.value[1]) {
    return `${formatRangeValue(reportStatRange.value[0]) || t('report.start')} ~ ${formatRangeValue(reportStatRange.value[1]) || t('report.end')}`
  }
  return t('report.fullRange')
})

const filteredUnits = computed(() => {
  const rows = report.value?.units ?? []
  if (!selectedReportUnitIds.value.length) return rows
  return rows.filter(row => selectedReportUnitIds.value.includes(row.id))
})

const filteredSummary = computed(() => {
  const rows = filteredUnits.value
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
  const avg = (key: keyof WorkspaceReportUnitRow) => {
    const values = rows
      .map(row => row[key])
      .filter((value): value is number => typeof value === 'number')
    if (!values.length) return null
    return values.reduce((sum, value) => sum + value, 0) / values.length
  }
  const totalTrades = rows
    .map(row => row.total_trades)
    .filter((value): value is number => typeof value === 'number')
    .reduce((sum, value) => sum + value, 0)
  const bestReturnUnit = rows.reduce<WorkspaceReportUnitRow | null>((best, row) => {
    if (!best) return row
    return (row.total_return ?? Number.NEGATIVE_INFINITY) > (best.total_return ?? Number.NEGATIVE_INFINITY) ? row : best
  }, null)
  const worstDrawdownUnit = rows.reduce<WorkspaceReportUnitRow | null>((worst, row) => {
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
    ElMessage.error(getErrorMessage(e, t('report.loadFailed')))
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
    ElMessage.success(t('report.recalculated'))
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('report.recalculateFailed')))
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
        ElMessage.success(t('report.loaded'))
      } else {
        ElMessage.warning(t('report.fileFormatErr'))
      }
    } catch {
      ElMessage.error(t('report.readFileFailed'))
    }
  }
  input.click()
}

// --- Delete report config (Bug-5 v2: safe semantics, only clears config not metrics) ---
async function handleDeleteReport() {
  try {
    await ElMessageBox.confirm(t('report.confirmClearConfig') + '？' + t('report.clearConfigHint') + '。', t('report.clearConfig'), { type: 'info' })
    await workspaceApi.deleteReport(props.workspaceId)
    report.value = null
    // Reset local config to defaults
    reportCalcMethod.value = 'simple'
    reportAnnualDays.value = 252
    weightMode.value = 'equal'
    maxCash.value = 1000000
    reportStatRange.value = [null, null]
    ElMessage.success(t('report.cleardConfig'))
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error(getErrorMessage(e, t('report.clearFailed')))
  }
}

// --- Clear (local view reset) ---
function handleClearReport() {
  report.value = null
  ElMessage.info(t('report.cleared') + '，' + t('report.refreshHint'))
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
  ElMessage.success(t('report.saved'))
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
    ElMessage.success(t('report.savedAsDefault'))
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('report.saveDefaultFailed')))
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

<style scoped>
.report-overview-panel {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 16px 18px;
  margin-bottom: 16px;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  background: linear-gradient(135deg, var(--bg-color-card) 0%, var(--bg-color-page) 100%);
}

.report-overview-panel__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color-primary);
}

.report-overview-panel__meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-color-secondary);
}

.report-overview-panel__tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.report-unit-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.report-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  padding: 16px;
  border: 1px solid var(--border-color-light);
  border-radius: 14px;
  background: var(--bg-color-card);
  text-align: center;
}

.summary-card__value {
  font-size: 24px;
  line-height: 1.1;
  font-weight: 700;
  color: var(--text-color-primary);
}

.summary-card__label {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-color-placeholder);
}

.report-highlight-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.highlight-card {
  padding: 16px;
  border: 1px solid var(--border-color-light);
  border-radius: 14px;
  background: var(--bg-color-card);
}

.highlight-card.is-success {
  border-color: var(--success-border-color);
  background: linear-gradient(135deg, var(--bg-color-card) 0%, var(--success-surface) 100%);
}

.highlight-card.is-danger {
  border-color: var(--danger-border-color);
  background: linear-gradient(135deg, var(--bg-color-card) 0%, var(--danger-surface) 100%);
}

.highlight-card__label {
  font-size: 12px;
  color: var(--text-color-secondary);
}

.highlight-card__main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 10px;
  font-size: 14px;
  color: var(--text-color-regular);
}

.report-table :deep(.el-table__header th) {
  background: var(--bg-color-page);
  color: var(--text-color-regular);
  font-weight: 600;
}

.report-table :deep(.el-table__row:hover > td) {
  background: var(--info-surface) !important;
}

@media (max-width: 1200px) {
  .report-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .report-highlight-grid,
  .report-summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
