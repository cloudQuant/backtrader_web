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
          <span class="message-author">{{ message.role === 'assistant' ? 'AI 助手' : '你' }}</span>
          <span
            v-if="message.role === 'assistant' && message.citations?.length"
            class="message-badge"
          >
            {{ message.citations.length }} 条引用
          </span>
          <span
            v-if="message.role === 'assistant' && message.strategyDraft"
            class="message-badge"
            :class="{
              success: !getStrategyDraftIssue(message.strategyDraft),
              warning: Boolean(getStrategyDraftIssue(message.strategyDraft)),
            }"
          >
            {{ getStrategyDraftIssue(message.strategyDraft) ? '草稿待补全' : '可保存为策略' }}
          </span>
        </div>
        <el-button
          circle
          size="small"
          title="复制消息"
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
          检索诊断
        </div>
        <div class="retrieval-meta">
          <span>{{ retrievalProfileLabel(message.diagnostics.retrieval_profile) }}</span>
          <span>{{ message.diagnostics.search_mode }}</span>
          <span>top_k {{ message.diagnostics.applied_top_k }}</span>
          <span>阈值 {{ message.diagnostics.applied_min_similarity }}</span>
        </div>
        <div class="retrieval-query">
          <strong>实际检索查询：</strong>{{ message.diagnostics.search_query }}
        </div>
        <div class="retrieval-meta">
          <span v-if="message.diagnostics.query_rewritten">已重写查询</span>
          <span>
            索引覆盖
            {{ message.diagnostics.indexed_documents ?? 0 }}/{{ message.diagnostics.total_indexable_documents ?? 0 }}
          </span>
          <span>历史消息 {{ message.diagnostics.history_messages_used ?? 0 }}</span>
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

      <section
        v-if="message.role === 'assistant' && message.reasoning"
        class="reasoning-box"
      >
        <div class="section-kicker">
          分析摘要
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
import { CopyDocument, Cpu, UserFilled } from '@element-plus/icons-vue'

import type { DraftWorkspaceExecutionState } from '@/composables/useStrategyDraftWorkspaceExecution'
import type { KBChatMessage } from '@/stores/kbChat'
import {
  getDiagnosticTitle,
  getStrategyDraftIssue,
  retrievalProfileLabel,
} from '@/composables/useAIChatRendering'
import CitationList from './CitationList.vue'
import StrategyDraftCard from './StrategyDraftCard.vue'

defineProps<{
  message: KBChatMessage
  saving: boolean
  saved: boolean
  added: boolean
  runningBacktest: boolean
  refreshingStatus: boolean
  generatingReport: boolean
  execution?: DraftWorkspaceExecutionState
}>()

const emit = defineEmits<{
  copyMessage: [content: string]
  saveStrategy: []
  addToWorkspace: []
  runBacktest: []
  refreshExecution: []
  generateReport: []
  copyCode: []
  jumpCitation: [documentId?: string | null]
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
