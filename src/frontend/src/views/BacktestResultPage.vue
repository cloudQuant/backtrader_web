<template>
  <div class="backtest-result-page p-6">
    <!-- Loading state -->
    <div
      v-if="loading"
      class="flex justify-center items-center h-64"
      role="status"
      :aria-label="t('common.loading')"
    >
      <el-icon
        class="is-loading text-4xl text-blue-500"
        aria-hidden="true"
      >
        <Loading />
      </el-icon>
    </div>

    <!-- Error state -->
    <div
      v-else-if="error"
      class="text-center py-12"
      role="alert"
    >
      <el-icon
        class="text-5xl text-red-400 mb-4"
        aria-hidden="true"
      >
        <CircleCloseFilled />
      </el-icon>
      <p class="text-gray-500">
        {{ error }}
      </p>
      <el-button
        class="mt-4"
        :aria-label="t('backtest.retry')"
        @click="loadData"
      >
        {{ t('backtest.retry') }}
      </el-button>
    </div>
    
    <!-- Content -->
    <template v-else-if="detail">
      <!-- Header title and actions -->
      <div
        class="flex justify-between items-center mb-6"
        data-test="backtest-detail"
      >
        <div>
          <h2 class="text-2xl font-bold">
            {{ t('backtest.results') }}
          </h2>
          <p class="text-gray-500 mt-1">
            {{ detail.strategy_name }} | {{ detail.symbol }} |
            {{ detail.start_date }} - {{ detail.end_date }}
          </p>
          <span
            data-test="backtest-status"
            class="sr-only"
          >{{ detail.artifact_status || 'completed' }}</span>
        </div>
        <div class="flex gap-2">
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
      </div>
      
      <!-- Performance metrics panel -->
      <el-card class="mb-6">
        <PerformancePanel :metrics="detail.metrics" />
      </el-card>

      <StrategyScoreCard
        v-if="strategyScore"
        :score="strategyScore"
        class="mb-6"
      />

      <OverfittingPanel
        v-if="overfittingTask || overfittingLoading"
        :result="overfittingTask"
        :loading="overfittingLoading"
        :progress-message="overfittingProgressInfo.message"
        class="mb-6"
        @rerun="loadOverfitting"
      />

      <StrategyExplanationCard
        v-if="strategyExplanation"
        :explanation="strategyExplanation"
        class="mb-6"
      />
      
      <!-- Charts area -->
      <el-tabs
        v-model="activeTab"
        class="mb-6"
      >
        <el-tab-pane
          :label="t('backtest.chartKline')"
          name="kline"
        >
          <el-card>
            <TradeSignalChart
              :klines="klineData?.klines || []"
              :signals="klineData?.signals || []"
              :indicators="klineData?.indicators"
              :height="550"
            />
          </el-card>
        </el-tab-pane>
        
        <el-tab-pane
          :label="t('backtest.chartEquity')"
          name="equity"
        >
          <el-card v-if="activeTab === 'equity'">
            <EquityCurve
              data-test="equity-curve"
              :data="detail.equity_curve"
              :height="350"
            />
            <DrawdownChart
              :data="detail.drawdown_curve"
              :height="180"
              class="mt-4"
            />
          </el-card>
        </el-tab-pane>
        
        <el-tab-pane
          :label="t('backtest.chartAnalysis')"
          name="analysis"
        >
          <div
            v-if="activeTab === 'analysis'"
            class="space-y-4"
          >
            <el-card>
              <ReturnHeatmap
                :returns="monthlyReturns?.returns || []"
                :years="monthlyReturns?.years || []"
                :height="300"
              />
            </el-card>
            <el-card>
              <div class="p-4">
                <h4 class="text-md font-medium mb-3">
                  {{ t('backtest.annualSummary') }}
                </h4>
                <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2 max-h-48 overflow-y-auto">
                  <div 
                    v-for="(ret, year) in monthlyReturns?.summary" 
                    :key="year"
                    class="flex justify-between items-center px-3 py-2 bg-gray-50 rounded text-sm"
                  >
                    <span class="font-medium mr-2">{{ year }}</span>
                    <span
                      :class="ret >= 0 ? 'text-green-600' : 'text-red-600'"
                      class="whitespace-nowrap"
                    >
                      {{ ret >= 0 ? '+' : '' }}{{ (ret * 100).toFixed(2) }}%
                    </span>
                  </div>
                </div>
              </div>
            </el-card>
          </div>
        </el-tab-pane>
        
        <el-tab-pane
          :label="t('backtest.chartTrades')"
          name="trades"
        >
          <el-card>
            <TradeRecordsTable :trades="detail.trades" />
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
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
const activeTab = ref('kline')

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

async function loadData() {
  stopOverfittingRuntime()
  loading.value = true
  error.value = null
  strategyScore.value = null
  strategyExplanation.value = null
  overfittingTask.value = null
  
  try {
    let detailRes: BacktestDetailResponse
    let klineRes: KlineWithSignalsResponse
    let returnsRes: MonthlyReturnsResponse
    let scoreRes: StrategyScoreResponse | null = null
    let explanationRes: StrategyExplanation | null = null

    if (isOptimizationArtifactMode.value && workspaceId.value && optimizationUnitId.value && optimizationResultIndex.value !== null) {
      [detailRes, klineRes, returnsRes] = await Promise.all([
        workspaceApi.getOptimizationResultDetail(workspaceId.value, optimizationUnitId.value, optimizationResultIndex.value),
        workspaceApi.getOptimizationResultKline(workspaceId.value, optimizationUnitId.value, optimizationResultIndex.value),
        workspaceApi.getOptimizationResultMonthlyReturns(workspaceId.value, optimizationUnitId.value, optimizationResultIndex.value),
      ])
    } else {
      [detailRes, klineRes, returnsRes, scoreRes, explanationRes] = await Promise.all([
        analyticsApi.getBacktestDetail(taskId.value),
        analyticsApi.getKlineWithSignals(taskId.value),
        analyticsApi.getMonthlyReturns(taskId.value),
        strategyApi.createScore({ backtest_id: taskId.value }).catch(() => null),
        strategyApi.explainStrategy({ backtest_id: taskId.value }).catch(() => null),
      ])
    }
    
    detail.value = detailRes
    klineData.value = klineRes
    monthlyReturns.value = returnsRes
    strategyScore.value = scoreRes
    strategyExplanation.value = explanationRes

    if (!isOptimizationArtifactMode.value) {
      void loadOverfitting()
    }
    
  } catch (e: unknown) {
    error.value = getErrorMessage(e, t('backtest.loadFailed'))
  } finally {
    loading.value = false
  }
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

</script>
