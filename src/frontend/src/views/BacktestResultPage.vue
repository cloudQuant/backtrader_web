<template>
  <div class="backtest-result-page">
    <!-- Loading state -->
    <div
      v-if="loading && !backtestSummary"
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

    <!-- Compact response is intentionally rendered before delayed full detail. -->
    <section
      v-else-if="backtestSummary && !detail"
      class="backtest-result-hero backtest-result-summary-first"
      data-test="backtest-summary-first"
      aria-live="polite"
    >
      <div class="backtest-result-copy">
        <span class="backtest-result-kicker">{{ t('backtest.resultHeroKicker') }}</span>
        <div class="backtest-result-title-row">
          <h1 id="backtest-result-title">{{ strategyNameFromQuery || backtestSummary.strategy_id }}</h1>
          <el-tag effect="plain">{{ backtestSummary.symbol }}</el-tag>
        </div>
        <p>{{ error || '正在加载完整回测明细…' }}</p>
      </div>
      <div class="backtest-result-metrics">
        <article
          v-for="metric in resultSummaryCards"
          :key="metric.label"
          class="backtest-result-metric"
        >
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
        </article>
      </div>
      <div class="backtest-summary-first-actions">
        <el-button v-if="error" @click="loadData">{{ t('backtest.retry') }}</el-button>
        <span v-else class="backtest-summary-first-loading">{{ t('common.loading') }}</span>
      </div>
    </section>

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
      <el-button
        :aria-label="t('common.back')"
        @click="handleBack"
      >
        {{ t('common.back') }}
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

      <ResearchWorkflowGuide
        v-if="!isOptimizationArtifactMode"
        data-test="backtest-workflow-guide"
        :kicker="t('workspace.flowKicker')"
        :title="t('workspace.flowTitle')"
        :steps="backtestWorkflowSteps"
        :complete-label="t('workspace.flowStateComplete')"
        :current-label="t('workspace.flowStateCurrent')"
        :upcoming-label="t('workspace.flowStateUpcoming')"
        :attention-label="t('workspace.flowStateAttention')"
        @action="handleWorkflowAction"
      />

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

      <button
        v-if="hasDiagnostics"
        type="button"
        class="backtest-mobile-diagnostics-trigger"
        data-test="backtest-open-diagnostics"
        :aria-expanded="mobileDiagnosticsOpen"
        aria-haspopup="dialog"
        @click="openMobileDiagnostics($event)"
      >
        {{ t('backtest.openDiagnostics') }}
      </button>

      <section
        v-if="hasDiagnostics"
        ref="diagnosticsPanel"
        class="backtest-result-panel backtest-result-panel--diagnostics"
        :class="{ 'backtest-result-panel--mobile-open': mobileDiagnosticsOpen }"
        :role="mobileDiagnosticsOpen ? 'dialog' : undefined"
        :aria-modal="mobileDiagnosticsOpen ? 'true' : undefined"
        :aria-label="mobileDiagnosticsOpen ? t('backtest.diagnosticsTitle') : undefined"
        @keydown="handleMobileDiagnosticsKeydown"
      >
        <header class="backtest-result-panel-head">
          <div>
            <span>{{ t('backtest.diagnosticsKicker') }}</span>
            <h2>{{ t('backtest.diagnosticsTitle') }}</h2>
          </div>
          <p>{{ t('backtest.diagnosticsSubtitle') }}</p>
          <button
            v-if="mobileDiagnosticsOpen"
            ref="diagnosticsPanelClose"
            type="button"
            class="backtest-mobile-diagnostics-close"
            :aria-label="t('backtest.closeDiagnostics')"
            @click="closeMobileDiagnostics"
          >
            <el-icon aria-hidden="true">
              <Close />
            </el-icon>
          </button>
        </header>

        <div class="backtest-result-diagnostics-grid">
          <article
            v-if="resultSummaryCards.length || dataPrecheckSnapshot"
            class="backtest-diagnostic-card backtest-trust-card"
            data-test="backtest-trust-summary"
          >
            <div class="backtest-trust-card-head">
              <div>
                <span>{{ t('backtest.trustSummary') }}</span>
                <strong>{{ t('backtest.precheckAndMetrics') }}</strong>
              </div>
              <el-tag
                size="small"
                :type="dataPrecheckTagType"
              >
                {{ dataPrecheckStatusLabel }}
              </el-tag>
            </div>
            <div
              v-if="resultSummaryCards.length"
              class="backtest-trust-summary-grid"
            >
              <div
                v-for="item in resultSummaryCards"
                :key="item.label"
              >
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
            <div
              v-if="dataPrecheckMessages.length"
              class="backtest-trust-message-list"
            >
              <p
                v-for="message in dataPrecheckMessages"
                :key="message"
              >
                {{ message }}
              </p>
            </div>
          </article>

          <article
            v-if="!isOptimizationArtifactMode"
            class="backtest-diagnostic-card backtest-robustness-card"
            data-test="backtest-robustness-panel"
          >
            <div class="backtest-robustness-head">
              <div>
                <span>{{ t('backtest.robustnessValidation') }}</span>
                <strong>{{ robustnessTitle }}</strong>
              </div>
              <el-tag
                size="small"
                :type="robustnessStatusTagType"
              >
                {{ robustnessStatusLabel }}
              </el-tag>
            </div>
            <div class="backtest-robustness-score">
              <span>{{ t('backtest.robustnessScore') }}</span>
              <strong>{{ robustnessScoreText }}</strong>
            </div>
            <div
              v-if="robustnessGateRows.length"
              class="backtest-robustness-gates"
            >
              <div
                v-for="gate in robustnessGateRows"
                :key="gate.key"
              >
                <span>{{ gate.label }}</span>
                <el-tag
                  size="small"
                  :type="gate.passed ? 'success' : 'danger'"
                >
                  {{ gate.passed ? t('backtest.passed') : t('backtest.notPassed') }}
                </el-tag>
              </div>
            </div>
            <p
              v-if="robustnessSnapshot?.error_message"
              class="backtest-robustness-error"
            >
              {{ robustnessSnapshot.error_message }}
            </p>
            <div class="backtest-robustness-actions">
              <el-button
                size="small"
                type="primary"
                plain
                :loading="robustnessLoading"
                data-test="run-robustness-validation"
                @click="runRobustnessValidation"
              >
                {{ t('backtest.runRobustnessValidation') }}
              </el-button>
            </div>
          </article>

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

      <button
        v-if="mobileDiagnosticsOpen"
        type="button"
        class="backtest-mobile-diagnostics-backdrop"
        tabindex="-1"
        :aria-label="t('backtest.closeDiagnostics')"
        @click="closeMobileDiagnostics"
      />

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
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading, CircleCloseFilled, Download, Back, Close, FolderOpened } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { getErrorMessage } from '@/api'
import ResearchWorkflowGuide from '@/components/research/ResearchWorkflowGuide.vue'
import { APP_PATHS } from '@/navigation/routes'
import type { ResearchWorkflowStep } from '@/types/researchWorkflow'
import { analyticsApi } from '@/api/analytics'
import { backtestApi } from '@/api/backtest'
import { strategyApi } from '@/api/strategy'
import type {
  StrategyExplanation,
  StrategyOverfittingMethod,
  StrategyOverfittingTaskResult,
  StrategyScoreResponse,
} from '@/api/strategy'
import type { BacktestSummaryResponse } from '@/types'
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
import type {
  DataPrecheckResponse,
  QualityGateEvaluation,
  RobustnessTestResultResponse,
} from '@/types/trust'

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
const mobileDiagnosticsOpen = ref(false)
const diagnosticsPanel = ref<HTMLElement | null>(null)
const diagnosticsPanelClose = ref<HTMLButtonElement | null>(null)
let diagnosticsPanelTrigger: HTMLElement | null = null

const detail = ref<BacktestDetailResponse | null>(null)
const klineData = ref<KlineWithSignalsResponse | null>(null)
const monthlyReturns = ref<MonthlyReturnsResponse | null>(null)
const strategyScore = ref<StrategyScoreResponse | null>(null)
const strategyExplanation = ref<StrategyExplanation | null>(null)
const overfittingTask = ref<StrategyOverfittingTaskResult | null>(null)
const backtestSummary = ref<BacktestSummaryResponse | null>(null)
const robustnessResult = ref<RobustnessTestResultResponse | null>(null)
const robustnessLoading = ref(false)

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
    cancelled: t('backtest.cancelled'),
    running: t('backtest.running'),
    pending: t('backtest.pending'),
  }
  return map[status] || status
})

const statusTagType = computed(() => {
  const status = detail.value?.artifact_status || 'completed'
  if (status === 'failed' || status === 'error' || status === 'cancelled') return 'danger'
  if (status === 'running' || status === 'pending') return 'warning'
  return 'success'
})

const backtestWorkflowSteps = computed<ResearchWorkflowStep[]>(() => {
  const status = detail.value?.artifact_status || 'completed'
  const runState = status === 'completed'
    ? 'complete'
    : status === 'failed' || status === 'error' || status === 'cancelled'
      ? 'attention'
      : 'current'
  const reviewState = runState === 'complete' ? 'current' : 'upcoming'

  return [
    {
      id: 'workspace',
      label: t('workspace.flowCreateTitle'),
      description: t('workspace.flowCreateDesc'),
      state: 'complete',
    },
    {
      id: 'configure',
      label: t('workspace.flowConfigureTitle'),
      description: t('workspace.flowConfigureDesc'),
      state: 'complete',
    },
    {
      id: 'backtest',
      label: t('workspace.flowBacktestTitle'),
      description: status === 'completed'
        ? t('workspace.flowBacktestDesc')
        : detail.value?.artifact_error || t('workspace.flowBacktestDesc'),
      state: runState,
      action: runState === 'attention' ? 'return-to-workspace' : undefined,
      actionLabel: runState === 'attention' ? t('common.back') : undefined,
    },
    {
      id: 'review',
      label: t('workspace.flowReviewTitle'),
      description: t('workspace.flowReviewDesc'),
      state: reviewState,
      action: reviewState === 'current' ? 'return-to-workspace' : undefined,
      actionLabel: reviewState === 'current' ? t('common.back') : undefined,
    },
  ]
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

const resultSummarySnapshot = computed(() => (
  backtestSummary.value
      ? {
        strategy_id: backtestSummary.value.strategy_id,
        symbol: backtestSummary.value.symbol,
        ...backtestSummary.value.metrics,
      }
    : detail.value?.result_summary
      ?? {}
))

const dataPrecheckSnapshot = computed<DataPrecheckResponse | null>(() => (
  backtestSummary.value?.data_precheck
  ?? detail.value?.data_precheck
  ?? null
))

const robustnessSnapshot = computed<RobustnessTestResultResponse | null>(() => (
  robustnessResult.value
  ?? (backtestSummary.value?.robustness as RobustnessTestResultResponse | null)
  ?? detail.value?.robustness
  ?? null
))

const resultSummaryCards = computed(() => {
  const summary = resultSummarySnapshot.value
  const rows = [
    summaryMetric('策略', summary.strategy_id),
    summaryMetric('标的', summary.symbol),
    summaryMetric('交易', summary.total_trades),
    summaryMetric('Sharpe', summary.sharpe_ratio, 2),
    summaryMetric('收益', summary.total_return, 2),
    summaryMetric('回撤', summary.max_drawdown, 2),
  ]
  return rows.filter((item) => item.value !== '-')
})

const dataPrecheckTagType = computed(() => {
  const status = dataPrecheckSnapshot.value?.status
  if (status === 'pass') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'warning') return 'warning'
  return 'info'
})

const dataPrecheckStatusLabel = computed(() => {
  const status = dataPrecheckSnapshot.value?.status || 'unknown'
  const labels: Record<string, string> = {
    pass: '预检通过',
    warning: '存在告警',
    failed: '预检失败',
    unknown: '未预检',
  }
  return labels[status] || status
})

const dataPrecheckMessages = computed(() => {
  const snapshot = dataPrecheckSnapshot.value
  if (!snapshot) return []
  return [...(snapshot.reasons || []), ...(snapshot.warnings || [])].slice(0, 4)
})

const robustnessTitle = computed(() => {
  const snapshot = robustnessSnapshot.value
  if (!snapshot) return '尚未运行'
  return snapshot.method || 'overfitting_suite'
})

const robustnessStatusTagType = computed(() => {
  const status = robustnessSnapshot.value?.status
  if (status === 'passed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running' || robustnessLoading.value) return 'warning'
  return 'info'
})

const robustnessStatusLabel = computed(() => {
  if (robustnessLoading.value) return '运行中'
  const status = robustnessSnapshot.value?.status || 'pending'
  const labels: Record<string, string> = {
    passed: '已通过',
    failed: '未通过',
    running: '运行中',
    pending: '未验证',
  }
  return labels[status] || status
})

const robustnessScoreText = computed(() => {
  const score = numericFromRecord(robustnessSnapshot.value?.metrics, 'robustness_score')
  return score === null ? '-' : formatNumber(score, 1)
})

const robustnessGateRows = computed<QualityGateEvaluation[]>(() => (
  robustnessSnapshot.value?.gate_evaluations || []
))

const hasDiagnostics = computed(() => (
  Boolean(
    strategyScore.value
      || !isOptimizationArtifactMode.value
      || overfittingTask.value
      || overfittingLoading.value
      || strategyExplanation.value
      || resultSummaryCards.value.length
      || dataPrecheckSnapshot.value
      || robustnessSnapshot.value
      || robustnessLoading.value,
  )
))

async function openMobileDiagnostics(event: MouseEvent) {
  diagnosticsPanelTrigger = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  mobileDiagnosticsOpen.value = true
  await nextTick()
  diagnosticsPanelClose.value?.focus()
}

function closeMobileDiagnostics() {
  mobileDiagnosticsOpen.value = false
  void nextTick(() => diagnosticsPanelTrigger?.focus())
}

function handleMobileDiagnosticsKeydown(event: KeyboardEvent) {
  if (!mobileDiagnosticsOpen.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closeMobileDiagnostics()
    return
  }
  if (event.key !== 'Tab') return

  const focusable = diagnosticsPanel.value
    ? Array.from(diagnosticsPanel.value.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ))
    : []
  if (focusable.length === 0) return

  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

async function loadData() {
  stopOverfittingRuntime()
  loading.value = true
  error.value = null
  strategyScore.value = null
  strategyExplanation.value = null
  overfittingTask.value = null
  backtestSummary.value = null
  robustnessResult.value = null
  klineData.value = null
  monthlyReturns.value = null

  const summaryRequest = isOptimizationArtifactMode.value
    ? Promise.resolve()
    : loadBacktestTrustSnapshot()

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
    await summaryRequest
  }
}

async function loadBacktestTrustSnapshot() {
  try {
    backtestSummary.value = await backtestApi.getSummary(taskId.value)
  } catch {
    backtestSummary.value = null
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

async function runRobustnessValidation() {
  robustnessLoading.value = true
  try {
    robustnessResult.value = await backtestApi.runRobustness(taskId.value, {
      methods: ['monte_carlo'],
      monte_carlo_iterations: 300,
      min_robustness_score: 55,
      require_no_high_risk: true,
    })
    ElMessage.success(t('backtest.robustnessValidationCompleted'))
  } catch {
    robustnessResult.value = null
    ElMessage.error(t('backtest.robustnessValidationFailed'))
  } finally {
    robustnessLoading.value = false
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
  router.push(APP_PATHS.backtest.list)
}

function handleWorkflowAction(action: string) {
  if (action === 'return-to-workspace') {
    handleBack()
  }
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '--'
  return `${(value * 100).toFixed(2)}%`
}

function formatNumber(value: number | null | undefined, precision = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '--'
  return value.toFixed(precision)
}

function summaryMetric(label: string, value: unknown, precision = 0) {
  const numeric = typeof value === 'number' ? value : null
  return {
    label,
    value: numeric === null ? String(value || '-') : formatNumber(numeric, precision),
  }
}

function numericFromRecord(payload: Record<string, unknown> | undefined, key: string) {
  const value = payload?.[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
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

.backtest-summary-first-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  color: var(--text-color-secondary);
  font-size: 13px;
}

.backtest-summary-first-loading {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
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

.backtest-mobile-diagnostics-trigger,
.backtest-mobile-diagnostics-close,
.backtest-mobile-diagnostics-backdrop {
  display: none;
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

.backtest-trust-card,
.backtest-robustness-card {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.backtest-trust-card-head,
.backtest-robustness-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.backtest-trust-card-head > div,
.backtest-robustness-head > div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.backtest-trust-card-head span,
.backtest-robustness-head span,
.backtest-robustness-score span,
.backtest-trust-summary-grid span,
.backtest-robustness-gates span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
}

.backtest-trust-card-head strong,
.backtest-robustness-head strong {
  color: var(--text-color-primary);
  font-size: 15px;
  line-height: 1.3;
}

.backtest-trust-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.backtest-trust-summary-grid > div {
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.backtest-trust-summary-grid strong {
  display: block;
  margin-top: 4px;
  color: var(--text-color-primary);
  font-size: 14px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.backtest-trust-message-list {
  display: grid;
  gap: 6px;
}

.backtest-trust-message-list p,
.backtest-robustness-error {
  margin: 0;
  color: var(--text-color-regular);
  font-size: 12px;
  line-height: 1.45;
}

.backtest-robustness-score {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.backtest-robustness-score strong {
  color: var(--primary-color);
  font-size: 26px;
  line-height: 1.1;
}

.backtest-robustness-gates {
  display: grid;
  gap: 8px;
}

.backtest-robustness-gates > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.backtest-robustness-actions {
  display: flex;
  justify-content: flex-end;
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

  .backtest-trust-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
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

  .backtest-mobile-diagnostics-trigger {
    display: inline-flex;
    width: 100%;
    align-items: center;
    justify-content: center;
    min-height: 44px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-color);
    color: var(--text-color-regular);
    font-weight: 700;
    cursor: pointer;
  }

  .backtest-result-panel--diagnostics {
    display: none;
  }

  .backtest-result-panel--diagnostics.backtest-result-panel--mobile-open {
    position: fixed;
    z-index: 1001;
    top: max(12px, env(safe-area-inset-top));
    right: max(12px, env(safe-area-inset-right));
    bottom: max(12px, env(safe-area-inset-bottom));
    display: block;
    width: min(560px, calc(100vw - 24px));
    overflow-y: auto;
    background: var(--bg-color);
    box-shadow: var(--shadow-lg, 0 10px 28px var(--shadow-color));
    overscroll-behavior: contain;
  }

  .backtest-mobile-diagnostics-close {
    display: inline-flex;
    width: 32px;
    height: 32px;
    align-items: center;
    justify-content: center;
    align-self: flex-end;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-color);
    color: var(--text-color-regular);
    cursor: pointer;
  }

  .backtest-mobile-diagnostics-backdrop {
    position: fixed;
    z-index: 1000;
    inset: 0;
    display: block;
    width: 100%;
    height: 100%;
    border: 0;
    background: color-mix(in srgb, var(--text-color-primary) 34%, transparent);
    cursor: default;
  }

  .backtest-trust-card-head,
  .backtest-robustness-head,
  .backtest-robustness-score,
  .backtest-robustness-gates > div {
    align-items: flex-start;
    flex-direction: column;
  }

  .backtest-trust-summary-grid {
    grid-template-columns: 1fr;
  }

  .backtest-robustness-actions :deep(.el-button) {
    width: 100%;
    justify-content: center;
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
