<template>
  <div class="ai-chat-page">
    <section class="ai-hero">
      <div class="min-w-0">
        <div class="eyebrow">
          AI Copilot
        </div>
        <h2>AI助手</h2>
        <p>
          围绕知识库、策略想法、Backtrader 草稿和策略审查组织对话，引用与执行动作集中在同一条回答内完成。
        </p>
      </div>

      <div class="hero-controls">
        <div class="control-label">
          <span>知识库</span>
          <el-select
            v-model="selectedKnowledgeBaseId"
            placeholder="请选择知识库"
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
        <el-button @click="handleNewConversation">
          <el-icon><Plus /></el-icon>
          新会话
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
        <span>深度模式</span>
      </div>
    </section>

    <div class="workspace-grid">
      <aside class="ai-panel conversation-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">
              会话
            </div>
            <div class="panel-subtitle">
              {{ chatStore.conversations.length }} 条记录
            </div>
          </div>
          <el-button
            circle
            size="small"
            title="新建会话"
            @click="handleNewConversation"
          >
            <el-icon><Plus /></el-icon>
          </el-button>
        </div>

        <el-input
          v-model="conversationSearch"
          placeholder="搜索会话标题"
          :prefix-icon="Search"
          clearable
          class="conversation-search"
        />

        <div
          v-if="filteredConversations.length === 0"
          class="empty-rail"
        >
          <el-icon><ChatDotRound /></el-icon>
          <span>暂无会话</span>
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
      </aside>

      <main class="chat-shell">
        <div class="chat-topbar">
          <div class="chat-context">
            <span class="context-icon"><el-icon><Collection /></el-icon></span>
            <div class="min-w-0">
              <div class="context-title">
                {{ currentKnowledgeBaseName || '未选择知识库' }}
              </div>
              <div class="context-meta">
                {{ currentModeMeta.label }}
                <span v-if="thinkingMode">/ 深度模式</span>
                <span v-if="currentKnowledgeBaseId">/ {{ retrievalProfileLabel(currentKnowledgeBaseSettings.retrieval_profile) }}</span>
                <span v-if="chatStore.currentConversationId">/ 会话进行中</span>
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
              复制
            </el-button>
            <el-button
              v-if="chatStore.messages.length > 0"
              size="small"
              type="danger"
              @click="handleNewConversation"
            >
              <el-icon><Delete /></el-icon>
              清空
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
              @copy-message="copyMessage"
              @save-strategy="handleSaveStrategyDraft(message, index)"
              @add-to-workspace="openAddToWorkspaceDialog(message, index)"
              @run-backtest="handleRunStrategyDraftBacktest(index)"
              @refresh-execution="handleRefreshWorkspaceExecution(index)"
              @generate-report="handleGenerateWorkspaceReport(message, index)"
              @copy-code="copyMessage(message.strategyDraft?.code || '')"
              @jump-citation="handleJumpToCitation"
            />

            <div
              v-if="chatStore.loading"
              class="typing-line"
            >
              <span />
              <span />
              <span />
              AI 正在生成回答
            </div>
          </template>
        </div>

        <div class="composer">
          <div class="composer-meta">
            <span>{{ selectedKnowledgeBaseId ? currentModeMeta.inputHint : '请先选择知识库' }}</span>
            <span>{{ question.length }}/500</span>
          </div>
          <div class="composer-row">
            <el-input
              v-model="question"
              type="textarea"
              :maxlength="500"
              :disabled="!selectedKnowledgeBaseId || chatStore.loading"
              :placeholder="inputPlaceholder"
              :rows="3"
              resize="vertical"
              @keydown.enter.exact.prevent="handleAsk"
            />
            <el-select
              v-model="selectedSessionModelKey"
              class="session-model-select"
              placeholder="默认模型"
            >
              <el-option
                label="默认模型"
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
              {{ chatStore.loading ? '发送中' : '发送' }}
            </el-button>
          </div>
        </div>
      </main>

      <aside class="ai-panel insight-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">
              上下文
            </div>
            <div class="panel-subtitle">
              {{ currentModeMeta.label }}
            </div>
          </div>
          <span
            class="status-dot"
            :class="{ active: Boolean(selectedKnowledgeBaseId) }"
          />
        </div>

        <div class="kb-card">
          <div class="kb-name">
            {{ currentKnowledgeBaseName || '未选择知识库' }}
          </div>
          <div class="kb-desc">
            {{ currentKnowledgeBase?.description || '选择知识库后开始问答' }}
          </div>
          <div class="metric-grid">
            <div>
              <span>文档</span>
              <strong>{{ currentKnowledgeBase?.document_count ?? 0 }}</strong>
            </div>
            <div>
              <span>已加载</span>
              <strong>{{ knowledgeBaseDocuments.length }}</strong>
            </div>
            <div>
              <span>已索引</span>
              <strong>{{ indexedDocumentCount }}</strong>
            </div>
          </div>
          <div class="kb-settings">
            <span>{{ retrievalProfileLabel(currentKnowledgeBaseSettings.retrieval_profile) }}</span>
            <span>{{ currentKnowledgeBaseSettings.search_mode }}</span>
            <span>top_k {{ currentKnowledgeBaseSettings.default_top_k }}</span>
            <span v-if="currentKnowledgeBaseSettings.use_conversation_memory">会话记忆开</span>
          </div>
          <div
            v-if="hasUnindexedDocuments"
            class="kb-index-warning"
          >
            <div>
              当前知识库有未索引文档，AI 检索结果可能不完整。
              <span>{{ indexedDocumentCount }}/{{ knowledgeBaseDocuments.length }} 已索引</span>
            </div>
            <button
              type="button"
              class="inline-link"
              @click="goToReindex"
            >
              前往重建索引
            </button>
          </div>
          <el-button
            class="w-full mt-3"
            :disabled="!currentKnowledgeBaseId"
            @click="goToKnowledgeBase"
          >
            <el-icon><Reading /></el-icon>
            打开知识库
          </el-button>
        </div>

        <div class="tool-section">
          <div class="section-kicker">
            快捷工具
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
      </aside>
    </div>

    <el-dialog
      v-model="showAddToWorkspaceDialog"
      title="添加策略草稿到工作区"
      width="520px"
    >
      <div class="dialog-form">
        <el-form-item label="研究工作区">
          <el-select
            v-model="workspaceDraftForm.workspaceId"
            placeholder="请选择工作区"
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
          <el-form-item label="标的代码">
            <el-input
              v-model="workspaceDraftForm.symbol"
              placeholder="例如 600519.SH"
            />
          </el-form-item>
          <el-form-item label="标的名称">
            <el-input
              v-model="workspaceDraftForm.symbolName"
              placeholder="例如 贵州茅台"
            />
          </el-form-item>
        </div>

        <div class="dialog-grid">
          <el-form-item label="周期">
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
          <el-form-item label="分组名">
            <el-input
              v-model="workspaceDraftForm.groupName"
              placeholder="例如 AI策略草稿"
            />
          </el-form-item>
        </div>

        <div
          v-if="researchWorkspaces.length === 0"
          class="dialog-warning"
        >
          当前没有可用的研究工作区，请先创建一个研究工作区。
        </div>
      </div>

      <template #footer>
        <div class="dialog-actions">
          <el-button
            v-if="researchWorkspaces.length === 0"
            @click="router.push({ name: 'WorkspaceList' })"
          >
            前往创建工作区
          </el-button>
          <el-button @click="resetWorkspaceDraftState">
            取消
          </el-button>
          <el-button
            type="primary"
            :loading="addingToWorkspace"
            @click="handleConfirmAddToWorkspace()"
          >
            确认添加
          </el-button>
          <el-button
            type="primary"
            :loading="addingToWorkspace"
            @click="handleConfirmAddToWorkspace(true)"
          >
            添加并回测
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound,
  Collection,
  Compass,
  CopyDocument,
  Delete,
  MagicStick,
  Plus,
  Promotion,
  Reading,
  Search,
} from '@element-plus/icons-vue'

import { getErrorMessage } from '@/api'
import { aiObservabilityApi, type AIModelOption } from '@/api/aiObservability'
import type { KBAssistantMode, KBStrategyDraft } from '@/api/kbChat'
import type { KnowledgeBaseSettings } from '@/api/knowledgeBase'
import ChatMessageBubble from '@/components/aichat/ChatMessageBubble.vue'
import {
  assistantModeMetaMap,
  assistantModeOptions,
  formatDate,
  getStrategyDraftIssue,
  retrievalProfileLabel,
} from '@/composables/useAIChatRendering'
import { useStrategyDraftWorkspaceExecution } from '@/composables/useStrategyDraftWorkspaceExecution'
import type { KBChatMessage } from '@/stores/kbChat'
import { strategyApi } from '@/api/strategy'
import { workspaceApi } from '@/api/workspace'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'
import { useKBChatStore } from '@/stores/kbChat'
import type { Workspace } from '@/types/workspace'

const router = useRouter()
const route = useRoute()
const kbStore = useKnowledgeBaseStore()
const chatStore = useKBChatStore()

const selectedKnowledgeBaseId = ref('')
const selectedAssistantMode = ref<KBAssistantMode>('knowledge_qa')
const thinkingMode = ref(false)
const conversationSearch = ref('')
const question = ref('')
const selectedSessionModelKey = ref('')
const sessionModelOptions = ref<AIModelOption[]>([])
const savingStrategyIndex = ref<number | null>(null)
const savedStrategyIds = ref<Record<number, string>>({})
const addedWorkspaceUnitIds = ref<Record<number, string>>({})
const showAddToWorkspaceDialog = ref(false)
const researchWorkspaces = ref<Workspace[]>([])
const addingToWorkspace = ref(false)
const pendingWorkspaceDraft = ref<KBStrategyDraft | null>(null)
const pendingWorkspaceDraftIndex = ref<number | null>(null)
const workspaceDraftForm = ref({
  workspaceId: '',
  symbol: '',
  symbolName: '',
  timeframe: '1d',
  groupName: '',
})
const {
  workspaceExecutions,
  runningBacktestIndex,
  refreshingStatusIndex,
  generatingReportIndex,
  buildReportConfigFromDraft,
  recordAddedExecution,
  recordBacktestExecution,
  runExecution,
  refreshExecution,
  generateReport,
  resetExecutions,
} = useStrategyDraftWorkspaceExecution()

const currentModeMeta = computed(() => assistantModeMetaMap[selectedAssistantMode.value])
const suggestedPrompts = computed(() => currentModeMeta.value.suggestedPrompts)
const quickTools = computed(() => currentModeMeta.value.quickTools)
const inputPlaceholder = computed(() => currentModeMeta.value.inputPlaceholder)
const currentKnowledgeBase = computed(
  () => kbStore.knowledgeBases.find(kb => kb.id === selectedKnowledgeBaseId.value)
    ?? kbStore.currentKnowledgeBase
    ?? null,
)
const currentKnowledgeBaseId = computed(
  () => selectedKnowledgeBaseId.value || currentKnowledgeBase.value?.id || '',
)
const currentKnowledgeBaseName = computed(() => currentKnowledgeBase.value?.name ?? '')

async function loadSessionModelOptions() {
  try {
    const payload = await aiObservabilityApi.getMyAvailableModels()
    sessionModelOptions.value = payload.models
  } catch {
    sessionModelOptions.value = []
    selectedSessionModelKey.value = ''
  }
}

function createDefaultKnowledgeBaseSettings(): KnowledgeBaseSettings {
  return {
    retrieval_profile: 'quant_research',
    search_mode: 'hybrid',
    default_top_k: 8,
    min_similarity: 0.08,
    title_weight: 0.35,
    keyword_weight: 0.35,
    phrase_weight: 0.2,
    recency_weight: 0.1,
    max_context_chunks: 6,
    use_conversation_memory: true,
    conversation_lookback_messages: 6,
    prioritize_title_matches: true,
    prefer_recent_documents: true,
    quant_focus: 'strategy_research',
    system_prompt_suffix: null,
  }
}
const currentKnowledgeBaseSettings = computed<KnowledgeBaseSettings>(() => ({
  ...createDefaultKnowledgeBaseSettings(),
  ...(currentKnowledgeBase.value?.settings ?? {}),
}))
const knowledgeBaseDocuments = computed(() => (
  Array.isArray(kbStore.documents) ? kbStore.documents : []
))
const indexableDocuments = computed(
  () => knowledgeBaseDocuments.value.filter(doc => !doc.is_folder),
)
const indexedDocumentCount = computed(
  () => indexableDocuments.value.filter(doc => doc.index_status === 'indexed').length,
)
const hasUnindexedDocuments = computed(
  () => indexableDocuments.value.some(doc => doc.index_status !== 'indexed'),
)

const filteredConversations = computed(() => {
  const keyword = conversationSearch.value.trim().toLowerCase()
  if (!keyword) return chatStore.conversations
  return chatStore.conversations.filter(c => c.title.toLowerCase().includes(keyword))
})

function ensureUsableStrategyDraft(draft?: KBStrategyDraft | null): draft is KBStrategyDraft {
  const issue = getStrategyDraftIssue(draft)
  if (issue) {
    ElMessage.warning(issue)
    return false
  }
  return true
}

function applyPrompt(prompt: string) {
  question.value = prompt
}

function copyMessage(content: string) {
  navigator.clipboard.writeText(content).then(() => {
    ElMessage.success('已复制到剪贴板')
  })
}

function copyConversation() {
  const text = chatStore.messages
    .map(m => `${m.role === 'user' ? '你' : 'AI'}:\n${m.content}`)
    .join('\n\n')
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('对话已复制')
  })
}

function getWorkspaceNameById(workspaceId: string) {
  return researchWorkspaces.value.find(item => item.id === workspaceId)?.name ?? workspaceId
}

function resetWorkspaceDraftState() {
  showAddToWorkspaceDialog.value = false
  researchWorkspaces.value = []
  addingToWorkspace.value = false
  pendingWorkspaceDraft.value = null
  pendingWorkspaceDraftIndex.value = null
  workspaceDraftForm.value = {
    workspaceId: '',
    symbol: '',
    symbolName: '',
    timeframe: '1d',
    groupName: '',
  }
}

async function handleSaveStrategyDraft(message: KBChatMessage, index: number) {
  const draft = message.strategyDraft
  if (!ensureUsableStrategyDraft(draft)) return
  savingStrategyIndex.value = index
  try {
    const created = await strategyApi.create({
      name: draft.name,
      description: draft.description,
      code: draft.code,
      params: draft.params,
      category: draft.category,
    })
    savedStrategyIds.value = {
      ...savedStrategyIds.value,
      [index]: created.id,
    }
    ElMessage.success(`策略已保存：${created.name}`)
  } catch {
    ElMessage.error('保存策略失败，请稍后重试')
  } finally {
    savingStrategyIndex.value = null
  }
}

async function openAddToWorkspaceDialog(message: KBChatMessage, index: number) {
  const draft = message.strategyDraft
  if (!ensureUsableStrategyDraft(draft)) return
  try {
    const response = await workspaceApi.list(0, 100, 'research')
    researchWorkspaces.value = response.items
    pendingWorkspaceDraft.value = draft
    pendingWorkspaceDraftIndex.value = index
    workspaceDraftForm.value = {
      workspaceId: response.items[0]?.id ?? '',
      symbol: draft.data_source?.symbol ?? draft.suggested_symbol ?? '',
      symbolName: draft.data_source?.symbol_name ?? '',
      timeframe: draft.data_source?.timeframe ?? draft.suggested_timeframe ?? '1d',
      groupName: draft.execution_plan?.group_name ?? draft.name,
    }
    showAddToWorkspaceDialog.value = true
  } catch {
    ElMessage.error('加载工作区失败，请稍后重试')
  }
}

async function handleConfirmAddToWorkspace(runBacktest = false) {
  if (!pendingWorkspaceDraft.value || pendingWorkspaceDraftIndex.value === null) return
  if (!workspaceDraftForm.value.workspaceId) {
    ElMessage.warning('请选择工作区')
    return
  }
  if (!workspaceDraftForm.value.symbol.trim()) {
    ElMessage.warning('请输入标的代码')
    return
  }

  addingToWorkspace.value = true
  try {
    const workspaceId = workspaceDraftForm.value.workspaceId
    const draft = pendingWorkspaceDraft.value
    if (!ensureUsableStrategyDraft(draft)) {
      addingToWorkspace.value = false
      return
    }
    const draftIndex = pendingWorkspaceDraftIndex.value
    const draftPayload = {
      strategy_draft: draft,
      strategy_id: savedStrategyIds.value[draftIndex] ?? null,
      symbol: workspaceDraftForm.value.symbol.trim(),
      symbol_name: workspaceDraftForm.value.symbolName.trim(),
      timeframe: workspaceDraftForm.value.timeframe,
      timeframe_n: 1,
      group_name: workspaceDraftForm.value.groupName.trim(),
    }
    const workspaceName = getWorkspaceNameById(workspaceId)
    if (runBacktest) {
      const response = await strategyApi.backtestCopilotDraft(workspaceId, {
        ...draftPayload,
        parallel: draft.execution_plan?.run_parallel ?? false,
        report_config: buildReportConfigFromDraft(draft),
      })
      savedStrategyIds.value = {
        ...savedStrategyIds.value,
        [draftIndex]: response.strategy.id,
      }
      addedWorkspaceUnitIds.value = {
        ...addedWorkspaceUnitIds.value,
        [draftIndex]: response.unit.id,
      }
      recordBacktestExecution(draftIndex, {
        workspaceId,
        workspaceName,
        unitId: response.unit.id,
        strategyId: response.strategy.id,
        runStatus: response.run_result.status,
        lastTaskId: response.run_result.task_id ?? null,
        report: response.report ?? null,
      }, draft)
      resetWorkspaceDraftState()
      ElMessage.success(`已添加并触发回测：${response.unit.strategy_name}`)
      return
    }

    const response = await strategyApi.addCopilotDraftToWorkspace(workspaceId, draftPayload)
    savedStrategyIds.value = {
      ...savedStrategyIds.value,
      [draftIndex]: response.strategy.id,
    }
    addedWorkspaceUnitIds.value = {
      ...addedWorkspaceUnitIds.value,
      [draftIndex]: response.unit.id,
    }
    recordAddedExecution(draftIndex, {
      workspaceId,
      workspaceName,
      unitId: response.unit.id,
      strategyId: response.strategy.id,
      runStatus: response.unit.run_status,
      lastTaskId: response.unit.last_task_id,
    })
    resetWorkspaceDraftState()
    ElMessage.success(`已添加到工作区：${response.unit.strategy_name}`)
  } catch {
    addingToWorkspace.value = false
    ElMessage.error('添加到工作区失败，请稍后重试')
  }
}

async function handleRunStrategyDraftBacktest(index: number) {
  const draft = chatStore.messages[index]?.strategyDraft
  if (!ensureUsableStrategyDraft(draft)) return
  await runExecution(index, draft)
}

async function handleRefreshWorkspaceExecution(index: number) {
  const draft = chatStore.messages[index]?.strategyDraft
  if (!ensureUsableStrategyDraft(draft)) return
  await refreshExecution(index, draft)
}

async function handleGenerateWorkspaceReport(message: KBChatMessage, index: number) {
  const draft = message.strategyDraft
  if (!ensureUsableStrategyDraft(draft)) return
  await generateReport(index, draft)
}

async function handleAsk() {
  if (!selectedKnowledgeBaseId.value || !question.value.trim()) return
  const q = question.value.trim()
  question.value = ''
  try {
    await chatStore.sendMessage(selectedKnowledgeBaseId.value, q, {
      assistantMode: selectedAssistantMode.value,
      thinkingMode: thinkingMode.value,
      modelId: selectedSessionModelKey.value || undefined,
    })
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '发送失败，请检查知识库或 AI 模型配置'))
  }
}

async function handleSelectConversation(conversationId: string) {
  await chatStore.fetchHistory(conversationId)
}

function handleNewConversation() {
  chatStore.resetConversationState()
  question.value = ''
  savingStrategyIndex.value = null
  savedStrategyIds.value = {}
  addedWorkspaceUnitIds.value = {}
  resetExecutions()
  resetWorkspaceDraftState()
}

async function handleJumpToCitation(documentId?: string | null) {
  if (!documentId) {
    ElMessage.warning('引用缺少文档信息，暂无法跳转')
    return
  }
  if (!currentKnowledgeBaseId.value) {
    ElMessage.warning('请先选择知识库')
    return
  }
  await router.push({
    path: `/knowledge-base/${currentKnowledgeBaseId.value}/documents/${documentId}`,
  })
}

function goToKnowledgeBase() {
  router.push({ path: '/knowledge-base', query: { kbId: currentKnowledgeBaseId.value } })
}

function goToReindex() {
  router.push({ path: '/knowledge-base', query: { kbId: currentKnowledgeBaseId.value, action: 'reindex' } })
}

watch(selectedKnowledgeBaseId, async (value) => {
  chatStore.resetConversationState()
  conversationSearch.value = ''
  if (value) {
    try {
      await kbStore.selectKnowledgeBase(value)
    } catch (error) {
      ElMessage.error(getErrorMessage(error, '加载知识库文档失败'))
    }
    try {
      await chatStore.fetchConversations(value)
    } catch (error) {
      ElMessage.error(getErrorMessage(error, '加载会话列表失败'))
    }
  }
})

onMounted(async () => {
  void loadSessionModelOptions()
  await kbStore.fetchKnowledgeBases()
  const queryKbId = typeof route.query.kbId === 'string' ? route.query.kbId : ''
  const firstId = kbStore.knowledgeBases[0]?.id
  selectedKnowledgeBaseId.value = queryKbId || firstId || ''

  const prompt = route.query.prompt
  if (prompt && typeof prompt === 'string') {
    question.value = prompt
  }
  const mode = route.query.mode
  if (mode && typeof mode === 'string' && mode in assistantModeMetaMap) {
    selectedAssistantMode.value = mode as KBAssistantMode
  }
})
</script>

<style scoped lang="scss">
/* AIChatPage - Refactored: CSS variables + Element Plus tokens */

.ai-chat-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.ai-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 20px;
  align-items: end;
  padding: 20px;
  border: 1px solid var(--border-color);
  border-radius: var(--el-border-radius-base);
  background: linear-gradient(135deg, var(--info-surface), var(--bg-color-hover));
}

.eyebrow,
.section-kicker {
  font-size: 12px;
  font-weight: 700;
  color: var(--primary-color);
  text-transform: uppercase;
}

.ai-hero h2 {
  margin: 4px 0 6px;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-color-primary);
}

.ai-hero p {
  max-width: 760px;
  margin: 0;
  color: var(--text-color-secondary);
  line-height: 1.7;
}

.hero-controls {
  display: flex;
  align-items: end;
  gap: 10px;
}

.control-label,
.dialog-form label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--text-color-secondary);
}

select,
input,
textarea {
  border: 1px solid var(--border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-card);
  color: var(--text-color-primary);
  outline: none;
}

select:focus,
input:focus,
textarea:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px var(--color-primary-100);
}

.control-label select {
  min-width: 240px;
  padding: 9px 12px;
  font-size: 14px;
}

button {
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.ghost-button,
.toolbar-button,
.secondary-action,
.primary-action,
.wide-link,
.send-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: var(--el-border-radius-base);
  font-weight: 600;
}

.ghost-button,
.toolbar-button,
.secondary-action,
.wide-link {
  border: 1px solid var(--border-color);
  background: var(--bg-color-card);
  color: var(--text-color-regular);
}



.primary-action,
.send-button {
  border: 1px solid var(--primary-color);
  background: var(--primary-color);
  color: var(--el-color-white);
}

.primary-action:hover:not(:disabled),
.send-button:hover:not(:disabled) {
  background: var(--primary-color-dark);
  border-color: var(--primary-color-dark);
}

.primary-action.accent {
  border-color: var(--primary-color-dark);
  background: var(--primary-color-dark);
}

.mode-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-card);
}

.mode-tab,
.thinking-toggle {
  border: 1px solid transparent;
  border-radius: var(--el-border-radius-base);
  padding: 9px 12px;
  font-size: 14px;
  color: var(--text-color-secondary);
  cursor: pointer;
  background: transparent;
}

.mode-tab.active {
  border-color: var(--info-border-color);
  background: var(--info-surface);
  color: var(--primary-color);
  font-weight: 700;
}

.thinking-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  background: var(--bg-color-hover);
}

.workspace-grid {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 300px;
  gap: 24px;
  align-items: stretch;
}

.ai-panel,
.chat-shell {
  border: 1px solid var(--border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-card);
}

.ai-panel {
  min-height: 640px;
  padding: 14px;
}

.panel-header,
.chat-topbar,
.dialog-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-color-primary);
}

.panel-subtitle {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-color-secondary);
}



/* Conversation search uses el-input */
.conversation-search {
  margin: 14px 0;
}

.conversation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.conversation-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-card);
  text-align: left;
  cursor: pointer;
}

.conversation-item.active {
  border-color: var(--info-border-color);
  background: var(--info-surface);
}

.conversation-title {
  overflow: hidden;
  color: var(--text-color-primary);
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-meta {
  font-size: 12px;
  color: var(--text-color-placeholder);
}

.empty-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--text-color-placeholder);
  font-size: 13px;
}

.chat-shell {
  display: flex;
  min-height: 640px;
  flex-direction: column;
  overflow: hidden;
}

.chat-topbar {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-color-hover);
}

.chat-context {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}

.context-icon,
.empty-chat-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--el-border-radius-base);
  background: var(--info-surface);
  color: var(--primary-color);
}

.context-icon {
  width: 36px;
  height: 36px;
}

.context-title {
  overflow: hidden;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-meta {
  margin-top: 2px;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.chat-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.toolbar-button {
  padding: 7px 10px;
  font-size: 12px;
}

.toolbar-button.danger {
  color: var(--danger-color);
}

.message-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px;
  background: var(--bg-color-card);
}

.empty-chat {
  display: flex;
  min-height: 460px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.empty-chat-icon {
  width: 52px;
  height: 52px;
  margin-bottom: 14px;
  font-size: 24px;
}

.empty-chat h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}

.empty-chat p {
  max-width: 460px;
  margin: 8px 0 0;
  color: var(--text-color-secondary);
  line-height: 1.7;
}

.prompt-grid {
  display: grid;
  width: min(620px, 100%);
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 22px;
}

.prompt-grid button,
.tool-item {
  border: 1px solid var(--border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-card);
  color: var(--text-color-regular);
  text-align: left;
  cursor: pointer;
}

.prompt-grid button {
  padding: 10px 12px;
  line-height: 1.5;
}

.metric-grid {
  display: grid;
  gap: 8px;
}

.dialog-actions {
  flex-wrap: wrap;
}

.kb-settings {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.kb-settings span {
  border-radius: 9999px;
  background: var(--info-surface);
  padding: 3px 8px;
  color: var(--primary-color);
  font-size: 12px;
}

.typing-line {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border-color);
  border-radius: 9999px;
  background: var(--bg-color-card);
  padding: 8px 12px;
  color: var(--text-color-secondary);
  font-size: 13px;
}

.typing-line span {
  width: 6px;
  height: 6px;
  border-radius: 9999px;
  background: var(--primary-color);
  animation: pulse-dot 1.2s infinite ease-in-out;
}

.typing-line span:nth-child(2) { animation-delay: 0.12s; }
.typing-line span:nth-child(3) { animation-delay: 0.24s; }

.composer {
  border-top: 1px solid var(--border-color);
  background: var(--bg-color-card);
  padding: 14px;
}

.composer-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.composer-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: stretch;
}

.composer textarea {
  min-height: 74px;
  resize: vertical;
  padding: 10px 12px;
  line-height: 1.6;
}

/* Send button sizing */
.send-button {
  min-width: 104px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 9999px;
  background: var(--border-color);
}

.status-dot.active {
  background: var(--success-color);
}

.kb-card {
  margin-top: 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-hover);
  padding: 12px;
}

.kb-name { font-weight: 700; }

.kb-desc {
  margin-top: 5px;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.metric-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 12px;
}

.metric-grid div {
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-card);
  padding: 8px;
}

.metric-grid span {
  display: block;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.metric-grid strong {
  display: block;
  margin-top: 2px;
  color: var(--text-color-primary);
}

.wide-link {
  width: 100%;
  margin-top: 12px;
  padding: 9px 12px;
}

.kb-index-warning {
  margin-top: 12px;
  border: 1px solid var(--warning-border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--warning-surface);
  padding: 10px;
  color: var(--warning-text-color);
  font-size: 12px;
  line-height: 1.6;
}

.kb-index-warning span {
  display: block;
  margin-top: 2px;
  color: var(--warning-text-strong);
}

.inline-link {
  margin-top: 8px;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.tool-section { margin-top: 16px; }

.tool-item {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 10px;
  width: 100%;
  margin-top: 8px;
  padding: 10px;
  cursor: pointer;
}

.tool-item strong,
.tool-item small { display: block; }
.tool-item strong { font-size: 13px; }
.tool-item small {
  margin-top: 3px;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.dialog-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.dialog-form input,
.dialog-form select {
  width: 100%;
  padding: 9px 10px;
}

.dialog-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.dialog-warning {
  border: 1px solid var(--warning-border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--warning-surface);
  padding: 10px;
  color: var(--warning-text-color);
  font-size: 13px;
}

@keyframes pulse-dot {
  0%, 80%, 100% { transform: scale(0.7); opacity: 0.45; }
  40% { transform: scale(1); opacity: 1; }
}

@media (max-width: 1280px) {
  .workspace-grid { grid-template-columns: 260px minmax(0, 1fr); }
  .insight-panel { grid-column: 1 / -1; min-height: auto; }
}

@media (max-width: 900px) {
  .ai-hero { grid-template-columns: 1fr; }
  .hero-controls { align-items: stretch; flex-direction: column; }
  .control-label select { min-width: 0; width: 100%; }
  .workspace-grid { grid-template-columns: 1fr; }
  .ai-panel, .chat-shell { min-height: auto; }
  .conversation-panel { max-height: 360px; overflow: auto; }
  .prompt-grid, .draft-stats, .dialog-grid { grid-template-columns: 1fr; }
  .composer-row { grid-template-columns: 1fr; }
  .send-button { min-height: 44px; }
}
</style>
