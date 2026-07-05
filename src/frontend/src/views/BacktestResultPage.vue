<template>
  <div class="backtest-result-page">
    <!-- Loading state -->
    <div
      v-if="loading"
      class="backtest-result-state"
      role="status"
      :aria-label="t('common.loading')"
    >
      <el-icon
        class="backtest-result-loading is-loading"
        aria-hidden="true"
      >
        <Loading />
      </el-icon>
      <span>{{ t('common.loading') }}</span>
    </div>

    <!-- Error state -->
    <div
      v-else-if="error"
      class="backtest-result-error"
      role="alert"
    >
      <el-icon
        class="backtest-result-error-icon"
        aria-hidden="true"
      >
        <CircleCloseFilled />
      </el-icon>
      <p>
        {{ error }}
      </p>
      <el-button
        :aria-label="t('backtest.retry')"
        @click="loadData"
      >
        {{ t('backtest.retry') }}
      </el-button>
    </div>

    <!-- Content -->
    <template v-else-if="detail">
      <!-- Header title and actions -->
      <section
        class="backtest-result-hero"
        data-test="backtest-detail"
        aria-labelledby="backtest-result-title"
      >
        <div class="backtest-result-copy">
          <span class="backtest-result-kicker">{{ t('backtest.resultHeroKicker') }}</span>
          <div class="backtest-result-title-row">
            <h1 id="backtest-result-title">
              {{ detail.strategy_name }}
            </h1>
            <el-tag
              :type="statusTagType"
              effect="plain"
            >
              {{ resultStatusLabel }}
            </el-tag>
          </div>
          <p>{{ t('backtest.resultHeroSubtitle') }}</p>
          <span
            data-test="backtest-status"
            class="sr-only"
          >{{ detail.artifact_status || 'completed' }}</span>
        </div>

        <div class="backtest-result-actions">
          <el-button
            v-if="isOptimizationArtifactMode"
            :aria-label="t('backtest.openArtifact')"
            @click="handleOpenArtifactDir"
          >
            <el-icon aria-hidden="true">
              <FolderOpened />
            </el-icon>{{ t('backtest.openArtifact') }}
          </el-button>
          <el-button
            v-if="isOptimizationArtifactMode"
            :aria-label="t('backtest.download')"
            @click="handleDownloadArtifact"
          >
            <el-icon aria-hidden="true">
              <Download />
            </el-icon>{{ t('backtest.downloadResult') }}
          </el-button>
          <el-button
            v-if="!isOptimizationArtifactMode"
            :aria-label="t('backtest.exportCSV')"
            @click="handleExport('csv')"
          >
            <el-icon aria-hidden="true">
              <Download />
            </el-icon>{{ t('backtest.exportCSV') }}
          </el-button>
          <el-button
            type="primary"
            :aria-label="t('common.back')"
            @click="handleBack"
          >
            <el-icon aria-hidden="true">
              <Back />
            </el-icon>{{ t('common.back') }}
          </el-button>
        </div>

        <div class="backtest-result-meta">
          <span>{{ t('backtest.symbol') }}: {{ detail.symbol }}</span>
          <span>{{ t('backtest.period') }}: {{ detail.start_date }} - {{ detail.end_date }}</span>
          <span>{{ t('backtest.createdAt') }}: {{ formatTime(detail.created_at) }}</span>
          <span>{{ t('backtest.taskId') }}: {{ detail.task_id }}</span>
        </div>

        <div class="backtest-result-metrics">
          <article
            v-for="metric in heroMetrics"
            :key="metric.key"
            class="backtest-result-metric"
            :class="`backtest-result-metric--${metric.tone}`"
          >
            <span>{{ metric.label }}</span>
            <strong>{{ metric.value }}</strong>
          </article>
        </div>
      </section>

      <!-- Performance metrics panel -->
      <section class="backtest-result-panel backtest-result-panel--performance">
        <header class="backtest-result-panel-head">
          <div>
            <span>{{ t('backtest.performanceKicker') }}</span>
            <h2>{{ t('backtest.performanceTitle') }}</h2>
          </div>
          <p>{{ t('backtest.performanceSubtitle') }}</p>
        </header>
        <PerformancePanel :metrics="detail.metrics" />
      </section>

      <section
        v-if="strategyScore || !isOptimizationArtifactMode || overfittingTask || overfittingLoading || strategyExplanation"
        class="backtest-result-panel backtest-result-panel--diagnostics"
      >
        <header class="backtest-result-panel-head">
          <div>
            <span>{{ t('backtest.diagnosticsKicker') }}</span>
            <h2>{{ t('backtest.diagnosticsTitle') }}</h2>
          </div>
          <p>{{ t('backtest.diagnosticsSubtitle') }}</p>
        </header>

        <div class="backtest-result-diagnostics-grid">
          <StrategyScoreCard
            v-if="strategyScore"
            :score="strategyScore"
            class="backtest-diagnostic-card"
          />

          <OverfittingPanel
            v-if="!isOptimizationArtifactMode"
            :result="overfittingTask"
            :loading="overfittingLoading"
            :progress-message="overfittingProgressInfo.message"
            class="backtest-diagnostic-card"
            @rerun="loadOverfitting"
          />

          <StrategyExplanationCard
            v-if="strategyExplanation"
            :explanation="strategyExplanation"
            class="backtest-diagnostic-card backtest-diagnostic-card--wide"
          />
        </div>
      </section>

      <!-- Charts area -->
      <section class="backtest-result-panel backtest-result-panel--charts">
        <header class="backtest-result-panel-head">
          <div>
            <span>{{ t('backtest.chartsKicker') }}</span>
            <h2>{{ t('backtest.chartsTitle') }}</h2>
          </div>
          <p>{{ t('backtest.chartsSubtitle') }}</p>
        </header>

        <el-tabs
          v-model="activeTab"
          class="backtest-chart-tabs"
          type="border-card"
        >
          <el-tab-pane
            :label="t('backtest.chartKline')"
            name="kline"
          >
            <div class="backtest-chart-surface">
              <TradeSignalChart
                :klines="klineData?.klines || []"
                :signals="klineData?.signals || []"
                :indicators="klineData?.indicators"
                :height="550"
              />
            </div>
          </el-tab-pane>

          <el-tab-pane
            :label="t('backtest.chartEquity')"
            name="equity"
          >
            <div
              v-if="activeTab === 'equity'"
              class="backtest-chart-surface"
            >
              <EquityCurve
                data-test="equity-curve"
                :data="detail.equity_curve"
                :height="350"
              />
              <DrawdownChart
                :data="detail.drawdown_curve"
                :height="180"
                class="backtest-drawdown-chart"
              />
            </div>
          </el-tab-pane>

          <el-tab-pane
            :label="t('backtest.chartAnalysis')"
            name="analysis"
          >
            <div
              v-if="activeTab === 'analysis'"
              class="backtest-analysis-grid"
            >
              <div class="backtest-chart-surface">
                <ReturnHeatmap
                  :returns="monthlyReturns?.returns || []"
                  :years="monthlyReturns?.years || []"
                  :height="300"
                />
              </div>
              <div class="backtest-chart-surface">
                <div class="backtest-annual-head">
                  <h3>{{ t('backtest.annualSummary') }}</h3>
                  <span>{{ t('backtest.annualSummaryHint') }}</span>
                </div>
                <div
                  v-if="annualReturnEntries.length"
                  class="backtest-annual-grid"
                >
                  <article
                    v-for="item in annualReturnEntries"
                    :key="item.year"
                    class="backtest-annual-item"
                  >
                    <span>{{ item.year }}</span>
                    <strong :class="item.value >= 0 ? 'is-positive' : 'is-negative'">
                      {{ item.value >= 0 ? '+' : '' }}{{ (item.value * 100).toFixed(2) }}%
                    </strong>
                  </article>
                </div>
                <p
                  v-else
                  class="backtest-annual-empty"
                >
                  {{ t('backtest.annualSummaryEmpty') }}
                </p>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane
            :label="t('backtest.chartTrades')"
            name="trades"
          >
            <div class="backtest-chart-surface backtest-trades-surface">
              <TradeRecordsTable :trades="detail.trades" />
            </div>
          </el-tab-pane>
        </el-tabs>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading, CircleCloseFilled, Download, Back, FolderOpened } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { getErrorMessage } from '@/api'
import { analyticsApi } from '@/api/analytics'
import { strategyApi } from '@/api/strategy'
import type {
  StrategyExplanation,
  StrategyOverfittingMethod,
  StrategyOverfittingTaskResult,
  StrategyScoreResponse,
} from '@/api/strategy'
import { workspaceApi } from '@/api/workspace'
import { useOverfittingRuntime } from '@/composables/useOverfittingRuntime'
import OverfittingPanel from '@/components/backtest/OverfittingPanel.vue'
import StrategyExplanationCard from '@/components/backtest/StrategyExplanationCard.vue'
import StrategyScoreCard from '@/components/backtest/StrategyScoreCard.vue'
import PerformancePanel from '@/components/charts/PerformancePanel.vue'
import TradeSignalChart from '@/components/charts/TradeSignalChart.vue'
import EquityCurve from '@/components/charts/EquityCurve.vue'
import DrawdownChart from '@/components/charts/DrawdownChart.vue'
import ReturnHeatmap from '@/components/charts/ReturnHeatmap.vue'
import TradeRecordsTable from '@/components/charts/TradeRecordsTable.vue'
import type {
  BacktestDetailResponse,
  KlineWithSignalsResponse,
  MonthlyReturnsResponse,
} from '@/types/analytics'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const taskId = computed(() => route.params.id as string)
const workspaceId = computed(() => {
  const value = route.query.workspaceId
  return typeof value === 'string' && value ? value : null
})
const strategyNameFromQuery = computed(() => {
  const value = route.query.strategyName
  return typeof value === 'string' && value.trim() ? value.trim() : null
})
const optimizationUnitId = computed(() => {
  const value = route.query.optimizationUnitId
  return typeof value === 'string' && value ? value : null
})
const optimizationResultIndex = computed(() => {
  const value = route.query.optimizationResultIndex
  if (typeof value !== 'string' || !value) return null
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : null
})
const isOptimizationArtifactMode = computed(() => (
  !!workspaceId.value && !!optimizationUnitId.value && optimizationResultIndex.value !== null
))

const loading = ref(true)
const error = ref<string | null>(null)
const activeTab = ref('equity')

const detail = ref<BacktestDetailResponse | null>(null)
const klineData = ref<KlineWithSignalsResponse | null>(null)
const monthlyReturns = ref<MonthlyReturnsResponse | null>(null)
const strategyScore = ref<StrategyScoreResponse | null>(null)
const strategyExplanation = ref<StrategyExplanation | null>(null)
const overfittingTask = ref<StrategyOverfittingTaskResult | null>(null)

const {
  loading: overfittingLoading,
  progressInfo: overfittingProgressInfo,
  startRuntime: startOverfittingRuntime,
  stopRuntime: stopOverfittingRuntime,
  disposeRuntime: disposeOverfittingRuntime,
} = useOverfittingRuntime({
  currentResult: overfittingTask,
})

onMounted(() => {
  loadData()
})

onUnmounted(() => {
  disposeOverfittingRuntime()
})

watch(activeTab, (tab) => {
  if (!detail.value) return
  if (tab === 'kline') {
    void ensureKlineData()
  } else if (tab === 'analysis') {
    void ensureMonthlyReturns()
  }
})

const resultStatusLabel = computed(() => {
  const status = detail.value?.artifact_status || 'completed'
  const map: Record<string, string> = {
    completed: t('backtest.completed'),
    failed: t('backtest.failed'),
    running: t('backtest.running'),
    pending: t('backtest.pending'),
  }
  return map[status] || status
})

const statusTagType = computed(() => {
  const status = detail.value?.artifact_status || 'completed'
  if (status === 'failed' || status === 'error') return 'danger'
  if (status === 'running' || status === 'pending') return 'warning'
  return 'success'
})

const heroMetrics = computed(() => {
  if (!detail.value) return []
  const metrics = detail.value.metrics
  return [
    {
      key: 'total-return',
      label: t('backtest.totalReturn'),
      value: formatPercent(metrics.total_return),
      tone: metrics.total_return >= 0 ? 'positive' : 'negative',
    },
    {
      key: 'annual-return',
      label: t('backtest.annualReturn'),
      value: formatPercent(metrics.annualized_return),
      tone: metrics.annualized_return >= 0 ? 'positive' : 'negative',
    },
    {
      key: 'sharpe',
      label: t('backtest.sharpeRatio'),
      value: formatNumber(metrics.sharpe_ratio, 2),
      tone: 'neutral',
    },
    {
      key: 'max-drawdown',
      label: t('backtest.maxDrawdown'),
      value: formatPercent(metrics.max_drawdown),
      tone: 'risk',
    },
  ]
})

const annualReturnEntries = computed(() => {
  const summary = monthlyReturns.value?.summary || {}
  return Object.entries(summary)
    .map(([year, value]) => ({ year, value: Number(value) }))
    .filter((item) => Number.isFinite(item.value))
    .sort((a, b) => Number(a.year) - Number(b.year))
})

async function loadData() {
  stopOverfittingRuntime()
  loading.value = true
  error.value = null
  strategyScore.value = null
  strategyExplanation.value = null
  overfittingTask.value = null
  klineData.value = null
  monthlyReturns.value = null

  try {
    let detailRes: BacktestDetailResponse

    if (isOptimizationArtifactMode.value && workspaceId.value && optimizationUnitId.value && optimizationResultIndex.value !== null) {
      detailRes = await workspaceApi.getOptimizationResultDetail(workspaceId.value, optimizationUnitId.value, optimizationResultIndex.value)
    } else {
      detailRes = await analyticsApi.getBacktestDetail(taskId.value)
    }

    detail.value = strategyNameFromQuery.value
      ? { ...detailRes, strategy_name: strategyNameFromQuery.value }
      : detailRes

    if (!isOptimizationArtifactMode.value) {
      void loadDiagnostics()
    }
    if (activeTab.value === 'kline') {
      void ensureKlineData()
    } else if (activeTab.value === 'analysis') {
      void ensureMonthlyReturns()
    }

  } catch (e: unknown) {
    error.value = getErrorMessage(e, t('backtest.loadFailed'))
  } finally {
    loading.value = false
  }
}

async function ensureKlineData() {
  if (klineData.value) return
  try {
    if (isOptimizationArtifactMode.value && workspaceId.value && optimizationUnitId.value && optimizationResultIndex.value !== null) {
      klineData.value = await workspaceApi.getOptimizationResultKline(
        workspaceId.value,
        optimizationUnitId.value,
        optimizationResultIndex.value,
      )
      return
    }
    klineData.value = await analyticsApi.getKlineWithSignals(taskId.value)
  } catch {
    klineData.value = { symbol: detail.value?.symbol || '', klines: [], signals: [], indicators: {} }
  }
}

async function ensureMonthlyReturns() {
  if (monthlyReturns.value) return
  try {
    if (isOptimizationArtifactMode.value && workspaceId.value && optimizationUnitId.value && optimizationResultIndex.value !== null) {
      monthlyReturns.value = await workspaceApi.getOptimizationResultMonthlyReturns(
        workspaceId.value,
        optimizationUnitId.value,
        optimizationResultIndex.value,
      )
      return
    }
    monthlyReturns.value = await analyticsApi.getMonthlyReturns(taskId.value)
  } catch {
    monthlyReturns.value = { returns: [], years: [], summary: {} }
  }
}

async function loadDiagnostics() {
  const [scoreRes, explanationRes] = await Promise.all([
    strategyApi.createScore({ backtest_id: taskId.value }).catch(() => null),
    strategyApi.explainStrategy({ backtest_id: taskId.value }).catch(() => null),
  ])
  strategyScore.value = scoreRes
  strategyExplanation.value = explanationRes
}

async function loadOverfitting(
  methods: StrategyOverfittingMethod[] = ['walk_forward', 'out_of_sample', 'monte_carlo'],
) {
  stopOverfittingRuntime()
  overfittingTask.value = null
  try {
    const submission = await strategyApi.createOverfittingTask(taskId.value, {
      methods,
      walk_forward_train_days: 180,
      walk_forward_test_days: 60,
      walk_forward_step_days: 60,
      walk_forward_max_concurrency: 4,
      out_of_sample_ratio: 0.3,
      monte_carlo_iterations: 300,
    })
    startOverfittingRuntime(submission.task_id)
  } catch {
    stopOverfittingRuntime()
    overfittingTask.value = null
  }
}

function handleExport(format: 'csv' | 'json') {
  analyticsApi.exportResults(taskId.value, format)
}

async function handleOpenArtifactDir() {
  if (!workspaceId.value || !optimizationUnitId.value || optimizationResultIndex.value === null) return
  let artifactPath = detail.value?.artifact_path || null
  if (!artifactPath) {
    const artifact = await workspaceApi.getOptimizationResultArtifact(
      workspaceId.value,
      optimizationUnitId.value,
      optimizationResultIndex.value,
    )
    artifactPath = artifact.artifact_path
  }
  if (!artifactPath) {
    ElMessage.warning(t('backtest.artifactNotFound'))
    return
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(artifactPath)
    }
  } catch {
    // Silently ignore clipboard errors
  }
  window.open(`file://${encodeURI(artifactPath.replace(/\\/g, '/'))}`, '_blank', 'noopener')
  ElMessage.success(t('backtest.artifactOpened'))
}

async function handleDownloadArtifact() {
  if (!workspaceId.value || !optimizationUnitId.value || optimizationResultIndex.value === null) return
  await workspaceApi.downloadOptimizationResultArtifact(
    workspaceId.value,
    optimizationUnitId.value,
    optimizationResultIndex.value,
  )
}

function handleBack() {
  if (workspaceId.value) {
    router.push({
      name: 'BacktestWorkspaceDetail',
      params: { id: workspaceId.value },
    })
    return
  }
  router.push('/backtest/legacy')
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '--'
  return `${(value * 100).toFixed(2)}%`
}

function formatNumber(value: number | null | undefined, precision = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '--'
  return value.toFixed(precision)
}

function formatTime(iso: string): string {
  return iso ? new Date(iso).toLocaleString() : ''
}
</script>

<style scoped>
.backtest-result-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: var(--text-color-primary);
}

.backtest-result-state,
.backtest-result-error,
.backtest-result-hero,
.backtest-result-panel {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  box-shadow: 0 10px 28px var(--shadow-color);
}

.backtest-result-state,
.backtest-result-error {
  min-height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.backtest-result-state {
  gap: 10px;
  color: var(--text-color-secondary);
  font-size: 14px;
}

.backtest-result-loading {
  color: var(--primary-color);
  font-size: 28px;
}

.backtest-result-error {
  flex-direction: column;
  gap: 14px;
  padding: 28px;
  background: var(--fill-color-lighter);
  text-align: center;
}

.backtest-result-error-icon {
  color: var(--danger-color);
  font-size: 42px;
}

.backtest-result-error p {
  margin: 0;
  color: var(--text-color-regular);
  font-size: 14px;
}

.backtest-result-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  padding: 20px;
}

.backtest-result-copy {
  min-width: 0;
}

.backtest-result-kicker,
.backtest-result-panel-head span {
  display: inline-flex;
  margin-bottom: 6px;
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.backtest-result-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.backtest-result-title-row h1 {
  overflow: hidden;
  margin: 0;
  color: var(--text-color-primary);
  font-size: 26px;
  font-weight: 760;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.backtest-result-copy p {
  max-width: 820px;
  margin: 8px 0 0;
  color: var(--text-color-regular);
  font-size: 14px;
  line-height: 1.65;
}

.backtest-result-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 8px;
}

.backtest-result-actions :deep(.el-button) {
  gap: 6px;
}

.backtest-result-meta {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.backtest-result-metrics {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.backtest-result-metric {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.backtest-result-metric span {
  display: block;
  margin-bottom: 6px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.backtest-result-metric strong {
  display: block;
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1.15;
}

.backtest-result-metric--positive strong,
.is-positive {
  color: var(--success-color);
}

.backtest-result-metric--negative strong,
.backtest-result-metric--risk strong,
.is-negative {
  color: var(--danger-color);
}

.backtest-result-panel {
  padding: 18px;
}

.backtest-result-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.backtest-result-panel-head div {
  min-width: 0;
}

.backtest-result-panel-head h2 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 740;
  line-height: 1.25;
}

.backtest-result-panel-head p {
  flex: 0 1 460px;
  margin: 0;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.45;
  text-align: right;
}

.backtest-result-diagnostics-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.backtest-diagnostic-card--wide {
  grid-column: 1 / -1;
}

.backtest-chart-tabs {
  overflow: hidden;
  border-color: var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.backtest-chart-tabs :deep(.el-tabs__header) {
  border-color: var(--border-color-light);
  background: var(--fill-color-lighter);
}

.backtest-chart-tabs :deep(.el-tabs__content) {
  padding: 14px;
  background: var(--bg-color);
}

.backtest-chart-tabs :deep(.el-tabs__item) {
  color: var(--text-color-secondary);
}

.backtest-chart-tabs :deep(.el-tabs__item.is-active) {
  color: var(--primary-color);
  font-weight: 700;
}

.backtest-chart-surface {
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.backtest-drawdown-chart {
  margin-top: 14px;
}

.backtest-analysis-grid {
  display: grid;
  gap: 14px;
}

.backtest-annual-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
}

.backtest-annual-head h3 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 16px;
  font-weight: 720;
  line-height: 1.25;
}

.backtest-annual-head span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
  text-align: right;
}

.backtest-annual-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px;
  max-height: 220px;
  overflow-y: auto;
}

.backtest-annual-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  font-size: 13px;
}

.backtest-annual-item span {
  color: var(--text-color-regular);
  font-weight: 650;
}

.backtest-annual-item strong {
  white-space: nowrap;
}

.backtest-annual-empty {
  margin: 0;
  color: var(--text-color-secondary);
  font-size: 13px;
}

.backtest-result-page :deep(.el-card),
.backtest-result-page :deep(.metric-card) {
  border-color: var(--border-color);
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: none;
}

.backtest-result-page :deep(.el-card__header) {
  border-bottom-color: var(--border-color-light);
}

.backtest-result-page :deep(.bg-white),
.backtest-result-page :deep(.bg-gray-50),
.backtest-result-page :deep(.bg-blue-50),
.backtest-result-page :deep(.bg-indigo-50),
.backtest-result-page :deep(.bg-amber-50) {
  background: var(--fill-color-lighter) !important;
}

.backtest-result-page :deep(.border),
.backtest-result-page :deep(.border-gray-100),
.backtest-result-page :deep(.border-gray-200),
.backtest-result-page :deep(.border-blue-100),
.backtest-result-page :deep(.border-indigo-100),
.backtest-result-page :deep(.border-amber-200),
.backtest-result-page :deep(.border-white) {
  border-color: var(--border-color-light) !important;
}

.backtest-result-page :deep(.text-gray-900),
.backtest-result-page :deep(.text-gray-800),
.backtest-result-page :deep(.text-gray-700),
.backtest-result-page :deep(.text-blue-900),
.backtest-result-page :deep(.text-indigo-900),
.backtest-result-page :deep(.text-amber-900) {
  color: var(--text-color-primary) !important;
}

.backtest-result-page :deep(.text-gray-600),
.backtest-result-page :deep(.text-blue-800),
.backtest-result-page :deep(.text-indigo-700),
.backtest-result-page :deep(.text-amber-800) {
  color: var(--text-color-regular) !important;
}

.backtest-result-page :deep(.text-gray-500),
.backtest-result-page :deep(.text-gray-400),
.backtest-result-page :deep(.text-blue-700) {
  color: var(--text-color-secondary) !important;
}

.backtest-result-page :deep(.text-blue-600) {
  color: var(--primary-color) !important;
}

.backtest-result-page :deep(.text-green-600),
.backtest-result-page :deep(.text-green-500) {
  color: var(--success-color) !important;
}

.backtest-result-page :deep(.text-red-600),
.backtest-result-page :deep(.text-red-500) {
  color: var(--danger-color) !important;
}

.backtest-result-page :deep(.text-yellow-600),
.backtest-result-page :deep(.text-amber-600) {
  color: var(--warning-color) !important;
}

.backtest-result-page :deep(.el-table) {
  --el-table-header-bg-color: var(--fill-color-lighter);
  --el-table-tr-bg-color: var(--bg-color);
  --el-table-row-hover-bg-color: var(--fill-color-light);
  --el-table-border-color: var(--border-color-light);
  --el-table-text-color: var(--text-color-regular);
  --el-table-header-text-color: var(--text-color-secondary);
}

.backtest-trades-surface {
  overflow-x: auto;
}

@media (max-width: 1180px) {
  .backtest-result-hero,
  .backtest-result-diagnostics-grid {
    grid-template-columns: 1fr;
  }

  .backtest-result-actions {
    justify-content: flex-start;
  }

  .backtest-result-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .backtest-diagnostic-card--wide {
    grid-column: auto;
  }
}

@media (max-width: 700px) {
  .backtest-result-page {
    gap: 14px;
  }

  .backtest-result-hero,
  .backtest-result-panel {
    padding: 14px;
  }

  .backtest-result-title-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .backtest-result-title-row h1 {
    font-size: 22px;
    white-space: normal;
  }

  .backtest-result-actions :deep(.el-button) {
    width: 100%;
    justify-content: center;
  }

  .backtest-result-metrics {
    grid-template-columns: 1fr;
  }

  .backtest-result-panel-head,
  .backtest-annual-head {
    flex-direction: column;
  }

  .backtest-result-panel-head p,
  .backtest-annual-head span {
    max-width: none;
    text-align: left;
  }

  .backtest-chart-tabs :deep(.el-tabs__content) {
    padding: 10px;
  }

  .backtest-chart-surface {
    padding: 10px;
  }
}
</style>
