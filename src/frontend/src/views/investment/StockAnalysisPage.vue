<template>
  <div class="stock-analysis-page">
    <section class="command-surface">
      <div class="command-header">
        <div class="title-block">
          <span class="eyebrow">{{ t('stockAnalysis.eyebrow') }}</span>
          <h2>{{ t('stockAnalysis.title') }}</h2>
          <p>{{ t('stockAnalysis.subtitle') }}</p>
        </div>
        <div class="status-stack">
          <span class="status-caption">{{ t('stockAnalysis.taskStatus') }}</span>
          <el-tag
            :type="currentTask ? statusTagType(currentTask.status) : 'info'"
            effect="plain"
            round
          >
            {{ currentTask ? statusLabel(currentTask.status) : t('stockAnalysis.notSubmitted') }}
          </el-tag>
        </div>
      </div>

      <div class="hero-metrics">
        <div
          v-for="item in heroMetrics"
          :key="item.label"
          class="hero-metric"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>

      <div class="command-bar">
        <label class="symbol-field">
          <span>{{ t('stockAnalysis.symbol') }}</span>
          <el-input
            v-model="form.symbol"
            size="large"
            :placeholder="t('stockAnalysis.symbolPlaceholder')"
            clearable
          />
        </label>

        <label class="compact-field">
          <span>{{ t('stockAnalysis.market') }}</span>
          <el-select
            v-model="form.marketType"
            size="large"
            class="full-width"
          >
            <el-option
              v-for="market in marketOptions"
              :key="market.value"
              :label="market.label"
              :value="market.value"
            />
          </el-select>
        </label>

        <label class="compact-field">
          <span>{{ t('stockAnalysis.analysisDate') }}</span>
          <el-date-picker
            v-model="form.analysisDate"
            size="large"
            type="date"
            value-format="YYYY-MM-DD"
            :placeholder="t('stockAnalysis.datePlaceholder')"
            class="full-width"
          />
        </label>

        <el-button
          type="primary"
          size="large"
          class="start-analysis-button"
          :loading="submitting"
          :disabled="!form.symbol.trim() || form.selectedModules.length === 0"
          @click="submitAnalysis"
        >
          <el-icon
            class="button-icon"
            aria-hidden="true"
          >
            <DataAnalysis />
          </el-icon>
          {{ t('stockAnalysis.startAnalysis') }}
        </el-button>
      </div>
    </section>

    <section class="analysis-workbench">
      <div class="workbench-main">
        <div class="analysis-panel">
          <div class="panel-head">
            <div>
              <span class="panel-kicker">{{ t('stockAnalysis.parametersKicker') }}</span>
              <h3>{{ t('stockAnalysis.configTitle') }}</h3>
            </div>
            <span class="panel-hint">{{ configHint }}</span>
          </div>

          <el-form
            class="analysis-form"
            label-position="top"
          >
            <div class="form-grid">
              <el-form-item>
                <span class="field-label">{{ t('stockAnalysis.researchDepth') }}</span>
                <el-select
                  v-model="form.researchDepth"
                  class="full-width"
                  :placeholder="t('stockAnalysis.depthPlaceholder')"
                >
                  <el-option
                    v-for="depth in depthOptions"
                    :key="depth.value"
                    :label="depth.label"
                    :value="depth.value"
                  />
                </el-select>
                <div class="depth-policy">
                  <span>{{ selectedDepthOption.description }}</span>
                  <strong>{{ selectedDepthOption.time }}</strong>
                </div>
              </el-form-item>

              <el-form-item>
                <span class="field-label">{{ t('stockAnalysis.model') }}</span>
                <el-select
                  v-model="form.modelId"
                  class="full-width"
                  :placeholder="t('stockAnalysis.defaultModel')"
                  clearable
                  :loading="loadingModels"
                >
                  <el-option
                    :label="t('stockAnalysis.defaultModel')"
                    value=""
                  />
                  <el-option
                    v-for="model in modelOptions"
                    :key="model.id"
                    :label="model.label"
                    :value="model.id"
                  />
                </el-select>
              </el-form-item>
            </div>

            <el-form-item>
              <div class="section-label-row">
                <span class="field-label">{{ t('stockAnalysis.modules') }}</span>
                <span>{{ moduleCoverageText }}</span>
              </div>
              <el-checkbox-group
                v-model="form.selectedModules"
                class="module-grid"
              >
                <el-checkbox
                  v-for="module in moduleOptions"
                  :key="module.value"
                  :value="module.value"
                  class="module-tile"
                >
                  <span class="module-name">{{ module.label }}</span>
                  <small>{{ module.description }}</small>
                </el-checkbox>
              </el-checkbox-group>
            </el-form-item>
          </el-form>
        </div>

        <section
          v-if="currentTask"
          class="runtime-panel"
        >
          <div class="runtime-head">
            <div>
              <span class="panel-kicker">{{ t('stockAnalysis.executionKicker') }}</span>
              <h3>{{ t('stockAnalysis.progressTitle', { symbol: currentTask.symbol }) }}</h3>
              <p>{{ currentTask.message || currentTask.current_step || t('stockAnalysis.runtimeFallback') }}</p>
            </div>
            <el-button
              v-if="canCancel"
              :loading="cancelling"
              @click="cancelTask"
            >
              {{ t('stockAnalysis.cancelTask') }}
            </el-button>
          </div>
          <el-progress
            :percentage="currentTask.progress"
            :stroke-width="10"
          />
          <div class="runtime-meta">
            <span>{{ t('stockAnalysis.runtimeMarket', { value: currentTask.market_type }) }}</span>
            <span>{{ t('stockAnalysis.runtimeDate', { value: currentTask.analysis_date }) }}</span>
            <span>{{ t('stockAnalysis.runtimeDepth', { value: currentTask.research_depth }) }}</span>
          </div>
        </section>

        <section
          v-if="!report"
          class="empty-panel"
        >
          <div class="empty-content">
            <span class="panel-kicker">{{ t('stockAnalysis.previewKicker') }}</span>
            <h3>{{ t('stockAnalysis.waitingTitle') }}</h3>
            <p>{{ t('stockAnalysis.waitingDesc') }}</p>
          </div>
          <div class="preview-steps">
            <span>{{ t('stockAnalysis.previewTechnical') }}</span>
            <span>{{ t('stockAnalysis.previewFundamentals') }}</span>
            <span>{{ t('stockAnalysis.previewNews') }}</span>
            <span>{{ t('stockAnalysis.previewRisk') }}</span>
          </div>
        </section>
      </div>

      <aside class="analysis-sidebar">
        <div class="side-panel">
          <div class="panel-head compact">
            <div>
              <span class="panel-kicker">{{ t('stockAnalysis.profileKicker') }}</span>
              <h3>{{ t('stockAnalysis.profileTitle') }}</h3>
            </div>
          </div>

          <dl class="profile-list">
            <div
              v-for="row in runProfileRows"
              :key="row.label"
            >
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </div>
          </dl>

          <p
            v-if="taskNotice"
            class="task-notice"
          >
            {{ taskNotice }}
          </p>
        </div>

        <div class="side-panel output-panel">
          <div>
            <span class="panel-kicker">{{ t('stockAnalysis.outputKicker') }}</span>
            <h3>{{ t('stockAnalysis.outputTitle') }}</h3>
          </div>
          <div class="output-grid">
            <span
              v-for="format in exportFormats"
              :key="format"
            >
              {{ format.toUpperCase() }}
            </span>
          </div>
        </div>
      </aside>
    </section>

    <section
      v-if="report"
      class="report-panel"
    >
      <div class="report-toolbar">
        <div>
          <h3>{{ t('stockAnalysis.reportTitle', { symbol: reportMeta.symbolName || currentTask?.symbol || '--' }) }}</h3>
          <p>{{ reportMeta.marketType }} · {{ reportMeta.analysisDate }} · {{ reportMeta.researchDepth }}</p>
        </div>
        <div
          v-if="currentTask?.report_id"
          class="export-actions"
        >
          <el-button
            v-for="format in exportFormats"
            :key="format"
            :loading="exporting === format"
            @click="downloadReport(format)"
          >
            {{ format.toUpperCase() }}
          </el-button>
        </div>
      </div>

      <div class="decision-grid">
        <div class="decision-card">
          <span>{{ t('stockAnalysis.investmentBias') }}</span>
          <strong>{{ decision.label || t('stockAnalysis.hold') }}</strong>
        </div>
        <div class="decision-card">
          <span>{{ t('stockAnalysis.confidence') }}</span>
          <strong>{{ formatPercent(decision.confidence_score) }}</strong>
        </div>
        <div class="decision-card">
          <span>{{ t('stockAnalysis.riskLevel') }}</span>
          <strong>{{ decision.risk_level || t('stockAnalysis.mediumRisk') }}</strong>
        </div>
        <div class="decision-card">
          <span>{{ t('stockAnalysis.targetPrice') }}</span>
          <strong>{{ decision.target_price ?? '--' }}</strong>
        </div>
      </div>

      <div class="executive-summary">
        <h4>{{ t('stockAnalysis.executiveSummary') }}</h4>
        <p>{{ report.executive_summary || decision.reasoning || t('stockAnalysis.noSummary') }}</p>
      </div>

      <el-tabs
        v-model="activeReportTab"
        class="report-tabs"
      >
        <el-tab-pane
          v-for="section in reportSections"
          :key="section.id"
          :label="section.title"
          :name="section.id"
        >
          <article class="report-section">
            <div class="section-head">
              <h4>{{ section.title }}</h4>
              <el-tag
                v-if="typeof section.score === 'number'"
                size="small"
                effect="plain"
              >
                {{ t('stockAnalysis.score', { score: Math.round(section.score * 100) }) }}
              </el-tag>
            </div>
            <p>{{ section.summary || t('stockAnalysis.noContent') }}</p>
            <ul v-if="section.findings.length > 1">
              <li
                v-for="finding in section.findings"
                :key="finding"
              >
                {{ finding }}
              </li>
            </ul>
          </article>
        </el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { DataAnalysis } from '@element-plus/icons-vue'

import { aiObservabilityApi, type AIModelOption } from '@/api/aiObservability'
import {
  stockAnalysisApi,
  type StockAnalysisCreateTaskParams,
  type StockAnalysisExportFormat,
  type StockAnalysisModule,
  type StockAnalysisResult,
  type StockAnalysisTask,
} from '@/api/stockAnalysis'

type TaskStatus = StockAnalysisTask['status']

interface AnalysisModuleOption {
  value: StockAnalysisModule
  label: string
  description: string
}

interface ResearchDepthOption {
  value: string
  label: string
  description: string
  time: string
  modules: StockAnalysisModule[]
  debateRounds: number
  riskRounds: number
  memoryEnabled: boolean
}

interface ReportMeta {
  symbol?: string
  symbol_name?: string
  market_type?: string
  analysis_date?: string
  research_depth?: string
}

interface ReportDecision {
  label?: string
  target_price?: string | number | null
  confidence_score?: number | null
  risk_score?: number | null
  risk_level?: string
  reasoning?: string
}

interface ReportSection {
  id: string
  title: string
  summary: string
  findings: string[]
  score?: number | null
}

interface StockAnalysisReport {
  meta?: ReportMeta
  executive_summary?: string
  decision?: ReportDecision
  sections?: ReportSection[]
  disclaimer?: string
}

const route = useRoute()
const { t, locale } = useI18n()

const marketOptions = computed(() => [
  { label: t('stockAnalysis.marketCnA'), value: 'A股' },
  { label: t('stockAnalysis.marketHk'), value: '港股' },
  { label: t('stockAnalysis.marketUs'), value: '美股' },
])

const depthOptions = computed<ResearchDepthOption[]>(() => [
  {
    value: '快速',
    label: t('stockAnalysis.depthQuickLabel'),
    description: t('stockAnalysis.depthQuickDesc'),
    time: t('stockAnalysis.depthQuickTime'),
    modules: ['market'],
    debateRounds: 1,
    riskRounds: 1,
    memoryEnabled: false,
  },
  {
    value: '基础',
    label: t('stockAnalysis.depthBaseLabel'),
    description: t('stockAnalysis.depthBaseDesc'),
    time: t('stockAnalysis.depthBaseTime'),
    modules: ['market', 'fundamentals'],
    debateRounds: 1,
    riskRounds: 1,
    memoryEnabled: true,
  },
  {
    value: '标准',
    label: t('stockAnalysis.depthStandardLabel'),
    description: t('stockAnalysis.depthStandardDesc'),
    time: t('stockAnalysis.depthStandardTime'),
    modules: ['market', 'fundamentals', 'news', 'risk'],
    debateRounds: 1,
    riskRounds: 2,
    memoryEnabled: true,
  },
  {
    value: '深度',
    label: t('stockAnalysis.depthDeepLabel'),
    description: t('stockAnalysis.depthDeepDesc'),
    time: t('stockAnalysis.depthDeepTime'),
    modules: ['market', 'fundamentals', 'news', 'social', 'risk'],
    debateRounds: 2,
    riskRounds: 2,
    memoryEnabled: true,
  },
  {
    value: '全面',
    label: t('stockAnalysis.depthFullLabel'),
    description: t('stockAnalysis.depthFullDesc'),
    time: t('stockAnalysis.depthFullTime'),
    modules: ['market', 'fundamentals', 'news', 'social', 'risk'],
    debateRounds: 3,
    riskRounds: 3,
    memoryEnabled: true,
  },
])

const moduleOptions = computed<AnalysisModuleOption[]>(() => [
  { value: 'market', label: t('stockAnalysis.moduleMarket'), description: t('stockAnalysis.moduleMarketDesc') },
  { value: 'fundamentals', label: t('stockAnalysis.moduleFundamentals'), description: t('stockAnalysis.moduleFundamentalsDesc') },
  { value: 'news', label: t('stockAnalysis.moduleNews'), description: t('stockAnalysis.moduleNewsDesc') },
  { value: 'social', label: t('stockAnalysis.moduleSocial'), description: t('stockAnalysis.moduleSocialDesc') },
  { value: 'risk', label: t('stockAnalysis.moduleRisk'), description: t('stockAnalysis.moduleRiskDesc') },
])

const exportFormats: StockAnalysisExportFormat[] = ['markdown', 'html', 'docx', 'pdf']

const today = new Date().toISOString().slice(0, 10)
const initialSymbol = typeof route.query.symbol === 'string' ? route.query.symbol : '000001.SZ'

const form = reactive({
  symbol: initialSymbol,
  marketType: 'A股',
  analysisDate: today,
  researchDepth: '标准',
  selectedModules: ['market', 'fundamentals', 'news', 'risk'] as StockAnalysisModule[],
  modelId: '',
})

const loadingModels = ref(false)
const submitting = ref(false)
const cancelling = ref(false)
const exporting = ref<StockAnalysisExportFormat | null>(null)
const currentTask = ref<StockAnalysisTask | null>(null)
const analysisResult = ref<StockAnalysisResult | null>(null)
const availableModels = ref<AIModelOption[]>([])
const taskNotice = ref('')
const activeReportTab = ref('technical')
let pollingTimer: number | null = null

const modelOptions = computed(() =>
  availableModels.value.map((model) => ({
    id: `${model.provider}:${model.model}`,
    label: `${model.display_name || model.model} (${model.provider})`,
  })),
)
const selectedModuleLabels = computed(() =>
  moduleOptions.value
    .filter((module) => form.selectedModules.includes(module.value))
    .map((module) => module.label),
)
const selectedDepthOption = computed<ResearchDepthOption>(() => {
  const options = depthOptions.value
  return options.find((depth) => depth.value === form.researchDepth) ?? options[2] ?? options[0]!
})
const configHint = computed(() =>
  t('stockAnalysis.configHint', {
    depth: selectedDepthOption.value.label,
    count: selectedModuleLabels.value.length,
  })
)
const heroMetrics = computed(() => [
  { label: t('stockAnalysis.heroModules'), value: moduleCoverageText.value },
  { label: t('stockAnalysis.heroTime'), value: selectedDepthOption.value.time },
  {
    label: t('stockAnalysis.heroRounds'),
    value: `${selectedDepthOption.value.debateRounds}/${selectedDepthOption.value.riskRounds}`,
  },
  { label: t('stockAnalysis.heroExports'), value: exportFormats.map(format => format.toUpperCase()).join(' / ') },
])
const currentLocale = computed(() => String(locale.value || 'zh-CN'))
const defaultModelLabel = computed(() => t('stockAnalysis.defaultModel'))
const activeMarketLabel = computed(() => {
  return marketOptions.value.find((market) => market.value === form.marketType)?.label ?? form.marketType
})
const moduleCoverageText = computed(() => {
  if (selectedModuleLabels.value.length === moduleOptions.value.length) return t('stockAnalysis.fullCoverage')
  if (selectedModuleLabels.value.length === 0) return t('stockAnalysis.noModules')
  return selectedModuleLabels.value.join(' / ')
})
const runProfileRows = computed(() => [
  { label: t('stockAnalysis.profileSymbol'), value: normalizeSymbol(form.symbol) || '--' },
  { label: t('stockAnalysis.profileMarket'), value: activeMarketLabel.value },
  { label: t('stockAnalysis.profileDate'), value: form.analysisDate || '--' },
  { label: t('stockAnalysis.profileDepth'), value: selectedDepthOption.value.label },
  {
    label: t('stockAnalysis.profileRounds'),
    value: t('stockAnalysis.roundsValue', {
      debate: selectedDepthOption.value.debateRounds,
      risk: selectedDepthOption.value.riskRounds,
    }),
  },
  {
    label: t('stockAnalysis.profileMemory'),
    value: selectedDepthOption.value.memoryEnabled ? t('stockAnalysis.enabled') : t('stockAnalysis.disabled'),
  },
  { label: t('stockAnalysis.profileModules'), value: moduleCoverageText.value },
  { label: t('stockAnalysis.profileModel'), value: modelOptions.value.find((model) => model.id === form.modelId)?.label ?? defaultModelLabel.value },
])

const report = computed(() => (analysisResult.value?.report ?? null) as StockAnalysisReport | null)
const decision = computed<ReportDecision>(() => report.value?.decision ?? {})
const reportMeta = computed(() => {
  const meta = report.value?.meta ?? {}
  return {
    symbolName: meta.symbol_name || currentTask.value?.symbol_name || meta.symbol,
    marketType: meta.market_type || currentTask.value?.market_type || '--',
    analysisDate: meta.analysis_date || currentTask.value?.analysis_date || '--',
    researchDepth: meta.research_depth || currentTask.value?.research_depth || '--',
  }
})
const reportSections = computed<ReportSection[]>(() => {
  const sections = report.value?.sections
  if (Array.isArray(sections) && sections.length > 0) {
    return sections.map((section) => ({
      id: section.id,
      title: section.title,
      summary: section.summary,
      findings: Array.isArray(section.findings) ? section.findings : [],
      score: section.score,
    }))
  }
  return []
})
const canCancel = computed(() => {
  return currentTask.value?.status === 'pending' || currentTask.value?.status === 'running'
})

onMounted(() => {
  loadAvailableModels()
})

onUnmounted(() => {
  stopPolling()
})

watch(
  () => form.researchDepth,
  (depth) => {
    const preset = depthOptions.value.find((item) => item.value === depth)
    if (!preset) return
    form.selectedModules = [...preset.modules]
  },
)

async function loadAvailableModels() {
  loadingModels.value = true
  try {
    const response = await aiObservabilityApi.getMyAvailableModels()
    availableModels.value = response.models ?? []
    const preferred = response.preferences?.provider && response.preferences?.model
      ? `${response.preferences.provider}:${response.preferences.model}`
      : ''
    form.modelId = preferred || modelOptions.value[0]?.id || ''
  } catch {
    availableModels.value = []
  } finally {
    loadingModels.value = false
  }
}

function normalizeSymbol(symbol: string): string {
  return symbol.trim().replace(/\s+/g, ' ').toUpperCase()
}

function buildPayload(): StockAnalysisCreateTaskParams {
  const selectedModules = moduleOptions.value
    .map((module) => module.value)
    .filter((module) => form.selectedModules.includes(module))

  return {
    symbol: normalizeSymbol(form.symbol),
    market_type: form.marketType,
    analysis_date: form.analysisDate || null,
    research_depth: form.researchDepth,
    selected_modules: selectedModules,
    include_sentiment: selectedModules.includes('social'),
    include_risk: selectedModules.includes('risk'),
    language: currentLocale.value,
    model_id: form.modelId || undefined,
  }
}

async function submitAnalysis() {
  const payload = buildPayload()
  if (!payload.symbol) {
    ElMessage.warning(t('stockAnalysis.symbolRequired'))
    return
  }
  if (payload.selected_modules.length === 0) {
    ElMessage.warning(t('stockAnalysis.moduleRequired'))
    return
  }

  submitting.value = true
  taskNotice.value = ''
  analysisResult.value = null
  try {
    const task = await stockAnalysisApi.createTask(payload)
    currentTask.value = task
    taskNotice.value = t('stockAnalysis.taskSubmitted')
    ElMessage.success(t('stockAnalysis.taskSubmitted'))
    if (task.status === 'completed') {
      await loadResult(task.task_id)
    } else {
      startPolling(task.task_id)
    }
  } catch {
    ElMessage.error(t('stockAnalysis.submitFailed'))
  } finally {
    submitting.value = false
  }
}

function startPolling(taskId: string) {
  stopPolling()
  pollingTimer = window.setInterval(() => {
    refreshTask(taskId)
  }, 3000)
}

function stopPolling() {
  if (pollingTimer !== null) {
    window.clearInterval(pollingTimer)
    pollingTimer = null
  }
}

async function refreshTask(taskId: string) {
  try {
    const task = await stockAnalysisApi.getTask(taskId)
    currentTask.value = task
    if (task.status === 'completed') {
      stopPolling()
      await loadResult(task.task_id)
      ElMessage.success(t('stockAnalysis.reportReady'))
    } else if (task.status === 'failed' || task.status === 'cancelled') {
      stopPolling()
      if (task.status === 'failed') {
        ElMessage.error(task.error_message || t('stockAnalysis.taskFailed'))
      }
    }
  } catch {
    stopPolling()
    ElMessage.error(t('stockAnalysis.refreshFailed'))
  }
}

async function loadResult(taskId: string) {
  const result = await stockAnalysisApi.getTaskResult(taskId)
  analysisResult.value = result
  const firstSection = reportSections.value[0]
  if (firstSection) {
    activeReportTab.value = firstSection.id
  }
}

async function cancelTask() {
  if (!currentTask.value) return
  cancelling.value = true
  try {
    const task = await stockAnalysisApi.cancelTask(currentTask.value.task_id)
    currentTask.value = task
    stopPolling()
    ElMessage.success(t('stockAnalysis.cancelSuccess'))
  } catch {
    ElMessage.error(t('stockAnalysis.cancelFailed'))
  } finally {
    cancelling.value = false
  }
}

async function downloadReport(format: StockAnalysisExportFormat) {
  const reportId = currentTask.value?.report_id
  if (!reportId) return
  exporting.value = format
  try {
    const payload = await stockAnalysisApi.exportReport(reportId, format)
    const blob = payload instanceof Blob ? payload : new Blob([payload])
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${currentTask.value?.symbol ?? 'stock'}_analysis.${format === 'markdown' ? 'md' : format}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error(t('stockAnalysis.exportFailed'))
  } finally {
    exporting.value = null
  }
}

function statusLabel(status: TaskStatus): string {
  const labels: Record<TaskStatus, string> = {
    pending: t('stockAnalysis.statusPending'),
    running: t('stockAnalysis.statusRunning'),
    completed: t('stockAnalysis.statusCompleted'),
    failed: t('stockAnalysis.statusFailed'),
    cancelled: t('stockAnalysis.statusCancelled'),
  }
  return labels[status]
}

function statusTagType(status: TaskStatus): 'success' | 'warning' | 'danger' | 'info' | undefined {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'cancelled') return 'info'
  if (status === 'running') return 'warning'
  return undefined
}

function formatPercent(value: unknown): string {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '--'
}
</script>

<style scoped>
.stock-analysis-page {
  display: grid;
  gap: 18px;
  max-width: 1480px;
  margin: 0 auto;
  color: var(--text-color-primary);
}

.command-surface,
.analysis-panel,
.side-panel,
.runtime-panel,
.report-panel,
.empty-panel {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  box-shadow: 0 10px 28px var(--shadow-color);
}

.command-surface {
  padding: 20px;
}

.command-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 28px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.title-block {
  min-width: 0;
}

.eyebrow {
  display: inline-flex;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0;
  color: var(--primary-color);
}

.command-header h2,
.panel-head h3,
.runtime-head h3,
.report-toolbar h3,
.empty-panel h3 {
  margin: 0;
}

.command-header h2 {
  font-size: 24px;
  line-height: 1.25;
  color: var(--text-color-primary);
}

.command-header p,
.panel-head p,
.runtime-head p,
.report-toolbar p,
.empty-panel p {
  margin: 8px 0 0;
  color: var(--text-color-secondary);
  line-height: 1.6;
}

.status-stack {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  min-width: 92px;
}

.status-caption {
  font-size: 12px;
  color: var(--text-color-secondary);
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.hero-metric {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.hero-metric span {
  display: block;
  margin-bottom: 6px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.hero-metric strong {
  display: block;
  color: var(--text-color-primary);
  font-size: 16px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.command-bar {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(150px, 180px) minmax(180px, 220px) 180px;
  gap: 14px;
  align-items: end;
  padding-top: 18px;
}

.symbol-field,
.compact-field {
  display: block;
  min-width: 0;
}

.symbol-field > span,
.compact-field > span {
  display: block;
  margin-bottom: 7px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-color-secondary);
}

.button-icon {
  margin-right: 6px;
}

.analysis-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 18px;
  align-items: start;
}

.workbench-main,
.analysis-sidebar {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.analysis-panel {
  padding: 20px;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.panel-head.compact {
  margin-bottom: 14px;
}

.panel-kicker {
  display: block;
  margin-bottom: 5px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  color: var(--text-color-secondary);
}

.panel-head h3,
.output-panel h3 {
  font-size: 17px;
  color: var(--text-color-primary);
}

.panel-hint {
  padding: 5px 9px;
  border: 1px solid var(--border-color-light);
  border-radius: 999px;
  background: var(--fill-color-lighter);
  color: var(--text-color-regular);
  font-size: 12px;
  white-space: nowrap;
}

.analysis-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.field-label,
.section-label-row > span:first-child {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color-primary);
}

.section-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
  margin-bottom: 8px;
}

.section-label-row > span:last-child {
  color: var(--text-color-secondary);
  font-size: 12px;
  text-align: right;
  overflow-wrap: anywhere;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.full-width {
  width: 100%;
}

.depth-policy {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.depth-policy strong {
  flex: 0 0 auto;
  color: var(--primary-color);
  font-size: 12px;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
  width: 100%;
}

.module-grid :deep(.el-checkbox.module-tile) {
  align-items: flex-start;
  min-height: 86px;
  height: auto;
  margin-right: 0;
  padding: 12px 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  white-space: normal;
  transition: border-color 0.18s ease, background-color 0.18s ease, box-shadow 0.18s ease;
}

.module-grid :deep(.el-checkbox.module-tile:hover) {
  border-color: var(--primary-color);
  background: var(--fill-color-light);
}

.module-grid :deep(.el-checkbox.is-checked.module-tile) {
  border-color: var(--primary-color);
  background: var(--fill-color-light);
  box-shadow: inset 0 0 0 1px var(--primary-color);
}

.module-grid :deep(.el-checkbox.is-checked.module-tile .el-checkbox__label),
.module-grid :deep(.el-checkbox.is-checked.module-tile .module-name),
.module-grid :deep(.el-checkbox.is-checked.module-tile small) {
  color: var(--text-color-primary);
}

.module-grid :deep(.el-checkbox__label) {
  min-width: 0;
  padding-left: 8px;
}

.module-name {
  display: block;
  margin-bottom: 5px;
  font-weight: 600;
  color: var(--text-color-primary);
}

.module-grid small {
  display: block;
  line-height: 1.5;
  color: var(--text-color-secondary);
}

.analysis-sidebar {
  position: sticky;
  top: 18px;
}

.side-panel {
  padding: 18px;
}

.profile-list {
  display: grid;
  gap: 0;
  margin: 0;
  border-top: 1px solid var(--border-color-light);
}

.profile-list div {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 0;
  border-bottom: 1px solid var(--border-color-light);
}

.profile-list dt {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.profile-list dd {
  margin: 0;
  text-align: right;
  color: var(--text-color-primary);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.start-analysis-button {
  width: 100%;
  min-height: 40px;
}

.task-notice {
  margin: 14px 0 0;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--success-border-color);
  background: var(--success-surface);
  color: var(--success-text-strong);
  font-size: 13px;
  font-weight: 600;
}

.output-panel {
  display: grid;
  gap: 14px;
}

.output-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.output-grid span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-regular);
  font-size: 12px;
  font-weight: 700;
}

.runtime-panel,
.report-panel,
.empty-panel {
  padding: 20px;
}

.runtime-head,
.report-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.runtime-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
  color: var(--text-color-secondary);
  font-size: 13px;
}

.runtime-meta span {
  padding: 5px 9px;
  border-radius: 999px;
  background: var(--fill-color-lighter);
}

.export-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.decision-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.decision-card {
  padding: 14px 16px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.decision-card span {
  display: block;
  margin-bottom: 6px;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.decision-card strong {
  font-size: 18px;
  color: var(--text-color-primary);
  overflow-wrap: anywhere;
}

.executive-summary {
  margin-bottom: 18px;
  padding: 16px 18px;
  border: 1px solid var(--info-border-color);
  border-left: 4px solid var(--primary-color);
  border-radius: 8px;
  background: var(--info-surface);
}

.executive-summary h4,
.report-section h4 {
  margin: 0 0 8px;
}

.executive-summary p,
.report-section p {
  margin: 0;
  line-height: 1.75;
  color: var(--text-color-regular);
  white-space: pre-wrap;
}

.report-tabs {
  margin-top: 8px;
}

.report-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.report-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: var(--border-color-light);
}

.report-section {
  padding: 18px 2px 4px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.report-section ul {
  margin: 14px 0 0;
  padding-left: 18px;
  color: var(--text-color-regular);
  line-height: 1.7;
}

.empty-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 150px;
}

.empty-content {
  max-width: 560px;
}

.preview-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(82px, 1fr));
  gap: 8px;
}

.preview-steps span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  padding: 0 12px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  text-align: center;
  overflow-wrap: normal;
}

.stock-analysis-page :deep(.el-form-item) {
  margin-bottom: 0;
}

.stock-analysis-page :deep(.el-input__wrapper),
.stock-analysis-page :deep(.el-select__wrapper) {
  background: var(--bg-color);
  box-shadow: 0 0 0 1px var(--border-color-light) inset;
}

.stock-analysis-page :deep(.el-input__wrapper:hover),
.stock-analysis-page :deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--primary-color) inset;
}

@media (max-width: 1180px) {
  .command-bar,
  .analysis-workbench {
    grid-template-columns: 1fr;
  }

  .analysis-sidebar {
    position: static;
  }

  .module-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .hero-metrics,
  .decision-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .empty-panel {
    align-items: stretch;
    flex-direction: column;
  }

  .preview-steps {
    width: 100%;
  }
}

@media (max-width: 720px) {
  .command-header,
  .runtime-head,
  .report-toolbar,
  .empty-panel {
    flex-direction: column;
  }

  .form-grid,
  .module-grid,
  .hero-metrics,
  .decision-grid,
  .preview-steps {
    grid-template-columns: 1fr;
  }

  .command-surface,
  .analysis-panel,
  .side-panel,
  .runtime-panel,
  .report-panel,
  .empty-panel {
    padding: 18px;
  }

  .status-stack {
    align-items: flex-start;
  }

  .command-bar {
    gap: 12px;
  }

  .start-analysis-button,
  .export-actions :deep(.el-button) {
    width: 100%;
  }

  .depth-policy,
  .section-label-row,
  .profile-list div {
    align-items: flex-start;
    flex-direction: column;
  }

  .section-label-row > span:last-child,
  .profile-list dd {
    text-align: left;
  }
}
</style>
