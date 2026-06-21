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
        <el-button
          circle
          size="small"
          :title="t('aiChat.copyMessage')"
          @click="emit('copyMessage', message.content)"
        >
          <el-icon><CopyDocument /></el-icon>
        </el-button>
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
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { CopyDocument, Cpu, UserFilled } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

import type { DraftWorkspaceExecutionState } from '@/composables/useStrategyDraftWorkspaceExecution'
import type { KBChatMessage } from '@/stores/kbChat'
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
}>()

type DisplayStockTask = KBStockAnalysisTask & { error_message?: string | null }

const localStockTask = ref<DisplayStockTask | null>(props.message.stockAnalysisTask ?? null)
const localStockReport = ref<KBStockAnalysisReport | null>(props.message.stockAnalysisReport ?? null)

const displayStockTask = computed<DisplayStockTask | null>(() => localStockTask.value)
const displayStockReport = computed<KBStockAnalysisReport | null>(() => localStockReport.value)

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
  background: var(--bg-color-hover);
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
  background: var(--bg-color-hover);
}

.message-avatar {
  display: inline-flex;
  width: 38px;
  height: 38px;
  align-items: center;
  justify-content: center;
  border-radius: var(--el-border-radius-base);
  background: var(--info-surface);
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

.message-author {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-color-primary);
}

.message-badge {
  margin-left: 8px;
  border-radius: 9999px;
  background: var(--info-surface);
  padding: 3px 8px;
  color: var(--primary-color);
  font-size: 12px;
}

.message-badge.success {
  background: var(--success-surface);
  color: var(--success-text-color);
}

.message-badge.warning {
  background: var(--warning-surface);
  color: var(--warning-text-color);
}

.message-content {
  margin-top: 8px;
  border: 1px solid var(--border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-card);
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
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-card);
  padding: 12px;
}

.section-kicker {
  font-size: 12px;
  font-weight: 700;
  color: var(--primary-color);
  text-transform: uppercase;
}

.reasoning-box {
  background: var(--warning-surface);
  color: var(--warning-text-color);
}

.diagnostic-box {
  border-color: var(--warning-border-color);
  background: var(--warning-surface);
  color: var(--warning-text-color);
  font-size: 13px;
  line-height: 1.7;
}

.diagnostic-box.ai_provider_failed {
  border-color: var(--danger-border-color);
  background: var(--danger-surface);
  color: var(--danger-text-color);
}

.retrieval-box {
  border-color: var(--info-border-color);
  background: var(--info-surface);
  color: var(--info-text-color);
}

.retrieval-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.retrieval-meta span {
  border-radius: 9999px;
  background: var(--color-primary-100);
  padding: 3px 8px;
  color: var(--primary-color);
  font-size: 12px;
}

.retrieval-query {
  margin-top: 8px;
  line-height: 1.7;
}
</style>
