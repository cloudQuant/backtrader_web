<template>
  <article
    class="message-card"
    :class="message.role"
  >
    <div class="message-avatar">
      <el-icon v-if="message.role === 'assistant'">
        <Cpu />
      </el-icon>
      <el-icon v-else>
        <UserFilled />
      </el-icon>
    </div>

    <div class="message-body">
      <div class="message-head">
        <div>
          <span class="message-author">{{ message.role === 'assistant' ? t('aiChat.aiAssistant') : t('aiChat.rolePrefix') }}</span>
          <span
            v-if="message.role === 'assistant' && message.citations?.length"
            class="message-badge"
          >
            {{ t('aiChat.citationsCount', { n: message.citations.length }) }}
          </span>
          <span
            v-if="message.role === 'assistant' && message.strategyDraft"
            class="message-badge"
            :class="{
              success: !getStrategyDraftIssue(message.strategyDraft),
              warning: Boolean(getStrategyDraftIssue(message.strategyDraft)),
            }"
          >
            {{ getStrategyDraftIssue(message.strategyDraft) ? t('aiChat.draftPending') : t('aiChat.canSaveAsStrategy') }}
          </span>
          <span
            v-if="message.role === 'assistant' && displayStockReport"
            class="message-badge success"
          >
            {{ t('aiChat.stockAnalysisReport') }}
          </span>
        </div>
        <div class="message-head-actions">
          <div
            v-if="hoverWorkflowActions.length"
            class="workflow-hover-actions"
          >
            <el-button
              v-for="action in hoverWorkflowActions"
              :key="`hover-${action.key}`"
              size="small"
              :disabled="action.disabled"
              :title="action.title"
              @click="emit('strategyWorkflowAction', action.key)"
            >
              <el-icon>
                <component :is="action.icon" />
              </el-icon>
              {{ action.label }}
            </el-button>
          </div>
          <el-button
            circle
            size="small"
            :title="t('aiChat.copyMessage')"
            @click="emit('copyMessage', message.content)"
          >
            <el-icon><CopyDocument /></el-icon>
          </el-button>
        </div>
      </div>

      <div class="message-content">
        {{ message.content }}
      </div>

      <section
        v-if="message.role === 'assistant' && message.diagnosticMessage"
        class="diagnostic-box"
        :class="message.reasonCode || ''"
      >
        <div class="section-kicker">
          {{ getDiagnosticTitle(message.reasonCode) }}
        </div>
        <div>{{ message.diagnosticMessage }}</div>
      </section>

      <section
        v-if="message.role === 'assistant' && message.diagnostics"
        class="retrieval-box"
      >
        <div class="section-kicker">
          {{ t('aiChat.retrievalDiagnostics') }}
        </div>
        <div class="retrieval-meta">
          <span>{{ retrievalProfileLabel(message.diagnostics.retrieval_profile) }}</span>
          <span>{{ message.diagnostics.search_mode }}</span>
          <span>top_k {{ message.diagnostics.applied_top_k }}</span>
          <span>{{ t('aiChat.threshold') }} {{ message.diagnostics.applied_min_similarity }}</span>
        </div>
        <div class="retrieval-query">
          <strong>{{ t('aiChat.actualQuery') }}:</strong>{{ message.diagnostics.search_query }}
        </div>
        <div class="retrieval-meta">
          <span v-if="message.diagnostics.query_rewritten">{{ t('aiChat.queryRewritten') }}</span>
          <span>
            {{ t('aiChat.indexCoverage') }}
            {{ message.diagnostics.indexed_documents ?? 0 }}/{{ message.diagnostics.total_indexable_documents ?? 0 }}
          </span>
          <span>{{ t('aiChat.historyMsgs') }} {{ message.diagnostics.history_messages_used ?? 0 }}</span>
        </div>
      </section>

      <StrategyDraftCard
        v-if="message.role === 'assistant' && message.strategyDraft"
        :draft="message.strategyDraft"
        :saving="saving"
        :saved="saved"
        :added="added"
        :running-backtest="runningBacktest"
        :refreshing-status="refreshingStatus"
        :generating-report="generatingReport"
        :execution="execution"
        @save="emit('saveStrategy')"
        @add-to-workspace="emit('addToWorkspace')"
        @run-backtest="emit('runBacktest')"
        @refresh-execution="emit('refreshExecution')"
        @generate-report="emit('generateReport')"
        @copy-code="emit('copyCode')"
      />

      <StockAnalysisTaskCard
        v-if="message.role === 'assistant' && displayStockTask"
        :key="displayStockTask.task_id"
        :task="displayStockTask"
        @task-updated="handleStockTaskUpdated"
        @result-loaded="handleStockResultLoaded"
      />

      <StockAnalysisReportCard
        v-if="message.role === 'assistant' && displayStockReport"
        :report="displayStockReport"
        :knowledge-base-id="knowledgeBaseId"
        @continue-strategy-idea="prompt => emit('continueStrategyIdea', prompt)"
        @continue-backtrader-strategy="prompt => emit('continueBacktraderStrategy', prompt)"
      />

      <section
        v-if="message.role === 'assistant' && message.reasoning"
        class="reasoning-box"
      >
        <div class="section-kicker">
          {{ t('aiChat.analysisSummary') }}
        </div>
        <div>{{ message.reasoning }}</div>
      </section>

      <CitationList
        v-if="message.role === 'assistant' && message.citations?.length"
        :citations="message.citations"
        @jump="documentId => emit('jumpCitation', documentId)"
      />

      <section
        v-if="nextWorkflowActions.length"
        class="workflow-next-actions"
      >
        <span>{{ t('aiChat.workflowNextStep') }}</span>
        <el-button
          v-for="action in nextWorkflowActions"
          :key="`next-${action.key}`"
          size="small"
          :type="action.primary ? 'primary' : 'default'"
          :disabled="action.disabled"
          @click="emit('strategyWorkflowAction', action.key)"
        >
          <el-icon>
            <component :is="action.icon" />
          </el-icon>
          {{ action.nextLabel || action.label }}
        </el-button>
      </section>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  CopyDocument,
  Cpu,
  DataAnalysis,
  MagicStick,
  Promotion,
  Refresh,
  UserFilled,
} from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

import type { DraftWorkspaceExecutionState } from '@/composables/useStrategyDraftWorkspaceExecution'
import type { KBChatMessage } from '@/stores/kbChat'
import type { KBAssistantMode } from '@/api/kbChat'
import type { KBStockAnalysisReport, KBStockAnalysisTask } from '@/api/kbChat'
import type { StockAnalysisTask } from '@/api/stockAnalysis'
import {
  getDiagnosticTitle,
  getStrategyDraftIssue,
  retrievalProfileLabel,
} from '@/composables/useAIChatRendering'
import CitationList from './CitationList.vue'
import StrategyDraftCard from './StrategyDraftCard.vue'
import StockAnalysisReportCard from './StockAnalysisReportCard.vue'
import StockAnalysisTaskCard from './StockAnalysisTaskCard.vue'

const { t } = useI18n()

const props = defineProps<{
  message: KBChatMessage
  saving: boolean
  saved: boolean
  added: boolean
  runningBacktest: boolean
  refreshingStatus: boolean
  generatingReport: boolean
  execution?: DraftWorkspaceExecutionState
  knowledgeBaseId?: string | null
  strategyWorkflowEnabled?: boolean
}>()

type DisplayStockTask = KBStockAnalysisTask & { error_message?: string | null }
export type StrategyWorkflowActionKey = 'rethink' | 'regenerate' | 'backtest' | 'review' | 'optimize'

interface WorkflowAction {
  key: StrategyWorkflowActionKey
  label: string
  nextLabel?: string
  title: string
  icon: typeof MagicStick
  disabled?: boolean
  primary?: boolean
}

const localStockTask = ref<DisplayStockTask | null>(props.message.stockAnalysisTask ?? null)
const localStockReport = ref<KBStockAnalysisReport | null>(props.message.stockAnalysisReport ?? null)

const displayStockTask = computed<DisplayStockTask | null>(() => localStockTask.value)
const displayStockReport = computed<KBStockAnalysisReport | null>(() => localStockReport.value)
const strategyModes: KBAssistantMode[] = ['strategy_idea', 'backtrader_strategy', 'strategy_review']
const isStrategyWorkflowMessage = computed(() => (
  props.strategyWorkflowEnabled === true
  && props.message.role === 'assistant'
  && (
    Boolean(props.message.strategyDraft)
    || Boolean(props.execution)
    || strategyModes.includes(props.message.assistantMode as KBAssistantMode)
  )
))
const hasStrategyDraft = computed(() => Boolean(props.message.strategyDraft))
const hasBacktestResult = computed(() => (
  Boolean(props.execution?.report)
  || Boolean(props.execution?.analysis)
  || props.execution?.runStatus === 'completed'
))
const canOptimize = computed(() => (
  hasStrategyDraft.value
  || hasBacktestResult.value
  || props.message.assistantMode === 'strategy_review'
))
const workflowActionMap = computed<Record<StrategyWorkflowActionKey, WorkflowAction>>(() => ({
  rethink: {
    key: 'rethink',
    label: t('aiChat.workflowRethink'),
    nextLabel: t('aiChat.workflowNextIdea'),
    title: t('aiChat.workflowRethinkTitle'),
    icon: MagicStick,
  },
  regenerate: {
    key: 'regenerate',
    label: t('aiChat.workflowRegenerate'),
    nextLabel: t('aiChat.workflowNextGenerate'),
    title: t('aiChat.workflowRegenerateTitle'),
    icon: Refresh,
  },
  backtest: {
    key: 'backtest',
    label: t('aiChat.workflowRebacktest'),
    nextLabel: t('aiChat.workflowNextBacktest'),
    title: t('aiChat.workflowRebacktestTitle'),
    icon: Promotion,
    disabled: !hasStrategyDraft.value,
  },
  review: {
    key: 'review',
    label: t('aiChat.workflowRereview'),
    nextLabel: t('aiChat.workflowNextReview'),
    title: t('aiChat.workflowRereviewTitle'),
    icon: DataAnalysis,
  },
  optimize: {
    key: 'optimize',
    label: t('aiChat.workflowOptimize'),
    nextLabel: t('aiChat.workflowNextOptimize'),
    title: t('aiChat.workflowOptimizeTitle'),
    icon: MagicStick,
    disabled: !canOptimize.value,
  },
}))
const hoverWorkflowActions = computed<WorkflowAction[]>(() => {
  if (!isStrategyWorkflowMessage.value) return []
  return [
    workflowActionMap.value.rethink,
    workflowActionMap.value.regenerate,
    workflowActionMap.value.backtest,
    workflowActionMap.value.review,
    workflowActionMap.value.optimize,
  ]
})
const nextWorkflowActions = computed<WorkflowAction[]>(() => {
  if (!isStrategyWorkflowMessage.value) return []
  const assistantMode = props.message.assistantMode
  if (assistantMode === 'strategy_review') {
    return [
      { ...workflowActionMap.value.optimize, primary: true },
      workflowActionMap.value.regenerate,
      workflowActionMap.value.rethink,
    ]
  }
  if (hasBacktestResult.value) {
    return [
      { ...workflowActionMap.value.review, primary: true },
      workflowActionMap.value.optimize,
      workflowActionMap.value.regenerate,
    ]
  }
  if (assistantMode === 'strategy_idea' && !hasStrategyDraft.value) {
    return [
      { ...workflowActionMap.value.regenerate, primary: true },
      workflowActionMap.value.review,
    ]
  }
  if (hasStrategyDraft.value || assistantMode === 'backtrader_strategy') {
    return [
      { ...workflowActionMap.value.backtest, primary: true },
      workflowActionMap.value.review,
      workflowActionMap.value.optimize,
    ]
  }
  return [
    { ...workflowActionMap.value.regenerate, primary: true },
    workflowActionMap.value.review,
  ]
})

watch(
  () => props.message.stockAnalysisTask,
  (task) => {
    localStockTask.value = task ?? null
  },
)

watch(
  () => props.message.stockAnalysisReport,
  (report) => {
    localStockReport.value = report ?? null
  },
)

function normalizeStockTask(task: StockAnalysisTask): DisplayStockTask {
  return {
    task_id: task.task_id,
    symbol: task.symbol,
    status: task.status,
    progress: task.progress,
    current_step: task.current_step,
    message: task.message,
    error_message: task.error_message,
  }
}

function handleStockTaskUpdated(task: StockAnalysisTask) {
  localStockTask.value = normalizeStockTask(task)
}

function handleStockResultLoaded(report: KBStockAnalysisReport) {
  localStockReport.value = report
}

const emit = defineEmits<{
  copyMessage: [content: string]
  saveStrategy: []
  addToWorkspace: []
  runBacktest: []
  refreshExecution: []
  generateReport: []
  copyCode: []
  jumpCitation: [documentId?: string | null]
  continueStrategyIdea: [prompt: string]
  continueBacktraderStrategy: [prompt: string]
  strategyWorkflowAction: [action: StrategyWorkflowActionKey]
}>()
</script>

<style scoped lang="scss">
.message-card {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  gap: 12px;
  margin-bottom: 18px;
}

.message-card.user {
  grid-template-columns: minmax(0, 1fr) 38px;
}

.message-card.user .message-avatar {
  grid-column: 2;
  grid-row: 1;
  background: color-mix(in srgb, var(--bg-color) 86%, var(--fill-color-light) 14%);
  color: var(--text-color-regular);
}

.message-card.user .message-body {
  grid-column: 1;
  grid-row: 1;
}

.message-card.user .message-head {
  flex-direction: row-reverse;
}

.message-card.user .message-content {
  background: color-mix(in srgb, var(--bg-color) 88%, var(--fill-color-light) 12%);
}

.message-avatar {
  display: inline-flex;
  width: 38px;
  height: 38px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-color) 76%, var(--primary-color) 24%);
  color: var(--primary-color);
}

.message-body {
  min-width: 0;
}

.message-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.message-head-actions,
.workflow-hover-actions,
.workflow-next-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.workflow-hover-actions {
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.16s ease;
}

.message-card.assistant:hover .workflow-hover-actions,
.message-card.assistant:focus-within .workflow-hover-actions {
  opacity: 1;
  pointer-events: auto;
}

.message-author {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-color-primary);
}

.message-badge {
  margin-left: 8px;
  border-radius: 9999px;
  background: color-mix(in srgb, var(--bg-color) 78%, var(--primary-color) 22%);
  padding: 3px 8px;
  color: var(--primary-color);
  font-size: 12px;
}

.message-badge.success {
  background: color-mix(in srgb, var(--bg-color) 78%, var(--success-color) 22%);
  color: var(--success-text-color);
}

.message-badge.warning {
  background: color-mix(in srgb, var(--bg-color) 78%, var(--warning-color) 22%);
  color: var(--warning-text-color);
}

.message-content {
  margin-top: 8px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  padding: 13px 14px;
  color: var(--text-color-primary);
  font-size: 15px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

.diagnostic-box,
.retrieval-box,
.reasoning-box {
  margin-top: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  padding: 12px;
}

.section-kicker {
  font-size: 12px;
  font-weight: 700;
  color: var(--primary-color);
  text-transform: uppercase;
}

.reasoning-box {
  background: color-mix(in srgb, var(--bg-color) 84%, var(--warning-color) 16%);
  color: var(--warning-text-color);
}

.diagnostic-box {
  border-color: color-mix(in srgb, var(--warning-color) 44%, var(--border-color) 56%);
  background: color-mix(in srgb, var(--bg-color) 84%, var(--warning-color) 16%);
  color: var(--warning-text-color);
  font-size: 13px;
  line-height: 1.7;
}

.diagnostic-box.ai_provider_failed {
  border-color: color-mix(in srgb, var(--danger-color) 44%, var(--border-color) 56%);
  background: color-mix(in srgb, var(--bg-color) 84%, var(--danger-color) 16%);
  color: var(--danger-text-color);
}

.retrieval-box {
  border-color: color-mix(in srgb, var(--primary-color) 38%, var(--border-color) 62%);
  background: color-mix(in srgb, var(--bg-color) 84%, var(--primary-color) 16%);
  color: var(--text-color-primary);
}

.retrieval-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.retrieval-meta span {
  border-radius: 9999px;
  background: color-mix(in srgb, var(--bg-color) 76%, var(--primary-color) 24%);
  padding: 3px 8px;
  color: var(--primary-color);
  font-size: 12px;
}

.retrieval-query {
  margin-top: 8px;
  line-height: 1.7;
}

.workflow-next-actions {
  margin-top: 12px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 38%, var(--border-color) 62%);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-color) 84%, var(--primary-color) 16%);
  padding: 10px 12px;
}

.workflow-next-actions span {
  color: var(--text-color-primary);
  font-size: 12px;
  font-weight: 700;
}
</style>
