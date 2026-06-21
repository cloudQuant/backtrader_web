<template>
  <div class="stock-analysis-page">
    <section class="command-surface">
      <div class="command-header">
        <div class="title-block">
          <span class="eyebrow">投资研究</span>
          <h2>单股分析</h2>
          <p>面向单一股票的完整研究流水线，覆盖技术面、基本面、新闻情绪和风险终审。</p>
        </div>
        <div class="status-stack">
          <span class="status-caption">任务状态</span>
          <el-tag
            :type="currentTask ? statusTagType(currentTask.status) : 'info'"
            effect="plain"
            round
          >
            {{ currentTask ? statusLabel(currentTask.status) : '未提交' }}
          </el-tag>
        </div>
      </div>

      <div class="command-bar">
        <label class="symbol-field">
          <span>股票代码</span>
          <el-input
            v-model="form.symbol"
            size="large"
            placeholder="000001.SZ / 600519.SH / AAPL"
            clearable
          />
        </label>

        <label class="compact-field">
          <span>市场</span>
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
          <span>分析日期</span>
          <el-date-picker
            v-model="form.analysisDate"
            size="large"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
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
          开始智能分析
        </el-button>
      </div>
    </section>

    <section class="analysis-workbench">
      <div class="workbench-main">
        <div class="analysis-panel">
          <div class="panel-head">
            <div>
              <span class="panel-kicker">PARAMETERS</span>
              <h3>分析配置</h3>
            </div>
            <span class="panel-hint">{{ form.researchDepth }} · {{ selectedModuleLabels.length }} 个模块</span>
          </div>

          <el-form
            class="analysis-form"
            label-position="top"
          >
            <div class="form-grid">
              <el-form-item>
                <span class="field-label">研究深度</span>
                <el-select
                  v-model="form.researchDepth"
                  class="full-width"
                  placeholder="选择研究深度"
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
                <span class="field-label">大模型</span>
                <el-select
                  v-model="form.modelId"
                  class="full-width"
                  placeholder="系统默认模型"
                  clearable
                  :loading="loadingModels"
                >
                  <el-option
                    label="系统默认模型"
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
                <span class="field-label">研究模块</span>
                <span>{{ moduleCoverageText }}</span>
              </div>
              <el-checkbox-group v-model="form.selectedModules" class="module-grid">
                <el-checkbox
                  v-for="module in moduleOptions"
                  :key="module.value"
                  :label="module.value"
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
              <span class="panel-kicker">EXECUTION</span>
              <h3>{{ currentTask.symbol }} 分析进度</h3>
              <p>{{ currentTask.message || currentTask.current_step || '任务已创建，等待执行。' }}</p>
            </div>
            <el-button
              v-if="canCancel"
              :loading="cancelling"
              @click="cancelTask"
            >
              取消任务
            </el-button>
          </div>
          <el-progress
            :percentage="currentTask.progress"
            :stroke-width="10"
          />
          <div class="runtime-meta">
            <span>市场：{{ currentTask.market_type }}</span>
            <span>日期：{{ currentTask.analysis_date }}</span>
            <span>深度：{{ currentTask.research_depth }}</span>
          </div>
        </section>

        <section
          v-if="!report"
          class="empty-panel"
        >
          <div class="empty-content">
            <span class="panel-kicker">REPORT PREVIEW</span>
            <h3>等待生成报告</h3>
            <p>提交后会在这里展示完整分析结果，任务运行期间可以离开页面稍后回来查看。</p>
          </div>
          <div class="preview-steps">
            <span>技术面</span>
            <span>基本面</span>
            <span>新闻情绪</span>
            <span>风险终审</span>
          </div>
        </section>
      </div>

      <aside class="analysis-sidebar">
        <div class="side-panel">
          <div class="panel-head compact">
            <div>
              <span class="panel-kicker">RUN PROFILE</span>
              <h3>执行画像</h3>
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
            <span class="panel-kicker">OUTPUT</span>
            <h3>报告输出</h3>
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
          <h3>{{ reportMeta.symbolName || currentTask?.symbol }} 投资研究报告</h3>
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
          <span>投资倾向</span>
          <strong>{{ decision.label || '持有' }}</strong>
        </div>
        <div class="decision-card">
          <span>置信度</span>
          <strong>{{ formatPercent(decision.confidence_score) }}</strong>
        </div>
        <div class="decision-card">
          <span>风险等级</span>
          <strong>{{ decision.risk_level || '中等' }}</strong>
        </div>
        <div class="decision-card">
          <span>目标价</span>
          <strong>{{ decision.target_price ?? '--' }}</strong>
        </div>
      </div>

      <div class="executive-summary">
        <h4>核心摘要</h4>
        <p>{{ report.executive_summary || decision.reasoning || '暂无摘要。' }}</p>
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
                评分 {{ Math.round(section.score * 100) }}
              </el-tag>
            </div>
            <p>{{ section.summary || '暂无内容。' }}</p>
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
import { ElMessage } from 'element-plus'

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

const marketOptions = [
  { label: 'A股', value: 'A股' },
  { label: '港股', value: '港股' },
  { label: '美股', value: '美股' },
]

const depthOptions = [
  {
    value: '快速',
    label: '1级 - 快速',
    description: '单点市场快扫，优先速度和成本',
    time: '2-5分钟',
    modules: ['market'],
    debateRounds: 1,
    riskRounds: 1,
    memoryEnabled: false,
  },
  {
    value: '基础',
    label: '2级 - 基础',
    description: '市场与基本面组合，覆盖常规投资判断',
    time: '3-6分钟',
    modules: ['market', 'fundamentals'],
    debateRounds: 1,
    riskRounds: 1,
    memoryEnabled: true,
  },
  {
    value: '标准',
    label: '3级 - 标准',
    description: '技术、基本面、新闻和风险终审，默认推荐',
    time: '4-8分钟',
    modules: ['market', 'fundamentals', 'news', 'risk'],
    debateRounds: 1,
    riskRounds: 2,
    memoryEnabled: true,
  },
  {
    value: '深度',
    label: '4级 - 深度',
    description: '启用完整研究模块和多轮辩论',
    time: '6-11分钟',
    modules: ['market', 'fundamentals', 'news', 'social', 'risk'],
    debateRounds: 2,
    riskRounds: 2,
    memoryEnabled: true,
  },
  {
    value: '全面',
    label: '5级 - 全面',
    description: '完整模块、最高讨论轮次和最完整报告',
    time: '8-16分钟',
    modules: ['market', 'fundamentals', 'news', 'social', 'risk'],
    debateRounds: 3,
    riskRounds: 3,
    memoryEnabled: true,
  },
] satisfies ResearchDepthOption[]

const moduleOptions: AnalysisModuleOption[] = [
  { value: 'market', label: '技术面', description: '行情结构、趋势和量价表现' },
  { value: 'fundamentals', label: '基本面', description: '财务质量、估值和经营线索' },
  { value: 'news', label: '新闻', description: '事件驱动和公开资讯影响' },
  { value: 'social', label: '情绪', description: '市场叙事和投资者情绪' },
  { value: 'risk', label: '风险', description: '波动、回撤和终审意见' },
]

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
  moduleOptions
    .filter((module) => form.selectedModules.includes(module.value))
    .map((module) => module.label),
)
const selectedDepthOption = computed(() => {
  return depthOptions.find((depth) => depth.value === form.researchDepth) ?? depthOptions[2]
})
const moduleCoverageText = computed(() => {
  if (selectedModuleLabels.value.length === moduleOptions.length) return '完整覆盖'
  if (selectedModuleLabels.value.length === 0) return '未选择模块'
  return selectedModuleLabels.value.join(' / ')
})
const runProfileRows = computed(() => [
  { label: '标的', value: normalizeSymbol(form.symbol) || '--' },
  { label: '市场', value: form.marketType },
  { label: '日期', value: form.analysisDate || '--' },
  { label: '深度', value: form.researchDepth },
  { label: '讨论轮次', value: `${selectedDepthOption.value.debateRounds} / ${selectedDepthOption.value.riskRounds}` },
  { label: '记忆', value: selectedDepthOption.value.memoryEnabled ? '启用' : '关闭' },
  { label: '模块', value: moduleCoverageText.value },
  { label: '模型', value: modelOptions.value.find((model) => model.id === form.modelId)?.label ?? '系统默认模型' },
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
    const preset = depthOptions.find((item) => item.value === depth)
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
  const selectedModules = moduleOptions
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
    language: 'zh-CN',
    model_id: form.modelId || undefined,
  }
}

async function submitAnalysis() {
  const payload = buildPayload()
  if (!payload.symbol) {
    ElMessage.warning('请输入股票代码')
    return
  }
  if (payload.selected_modules.length === 0) {
    ElMessage.warning('请至少选择一个研究模块')
    return
  }

  submitting.value = true
  taskNotice.value = ''
  analysisResult.value = null
  try {
    const task = await stockAnalysisApi.createTask(payload)
    currentTask.value = task
    taskNotice.value = '分析任务已提交'
    ElMessage.success('分析任务已提交')
    if (task.status === 'completed') {
      await loadResult(task.task_id)
    } else {
      startPolling(task.task_id)
    }
  } catch {
    ElMessage.error('提交分析任务失败')
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
      ElMessage.success('分析报告已生成')
    } else if (task.status === 'failed' || task.status === 'cancelled') {
      stopPolling()
      if (task.status === 'failed') {
        ElMessage.error(task.error_message || '分析任务失败')
      }
    }
  } catch {
    stopPolling()
    ElMessage.error('刷新任务状态失败')
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
    ElMessage.success('任务已取消')
  } catch {
    ElMessage.error('取消任务失败')
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
    ElMessage.error('导出报告失败')
  } finally {
    exporting.value = null
  }
}

function statusLabel(status: TaskStatus): string {
  const labels: Record<TaskStatus, string> = {
    pending: '等待中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
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
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: #172033;
  max-width: 1480px;
  margin: 0 auto;
}

.command-surface,
.analysis-panel,
.side-panel,
.runtime-panel,
.report-panel,
.empty-panel {
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
}

.command-surface {
  padding: 22px;
}

.command-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 28px;
  padding-bottom: 18px;
  border-bottom: 1px solid #e6edf5;
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
  color: #1d4ed8;
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
  color: #0f172a;
}

.command-header p,
.panel-head p,
.runtime-head p,
.report-toolbar p,
.empty-panel p {
  margin: 8px 0 0;
  color: #5f6f86;
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
  color: #718096;
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
  color: #53657d;
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
  color: #64748b;
}

.panel-head h3,
.output-panel h3 {
  font-size: 17px;
  color: #0f172a;
}

.panel-hint {
  padding: 5px 9px;
  border: 1px solid #d7e1ee;
  border-radius: 999px;
  background: #f8fafc;
  color: #475569;
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
  color: #26364d;
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
  color: #64748b;
  font-size: 12px;
  text-align: right;
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
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.depth-policy strong {
  flex: 0 0 auto;
  color: #1d4ed8;
  font-size: 12px;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  gap: 10px;
  width: 100%;
}

.module-grid :deep(.el-checkbox.module-tile) {
  align-items: flex-start;
  min-height: 86px;
  height: auto;
  margin-right: 0;
  padding: 12px 10px;
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: #fbfdff;
  white-space: normal;
  transition: border-color 0.18s ease, background-color 0.18s ease, box-shadow 0.18s ease;
}

.module-grid :deep(.el-checkbox.module-tile:hover) {
  border-color: #93c5fd;
  background: #f8fbff;
}

.module-grid :deep(.el-checkbox.is-checked.module-tile) {
  border-color: #2563eb;
  background: #eff6ff;
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.12);
}

.module-grid :deep(.el-checkbox__label) {
  min-width: 0;
  padding-left: 8px;
}

.module-name {
  display: block;
  margin-bottom: 5px;
  font-weight: 600;
  color: #0f172a;
}

.module-grid small {
  display: block;
  line-height: 1.5;
  color: #66758a;
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
  border-top: 1px solid #edf2f7;
}

.profile-list div {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 0;
  border-bottom: 1px solid #edf2f7;
}

.profile-list dt {
  color: #64748b;
  font-size: 12px;
}

.profile-list dd {
  margin: 0;
  text-align: right;
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.45;
}

.start-analysis-button {
  width: 100%;
  min-height: 40px;
}

.task-notice {
  margin: 14px 0 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #ecfdf5;
  color: #047857;
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
  border: 1px solid #dde7f2;
  border-radius: 8px;
  background: #f8fafc;
  color: #475569;
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
  color: #516173;
  font-size: 13px;
}

.runtime-meta span {
  padding: 5px 9px;
  border-radius: 999px;
  background: #f1f5f9;
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
  border: 1px solid #dfe8f3;
  border-radius: 8px;
  background: #fbfdff;
}

.decision-card span {
  display: block;
  margin-bottom: 6px;
  color: #64748b;
  font-size: 12px;
}

.decision-card strong {
  font-size: 18px;
  color: #0f172a;
}

.executive-summary {
  margin-bottom: 18px;
  padding: 16px 18px;
  border: 1px solid #cfe0f4;
  border-left: 4px solid #2563eb;
  border-radius: 8px;
  background: #f7fbff;
}

.executive-summary h4,
.report-section h4 {
  margin: 0 0 8px;
}

.executive-summary p,
.report-section p {
  margin: 0;
  line-height: 1.75;
  color: #334155;
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
  background: #e2e8f0;
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
  color: #334155;
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
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  background: #f8fafc;
  color: #64748b;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.stock-analysis-page :deep(.el-form-item) {
  margin-bottom: 0;
}

.stock-analysis-page :deep(.el-input__wrapper),
.stock-analysis-page :deep(.el-select__wrapper) {
  box-shadow: 0 0 0 1px #d7e1ee inset;
}

.stock-analysis-page :deep(.el-input__wrapper:hover),
.stock-analysis-page :deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px #93c5fd inset;
}

@media (max-width: 1024px) {
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
}
</style>
