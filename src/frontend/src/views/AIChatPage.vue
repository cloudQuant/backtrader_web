<template>
  <div
    class="ai-chat-page"
    data-test="ai-chat-page"
  >
    <section
      class="ai-hero"
      data-test="ai-chat-hero"
    >
      <div class="hero-copy">
        <div class="eyebrow">
          {{ t('aiChat.heroKicker') }}
        </div>
        <h1>{{ t('aiChat.heroTitle') }}</h1>
        <p>
          {{ t('aiChat.heroSubtitle') }}
        </p>
        <div
          class="hero-metrics"
          data-test="ai-chat-metrics"
        >
          <article class="hero-metric">
            <span>{{ t('aiChat.heroKnowledgeBases') }}</span>
            <strong>{{ kbStore.knowledgeBases.length }}</strong>
          </article>
          <article class="hero-metric">
            <span>{{ t('aiChat.heroDocuments') }}</span>
            <strong>{{ currentKnowledgeBase?.document_count ?? 0 }}</strong>
          </article>
          <article class="hero-metric">
            <span>{{ t('aiChat.heroIndexed') }}</span>
            <strong>{{ indexedDocumentCount }}/{{ knowledgeBaseDocuments.length }}</strong>
          </article>
          <article class="hero-metric">
            <span>{{ t('aiChat.heroSessions') }}</span>
            <strong>{{ chatStore.conversations.length }}</strong>
          </article>
        </div>
      </div>

      <div class="hero-command">
        <div class="hero-command__header">
          <span
            class="status-dot"
            :class="{ active: Boolean(currentKnowledgeBaseId) }"
          />
          <div>
            <strong>{{ t('aiChat.retrievalStatusTitle') }}</strong>
            <span>{{ currentKnowledgeBaseId ? t('aiChat.retrievalReady') : t('aiChat.retrievalMissing') }}</span>
          </div>
        </div>
        <div
          v-if="requiresKnowledgeBase"
          class="control-label hero-kb-select"
        >
          <span>{{ t('aiChat.knowledgeBase') }}</span>
          <el-select
            v-model="selectedKnowledgeBaseId"
            :placeholder="t('aiChat.selectKnowledgeBasePrompt')"
            :aria-label="t('aiChat.knowledgeBase')"
          >
            <el-option
              v-for="kb in kbStore.knowledgeBases"
              :key="kb.id"
              :label="kb.name"
              :value="kb.id"
            />
          </el-select>
        </div>
        <div
          v-else
          class="control-label standalone-mode-label"
        >
          <span>{{ t('aiChat.contextSource') }}</span>
          <el-tag type="info">
            {{ t('aiChat.noKnowledgeBaseRequired') }}
          </el-tag>
        </div>
        <el-button
          :aria-label="t('aiChat.newConversationShort')"
          @click="handleNewConversation"
        >
          <el-icon aria-hidden="true">
            <Plus />
          </el-icon>
          {{ t('aiChat.newConversationShort') }}
        </el-button>
      </div>
    </section>

    <section
      class="mode-strip"
      data-test="ai-chat-toolbar"
    >
      <div class="mode-strip__label">
        {{ t('aiChat.modeStripLabel') }}
      </div>
      <div class="mode-tabs">
        <button
          v-for="option in assistantModeOptions"
          :key="option.value"
          type="button"
          class="mode-tab"
          :class="{ active: isAssistantModeTabActive(option.value) }"
          @click="selectAssistantMode(option.value)"
        >
          <el-icon aria-hidden="true">
            <Collection />
          </el-icon>
          {{ option.label }}
        </button>
      </div>
      <div class="thinking-toggle">
        <el-switch
          v-model="thinkingMode"
          size="small"
          :aria-label="t('aiChat.deepMode')"
        />
        <span>{{ t('aiChat.deepMode') }}</span>
      </div>
    </section>

    <div
      class="workspace-grid"
      :class="{
        'left-collapsed': leftPanelCollapsed,
        'right-collapsed': rightPanelCollapsed,
      }"
    >
      <aside
        ref="conversationPanel"
        class="ai-panel conversation-panel"
        :class="{
          collapsed: leftPanelCollapsed,
          'mobile-open': mobilePanel === 'conversations',
        }"
        :role="mobilePanel === 'conversations' ? 'dialog' : undefined"
        :aria-modal="mobilePanel === 'conversations' ? 'true' : undefined"
        :aria-label="mobilePanel === 'conversations' ? t('aiChat.conversations') : undefined"
        data-test="ai-chat-conversations"
        @keydown="handleMobilePanelKeydown"
      >
        <button
          v-if="leftPanelCollapsed"
          type="button"
          class="collapsed-panel-toggle"
          :aria-label="t('aiChat.expandConversations')"
          @click="toggleLeftPanel"
        >
          <el-icon aria-hidden="true">
            <Expand />
          </el-icon>
          <span>{{ t('aiChat.conversations') }}</span>
        </button>

        <template v-else>
          <div class="panel-header">
            <div>
              <div class="panel-title">
                {{ t('aiChat.conversations') }}
              </div>
              <div class="panel-subtitle">
                {{ chatStore.conversations.length }} {{ t('aiChat.counter') }}
              </div>
            </div>
            <div class="panel-header-actions">
              <button
                v-if="mobilePanel === 'conversations'"
                ref="conversationPanelClose"
                type="button"
                class="mobile-panel-close"
                :aria-label="t('aiChat.closeMobilePanel')"
                @click="closeMobilePanel"
              >
                <el-icon aria-hidden="true">
                  <Close />
                </el-icon>
              </button>
              <el-button
                circle
                size="small"
                :title="t('aiChat.newConversation')"
                :aria-label="t('aiChat.newConversation')"
                @click="handleNewConversation"
              >
                <el-icon aria-hidden="true">
                  <Plus />
                </el-icon>
              </el-button>
              <el-button
                circle
                size="small"
                :title="t('aiChat.collapseConversations')"
                :aria-label="t('aiChat.collapseConversations')"
                @click="toggleLeftPanel"
              >
                <el-icon aria-hidden="true">
                  <Fold />
                </el-icon>
              </el-button>
            </div>
          </div>

          <el-input
            v-model="conversationSearch"
            :placeholder="t('aiChat.searchConversations')"
            :aria-label="t('aiChat.searchConversations')"
            :prefix-icon="Search"
            clearable
            class="conversation-search"
          />

          <div
            v-if="filteredConversations.length === 0"
            class="empty-rail"
          >
            <el-icon><ChatDotRound /></el-icon>
            <span>{{ t('aiChat.noConversations') }}</span>
          </div>

          <div
            v-else
            class="conversation-list"
          >
            <button
              v-for="conversation in filteredConversations"
              :key="conversation.id"
              type="button"
              class="conversation-item"
              :class="{ active: conversation.id === chatStore.currentConversationId }"
              @click="handleSelectConversation(conversation.id)"
            >
              <span class="conversation-title">{{ conversation.title }}</span>
              <span class="conversation-meta">{{ formatDate(conversation.updated_at) }}</span>
            </button>
          </div>
        </template>
      </aside>

      <main class="chat-shell">
        <div class="chat-topbar">
          <div class="chat-context">
            <span class="context-icon"><el-icon><Collection /></el-icon></span>
            <div class="min-w-0">
              <div class="context-title">
                {{ displayContextTitle }}
              </div>
              <div class="context-meta">
                {{ currentModeMeta.label }}
                <span v-if="thinkingMode">/ {{ t('aiChat.deepMode') }}</span>
                <span v-if="requiresKnowledgeBase && currentKnowledgeBaseId">/ {{ retrievalProfileLabel(currentKnowledgeBaseSettings.retrieval_profile) }}</span>
                <span v-if="chatStore.currentConversationId">/ {{ t('aiChat.sessionInProgress') }}</span>
              </div>
            </div>
          </div>

          <div class="chat-actions">
            <el-button
              v-if="chatStore.messages.length > 0"
              size="small"
              @click="copyConversation"
            >
              <el-icon><CopyDocument /></el-icon>
              {{ t('aiChat.copyConversation') }}
            </el-button>
            <el-button
              v-if="chatStore.messages.length > 0"
              size="small"
              type="danger"
              @click="handleNewConversation"
            >
              <el-icon><Delete /></el-icon>
              {{ t('aiChat.clearConversation') }}
            </el-button>
          </div>
          <div
            class="mobile-workspace-actions"
            :aria-label="t('aiChat.mobilePanelActions')"
          >
            <button
              type="button"
              data-test="ai-chat-open-conversations"
              :aria-expanded="mobilePanel === 'conversations'"
              aria-haspopup="dialog"
              @click="openMobilePanel('conversations', $event)"
            >
              <el-icon aria-hidden="true">
                <ChatDotRound />
              </el-icon>
              <span>{{ t('aiChat.conversations') }}</span>
            </button>
            <button
              type="button"
              data-test="ai-chat-open-context"
              :aria-expanded="mobilePanel === 'context'"
              aria-haspopup="dialog"
              @click="openMobilePanel('context', $event)"
            >
              <el-icon aria-hidden="true">
                <Collection />
              </el-icon>
              <span>{{ t('aiChat.contextPanel') }}</span>
            </button>
          </div>
        </div>

        <div class="message-scroll">
          <div
            v-if="chatStore.messages.length === 0 && !chatStore.loading"
            class="empty-chat"
          >
            <div class="empty-chat-icon">
              <el-icon><MagicStick /></el-icon>
            </div>
            <h3>{{ currentModeMeta.emptyTitle }}</h3>
            <p>{{ currentModeMeta.emptyDescription }}</p>
            <div class="prompt-grid">
              <button
                v-for="prompt in suggestedPrompts"
                :key="prompt"
                type="button"
                @click="applyPrompt(prompt)"
              >
                {{ prompt }}
              </button>
            </div>
          </div>

          <template v-else>
            <ChatMessageBubble
              v-for="(message, index) in chatStore.messages"
              :key="`${message.role}-${index}`"
              :message="message"
              :saving="savingStrategyIndex === index"
              :saved="Boolean(savedStrategyIds[index])"
              :added="Boolean(addedWorkspaceUnitIds[index])"
              :running-backtest="runningBacktestIndex === index"
              :refreshing-status="refreshingStatusIndex === index"
              :generating-report="generatingReportIndex === index"
              :execution="workspaceExecutions[index]"
              :knowledge-base-id="requiresKnowledgeBase ? selectedKnowledgeBaseId : null"
              :strategy-workflow-enabled="strategyWorkflowEnabled"
              @copy-message="copyMessage"
              @save-strategy="handleSaveStrategyDraft(message, index)"
              @add-to-workspace="openAddToWorkspaceDialog(message, index)"
              @run-backtest="handleRunStrategyDraftBacktest(index)"
              @refresh-execution="handleRefreshWorkspaceExecution(index)"
              @generate-report="handleGenerateWorkspaceReport(message, index)"
              @copy-code="copyMessage(message.strategyDraft?.code || '')"
              @jump-citation="handleJumpToCitation"
              @continue-strategy-idea="prompt => handleContinueFromStockAnalysis('strategy_idea', prompt)"
              @continue-backtrader-strategy="prompt => handleContinueFromStockAnalysis('backtrader_strategy', prompt)"
              @strategy-workflow-action="action => handleStrategyWorkflowAction(action, message, index)"
            />

            <div
              v-if="chatStore.loading"
              class="typing-line"
            >
              <span />
              <span />
              <span />
              {{ t('aiChat.aiThinking') }}
            </div>
          </template>
        </div>

        <div class="composer">
          <div class="composer-meta">
            <span>{{ composerHint }}</span>
            <span>{{ question.length }}/500</span>
          </div>
          <div class="composer-row">
            <el-input
              v-model="question"
              data-test="ai-chat-input"
              type="textarea"
              :maxlength="500"
              :disabled="(requiresKnowledgeBase && !currentKnowledgeBaseId) || chatStore.loading"
              :placeholder="inputPlaceholder"
              :aria-label="inputPlaceholder"
              :rows="3"
              resize="vertical"
              @keydown.enter.exact.prevent="handleAsk"
            />
            <el-select
              v-model="selectedSessionModelKey"
              class="session-model-select"
              :placeholder="t('aiChat.defaultModel')"
              :aria-label="t('aiChat.modelLabel')"
            >
              <el-option
                :label="t('aiChat.defaultModel')"
                value=""
              />
              <el-option
                v-for="model in sessionModelOptions"
                :key="`${model.provider}::${model.model}`"
                :label="model.display_name"
                :value="`${model.provider}::${model.model}`"
              />
            </el-select>
            <el-button
              type="primary"
              :disabled="!canSubmitQuestion"
              class="send-button"
              data-test="ai-chat-send"
              @click="handleAsk"
            >
              <el-icon><Promotion /></el-icon>
              {{ chatStore.loading ? t('aiChat.sending') : t('aiChat.sendButton') }}
            </el-button>
          </div>
        </div>
      </main>

      <aside
        ref="contextPanel"
        class="ai-panel insight-panel"
        :class="{
          collapsed: rightPanelCollapsed,
          'mobile-open': mobilePanel === 'context',
        }"
        :role="mobilePanel === 'context' ? 'dialog' : undefined"
        :aria-modal="mobilePanel === 'context' ? 'true' : undefined"
        :aria-label="mobilePanel === 'context' ? t('aiChat.contextPanel') : undefined"
        data-test="ai-chat-context"
        @keydown="handleMobilePanelKeydown"
      >
        <button
          v-if="rightPanelCollapsed"
          type="button"
          class="collapsed-panel-toggle"
          :aria-label="t('aiChat.expandContextPanel')"
          @click="toggleRightPanel"
        >
          <el-icon aria-hidden="true">
            <Expand />
          </el-icon>
          <span>{{ t('aiChat.contextPanel') }}</span>
        </button>

        <template v-else>
          <div class="panel-header">
            <div>
              <div class="panel-title">
                {{ t('aiChat.contextPanel') }}
              </div>
              <div class="panel-subtitle">
                {{ currentModeMeta.label }}
              </div>
            </div>
            <div class="panel-header-actions">
              <button
                v-if="mobilePanel === 'context'"
                ref="contextPanelClose"
                type="button"
                class="mobile-panel-close"
                :aria-label="t('aiChat.closeMobilePanel')"
                @click="closeMobilePanel"
              >
                <el-icon aria-hidden="true">
                  <Close />
                </el-icon>
              </button>
              <span
                class="status-dot"
                :class="{ active: !requiresKnowledgeBase || Boolean(selectedKnowledgeBaseId) }"
              />
              <el-button
                circle
                size="small"
                :title="t('aiChat.collapseContextPanel')"
                :aria-label="t('aiChat.collapseContextPanel')"
                @click="toggleRightPanel"
              >
                <el-icon aria-hidden="true">
                  <Fold />
                </el-icon>
              </el-button>
            </div>
          </div>

          <div
            v-if="requiresKnowledgeBase"
            class="kb-card"
          >
            <div class="kb-name">
              {{ currentKnowledgeBaseName || t('aiChat.noKnowledgeBaseSelected') }}
            </div>
            <div class="kb-desc">
              {{ currentKnowledgeBase?.description || t('aiChat.startQAPrompt') }}
            </div>
            <div class="metric-grid">
              <div>
                <span>{{ t('aiChat.documentsLabel') }}</span>
                <strong>{{ currentKnowledgeBase?.document_count ?? 0 }}</strong>
              </div>
              <div>
                <span>{{ t('aiChat.loaded') }}</span>
                <strong>{{ knowledgeBaseDocuments.length }}</strong>
              </div>
              <div>
                <span>{{ t('aiChat.indexed') }}</span>
                <strong>{{ indexedDocumentCount }}</strong>
              </div>
            </div>
            <div class="kb-settings">
              <span>{{ retrievalProfileLabel(currentKnowledgeBaseSettings.retrieval_profile) }}</span>
              <span>{{ currentKnowledgeBaseSettings.search_mode }}</span>
              <span>top_k {{ currentKnowledgeBaseSettings.default_top_k }}</span>
              <span v-if="currentKnowledgeBaseSettings.use_conversation_memory">{{ t('aiChat.sessionMemoryOn') }}</span>
            </div>
            <div
              v-if="hasUnindexedDocuments"
              class="kb-index-warning"
            >
              <div>
                {{ t('aiChat.indexIncomplete') }}{{ t('aiChat.indexResultIncomplete') }}
                <span>{{ indexedDocumentCount }}/{{ knowledgeBaseDocuments.length }} {{ t('aiChat.indexed') }}</span>
              </div>
              <button
                type="button"
                class="inline-link"
                @click="goToReindex"
              >
                {{ t('aiChat.rebuildIndex') }}
              </button>
            </div>
            <el-button
              class="w-full mt-3"
              :disabled="!currentKnowledgeBaseId"
              @click="goToKnowledgeBase"
            >
              <el-icon aria-hidden="true">
                <Reading />
              </el-icon>
              {{ t('aiChat.openKnowledgeBase') }}
            </el-button>
          </div>

          <div
            v-else
            class="kb-card standalone-context-card"
          >
            <div class="kb-name">
              {{ t('aiChat.noKnowledgeBaseRequired') }}
            </div>
            <div class="kb-desc">
              {{ t('aiChat.standaloneModeDescription') }}
            </div>
            <div class="kb-settings">
              <span>{{ currentModeMeta.label }}</span>
              <span>{{ t('aiChat.modelOnlyContext') }}</span>
              <span v-if="thinkingMode">{{ t('aiChat.deepMode') }}</span>
            </div>
          </div>

          <div class="tool-section">
            <div class="section-kicker">
              {{ t('aiChat.quickTools') }}
            </div>
            <button
              v-for="tool in quickTools"
              :key="tool.title"
              type="button"
              class="tool-item"
              @click="applyQuickTool(tool)"
            >
              <el-icon><Compass /></el-icon>
              <span>
                <strong>{{ tool.title }}</strong>
                <small>{{ tool.description }}</small>
              </span>
            </button>
          </div>
        </template>
      </aside>
    </div>

    <button
      v-if="mobilePanel"
      type="button"
      class="mobile-panel-backdrop"
      tabindex="-1"
      :aria-label="t('aiChat.closeMobilePanel')"
      @click="closeMobilePanel"
    />

    <el-dialog
      v-model="showAddToWorkspaceDialog"
      :title="t('aiChat.addStrategyDraftToWorkspace')"
      width="520px"
    >
      <div class="dialog-form">
        <el-form-item :label="t('aiChat.workspaceLabel')">
          <el-select
            v-model="workspaceDraftForm.workspaceId"
            :placeholder="t('aiChat.selectWorkspacePrompt')"
            class="w-full"
          >
            <el-option
              v-for="workspace in researchWorkspaces"
              :key="workspace.id"
              :label="workspace.name"
              :value="workspace.id"
            />
          </el-select>
        </el-form-item>

        <div class="dialog-grid">
          <el-form-item :label="t('aiChat.symbolCode')">
            <el-input
              v-model="workspaceDraftForm.symbol"
              :placeholder="t('aiChat.examplePlaceholder') + ' 600519.SH'"
            />
          </el-form-item>
          <el-form-item :label="t('aiChat.symbolName')">
            <el-input
              v-model="workspaceDraftForm.symbolName"
              :placeholder="t('aiChat.examplePlaceholder') + ' ' + t('aiChat.sampleSymbolName')"
            />
          </el-form-item>
        </div>

        <div class="dialog-grid">
          <el-form-item :label="t('aiChat.timeframe')">
            <el-select
              v-model="workspaceDraftForm.timeframe"
              class="w-full"
            >
              <el-option
                label="1m"
                value="1m"
              />
              <el-option
                label="5m"
                value="5m"
              />
              <el-option
                label="15m"
                value="15m"
              />
              <el-option
                label="30m"
                value="30m"
              />
              <el-option
                label="1h"
                value="1h"
              />
              <el-option
                label="1d"
                value="1d"
              />
              <el-option
                label="1w"
                value="1w"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('aiChat.groupName')">
            <el-input
              v-model="workspaceDraftForm.groupName"
              :placeholder="t('aiChat.examplePlaceholder') + ' ' + t('aiChat.strategyDraftCard')"
            />
          </el-form-item>
        </div>

        <div
          v-if="researchWorkspaces.length === 0"
          class="dialog-warning"
        >
          {{ t('aiChat.noWorkspaceAvailable') }} {{ t('aiChat.createWorkspaceFirst') }}
        </div>
      </div>

      <template #footer>
        <div class="dialog-actions">
          <el-button
            v-if="researchWorkspaces.length === 0"
            @click="router.push({ name: 'ResearchWorkspaces' })"
          >
            {{ t('aiChat.goCreateWorkspace') }}
          </el-button>
          <el-button @click="resetWorkspaceDraftState">
            {{ t('aiChat.cancel') }}
          </el-button>
          <el-button
            type="primary"
            :loading="addingToWorkspace"
            @click="handleConfirmAddToWorkspace()"
          >
            {{ t('aiChat.confirmAdd') }}
          </el-button>
          <el-button
            type="primary"
            :loading="addingToWorkspace"
            @click="handleConfirmAddToWorkspace(true)"
          >
            {{ t('aiChat.addAndBacktest') }}
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ChatDotRound,
  Close,
  Collection,
  Compass,
  CopyDocument,
  Delete,
  Expand,
  Fold,
  MagicStick,
  Plus,
  Promotion,
  Reading,
  Search,
} from '@element-plus/icons-vue'
import ChatMessageBubble from '@/components/aichat/ChatMessageBubble.vue'
import { useAIChatPage } from '@/composables/useAIChatPage'

const { t } = useI18n()

type MobilePanel = 'conversations' | 'context'

const mobilePanel = ref<MobilePanel | null>(null)
const conversationPanel = ref<HTMLElement | null>(null)
const contextPanel = ref<HTMLElement | null>(null)
const conversationPanelClose = ref<HTMLButtonElement | null>(null)
const contextPanelClose = ref<HTMLButtonElement | null>(null)
let mobilePanelTrigger: HTMLElement | null = null

function getMobilePanelRoot(panel: MobilePanel): HTMLElement | null {
  return panel === 'conversations' ? conversationPanel.value : contextPanel.value
}

function getMobilePanelCloseButton(panel: MobilePanel): HTMLButtonElement | null {
  return panel === 'conversations' ? conversationPanelClose.value : contextPanelClose.value
}

async function openMobilePanel(panel: MobilePanel, event: MouseEvent) {
  mobilePanelTrigger = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  if (panel === 'conversations') {
    leftPanelCollapsed.value = false
  } else {
    rightPanelCollapsed.value = false
  }
  mobilePanel.value = panel
  await nextTick()
  getMobilePanelCloseButton(panel)?.focus()
}

function closeMobilePanel() {
  mobilePanel.value = null
  void nextTick(() => mobilePanelTrigger?.focus())
}

function handleMobilePanelKeydown(event: KeyboardEvent) {
  if (!mobilePanel.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closeMobilePanel()
    return
  }
  if (event.key !== 'Tab') return

  const panel = getMobilePanelRoot(mobilePanel.value)
  const focusable = panel
    ? Array.from(panel.querySelectorAll<HTMLElement>(
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

const {
  kbStore,
  chatStore,
  router,
  selectedKnowledgeBaseId,
  thinkingMode,
  leftPanelCollapsed,
  rightPanelCollapsed,
  conversationSearch,
  question,
  selectedSessionModelKey,
  sessionModelOptions,
  savingStrategyIndex,
  savedStrategyIds,
  addedWorkspaceUnitIds,
  showAddToWorkspaceDialog,
  researchWorkspaces,
  addingToWorkspace,
  workspaceDraftForm,
  workspaceExecutions,
  runningBacktestIndex,
  refreshingStatusIndex,
  generatingReportIndex,
  currentModeMeta,
  requiresKnowledgeBase,
  suggestedPrompts,
  quickTools,
  inputPlaceholder,
  currentKnowledgeBase,
  currentKnowledgeBaseId,
  currentKnowledgeBaseName,
  displayContextTitle,
  composerHint,
  canSubmitQuestion,
  strategyWorkflowEnabled,
  currentKnowledgeBaseSettings,
  knowledgeBaseDocuments,
  indexedDocumentCount,
  hasUnindexedDocuments,
  filteredConversations,
  assistantModeOptions,
  formatDate,
  retrievalProfileLabel,
  applyPrompt,
  applyQuickTool,
  isAssistantModeTabActive,
  selectAssistantMode,
  handleContinueFromStockAnalysis,
  toggleLeftPanel,
  toggleRightPanel,
  copyMessage,
  copyConversation,
  resetWorkspaceDraftState,
  handleSaveStrategyDraft,
  openAddToWorkspaceDialog,
  handleConfirmAddToWorkspace,
  handleRunStrategyDraftBacktest,
  handleRefreshWorkspaceExecution,
  handleGenerateWorkspaceReport,
  handleStrategyWorkflowAction,
  handleAsk,
  handleSelectConversation,
  handleNewConversation,
  handleJumpToCitation,
  goToKnowledgeBase,
  goToReindex,
} = useAIChatPage()
</script>

<style scoped lang="scss" src="./AIChatPage.styles.scss"></style>
