<template>
  <div class="backtest-launch-page">
    <section
      class="backtest-launch-hero"
      aria-labelledby="backtest-launch-title"
      data-test="backtest-legacy-page"
    >
      <div class="backtest-launch-copy">
        <span class="backtest-launch-kicker">{{ t('backtestPg.heroKicker') }}</span>
        <h1 id="backtest-launch-title">
          {{ t('backtestPg.heroTitle') }}
        </h1>
        <p>{{ t('backtestPg.heroSubtitle') }}</p>
      </div>

      <div class="backtest-launch-actions">
        <el-button
          type="primary"
          :loading="loading"
          :disabled="configLoading"
          :aria-label="t('backtestPg.btnRun')"
          @click="runBacktest"
        >
          <el-icon aria-hidden="true">
            <VideoPlay />
          </el-icon>
          {{ t('backtestPg.btnRun') }}
        </el-button>
        <el-button
          v-if="loading && currentTaskId"
          type="danger"
          :aria-label="t('backtestPg.btnCancel')"
          @click="cancelBacktest"
        >
          <el-icon aria-hidden="true">
            <Close />
          </el-icon>
          {{ t('backtestPg.btnCancel') }}
        </el-button>
      </div>

      <div class="backtest-launch-stats">
        <article
          v-for="stat in heroStats"
          :key="stat.key"
          class="backtest-launch-stat"
        >
          <span>{{ stat.label }}</span>
          <strong>{{ stat.value }}</strong>
        </article>
      </div>
    </section>

    <section class="backtest-launch-workbench">
      <div class="backtest-launch-panel backtest-launch-config">
        <header class="backtest-launch-panel-head">
          <div>
            <span>{{ t('backtestPg.panelKicker') }}</span>
            <h2>{{ t('backtestPg.panelTitle') }}</h2>
          </div>
          <p>{{ t('backtestPg.panelSubtitle') }}</p>
        </header>

        <el-form
          :model="form"
          label-position="top"
          class="backtest-launch-form"
        >
          <section class="backtest-form-section">
            <div class="backtest-form-section-title">
              <el-icon aria-hidden="true">
                <Document />
              </el-icon>
              <span>{{ t('backtestPg.formSectionStrategy') }}</span>
            </div>

            <el-form-item :label="t('backtestPg.formStrategy')">
              <el-select
                v-model="form.strategy_id"
                :placeholder="t('backtestPg.formStrategyPlaceholder')"
                class="backtest-field"
                filterable
                @change="onStrategyChange"
              >
                <el-option
                  v-for="template in templates"
                  :key="template.id"
                  :label="template.name"
                  :value="template.id"
                />
              </el-select>
            </el-form-item>

            <div
              v-if="strategyConfig"
              class="backtest-strategy-note"
            >
              <span>{{ t('backtestPg.formStrategyDesc') }}</span>
              <p>
                {{ strategyConfig.strategy.description || t('backtestPg.noStrategyDescription') }}
                <em v-if="strategyConfig.strategy.author">
                  {{ strategyConfig.strategy.author }}
                </em>
              </p>
            </div>
          </section>

          <section class="backtest-form-section">
            <div class="backtest-form-section-title">
              <el-icon aria-hidden="true">
                <Setting />
              </el-icon>
              <span>{{ t('backtestPg.paramsDivider') }}</span>
            </div>

            <div
              v-if="paramEntries.length"
              class="backtest-param-grid"
            >
              <el-form-item
                v-for="[key, val] in paramEntries"
                :key="key"
                :label="String(key)"
              >
                <el-input-number
                  v-if="typeof val === 'number'"
                  v-model="dynamicParams[key]"
                  :step="Number.isInteger(val) ? 1 : 0.01"
                  :precision="Number.isInteger(val) ? 0 : 4"
                  class="backtest-field"
                />
                <el-input
                  v-else
                  v-model="dynamicParams[key]"
                  class="backtest-field"
                />
              </el-form-item>
            </div>
            <div
              v-else
              class="backtest-param-empty"
            >
              {{ t('backtestPg.paramEmpty') }}
            </div>
          </section>
        </el-form>
      </div>

      <aside class="backtest-launch-side">
        <section class="backtest-launch-panel">
          <header class="backtest-side-head">
            <span>{{ t('backtestPg.configSummaryTitle') }}</span>
            <p>{{ t('backtestPg.configSummarySubtitle') }}</p>
          </header>
          <dl class="backtest-summary-list">
            <div>
              <dt>{{ t('backtestPg.selectedStrategy') }}</dt>
              <dd>{{ selectedStrategyName }}</dd>
            </div>
            <div>
              <dt>{{ t('backtestPg.selectedSymbol') }}</dt>
              <dd>{{ selectedSymbol }}</dd>
            </div>
            <div>
              <dt>{{ t('backtestPg.initialCash') }}</dt>
              <dd>{{ initialCashDisplay }}</dd>
            </div>
            <div>
              <dt>{{ t('backtestPg.commission') }}</dt>
              <dd>{{ commissionDisplay }}</dd>
            </div>
            <div>
              <dt>{{ t('backtestPg.paramsCount') }}</dt>
              <dd>{{ paramEntries.length }}</dd>
            </div>
            <div>
              <dt>{{ t('backtestPg.lookbackWindow') }}</dt>
              <dd>{{ t('backtestPg.lookbackWindowValue') }}</dd>
            </div>
          </dl>
        </section>

        <section
          v-if="loading"
          class="backtest-launch-panel backtest-progress-panel"
          role="status"
          :aria-label="t('backtestPg.progressTitle')"
        >
          <div class="backtest-progress-head">
            <span>{{ t('backtestPg.progressTitle') }}</span>
            <strong>{{ progressInfo.progress }}%</strong>
          </div>
          <p>{{ progressInfo.message || t('backtestPg.progressIdle') }}</p>
          <el-progress
            :percentage="progressInfo.progress"
            :status="progressInfo.progress >= 100 ? 'success' : undefined"
          />
        </section>

        <section
          v-if="latestResult"
          class="backtest-launch-panel backtest-latest-panel"
        >
          <header class="backtest-side-head">
            <span>{{ t('backtestPg.latestResult') }}</span>
            <p>{{ formatDate(latestResult.created_at) }}</p>
          </header>
          <div class="backtest-latest-metrics">
            <span>{{ latestResult.symbol || '--' }}</span>
            <strong :class="resultToneClass(latestResult.total_return)">
              {{ formatPercent(latestResult.total_return) }}
            </strong>
          </div>
          <el-button
            class="backtest-latest-action"
            :disabled="!latestResult"
            @click="viewResult(latestResult)"
          >
            <el-icon aria-hidden="true">
              <TrendCharts />
            </el-icon>
            {{ t('backtestPg.analysisAction') }}
          </el-button>
        </section>
      </aside>
    </section>

    <BacktestMetricsPanel
      v-if="currentResult"
      :result="currentResult"
    />

    <section
      v-if="results.length > 0"
      class="backtest-analysis-panel"
    >
      <div>
        <span>{{ t('backtestPg.sectionAnalysisTitle') }}</span>
        <p>{{ t('backtestPg.analysisTip') }}</p>
      </div>
      <el-button
        v-if="latestResult"
        @click="viewResult(latestResult)"
      >
        <el-icon aria-hidden="true">
          <TrendCharts />
        </el-icon>
        {{ t('backtestPg.analysisAction') }}
      </el-button>
    </section>

    <BacktestHistoryTable
      :results="results"
      :templates="templates"
      :strategies="strategies"
      :loading="backtestStore.loading"
      @view="viewResult"
      @delete="deleteBacktest"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, Document, Setting, TrendCharts, VideoPlay } from '@element-plus/icons-vue'
import { getErrorMessage } from '@/api/index'
import { useBacktestStore } from '@/stores/backtest'
import { useStrategyStore } from '@/stores/strategy'
import { strategyApi } from '@/api/strategy'
import BacktestMetricsPanel from '@/components/backtest/BacktestMetricsPanel.vue'
import BacktestHistoryTable from '@/components/backtest/BacktestHistoryTable.vue'
import { useBacktestRuntime } from '@/composables/useBacktestRuntime'
import type { BacktestResult, StrategyConfig } from '@/types'
import dayjs from 'dayjs'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const backtestStore = useBacktestStore()
const strategyStore = useStrategyStore()

const configLoading = ref(false)
const currentResult = ref<BacktestResult | null>(null)
const strategyConfig = ref<StrategyConfig | null>(null)
const dynamicParams = reactive<Record<string, number | string>>({})

const {
  loading,
  currentTaskId,
  progressInfo,
  cancelBacktest,
  closeWebSocket,
  connectWebSocket,
  disposeRuntime,
  startRuntime,
  stopRuntime,
} = useBacktestRuntime({
  currentResult,
  fetchResult: (taskId) => backtestStore.fetchResult(taskId),
  refreshResults: () => backtestStore.fetchResults(),
})

defineExpose({
  closeWebSocket,
  connectWebSocket,
})

const form = reactive({
  strategy_id: '',
})

function hasAxiosResponse(e: unknown): e is { response: unknown } {
  return !!e && typeof e === 'object' && 'response' in e
}

function showRequestMessage(
  e: unknown,
  fallback: string,
  level: 'error' | 'warning' = 'error'
): void {
  // error 场景：全局响应拦截器已处理 Axios 错误，此处不重复显示
  if (level === 'error' && hasAxiosResponse(e)) {
    return
  }

  // warning 场景：全局拦截器只显示 error，此处需要单独处理 warning
  // 提取实际错误消息显示，而非只显示 fallback
  const message = getErrorMessage(e, fallback)
  if (level === 'warning') {
    ElMessage.warning(message)
    return
  }
  ElMessage.error(message)
}

async function onStrategyChange(strategyId: string) {
  if (!strategyId) {
    strategyConfig.value = null
    return
  }
  configLoading.value = true
  try {
    const config = await strategyApi.getTemplateConfig(strategyId)
    strategyConfig.value = config

    // 填充策略参数（仅 params 段）
    Object.keys(dynamicParams).forEach(k => delete dynamicParams[k])
    if (config.params) {
      Object.entries(config.params).forEach(([k, v]) => {
        dynamicParams[k] = v
      })
    }
  } catch (e: unknown) {
    showRequestMessage(e, t('backtestPg.msgConfigLoadFail'), 'warning')
    strategyConfig.value = null
  } finally {
    configLoading.value = false
  }
}

const strategies = computed(() => strategyStore.strategies)
const templates = computed(() => strategyStore.templates)
const results = computed(() => backtestStore.results)
const paramEntries = computed(() => Object.entries(dynamicParams))
const selectedTemplate = computed(() => templates.value.find(item => item.id === form.strategy_id) ?? null)
const latestResult = computed(() => results.value[0] ?? null)
const selectedStrategyName = computed(() => {
  if (selectedTemplate.value?.name) return selectedTemplate.value.name
  if (strategyConfig.value?.strategy?.name) return strategyConfig.value.strategy.name
  return t('backtestPg.noStrategySelected')
})
const selectedSymbol = computed(() => strategyConfig.value?.data?.symbol || '--')
const initialCashDisplay = computed(() =>
  formatCurrency(strategyConfig.value?.backtest?.initial_cash ?? 100000),
)
const commissionDisplay = computed(() =>
  `${((strategyConfig.value?.backtest?.commission ?? 0.001) * 100).toFixed(3)}%`,
)
const latestStatusLabel = computed(() => latestResult.value ? statusLabel(latestResult.value.status) : '--')
const heroStats = computed(() => [
  {
    key: 'templates',
    label: t('backtestPg.metricTemplates'),
    value: formatNumber(templates.value.length),
  },
  {
    key: 'custom-strategies',
    label: t('backtestPg.metricCustomStrategies'),
    value: formatNumber(strategies.value.length),
  },
  {
    key: 'history',
    label: t('backtestPg.metricHistory'),
    value: formatNumber(results.value.length),
  },
  {
    key: 'latest-status',
    label: t('backtestPg.metricLatestStatus'),
    value: latestStatusLabel.value,
  },
])

async function runBacktest() {
  if (!form.strategy_id) {
    ElMessage.warning(t('backtestPg.msgPickStrategy'))
    return
  }

  loading.value = true
  progressInfo.value = { progress: 0, message: t('backtestPg.msgSubmitProgress') }
  try {
    const response = await backtestStore.runBacktest({
      strategy_id: form.strategy_id,
      symbol: strategyConfig.value?.data?.symbol || '',
      start_date: dayjs().subtract(10, 'year').format('YYYY-MM-DDTHH:mm:ss'),
      end_date: dayjs().format('YYYY-MM-DDTHH:mm:ss'),
      initial_cash: strategyConfig.value?.backtest?.initial_cash ?? 100000,
      commission: strategyConfig.value?.backtest?.commission ?? 0.001,
      params: { ...dynamicParams },
    })

    ElMessage.success(t('backtestPg.msgSubmitted'))

    startRuntime(response.task_id)
  } catch (e: unknown) {
    stopRuntime()
    showRequestMessage(e, t('backtestPg.msgSubmitFailed'))
  }
}

function viewResult(result: BacktestResult) {
  // 导航到详细分析页面
  router.push(`/backtest/result/${result.task_id}`)
}

async function deleteBacktest(taskId: string) {
  await ElMessageBox.confirm(t('backtestPg.confirmDelete'), t('backtestPg.msgDeletePrompt'), {
    type: 'warning',
  })
  
  await backtestStore.deleteResult(taskId)
  ElMessage.success(t('backtestPg.msgDeleted'))
}

onMounted(async () => {
  try {
    await Promise.all([
      strategyStore.fetchStrategies(),
      strategyStore.fetchTemplates(),
      backtestStore.fetchResults(),
    ])
  
    // Support ?strategy= query param from strategy gallery
    const queryStrategy = route.query.strategy as string
    if (queryStrategy) {
      form.strategy_id = queryStrategy
      await onStrategyChange(queryStrategy)
    } else if (templates.value.length > 0) {
      form.strategy_id = templates.value[0].id
      await onStrategyChange(templates.value[0].id)
    }
  } catch (e: unknown) {
    showRequestMessage(e, t('backtestPg.msgInitFailed'))
  }
})

onBeforeUnmount(() => {
  disposeRuntime()
})

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: t('backtest.pending'),
    running: t('backtest.running'),
    completed: t('backtest.completed'),
    failed: t('backtest.failed'),
    cancelled: t('dashboard.cancelled'),
  }
  return map[status] || status
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'CNY',
    maximumFractionDigits: 0,
  }).format(value)
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat().format(value)
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '--'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatDate(value: string): string {
  return value ? new Date(value).toLocaleString() : '--'
}

function resultToneClass(value: number | null | undefined): string {
  return (value ?? 0) >= 0 ? 'is-positive' : 'is-negative'
}
</script>

<style scoped>
.backtest-launch-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: var(--text-color-primary);
}

.backtest-launch-hero,
.backtest-launch-panel,
.backtest-analysis-panel {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  box-shadow: 0 10px 28px var(--shadow-color);
}

.backtest-launch-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  padding: 20px;
}

.backtest-launch-copy {
  min-width: 0;
}

.backtest-launch-kicker,
.backtest-launch-panel-head span {
  display: inline-flex;
  margin-bottom: 6px;
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 760;
  line-height: 1.2;
}

.backtest-launch-copy h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 26px;
  font-weight: 760;
  line-height: 1.2;
}

.backtest-launch-copy p {
  max-width: 820px;
  margin: 8px 0 0;
  color: var(--text-color-regular);
  font-size: 14px;
  line-height: 1.65;
}

.backtest-launch-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.backtest-launch-actions :deep(.el-button),
.backtest-analysis-panel :deep(.el-button),
.backtest-latest-action {
  gap: 6px;
}

.backtest-launch-stats {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.backtest-launch-stat {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.backtest-launch-stat span {
  display: block;
  margin-bottom: 6px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.backtest-launch-stat strong {
  display: block;
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1.15;
}

.backtest-launch-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
  gap: 18px;
  align-items: start;
}

.backtest-launch-panel {
  min-width: 0;
  padding: 18px;
}

.backtest-launch-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.backtest-launch-panel-head h2 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 740;
  line-height: 1.25;
}

.backtest-launch-panel-head p {
  flex: 0 1 420px;
  margin: 0;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.45;
  text-align: right;
}

.backtest-launch-form {
  display: grid;
  gap: 16px;
}

.backtest-form-section {
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.backtest-form-section-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  color: var(--text-color-primary);
  font-size: 14px;
  font-weight: 720;
}

.backtest-field {
  width: 100%;
}

.backtest-strategy-note {
  margin-top: 8px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.backtest-strategy-note span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 700;
}

.backtest-strategy-note p {
  margin: 6px 0 0;
  color: var(--text-color-regular);
  font-size: 13px;
  line-height: 1.55;
}

.backtest-strategy-note em {
  display: inline-flex;
  margin-left: 8px;
  color: var(--text-color-secondary);
  font-style: normal;
}

.backtest-param-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px 14px;
}

.backtest-param-empty {
  padding: 14px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  color: var(--text-color-secondary);
  font-size: 13px;
  text-align: center;
}

.backtest-launch-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.backtest-side-head span,
.backtest-progress-head span,
.backtest-analysis-panel span {
  display: block;
  color: var(--text-color-primary);
  font-size: 15px;
  font-weight: 740;
  line-height: 1.3;
}

.backtest-side-head p,
.backtest-progress-panel p,
.backtest-analysis-panel p {
  margin: 6px 0 0;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.45;
}

.backtest-summary-list {
  display: grid;
  gap: 10px;
  margin: 14px 0 0;
}

.backtest-summary-list div {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-color-light);
}

.backtest-summary-list div:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.backtest-summary-list dt {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.backtest-summary-list dd {
  max-width: 190px;
  margin: 0;
  color: var(--text-color-primary);
  font-size: 13px;
  font-weight: 690;
  text-align: right;
  overflow-wrap: anywhere;
}

.backtest-progress-panel {
  background: var(--fill-color-lighter);
}

.backtest-progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.backtest-progress-head strong {
  color: var(--primary-color);
  font-size: 18px;
}

.backtest-latest-metrics {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 14px 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.backtest-latest-metrics span {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.backtest-latest-metrics strong {
  font-size: 20px;
}

.backtest-latest-action {
  width: 100%;
  justify-content: center;
}

.backtest-analysis-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
}

.is-positive {
  color: var(--success-color);
}

.is-negative {
  color: var(--danger-color);
}

.backtest-launch-page :deep(.el-form-item__label) {
  color: var(--text-color-regular);
  font-weight: 650;
}

.backtest-launch-page :deep(.el-input__wrapper),
.backtest-launch-page :deep(.el-select__wrapper),
.backtest-launch-page :deep(.el-input-number),
.backtest-launch-page :deep(.el-input-number .el-input__wrapper) {
  background: var(--bg-color);
}

@media (max-width: 1180px) {
  .backtest-launch-hero,
  .backtest-launch-workbench {
    grid-template-columns: 1fr;
  }

  .backtest-launch-actions {
    justify-content: flex-start;
  }

  .backtest-launch-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .backtest-launch-page {
    gap: 14px;
  }

  .backtest-launch-hero,
  .backtest-launch-panel,
  .backtest-analysis-panel {
    padding: 14px;
  }

  .backtest-launch-copy h1 {
    font-size: 22px;
  }

  .backtest-launch-actions :deep(.el-button),
  .backtest-analysis-panel :deep(.el-button) {
    width: 100%;
    justify-content: center;
  }

  .backtest-launch-stats,
  .backtest-param-grid {
    grid-template-columns: 1fr;
  }

  .backtest-launch-panel-head,
  .backtest-analysis-panel {
    flex-direction: column;
    align-items: stretch;
  }

  .backtest-launch-panel-head p {
    flex-basis: auto;
    text-align: left;
  }

  .backtest-summary-list div {
    flex-direction: column;
    gap: 4px;
  }

  .backtest-summary-list dd {
    max-width: none;
    text-align: left;
  }
}
</style>
