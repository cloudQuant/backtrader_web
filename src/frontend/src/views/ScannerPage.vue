<template>
  <div
    class="scanner-page"
    data-test="scanner-page"
  >
    <section class="scanner-hero">
      <div class="scanner-hero-copy">
        <div class="scanner-eyebrow">
          {{ t('scannerPage.headerEyebrow') }}
        </div>
        <h1>
          {{ t('scannerPage.headerTitle') }}
        </h1>
        <p>
          {{ t('scannerPage.headerDesc') }}
        </p>
      </div>

      <div class="scanner-hero-stats">
        <article
          v-for="stat in scannerHeroStats"
          :key="stat.key"
          class="scanner-hero-stat"
        >
          <span>{{ stat.label }}</span>
          <strong>{{ stat.value }}</strong>
          <small>{{ stat.helper }}</small>
        </article>
      </div>
    </section>

    <el-card class="scanner-workbench">
      <section class="scanner-query-panel">
        <div class="scanner-section-header">
          <div>
            <h3>{{ t('scannerPage.queryTitle') }}</h3>
            <p>{{ t('scannerPage.queryDesc') }}</p>
          </div>
          <el-tag
            class="scanner-status-tag"
            :type="statusTagType"
          >
            {{ taskStatus }}
          </el-tag>
        </div>

        <div class="scanner-command-grid">
          <section class="scanner-plan-panel">
            <div class="scanner-section-header">
              <div>
                <h3>{{ t('scannerPage.planCenterTitle') }}</h3>
                <p>{{ t('scannerPage.planCenterDesc') }}</p>
              </div>
              <span class="scanner-row-count">{{ t('scannerPage.planCount', { count: scannerPlans.length }) }}</span>
            </div>
            <div class="scanner-plan-grid">
              <label class="scanner-field">
                <span>{{ t('scannerPage.fieldSavedPlan') }}</span>
                <el-select
                  v-model="selectedPlanId"
                  clearable
                  @change="applySelectedPlan"
                >
                  <el-option
                    v-for="plan in scannerPlans"
                    :key="plan.id"
                    :label="plan.name"
                    :value="plan.id"
                  />
                </el-select>
              </label>
              <div class="scanner-plan-actions">
                <el-button
                  type="primary"
                  @click="openNewPlanDialog"
                >
                  <el-icon aria-hidden="true">
                    <Plus />
                  </el-icon>
                  {{ t('scannerPage.btnNewPlan') }}
                </el-button>
                <el-button
                  :disabled="!selectedPlanId"
                  @click="openEditPlanDialog()"
                >
                  <el-icon aria-hidden="true">
                    <EditPen />
                  </el-icon>
                  {{ t('scannerPage.btnEditPlan') }}
                </el-button>
                <el-button
                  :loading="planLoading"
                  :disabled="!selectedPoolId"
                  @click="saveScannerPlan"
                >
                  {{ t('scannerPage.btnSavePlan') }}
                </el-button>
                <el-button
                  :loading="planRunLoading"
                  :disabled="!selectedPlanId"
                  @click="runSelectedPlan"
                >
                  {{ t('scannerPage.btnRunPlan') }}
                </el-button>
                <el-button
                  :loading="dailyRunLoading"
                  @click="runDailyPlans"
                >
                  {{ t('scannerPage.btnRunDailyPlans') }}
                </el-button>
              </div>
            </div>
            <div class="scanner-plan-run-strip">
              <span>{{ t('scannerPage.planLatestRun') }}</span>
              <strong>{{ latestPlanRunLabel }}</strong>
            </div>
          </section>

          <section class="scanner-live-panel">
            <div class="scanner-section-header">
              <div>
                <h3>{{ t('scannerPage.liveRunTitle') }}</h3>
                <p>{{ t('scannerPage.liveRunDesc') }}</p>
              </div>
            </div>

            <div class="scanner-live-grid">
              <label class="scanner-field">
                <span>{{ t('scannerPage.fieldUniversePool') }}</span>
                <el-select
                  v-model="selectedPoolId"
                  @change="selectManagerPool"
                >
                  <el-option
                    v-for="pool in universePools"
                    :key="pool.id"
                    :label="`${pool.name} · ${pool.instrument_count}`"
                    :value="pool.id"
                  />
                </el-select>
              </label>
              <label class="scanner-field">
                <span>{{ t('scannerPage.fieldLookback') }}</span>
                <el-input-number
                  v-model="lookbackDays"
                  :min="1"
                  :max="365"
                />
              </label>
              <label class="scanner-field">
                <span>{{ t('scannerPage.fieldTimeframe') }}</span>
                <el-select v-model="timeframe">
                  <el-option
                    label="1d"
                    value="1d"
                  />
                  <el-option
                    label="4h"
                    value="4h"
                  />
                  <el-option
                    label="1h"
                    value="1h"
                  />
                </el-select>
              </label>
            </div>

            <div class="scanner-active-condition">
              <span>{{ t('scannerPage.fieldActiveCondition') }}</span>
              <strong>{{ condition }}</strong>
            </div>

            <div class="scanner-live-actions">
              <el-button
                type="primary"
                :loading="loading"
                :disabled="!selectedPoolId"
                @click="run"
              >
                <el-icon aria-hidden="true">
                  <VideoPlay />
                </el-icon>
                {{ t('scannerPage.btnRunNow') }}
              </el-button>
              <el-button @click="openEditPlanDialog()">
                <el-icon aria-hidden="true">
                  <Setting />
                </el-icon>
                {{ t('scannerPage.btnManagePools') }}
              </el-button>
            </div>
          </section>
        </div>
      </section>

      <section class="scanner-metric-panel">
        <div class="scanner-section-header">
          <div>
            <h3>{{ t('scannerPage.metricsTitle') }}</h3>
            <p>{{ t('scannerPage.metricsDesc') }}</p>
          </div>
          <span class="scanner-run-pill">
            {{ t('scannerPage.taskInfo', { taskId: taskId || '-', status: taskStatus }) }}
          </span>
        </div>

        <div class="scanner-metric-grid">
          <div
            v-for="metric in metricCards"
            :key="metric.key"
            class="scanner-metric-card"
            :class="`is-${metric.tone}`"
          >
            <span>{{ metric.label }}</span>
            <strong>{{ metric.value }}</strong>
            <small>{{ metric.helper }}</small>
          </div>
        </div>
      </section>

      <section class="scanner-match-board">
        <div class="scanner-section-header">
          <div>
            <h3>{{ t('scannerPage.matchBoardTitle') }}</h3>
            <p>{{ t('scannerPage.matchBoardDesc') }}</p>
          </div>
          <span class="scanner-row-count">{{ t('scannerPage.resultCount', { count: matches.length }) }}</span>
        </div>

        <div
          v-if="matches.length === 0"
          class="scanner-empty-state"
        >
          <strong>{{ t('scannerPage.emptyMatchesTitle') }}</strong>
          <p>{{ t('scannerPage.emptyMatchesDesc') }}</p>
        </div>
        <el-table
          v-else
          class="scanner-match-table"
          :data="matches"
          :empty-text="t('scannerPage.emptyMatchesTitle')"
        >
          <el-table-column
            :label="t('scannerPage.colSymbol')"
            min-width="150"
          >
            <template #default="scope">
              <div class="scanner-symbol-cell">
                <strong>{{ displayValue(scope.row.symbol) }}</strong>
                <span>{{ displayValue(scope.row.provider) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            prop="name"
            :label="t('scannerPage.colName')"
            min-width="140"
          />
          <el-table-column
            :label="t('scannerPage.colPrice')"
            width="110"
          >
            <template #default="scope">
              {{ formatNumber(scope.row.price) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('scannerPage.colChangePct')"
            width="120"
          >
            <template #default="scope">
              {{ formatPercent(scope.row.change_pct) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('scannerPage.colIndicator')"
            width="130"
          >
            <template #default="scope">
              <span
                class="scanner-score-pill"
                :class="scoreClass(scope.row.indicator)"
              >
                {{ formatPercent(scope.row.indicator) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('scannerPage.colFactor')"
            width="120"
          >
            <template #default="scope">
              {{ formatPercent(scope.row.factor) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('scannerPage.colNewsSentiment')"
            width="150"
          >
            <template #default="scope">
              {{ formatPercent(scope.row.news_sentiment) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('scannerPage.colPortfolioExposure')"
            width="150"
          >
            <template #default="scope">
              {{ formatPercent(scope.row.portfolio_exposure) }}
            </template>
          </el-table-column>
        </el-table>
      </section>
    </el-card>

    <el-dialog
      v-model="planDialogVisible"
      class="scanner-plan-editor-dialog scanner-pool-dialog"
      :title="planDialogTitle"
      :width="editingPlanId ? '1040px' : '900px'"
    >
      <div
        v-if="planDialogVisible"
        class="scanner-plan-dialog-shell"
        :class="editingPlanId ? 'is-edit' : 'is-create'"
      >
        <aside
          v-if="editingPlanId"
          class="scanner-plan-dialog-aside"
        >
          <div class="scanner-plan-dialog-summary">
            <span>{{ t('scannerPage.fieldPlanName') }}</span>
            <strong>{{ planName.trim() || defaultPlanName() }}</strong>
          </div>
          <div class="scanner-plan-dialog-summary">
            <span>{{ t('scannerPage.fieldUniversePool') }}</span>
            <strong>{{ selectedPool?.name || '-' }}</strong>
          </div>
          <div class="scanner-plan-dialog-summary">
            <span>{{ t('scannerPage.fieldTimeframe') }}</span>
            <strong>{{ timeframe }} · {{ lookbackDays }}{{ t('scannerPage.metricLookbackHelper') }}</strong>
          </div>
          <div class="scanner-plan-dialog-summary">
            <span>{{ t('scannerPage.resultTableTitle') }}</span>
            <strong>{{ selectedPlanResultTableLabel }}</strong>
          </div>
        </aside>

        <div class="scanner-plan-dialog-main">
          <section class="scanner-plan-editor-section scanner-plan-primary-section">
            <div class="scanner-section-header">
              <div>
                <h3>{{ t('scannerPage.planBasicTitle') }}</h3>
                <p>{{ t('scannerPage.planBasicDesc') }}</p>
              </div>
            </div>
            <div class="scanner-plan-editor-grid">
              <label class="scanner-field">
                <span>{{ t('scannerPage.fieldPlanName') }}</span>
                <el-input
                  v-model="planName"
                  :placeholder="t('scannerPage.planNamePlaceholder')"
                />
              </label>
            </div>
            <div class="scanner-plan-editor-parameters">
              <label class="scanner-field">
                <span>{{ t('scannerPage.fieldLookback') }}</span>
                <el-input-number
                  v-model="lookbackDays"
                  :min="1"
                  :max="365"
                />
              </label>
              <label class="scanner-field">
                <span>{{ t('scannerPage.fieldTimeframe') }}</span>
                <el-select v-model="timeframe">
                  <el-option
                    label="1d"
                    value="1d"
                  />
                  <el-option
                    label="4h"
                    value="4h"
                  />
                  <el-option
                    label="1h"
                    value="1h"
                  />
                </el-select>
              </label>
            </div>
          </section>

          <section class="scanner-plan-editor-section scanner-plan-universe-section">
            <div class="scanner-section-header">
              <div>
                <h3>{{ t('scannerPage.poolManagerTitle') }}</h3>
                <p>{{ selectedPool?.description || t('scannerPage.poolNoDescription') }}</p>
              </div>
            </div>
            <div class="scanner-pool-manager-panel">
              <div class="scanner-manager-toolbar">
                <label class="scanner-field scanner-manager-select">
                  <span>{{ t('scannerPage.fieldUniversePool') }}</span>
                  <el-select
                    v-model="managerPoolId"
                    @change="selectManagerPool"
                  >
                    <el-option
                      v-for="pool in universePools"
                      :key="pool.id"
                      :label="`${pool.name} · ${pool.instrument_count}`"
                      :value="pool.id"
                    />
                  </el-select>
                </label>
                <div class="scanner-manager-actions">
                  <el-button
                    v-if="managerPool?.refreshable"
                    :loading="refreshingPoolId === managerPool.id"
                    @click="refreshPool(managerPool.id)"
                  >
                    {{ t('scannerPage.btnRefreshConstituents') }}
                  </el-button>
                  <el-button
                    v-if="managerPool"
                    type="primary"
                    :loading="precomputingPoolId === managerPool.id"
                    @click="precomputePoolMetrics(managerPool.id)"
                  >
                    {{ t('scannerPage.btnPrecomputeMetrics') }}
                  </el-button>
                </div>
              </div>

              <div class="scanner-manager-detail scanner-manager-layout">
                <div class="scanner-manager-overview">
                  <div class="scanner-manager-detail-header">
                    <div>
                      <h3>{{ t('scannerPage.poolDetailTitle') }}</h3>
                      <p>{{ managerPool?.name || t('scannerPage.poolNoDescription') }} · {{ managerPool?.description || t('scannerPage.poolNoDescription') }}</p>
                    </div>
                    <el-tag
                      v-if="managerPool"
                      size="small"
                      effect="plain"
                    >
                      {{ managerPool.is_custom ? t('scannerPage.poolCustom') : managerPool.source }}
                    </el-tag>
                  </div>

                  <div class="scanner-pool-meta-grid">
                    <span>{{ t('scannerPage.metaUniverse') }} <strong>{{ managerPool?.instrument_count || 0 }}</strong></span>
                    <span>{{ t('scannerPage.metaSource') }} <strong>{{ managerPool?.source || '-' }}</strong></span>
                    <span>{{ t('scannerPage.metaUpdatedAt') }} <strong>{{ formatDateTime(managerPool?.updated_at) }}</strong></span>
                    <span>
                      {{ t('scannerPage.metaMetricSnapshot') }}
                      <strong>{{ metricSnapshotLabel }}</strong>
                    </span>
                  </div>
                </div>

                <div class="scanner-manager-symbols">
                  <div class="scanner-symbol-heading">
                    <span>{{ t('scannerPage.poolSymbolsTitle') }}</span>
                    <small>{{ t('scannerPage.poolInstrumentCount', { count: managerPool?.instrument_count || 0 }) }}</small>
                  </div>
                  <div class="scanner-symbol-grid">
                    <div
                      v-for="instrument in managerPool?.instruments || []"
                      :key="instrument.symbol"
                      class="scanner-symbol-chip"
                    >
                      <strong>{{ instrument.symbol }}</strong>
                      <span>{{ instrument.name || instrument.symbol }}</span>
                      <small>{{ instrument.asset_type || '-' }} · {{ instrument.exchange || '-' }}</small>
                    </div>
                  </div>
                </div>

                <div class="scanner-custom-panel">
                  <div class="scanner-symbol-heading">
                    <span>{{ t('scannerPage.customUniverseTitle') }}</span>
                    <small>{{ t('scannerPage.customUniverseDesc') }}</small>
                  </div>
                  <div class="scanner-custom-grid">
                    <label class="scanner-field">
                      <span>{{ t('scannerPage.customPoolName') }}</span>
                      <el-input
                        v-model="customPoolName"
                        :placeholder="t('scannerPage.customPoolNamePlaceholder')"
                      />
                    </label>
                    <label class="scanner-field scanner-custom-symbols-field">
                      <span>{{ t('scannerPage.customPoolSymbols') }}</span>
                      <el-input
                        v-model="customSymbolText"
                        type="textarea"
                        :rows="3"
                        :placeholder="t('scannerPage.customSymbolPlaceholder')"
                      />
                    </label>
                    <div class="scanner-custom-actions">
                      <el-button
                        type="primary"
                        :loading="poolLoading"
                        @click="saveCustomPool"
                      >
                        {{ t('scannerPage.btnSaveCustomPool') }}
                      </el-button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section class="scanner-plan-editor-section scanner-plan-indicator-section">
            <div class="scanner-indicator-manager-panel">
              <div class="scanner-symbol-heading">
                <span>{{ t('scannerPage.indicatorManagerTitle') }}</span>
                <small>{{ t('scannerPage.indicatorManagerDesc') }}</small>
              </div>
              <div class="scanner-indicator-rule-list">
                <div
                  v-for="rule in indicatorRules"
                  :key="rule.id"
                  class="scanner-indicator-rule"
                >
                  <el-checkbox v-model="rule.enabled">
                    {{ t('scannerPage.metricRuleEnabled') }}
                  </el-checkbox>
                  <label class="scanner-field">
                    <span>{{ t('scannerPage.metricRuleMetric') }}</span>
                    <el-select v-model="rule.metric">
                      <el-option
                        v-for="option in indicatorMetricOptions"
                        :key="option.value"
                        :label="t(option.labelKey)"
                        :value="option.value"
                      />
                    </el-select>
                  </label>
                  <label class="scanner-field">
                    <span>{{ t('scannerPage.metricRuleOperator') }}</span>
                    <el-select v-model="rule.operator">
                      <el-option
                        v-for="operator in indicatorOperatorOptions"
                        :key="operator"
                        :label="operator"
                        :value="operator"
                      />
                    </el-select>
                  </label>
                  <label class="scanner-field">
                    <span>{{ t('scannerPage.metricRuleValue') }}</span>
                    <el-input-number
                      v-model="rule.value"
                      :step="0.01"
                      :min="-100000000"
                      :max="100000000"
                    />
                  </label>
                  <el-button
                    text
                    @click="removeIndicatorRule(rule.id)"
                  >
                    {{ t('scannerPage.btnRemoveMetricRule') }}
                  </el-button>
                </div>
              </div>
              <div class="scanner-indicator-footer">
                <el-button @click="addIndicatorRule">
                  {{ t('scannerPage.btnAddMetricRule') }}
                </el-button>
                <span class="scanner-generated-condition">
                  {{ t('scannerPage.generatedCondition') }}
                  <strong>{{ condition }}</strong>
                </span>
              </div>
            </div>
          </section>

          <section
            v-if="editingPlanId"
            class="scanner-plan-editor-section scanner-plan-result-section"
          >
            <div class="scanner-section-header">
              <div>
                <h3>{{ t('scannerPage.resultTableTitle') }}</h3>
                <p>{{ selectedPlanResultTableLabel }}</p>
              </div>
              <div class="scanner-plan-table-actions">
                <el-button
                  :disabled="!editingPlanId"
                  :loading="planTableLoading"
                  @click="createSelectedPlanResultTable"
                >
                  {{ t('scannerPage.btnCreateResultTable') }}
                </el-button>
                <el-button
                  :disabled="!editingPlanId"
                  :loading="planTableLoading"
                  @click="deleteSelectedPlanResultTable"
                >
                  {{ t('scannerPage.btnDeleteResultTable') }}
                </el-button>
              </div>
            </div>
            <label class="scanner-field scanner-condition-field">
              <span>{{ t('scannerPage.generatedCondition') }}</span>
              <el-input
                :model-value="condition"
                type="textarea"
                :rows="3"
                readonly
              />
            </label>
          </section>
        </div>
      </div>

      <template #footer>
        <div
          v-if="planDialogVisible"
          class="scanner-plan-editor-toolbar"
        >
          <el-button
            v-if="editingPlanId"
            type="danger"
            plain
            :loading="planLoading"
            @click="deleteSelectedPlan"
          >
            {{ t('scannerPage.btnDeletePlan') }}
          </el-button>
          <el-button
            type="primary"
            :loading="planLoading"
            :disabled="!selectedPoolId"
            @click="savePlanFromDialog"
          >
            {{ t('scannerPage.btnSavePlan') }}
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { EditPen, Plus, Setting, VideoPlay } from '@element-plus/icons-vue'
import {
  marketIntelApi,
  type ScannerIndicatorRule,
  type ScannerMetricSnapshot,
  type ScannerPlan,
  type ScannerPlanRun,
  type ScannerUniversePool,
} from '@/api/marketIntel'

const { t } = useI18n()

type IndicatorRule = {
  id: string
  metric: string
  operator: string
  value: number
  enabled: boolean
}

const indicatorMetricOptions = [
  { value: 'indicator', labelKey: 'scannerPage.metricOptionIndicator' },
  { value: 'factor', labelKey: 'scannerPage.metricOptionFactor' },
  { value: 'change_pct', labelKey: 'scannerPage.metricOptionChangePct' },
  { value: 'volume', labelKey: 'scannerPage.metricOptionVolume' },
  { value: 'news_sentiment', labelKey: 'scannerPage.metricOptionNewsSentiment' },
  { value: 'portfolio_exposure', labelKey: 'scannerPage.metricOptionPortfolioExposure' },
  { value: 'price', labelKey: 'scannerPage.metricOptionPrice' },
]

const indicatorOperatorOptions = ['>=', '>', '<=', '<', '==', '!=']

const fallbackPools: ScannerUniversePool[] = [
  {
    id: 'hs300',
    name: '沪深300',
    description: '沪深300指数最新成分股，可从后端刷新。',
    category: 'equity_index',
    source: 'seed',
    instrument_count: 2,
    is_custom: false,
    refreshable: true,
    instruments: [
      { symbol: '000001.SZ', name: '平安银行', asset_type: 'equity', exchange: 'SZSE' },
      { symbol: '600519.SH', name: '贵州茅台', asset_type: 'equity', exchange: 'SSE' },
    ],
  },
]

const lookbackDays = ref(20)
const timeframe = ref('1d')
const loading = ref(false)
const poolLoading = ref(false)
const matches = ref<Array<Record<string, unknown>>>([])
const taskId = ref('')
const taskStatus = ref('idle')
const universePools = ref<ScannerUniversePool[]>([])
const selectedPoolId = ref('')
const managerPoolId = ref('')
const planDialogVisible = ref(false)
const editingPlanId = ref('')
const refreshingPoolId = ref('')
const precomputingPoolId = ref('')
const customPoolName = ref('')
const customSymbolText = ref('')
const metricSnapshotInfo = ref<ScannerMetricSnapshot | null>(null)
const scannerPlans = ref<ScannerPlan[]>([])
const selectedPlanId = ref('')
const planRuns = ref<ScannerPlanRun[]>([])
const planName = ref('')
const planLoading = ref(false)
const planTableLoading = ref(false)
const planRunLoading = ref(false)
const dailyRunLoading = ref(false)
const indicatorRules = ref<IndicatorRule[]>([
  { id: 'indicator-default', metric: 'indicator', operator: '>=', value: 0.5, enabled: true },
  { id: 'sentiment-default', metric: 'news_sentiment', operator: '>=', value: 0.4, enabled: true },
])

const selectedPool = computed(() => findPool(selectedPoolId.value))
const selectedPlan = computed(() => scannerPlans.value.find((plan) => plan.id === selectedPlanId.value))
const managerPool = computed(() => findPool(managerPoolId.value) || selectedPool.value)
const selectedPoolInstrumentCount = computed(() => selectedPool.value?.instrument_count || 0)
const condition = computed(() => buildCondition(indicatorRules.value))
const planDialogTitle = computed(() => (
  editingPlanId.value ? t('scannerPage.editPlanTitle') : t('scannerPage.newPlanTitle')
))
const selectedPlanResultTableLabel = computed(() => {
  const status = selectedPlan.value?.result_table_status || 'missing'
  const tableName = selectedPlan.value?.result_table_name
  if (status === 'ready' && tableName) {
    return t('scannerPage.resultTableReady', { table: tableName })
  }
  if (status === 'dropped') {
    return t('scannerPage.resultTableDropped')
  }
  return t('scannerPage.resultTableMissing')
})
const latestPlanRunLabel = computed(() => {
  const latest = planRuns.value[0]
  if (!latest) return t('scannerPage.planNoRuns')
  return t('scannerPage.planRunSummary', {
    date: latest.run_date,
    status: latest.status,
  })
})
const activeMetricSnapshot = computed(() => {
  if (metricSnapshotInfo.value?.pool_id === managerPool.value?.id) {
    return metricSnapshotInfo.value
  }
  return managerPool.value?.metric_snapshot || null
})
const metricSnapshotLabel = computed(() => {
  const snapshot = activeMetricSnapshot.value
  if (!snapshot?.computed_at) return t('scannerPage.metricSnapshotEmpty')
  return t('scannerPage.metricSnapshotSummary', {
    total: snapshot.total,
    updatedAt: formatDateTime(snapshot.computed_at),
  })
})

const statusTagType = computed(() => {
  if (taskStatus.value === 'completed') return 'success'
  if (taskStatus.value === 'failed') return 'danger'
  if (taskStatus.value === 'running' || taskStatus.value === 'submitted') return 'warning'
  return 'info'
})

const scannerHeroStats = computed(() => [
  {
    key: 'pools',
    label: t('scannerPage.statPools'),
    value: formatNumber(universePools.value.length, 0),
    helper: t('scannerPage.statPoolsHelper'),
  },
  {
    key: 'plans',
    label: t('scannerPage.statPlans'),
    value: formatNumber(scannerPlans.value.length, 0),
    helper: t('scannerPage.statPlansHelper'),
  },
  {
    key: 'universe',
    label: t('scannerPage.statUniverse'),
    value: formatNumber(selectedPoolInstrumentCount.value, 0),
    helper: selectedPool.value?.name || t('scannerPage.poolNoDescription'),
  },
  {
    key: 'results',
    label: t('scannerPage.statResults'),
    value: formatNumber(matches.value.length, 0),
    helper: taskStatus.value || 'idle',
  },
])

const metricCards = computed(() => [
  {
    key: 'bestIndicator',
    label: t('scannerPage.metricBestIndicator'),
    value: formatPercent(maxValue('indicator')),
    helper: t('scannerPage.metricBestIndicatorHelper'),
    tone: 'teal',
  },
  {
    key: 'avgChange',
    label: t('scannerPage.metricAvgChange'),
    value: formatPercent(avgValue('change_pct')),
    helper: t('scannerPage.metricAvgChangeHelper'),
    tone: 'amber',
  },
  {
    key: 'avgExposure',
    label: t('scannerPage.metricAvgExposure'),
    value: formatPercent(avgValue('portfolio_exposure')),
    helper: t('scannerPage.metricAvgExposureHelper'),
    tone: 'neutral',
  },
  {
    key: 'lookback',
    label: t('scannerPage.metricLookback'),
    value: formatNumber(lookbackDays.value, 0),
    helper: t('scannerPage.metricLookbackHelper'),
    tone: 'neutral',
  },
  {
    key: 'universe',
    label: t('scannerPage.metricUniverse'),
    value: formatNumber(selectedPoolInstrumentCount.value, 0),
    helper: selectedPool.value?.name || '-',
    tone: 'neutral',
  },
])

onMounted(() => {
  void initialize()
})

async function initialize() {
  await loadUniversePools()
  await loadScannerPlans()
  if (planRuns.value.length) {
    loadRunResult(planRuns.value[0])
    return
  }
  if (!scannerPlans.value.length && selectedPoolId.value) {
    await run()
  }
}

async function loadUniversePools() {
  try {
    const response = await marketIntelApi.listScannerUniversePools()
    universePools.value = normalizePools(response.items)
  } catch {
    universePools.value = fallbackPools
  }
  if (!universePools.value.length) {
    universePools.value = fallbackPools
  }
  if (!selectedPoolId.value || !findPool(selectedPoolId.value)) {
    selectedPoolId.value = universePools.value[0]?.id || ''
  }
  if (!managerPoolId.value || !findPool(managerPoolId.value)) {
    managerPoolId.value = selectedPoolId.value
  }
}

async function loadScannerPlans() {
  try {
    const response = await marketIntelApi.listScannerPlans()
    scannerPlans.value = Array.isArray(response.items) ? response.items : []
  } catch {
    scannerPlans.value = []
  }
  if (scannerPlans.value.length && !selectedPlanId.value) {
    selectedPlanId.value = scannerPlans.value[0].id
    applyPlan(scannerPlans.value[0])
    await loadPlanRuns(selectedPlanId.value)
  }
}

async function run() {
  if (!selectedPoolId.value) return
  loading.value = true
  try {
    const response = await marketIntelApi.runScanner({
      universe_pool_id: selectedPoolId.value,
      condition: condition.value,
      lookback_days: lookbackDays.value,
      timeframe: timeframe.value,
    })
    taskId.value = String(response.task_id || '')
    taskStatus.value = String(response.status || 'submitted')
    if (!taskId.value) {
      matches.value = normalizeMatches(response.matches)
      return
    }
    const task = await marketIntelApi.getScannerTask(taskId.value)
    taskStatus.value = String(task.status || taskStatus.value)
    matches.value = normalizeMatches(task.matches)
  } finally {
    loading.value = false
  }
}

async function saveScannerPlan() {
  if (!selectedPoolId.value) return
  planLoading.value = true
  try {
    const plan = await marketIntelApi.createScannerPlan(buildPlanPayload())
    upsertPlan(plan)
    selectedPlanId.value = plan.id
    planName.value = plan.name
    await loadPlanRuns(plan.id)
  } finally {
    planLoading.value = false
  }
}

async function savePlanFromDialog() {
  if (!selectedPoolId.value) return
  planLoading.value = true
  try {
    const payload = buildPlanPayload()
    const plan = editingPlanId.value
      ? await marketIntelApi.updateScannerPlan(editingPlanId.value, { ...payload, status: 'active' })
      : await marketIntelApi.createScannerPlan(payload)
    upsertPlan(plan)
    selectedPlanId.value = plan.id
    editingPlanId.value = plan.id
    planName.value = plan.name
    await loadPlanRuns(plan.id)
  } finally {
    planLoading.value = false
  }
}

async function deleteSelectedPlan() {
  const deletedPlanId = editingPlanId.value || selectedPlanId.value
  if (!deletedPlanId) return
  planLoading.value = true
  try {
    await marketIntelApi.deleteScannerPlan(deletedPlanId)
    scannerPlans.value = scannerPlans.value.filter((plan) => plan.id !== deletedPlanId)
    selectedPlanId.value = scannerPlans.value[0]?.id || ''
    editingPlanId.value = selectedPlanId.value
    planRuns.value = []
    if (selectedPlan.value) {
      applyPlan(selectedPlan.value)
      await loadPlanRuns(selectedPlan.value.id)
    } else {
      planName.value = ''
    }
    planDialogVisible.value = false
  } finally {
    planLoading.value = false
  }
}

async function createSelectedPlanResultTable() {
  const planId = editingPlanId.value || selectedPlanId.value
  if (!planId) return
  planTableLoading.value = true
  try {
    const plan = await marketIntelApi.createScannerPlanResultTable(planId)
    upsertPlan(plan)
    selectedPlanId.value = plan.id
    editingPlanId.value = plan.id
  } finally {
    planTableLoading.value = false
  }
}

async function deleteSelectedPlanResultTable() {
  const planId = editingPlanId.value || selectedPlanId.value
  if (!planId) return
  planTableLoading.value = true
  try {
    const plan = await marketIntelApi.deleteScannerPlanResultTable(planId)
    upsertPlan(plan)
    selectedPlanId.value = plan.id
    editingPlanId.value = plan.id
  } finally {
    planTableLoading.value = false
  }
}

async function runSelectedPlan() {
  const planId = selectedPlanId.value || scannerPlans.value[0]?.id || ''
  if (!planId) return
  selectedPlanId.value = planId
  planRunLoading.value = true
  try {
    const runItem = await marketIntelApi.runScannerPlan(planId, {})
    const executedPlanId = runItem.plan_id || planId
    selectedPlanId.value = executedPlanId
    upsertPlanRun(runItem)
    loadRunResult(runItem)
    await loadPlanRuns(executedPlanId)
  } finally {
    planRunLoading.value = false
  }
}

async function runDailyPlans() {
  dailyRunLoading.value = true
  try {
    const response = await marketIntelApi.runDailyScannerPlans({})
    const selectedRun = response.items.find((item) => item.plan_id === selectedPlanId.value)
      || response.items[0]
    if (selectedRun) {
      selectedPlanId.value = selectedRun.plan_id
      upsertPlanRun(selectedRun)
      loadRunResult(selectedRun)
      await loadPlanRuns(selectedRun.plan_id)
    }
  } finally {
    dailyRunLoading.value = false
  }
}

async function loadPlanRuns(planId: string) {
  if (!planId) return
  const response = await marketIntelApi.listScannerPlanRuns(planId)
  planRuns.value = Array.isArray(response.items) ? response.items : []
}

function applySelectedPlan() {
  const plan = scannerPlans.value.find((item) => item.id === selectedPlanId.value)
  if (!plan) return
  applyPlan(plan)
  void loadPlanRuns(plan.id)
}

function applyPlan(plan: ScannerPlan) {
  selectedPoolId.value = plan.universe_pool_id
  managerPoolId.value = plan.universe_pool_id
  lookbackDays.value = Number(plan.lookback_days || 20)
  timeframe.value = plan.timeframe || '1d'
  indicatorRules.value = normalizeIndicatorRules(plan.indicator_rules)
  planName.value = plan.name
}

function loadRunResult(runItem: ScannerPlanRun) {
  matches.value = normalizeMatches(runItem.matches)
  taskId.value = String(runItem.id || '')
  taskStatus.value = String(runItem.status || 'completed')
}

function openNewPlanDialog() {
  editingPlanId.value = ''
  planName.value = ''
  lookbackDays.value = 20
  timeframe.value = '1d'
  indicatorRules.value = normalizeIndicatorRules([])
  selectedPoolId.value = selectedPoolId.value || universePools.value[0]?.id || ''
  managerPoolId.value = selectedPoolId.value
  planDialogVisible.value = true
}

function openEditPlanDialog(planId = selectedPlanId.value) {
  const plan = scannerPlans.value.find((item) => item.id === planId)
  if (plan) {
    selectedPlanId.value = plan.id
    editingPlanId.value = plan.id
    applyPlan(plan)
  } else {
    editingPlanId.value = ''
  }
  managerPoolId.value = selectedPoolId.value || universePools.value[0]?.id || ''
  planDialogVisible.value = true
}

function selectManagerPool(poolId: string) {
  managerPoolId.value = poolId
  selectedPoolId.value = poolId
}

async function refreshPool(poolId: string) {
  if (!poolId) return
  refreshingPoolId.value = poolId
  try {
    const pool = await marketIntelApi.refreshScannerUniversePool(poolId)
    upsertPool(pool)
    managerPoolId.value = pool.id
    if (!selectedPoolId.value) {
      selectedPoolId.value = pool.id
    }
  } finally {
    refreshingPoolId.value = ''
  }
}

async function precomputePoolMetrics(poolId: string) {
  if (!poolId) return
  precomputingPoolId.value = poolId
  try {
    const snapshot = await marketIntelApi.precomputeScannerUniversePool(poolId, {
      lookback_days: lookbackDays.value,
      timeframe: timeframe.value,
    })
    metricSnapshotInfo.value = snapshot
    const pool = findPool(poolId)
    if (pool) {
      upsertPool({ ...pool, metric_snapshot: snapshot })
    }
  } finally {
    precomputingPoolId.value = ''
  }
}

async function saveCustomPool() {
  const instruments = parseSymbols(customSymbolText.value).map((symbol) => ({
    symbol,
    name: symbol,
    asset_type: 'custom',
  }))
  if (!customPoolName.value.trim() || !instruments.length) return

  poolLoading.value = true
  try {
    const pool = await marketIntelApi.saveCustomScannerUniversePool({
      name: customPoolName.value.trim(),
      description: '',
      instruments,
    })
    upsertPool(pool)
    selectedPoolId.value = pool.id
    managerPoolId.value = pool.id
    customPoolName.value = ''
    customSymbolText.value = ''
  } finally {
    poolLoading.value = false
  }
}

function upsertPool(pool: ScannerUniversePool) {
  const normalized = normalizePool(pool)
  const index = universePools.value.findIndex((item) => item.id === normalized.id)
  if (index >= 0) {
    universePools.value.splice(index, 1, normalized)
    return
  }
  universePools.value.push(normalized)
}

function upsertPlan(plan: ScannerPlan) {
  const index = scannerPlans.value.findIndex((item) => item.id === plan.id)
  if (index >= 0) {
    scannerPlans.value.splice(index, 1, plan)
    return
  }
  scannerPlans.value.unshift(plan)
}

function upsertPlanRun(runItem: ScannerPlanRun) {
  const index = planRuns.value.findIndex((item) => item.id === runItem.id)
  if (index >= 0) {
    planRuns.value.splice(index, 1, runItem)
    return
  }
  planRuns.value.unshift(runItem)
}

function buildPlanPayload() {
  return {
    name: planName.value.trim() || defaultPlanName(),
    universe_pool_id: selectedPoolId.value,
    indicator_rules: indicatorRules.value.map((rule) => ({ ...rule })),
    condition: condition.value,
    lookback_days: lookbackDays.value,
    timeframe: timeframe.value,
    schedule_enabled: true,
    schedule_frequency: 'daily',
  }
}

function findPool(poolId: string) {
  return universePools.value.find((pool) => pool.id === poolId)
}

function normalizePools(pools: ScannerUniversePool[] | undefined) {
  return (pools || []).map(normalizePool)
}

function normalizePool(pool: ScannerUniversePool) {
  const instruments = Array.isArray(pool.instruments) ? pool.instruments : []
  return {
    ...pool,
    instrument_count: Number(pool.instrument_count ?? instruments.length),
    instruments,
  }
}

function parseSymbols(value: string) {
  return Array.from(new Set(
    value
      .split(/[,\s，、]+/)
      .map((item) => item.trim())
      .filter(Boolean),
  ))
}

function normalizeMatches(value: unknown) {
  return Array.isArray(value) ? value as Array<Record<string, unknown>> : []
}

function normalizeIndicatorRules(rules: ScannerIndicatorRule[] | undefined) {
  const normalized = (rules || []).map((rule, index) => ({
    id: rule.id || `plan-rule-${index}`,
    metric: rule.metric,
    operator: rule.operator,
    value: Number(rule.value),
    enabled: Boolean(rule.enabled),
  }))
  return normalized.length ? normalized : [
    { id: 'indicator-default', metric: 'indicator', operator: '>=', value: 0.5, enabled: true },
    { id: 'sentiment-default', metric: 'news_sentiment', operator: '>=', value: 0.4, enabled: true },
  ]
}

function defaultPlanName() {
  return `${selectedPool.value?.name || 'Scanner'} ${timeframe.value}`
}

function addIndicatorRule() {
  indicatorRules.value.push({
    id: `metric-${Date.now()}-${indicatorRules.value.length}`,
    metric: 'indicator',
    operator: '>=',
    value: 0.5,
    enabled: true,
  })
}

function removeIndicatorRule(ruleId: string) {
  indicatorRules.value = indicatorRules.value.filter((rule) => rule.id !== ruleId)
}

function buildCondition(rules: IndicatorRule[]) {
  const parts = rules
    .filter((rule) => rule.enabled)
    .map((rule) => `${rule.metric} ${rule.operator} ${formatRuleValue(rule.value)}`)
  return parts.length ? parts.join(' and ') : 'price > 0'
}

function formatRuleValue(value: unknown) {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? String(numericValue) : '0'
}

function maxValue(key: string) {
  const values = matches.value.map((row) => toFiniteNumber(row[key])).filter((value) => value !== undefined)
  return values.length ? Math.max(...values) : undefined
}

function avgValue(key: string) {
  const values = matches.value.map((row) => toFiniteNumber(row[key])).filter((value) => value !== undefined)
  if (!values.length) return undefined
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function toFiniteNumber(value: unknown) {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : undefined
}

function formatNumber(value: unknown, digits = 2) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === undefined) return '-'
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(numericValue)
}

function formatPercent(value: unknown) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === undefined) return '-'
  return `${(numericValue * 100).toFixed(2)}%`
}

function formatDateTime(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function displayValue(value: unknown) {
  const text = String(value ?? '').trim()
  return text || '-'
}

function scoreClass(value: unknown) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === undefined) return 'is-empty'
  if (numericValue >= 0.7) return 'is-strong'
  if (numericValue >= 0.45) return 'is-medium'
  return 'is-muted'
}
</script>

<style scoped>
.scanner-page {
  display: grid;
  gap: 16px;
}

.scanner-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-end;
}

.scanner-eyebrow {
  margin-bottom: 4px;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 600;
}

.scanner-header h2 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 24px;
  line-height: 1.25;
}

.scanner-header p {
  margin: 6px 0 0;
  color: var(--text-color-secondary);
  font-size: 14px;
}

.scanner-status-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.scanner-status-strip span,
.scanner-run-pill,
.scanner-row-count {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 4px 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 6px;
  background: var(--bg-color-card);
}

.scanner-status-strip strong {
  margin-left: 4px;
  color: var(--text-color-primary);
  font-weight: 600;
}

.scanner-workbench {
  border-radius: 8px;
}

:global(.scanner-pool-dialog) {
  max-width: min(1040px, calc(100vw - 24px));
}

:global(.scanner-pool-dialog .el-dialog__body) {
  max-height: min(76vh, 760px);
  overflow: auto;
}

.scanner-query-panel,
.scanner-metric-panel {
  display: grid;
  gap: 14px;
}

.scanner-query-panel,
.scanner-metric-panel {
  margin-bottom: 18px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.scanner-section-header,
.scanner-symbol-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.scanner-section-header h3 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 16px;
  line-height: 1.35;
}

.scanner-section-header p {
  margin: 4px 0 0;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.scanner-status-tag {
  text-transform: capitalize;
}

.scanner-plan-panel {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-page);
}

.scanner-plan-grid {
  display: grid;
  grid-template-columns: minmax(220px, 0.65fr) minmax(420px, 1.35fr);
  gap: 10px;
  align-items: end;
}

.scanner-plan-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.scanner-plan-run-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.scanner-plan-run-strip strong {
  color: var(--text-color-primary);
}

.scanner-plan-dialog-shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.scanner-plan-dialog-shell.is-create {
  grid-template-columns: minmax(0, 1fr);
}

.scanner-plan-dialog-shell.is-create .scanner-plan-dialog-main {
  max-width: 860px;
  width: 100%;
  justify-self: center;
}

.scanner-plan-dialog-aside,
.scanner-plan-dialog-main,
.scanner-plan-editor-section {
  display: grid;
  gap: 12px;
}

.scanner-plan-dialog-aside {
  position: sticky;
  top: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-page);
}

.scanner-plan-dialog-summary {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.scanner-plan-dialog-summary span {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.scanner-plan-dialog-summary strong {
  min-width: 0;
  color: var(--text-color-primary);
  font-size: 13px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.scanner-plan-editor-section {
  display: grid;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-page);
}

.scanner-plan-editor-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 10px;
  align-items: end;
}

.scanner-plan-editor-parameters {
  display: grid;
  grid-template-columns: minmax(140px, 0.45fr) minmax(160px, 0.55fr);
  gap: 10px;
  align-items: end;
}

.scanner-plan-editor-toolbar,
.scanner-plan-table-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.scanner-manager-pool-card small,
.scanner-symbol-chip span,
.scanner-symbol-chip small,
.scanner-symbol-heading small {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.scanner-field {
  display: grid;
  gap: 6px;
}

.scanner-field span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 600;
}

.scanner-metric-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.scanner-metric-card {
  display: grid;
  gap: 6px;
  min-height: 112px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-page);
}

.scanner-metric-card span,
.scanner-metric-card small {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.scanner-metric-card strong {
  color: var(--text-color-primary);
  font-size: 24px;
  line-height: 1.1;
}

.scanner-metric-card.is-teal {
  border-color: rgba(20, 184, 166, 0.35);
}

.scanner-metric-card.is-blue {
  border-color: rgba(59, 130, 246, 0.35);
}

.scanner-metric-card.is-amber {
  border-color: rgba(245, 158, 11, 0.38);
}

.scanner-pool-manager-panel {
  display: grid;
  gap: 12px;
}

.scanner-manager-toolbar,
.scanner-manager-detail,
.scanner-manager-overview,
.scanner-manager-symbols,
.scanner-indicator-manager-panel,
.scanner-custom-panel {
  display: grid;
  gap: 10px;
}

.scanner-manager-toolbar {
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-card);
}

.scanner-manager-select {
  max-width: none;
}

.scanner-manager-detail {
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-page);
}

.scanner-manager-layout {
  gap: 12px;
}

.scanner-manager-overview,
.scanner-manager-symbols {
  min-width: 0;
}

.scanner-manager-detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.scanner-manager-detail-header h3 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 15px;
  line-height: 1.35;
}

.scanner-manager-detail-header p {
  margin: 4px 0 0;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.scanner-manager-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-start;
  gap: 8px;
}

.scanner-symbol-chip {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-card);
  color: var(--text-color-primary);
}

.scanner-symbol-heading span {
  font-weight: 600;
}

.scanner-symbol-chip {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.scanner-pool-meta-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.scanner-pool-meta-grid span {
  display: grid;
  gap: 4px;
  min-height: 56px;
  padding: 8px 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-page);
  color: var(--text-color-secondary);
  font-size: 12px;
}

.scanner-pool-meta-grid strong {
  color: var(--text-color-primary);
  font-size: 13px;
}

.scanner-indicator-manager-panel {
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-page);
}

.scanner-indicator-rule-list {
  display: grid;
  gap: 8px;
}

.scanner-indicator-rule {
  display: grid;
  grid-template-columns: minmax(74px, 0.35fr) minmax(140px, 1fr) minmax(96px, 0.55fr) minmax(132px, 0.85fr) auto;
  gap: 8px;
  align-items: end;
  padding: 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-card);
}

.scanner-indicator-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.scanner-generated-condition {
  display: inline-flex;
  flex: 1;
  min-width: min(100%, 360px);
  gap: 8px;
  align-items: center;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.scanner-generated-condition strong {
  min-width: 0;
  color: var(--text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.scanner-symbol-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  max-height: 300px;
  overflow: auto;
}

.scanner-symbol-chip {
  display: grid;
  gap: 4px;
  min-height: 72px;
  padding: 9px 10px;
}

.scanner-symbol-chip strong {
  font-size: 13px;
  line-height: 1.2;
}

.scanner-custom-panel {
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-page);
}

.scanner-custom-grid {
  display: grid;
  grid-template-columns: minmax(180px, 0.45fr) minmax(0, 1fr) auto;
  gap: 10px;
  align-items: end;
}

.scanner-custom-actions {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 1120px) {
  .scanner-metric-grid,
  .scanner-symbol-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .scanner-plan-grid,
  .scanner-plan-editor-grid,
  .scanner-plan-editor-parameters,
  .scanner-pool-meta-grid,
  .scanner-indicator-rule {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 840px) {
  :global(.scanner-pool-dialog) {
    width: calc(100vw - 24px) !important;
    margin-top: 12px;
  }

  :global(.scanner-pool-dialog .el-dialog__body) {
    max-height: calc(100vh - 96px);
  }

  .scanner-header,
  .scanner-section-header,
  .scanner-symbol-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .scanner-plan-grid,
  .scanner-plan-dialog-shell,
  .scanner-plan-editor-grid,
  .scanner-plan-editor-parameters,
  .scanner-metric-grid,
  .scanner-pool-manager-panel,
  .scanner-manager-toolbar,
  .scanner-pool-meta-grid,
  .scanner-symbol-grid,
  .scanner-indicator-rule,
  .scanner-custom-grid {
    grid-template-columns: 1fr;
  }

  .scanner-manager-select {
    max-width: none;
  }

  .scanner-manager-detail-header {
    flex-direction: column;
  }

  .scanner-plan-actions,
  .scanner-plan-actions :deep(.el-button),
  .scanner-plan-editor-toolbar,
  .scanner-plan-editor-toolbar :deep(.el-button),
  .scanner-manager-actions,
  .scanner-manager-actions :deep(.el-button),
  .scanner-plan-table-actions,
  .scanner-plan-table-actions :deep(.el-button),
  .scanner-custom-actions,
  .scanner-custom-actions :deep(.el-button) {
    width: 100%;
  }
}

.scanner-page {
  --scanner-bg: var(--bg-color-page);
  --scanner-surface: color-mix(in srgb, var(--bg-color) 92%, transparent);
  --scanner-surface-strong: color-mix(in srgb, var(--bg-color) 82%, var(--el-color-primary) 18%);
  --scanner-text: var(--text-color-primary);
  --scanner-muted: var(--text-color-secondary);
  --scanner-border: color-mix(in srgb, var(--border-color) 78%, transparent);
  --scanner-border-strong: color-mix(in srgb, var(--border-color) 64%, var(--el-color-primary) 36%);
  --scanner-shadow: 0 18px 48px color-mix(in srgb, #000 16%, transparent);
  --scanner-good: var(--success-color, #16a34a);
  --scanner-warn: var(--warning-color, #d97706);
  --scanner-bad: var(--danger-color, #dc2626);
  gap: 18px;
  color: var(--scanner-text);
}

.scanner-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(360px, 0.92fr);
  gap: 18px;
  padding: clamp(22px, 3.2vw, 34px);
  border: 1px solid var(--scanner-border);
  border-radius: 8px;
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--bg-color) 94%, var(--el-color-primary) 6%), transparent),
    var(--scanner-surface);
  background-color: var(--scanner-surface);
  box-shadow: var(--scanner-shadow);
}

.scanner-hero-copy {
  display: grid;
  align-content: center;
  gap: 10px;
  min-width: 0;
}

.scanner-eyebrow {
  margin: 0;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.scanner-hero h1 {
  margin: 0;
  color: var(--scanner-text);
  font-size: clamp(30px, 4vw, 46px);
  line-height: 1.06;
  letter-spacing: 0;
}

.scanner-hero p {
  max-width: 760px;
  margin: 0;
  color: var(--scanner-muted);
  line-height: 1.68;
}

.scanner-hero-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.scanner-hero-stat,
.scanner-metric-card,
.scanner-source-card {
  min-width: 0;
  border: 1px solid var(--scanner-border);
  border-radius: 8px;
  background: var(--scanner-surface);
  background-color: var(--scanner-surface);
}

.scanner-hero-stat {
  display: grid;
  align-content: center;
  gap: 8px;
  min-height: 118px;
  padding: 16px;
}

.scanner-hero-stat span,
.scanner-hero-stat small,
.scanner-metric-card span,
.scanner-metric-card small {
  color: var(--scanner-muted);
  font-size: 12px;
  line-height: 1.5;
}

.scanner-hero-stat strong,
.scanner-metric-card strong {
  color: var(--scanner-text);
  font-size: 26px;
  line-height: 1.1;
}

.scanner-workbench {
  border: 1px solid var(--scanner-border);
  border-radius: 8px;
  background: var(--scanner-surface);
  background-color: var(--scanner-surface);
  box-shadow: 0 12px 30px color-mix(in srgb, #000 10%, transparent);
}

.scanner-workbench :deep(.el-card__body) {
  display: grid;
  gap: 18px;
  padding: 18px;
}

.scanner-query-panel,
.scanner-metric-panel {
  gap: 16px;
  margin: 0;
  padding: 0;
  border: 0;
}

.scanner-command-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.14fr) minmax(320px, 0.86fr);
  gap: 16px;
}

.scanner-plan-panel,
.scanner-live-panel,
.scanner-metric-panel,
.scanner-match-board,
.scanner-plan-editor-section,
.scanner-plan-dialog-aside,
.scanner-manager-toolbar,
.scanner-manager-detail,
.scanner-custom-panel,
.scanner-indicator-manager-panel {
  border: 1px solid var(--scanner-border);
  border-radius: 8px;
  background: var(--scanner-surface);
  background-color: var(--scanner-surface);
}

.scanner-plan-panel,
.scanner-live-panel,
.scanner-metric-panel,
.scanner-match-board {
  display: grid;
  gap: 14px;
  padding: 16px;
}

.scanner-section-header,
.scanner-symbol-heading {
  align-items: flex-start;
}

.scanner-section-header h3,
.scanner-symbol-heading span {
  color: var(--scanner-text);
  font-size: 16px;
  line-height: 1.35;
}

.scanner-section-header p,
.scanner-symbol-heading small {
  color: var(--scanner-muted);
  font-size: 12px;
  line-height: 1.55;
}

.scanner-row-count,
.scanner-run-pill,
.scanner-status-strip span {
  border-color: var(--scanner-border);
  border-radius: 999px;
  color: var(--scanner-muted);
  background: var(--scanner-surface-strong);
}

.scanner-plan-grid {
  grid-template-columns: minmax(220px, 0.72fr) minmax(360px, 1.28fr);
}

.scanner-plan-actions,
.scanner-live-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.scanner-live-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(132px, 0.38fr) minmax(132px, 0.38fr);
  gap: 10px;
  align-items: end;
}

.scanner-active-condition {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid var(--scanner-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--scanner-bg) 64%, var(--bg-color) 36%);
}

.scanner-active-condition span {
  color: var(--scanner-muted);
  font-size: 12px;
  font-weight: 700;
}

.scanner-active-condition strong {
  color: var(--scanner-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.scanner-plan-run-strip {
  padding: 10px 12px;
  border: 1px solid var(--scanner-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--scanner-bg) 64%, var(--bg-color) 36%);
}

.scanner-field span {
  color: var(--scanner-muted);
}

.scanner-metric-grid {
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.scanner-metric-card {
  min-height: 118px;
  padding: 14px;
}

.scanner-metric-card.is-teal,
.scanner-score-pill.is-strong {
  border-color: color-mix(in srgb, var(--scanner-good) 55%, transparent);
  color: var(--scanner-good);
  background: color-mix(in srgb, var(--scanner-good) 12%, var(--bg-color));
}

.scanner-metric-card.is-amber,
.scanner-score-pill.is-medium {
  border-color: color-mix(in srgb, var(--scanner-warn) 55%, transparent);
  color: var(--scanner-warn);
  background: color-mix(in srgb, var(--scanner-warn) 12%, var(--bg-color));
}

.scanner-metric-card.is-blue {
  border-color: color-mix(in srgb, var(--el-color-primary) 55%, transparent);
}

.scanner-match-board {
  overflow: hidden;
  padding: 0;
}

.scanner-match-board > .scanner-section-header {
  padding: 18px 18px 14px;
  border-bottom: 1px solid var(--scanner-border);
}

.scanner-match-table {
  --el-table-bg-color: var(--scanner-surface);
  --el-table-tr-bg-color: var(--scanner-surface);
  --el-table-header-bg-color: color-mix(in srgb, var(--scanner-bg) 62%, var(--bg-color) 38%);
  --el-table-text-color: var(--scanner-text);
  --el-table-header-text-color: var(--scanner-text);
  --el-table-border-color: var(--scanner-border);
}

.scanner-symbol-cell {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.scanner-symbol-cell strong {
  color: var(--scanner-text);
  font-size: 13px;
  line-height: 1.3;
}

.scanner-symbol-cell span {
  color: var(--scanner-muted);
  font-size: 12px;
}

.scanner-score-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 26px;
  min-width: 76px;
  padding: 0 9px;
  border: 1px solid var(--scanner-border);
  border-radius: 999px;
  color: var(--scanner-muted);
  background: var(--scanner-surface-strong);
  font-size: 12px;
  font-weight: 700;
}

.scanner-score-pill.is-muted,
.scanner-score-pill.is-empty {
  border-color: color-mix(in srgb, var(--scanner-border) 72%, transparent);
  color: var(--scanner-muted);
  background: var(--scanner-surface-strong);
}

.scanner-empty-state {
  display: grid;
  justify-items: center;
  gap: 8px;
  margin: 18px;
  padding: 34px 18px;
  border: 1px dashed var(--scanner-border-strong);
  border-radius: 8px;
  color: var(--scanner-muted);
  text-align: center;
  background: color-mix(in srgb, var(--scanner-bg) 68%, var(--bg-color) 32%);
}

.scanner-empty-state strong {
  color: var(--scanner-text);
}

.scanner-empty-state p {
  max-width: 560px;
  margin: 0;
  line-height: 1.6;
}

.scanner-plan-dialog-aside,
.scanner-plan-editor-section,
.scanner-manager-toolbar,
.scanner-manager-detail,
.scanner-custom-panel,
.scanner-indicator-manager-panel {
  background: color-mix(in srgb, var(--scanner-bg) 58%, var(--bg-color) 42%);
}

.scanner-symbol-chip,
.scanner-pool-meta-grid span,
.scanner-indicator-rule {
  border-color: var(--scanner-border);
  color: var(--scanner-text);
  background: var(--scanner-surface);
}

.scanner-symbol-chip {
  background: color-mix(in srgb, var(--el-color-primary) 10%, var(--bg-color));
}

:global(.scanner-pool-dialog.el-dialog),
:global(.scanner-pool-dialog .el-dialog) {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

:global(.scanner-pool-dialog.el-dialog .el-dialog__title),
:global(.scanner-pool-dialog .el-dialog__title),
:global(.scanner-pool-dialog.el-dialog .el-dialog__body),
:global(.scanner-pool-dialog .el-dialog__body) {
  color: var(--text-color-primary);
}

@media (max-width: 1120px) {
  .scanner-hero,
  .scanner-command-grid {
    grid-template-columns: 1fr;
  }

  .scanner-metric-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 840px) {
  .scanner-hero,
  .scanner-workbench :deep(.el-card__body),
  .scanner-plan-panel,
  .scanner-live-panel,
  .scanner-metric-panel {
    padding: 16px;
  }

  .scanner-hero-stats,
  .scanner-plan-grid,
  .scanner-live-grid,
  .scanner-metric-grid {
    grid-template-columns: 1fr;
  }

  .scanner-plan-actions,
  .scanner-live-actions,
  .scanner-plan-actions :deep(.el-button),
  .scanner-live-actions :deep(.el-button) {
    width: 100%;
  }
}
</style>
