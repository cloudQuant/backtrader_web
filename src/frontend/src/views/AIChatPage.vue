<template>
  <div class="ai-chat-page">
    <section class="ai-hero">
      <div class="min-w-0">
        <div class="eyebrow">
          AI Copilot
        </div>
        <h2>{{ t('nav.aiChat') }}</h2>
        <p>
          {{ t('aiChat.aroundKnowledgeBase') }}, Backtrader {{ t('aiChat.draftAndStrategyReview') }}. {{ t('aiChat.citationActionHint') }}
        </p>
      </div>

      <div class="hero-controls">
        <div class="control-label">
          <span>{{ t('aiChat.knowledgeBase') }}</span>
          <el-select
            v-model="selectedKnowledgeBaseId"
            :placeholder="t('aiChat.selectKnowledgeBasePrompt')"
            style="min-width: 240px"
          >
            <el-option
              v-for="kb in kbStore.knowledgeBases"
              :key="kb.id"
              :label="kb.name"
              :value="kb.id"
            />
          </el-select>
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

    <section class="mode-strip">
      <button
        v-for="option in assistantModeOptions"
        :key="option.value"
        type="button"
        class="mode-tab"
        :class="{ active: selectedAssistantMode === option.value }"
        @click="selectedAssistantMode = option.value"
      >
        {{ option.label }}
      </button>
      <div class="thinking-toggle">
        <el-switch
          v-model="thinkingMode"
          size="small"
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
        class="ai-panel conversation-panel"
        :class="{ collapsed: leftPanelCollapsed }"
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
                {{ currentKnowledgeBaseName || t('aiChat.noKnowledgeBaseSelected') }}
              </div>
              <div class="context-meta">
                {{ currentModeMeta.label }}
                <span v-if="thinkingMode">/ {{ t('aiChat.deepMode') }}</span>
                <span v-if="currentKnowledgeBaseId">/ {{ retrievalProfileLabel(currentKnowledgeBaseSettings.retrieval_profile) }}</span>
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
              :knowledge-base-id="selectedKnowledgeBaseId"
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
            <span>{{ selectedKnowledgeBaseId ? currentModeMeta.inputHint : t('aiChat.selectKnowledgeBaseFirst') }}</span>
            <span>{{ question.length }}/500</span>
          </div>
          <div class="composer-row">
            <el-input
              v-model="question"
              type="textarea"
              :maxlength="500"
              :disabled="!selectedKnowledgeBaseId || chatStore.loading"
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
              :disabled="!selectedKnowledgeBaseId || !question.trim() || chatStore.loading"
              class="send-button"
              @click="handleAsk"
            >
              <el-icon><Promotion /></el-icon>
              {{ chatStore.loading ? t('aiChat.sending') : t('aiChat.sendButton') }}
            </el-button>
          </div>
        </div>
      </main>

      <aside
        class="ai-panel insight-panel"
        :class="{ collapsed: rightPanelCollapsed }"
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
              <span
                class="status-dot"
                :class="{ active: Boolean(selectedKnowledgeBaseId) }"
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

          <div class="kb-card">
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
            v-if="selectedAssistantMode === 'stock_analysis'"
            class="stock-analysis-panel"
          >
            <div class="section-kicker">
              {{ t('aiChat.stockPanelTitle') }}
            </div>
            <div class="stock-form-grid">
              <label>
                <span>{{ t('aiChat.symbolCode') }}</span>
                <el-input
                  v-model="stockAnalysisForm.symbol"
                  size="small"
                  placeholder="000001.SZ"
                />
              </label>
              <label>
                <span>{{ t('aiChat.stockMarketType') }}</span>
                <el-select
                  v-model="stockAnalysisForm.marketType"
                  size="small"
                  class="w-full"
                >
                  <el-option
                    :label="t('aiChat.stockMarketA')"
                    value="cn_a"
                  />
                  <el-option
                    :label="t('aiChat.stockMarketHK')"
                    value="hk"
                  />
                  <el-option
                    :label="t('aiChat.stockMarketUS')"
                    value="us"
                  />
                </el-select>
              </label>
              <label>
                <span>{{ t('aiChat.stockAnalysisDate') }}</span>
                <el-date-picker
                  v-model="stockAnalysisForm.analysisDate"
                  type="date"
                  value-format="YYYY-MM-DD"
                  size="small"
                  class="w-full"
                />
              </label>
              <label>
                <span>{{ t('aiChat.stockResearchDepth') }}</span>
                <el-select
                  v-model="stockAnalysisForm.researchDepth"
                  size="small"
                  class="w-full"
                >
                  <el-option
                    :label="t('aiChat.stockDepthQuick')"
                    value="quick"
                  />
                  <el-option
                    :label="t('aiChat.stockDepthBasic')"
                    value="basic"
                  />
                  <el-option
                    :label="t('aiChat.stockDepthStandard')"
                    value="standard"
                  />
                  <el-option
                    :label="t('aiChat.stockDepthDeep')"
                    value="deep"
                  />
                  <el-option
                    :label="t('aiChat.stockDepthFull')"
                    value="full"
                  />
                </el-select>
              </label>
            </div>
            <el-checkbox-group
              v-model="stockAnalysisForm.modules"
              class="stock-module-grid"
            >
              <el-checkbox label="market">
                {{ t('aiChat.stockModuleMarket') }}
              </el-checkbox>
              <el-checkbox label="fundamentals">
                {{ t('aiChat.stockModuleFundamentals') }}
              </el-checkbox>
              <el-checkbox label="news">
                {{ t('aiChat.stockModuleNews') }}
              </el-checkbox>
              <el-checkbox label="social">
                {{ t('aiChat.stockModuleSentiment') }}
              </el-checkbox>
              <el-checkbox label="risk">
                {{ t('aiChat.stockModuleRisk') }}
              </el-checkbox>
            </el-checkbox-group>
            <el-button
              class="w-full"
              type="primary"
              :disabled="!currentKnowledgeBaseId || chatStore.loading"
              @click="handleStockAnalysisSubmit"
            >
              <el-icon><Promotion /></el-icon>
              {{ t('aiChat.stockStartAnalysis') }}
            </el-button>
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
              @click="applyPrompt(tool.prompt)"
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
            @click="router.push({ name: 'WorkspaceList' })"
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
import { useI18n } from 'vue-i18n'
import {
  ChatDotRound,
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

const {
  kbStore,
  chatStore,
  router,
  selectedKnowledgeBaseId,
  selectedAssistantMode,
  thinkingMode,
  leftPanelCollapsed,
  rightPanelCollapsed,
  conversationSearch,
  question,
  selectedSessionModelKey,
  stockAnalysisForm,
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
  suggestedPrompts,
  quickTools,
  inputPlaceholder,
  currentKnowledgeBase,
  currentKnowledgeBaseId,
  currentKnowledgeBaseName,
  currentKnowledgeBaseSettings,
  knowledgeBaseDocuments,
  indexedDocumentCount,
  hasUnindexedDocuments,
  filteredConversations,
  assistantModeOptions,
  formatDate,
  retrievalProfileLabel,
  applyPrompt,
  handleContinueFromStockAnalysis,
  toggleLeftPanel,
  toggleRightPanel,
  copyMessage,
  copyConversation,
  handleStockAnalysisSubmit,
  resetWorkspaceDraftState,
  handleSaveStrategyDraft,
  openAddToWorkspaceDialog,
  handleConfirmAddToWorkspace,
  handleRunStrategyDraftBacktest,
  handleRefreshWorkspaceExecution,
  handleGenerateWorkspaceReport,
  handleAsk,
  handleSelectConversation,
  handleNewConversation,
  handleJumpToCitation,
  goToKnowledgeBase,
  goToReindex,
} = useAIChatPage()
</script>

<style scoped lang="scss" src="./AIChatPage.styles.scss"></style>
