<template>
  <div class="ai-chat-page">
    <section class="ai-hero">
      <div class="min-w-0">
        <div class="eyebrow">AI Copilot</div>
        <h2>AI助手</h2>
        <p>
          围绕知识库、策略想法、Backtrader 草稿和策略审查组织对话，引用与执行动作集中在同一条回答内完成。
        </p>
      </div>

      <div class="hero-controls">
        <label class="control-label">
          <span>知识库</span>
          <select v-model="selectedKnowledgeBaseId">
            <option value="">请选择知识库</option>
            <option v-for="kb in kbStore.knowledgeBases" :key="kb.id" :value="kb.id">
              {{ kb.name }}
            </option>
          </select>
        </label>
        <button type="button" class="ghost-button" @click="handleNewConversation">
          <el-icon><Plus /></el-icon>
          新会话
        </button>
      </div>
    </section>

    <section class="mode-strip">
      <button
        v-for="option in assistantModeOptions"
        :key="option.value"
        type="button"
        class="mode-tab"
        :class="{ active: option.value === selectedAssistantMode }"
        @click="selectedAssistantMode = option.value"
      >
        {{ option.label }}
      </button>
      <label class="thinking-toggle">
        <input v-model="thinkingMode" type="checkbox">
        <span>深度模式</span>
      </label>
    </section>

    <div class="workspace-grid">
      <aside class="ai-panel conversation-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">会话</div>
            <div class="panel-subtitle">{{ chatStore.conversations.length }} 条记录</div>
          </div>
          <button type="button" class="icon-button" title="新建会话" @click="handleNewConversation">
            <el-icon><Plus /></el-icon>
          </button>
        </div>

        <label class="search-box">
          <el-icon><Search /></el-icon>
          <input v-model="conversationSearch" placeholder="搜索会话标题">
        </label>

        <div v-if="filteredConversations.length === 0" class="empty-rail">
          <el-icon><ChatDotRound /></el-icon>
          <span>暂无会话</span>
        </div>

        <div v-else class="conversation-list">
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
              <div class="context-title">{{ currentKnowledgeBaseName || '未选择知识库' }}</div>
              <div class="context-meta">
                {{ currentModeMeta.label }}
                <span v-if="thinkingMode">/ 深度模式</span>
                <span v-if="chatStore.currentConversationId">/ 会话进行中</span>
              </div>
            </div>
          </div>

          <div class="chat-actions">
            <button
              v-if="chatStore.messages.length > 0"
              type="button"
              class="toolbar-button"
              @click="copyConversation"
            >
              <el-icon><CopyDocument /></el-icon>
              复制
            </button>
            <button
              v-if="chatStore.messages.length > 0"
              type="button"
              class="toolbar-button danger"
              @click="handleNewConversation"
            >
              <el-icon><Delete /></el-icon>
              清空
            </button>
          </div>
        </div>

        <div class="message-scroll">
          <div v-if="chatStore.messages.length === 0 && !chatStore.loading" class="empty-chat">
            <div class="empty-chat-icon"><el-icon><MagicStick /></el-icon></div>
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
            <article
              v-for="(message, index) in chatStore.messages"
              :key="`${message.role}-${index}`"
              class="message-card"
              :class="message.role"
            >
              <div class="message-avatar">
                <el-icon v-if="message.role === 'assistant'"><Cpu /></el-icon>
                <el-icon v-else><UserFilled /></el-icon>
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
                  <button
                    type="button"
                    class="icon-button subtle"
                    title="复制消息"
                    @click="copyMessage(message.content)"
                  >
                    <el-icon><CopyDocument /></el-icon>
                  </button>
                </div>

                <div class="message-content">{{ message.content }}</div>

                <section
                  v-if="message.role === 'assistant' && message.diagnosticMessage"
                  class="diagnostic-box"
                  :class="message.reasonCode || ''"
                >
                  <div class="section-kicker">{{ getDiagnosticTitle(message.reasonCode) }}</div>
                  <div>{{ message.diagnosticMessage }}</div>
                </section>

                <section v-if="message.role === 'assistant' && message.strategyDraft" class="strategy-draft">
                  <div class="draft-head">
                    <div>
                      <div class="draft-title">{{ message.strategyDraft.name }}</div>
                      <div class="draft-meta">
                        {{ message.strategyDraft.category || '未分类' }}
                        / {{ getDraftParamCount(message.strategyDraft) }} 个参数
                        <span v-if="message.strategyDraft.suggested_timeframe">
                          / {{ message.strategyDraft.suggested_timeframe }}
                        </span>
                      </div>
                    </div>
                    <div class="draft-actions">
                      <button
                        type="button"
                        class="primary-action"
                        :disabled="
                          savingStrategyIndex === index
                            || Boolean(savedStrategyIds[index])
                            || Boolean(getStrategyDraftIssue(message.strategyDraft))
                        "
                        @click="handleSaveStrategyDraft(message, index)"
                      >
                        <el-icon><Document /></el-icon>
                        {{
                          savedStrategyIds[index]
                            ? '已保存到策略中心'
                            : savingStrategyIndex === index
                              ? '保存中...'
                              : '保存为策略'
                        }}
                      </button>
                      <button
                        type="button"
                        class="secondary-action"
                        :disabled="
                          Boolean(addedWorkspaceUnitIds[index])
                            || Boolean(getStrategyDraftIssue(message.strategyDraft))
                        "
                        @click="openAddToWorkspaceDialog(message, index)"
                      >
                        <el-icon><Aim /></el-icon>
                        {{ addedWorkspaceUnitIds[index] ? '已添加到工作区' : '添加到工作区' }}
                      </button>
                      <button
                        v-if="workspaceExecutions[index]"
                        type="button"
                        class="secondary-action"
                        :disabled="
                          runningBacktestIndex === index
                            || Boolean(getStrategyDraftIssue(message.strategyDraft))
                        "
                        @click="handleRunStrategyDraftBacktest(index)"
                      >
                        <el-icon><Promotion /></el-icon>
                        {{ runningBacktestIndex === index ? '回测提交中...' : '一键回测' }}
                      </button>
                      <button
                        v-if="workspaceExecutions[index]"
                        type="button"
                        class="secondary-action"
                        :disabled="refreshingStatusIndex === index"
                        @click="handleRefreshWorkspaceExecution(index)"
                      >
                        <el-icon><Refresh /></el-icon>
                        {{ refreshingStatusIndex === index ? '刷新中...' : '刷新状态' }}
                      </button>
                      <button
                        v-if="workspaceExecutions[index]"
                        type="button"
                        class="secondary-action"
                        :disabled="
                          generatingReportIndex === index
                            || Boolean(getStrategyDraftIssue(message.strategyDraft))
                        "
                        @click="handleGenerateWorkspaceReport(message, index)"
                      >
                        <el-icon><DataAnalysis /></el-icon>
                        {{ generatingReportIndex === index ? '生成中...' : '生成报告' }}
                      </button>
                      <button
                        type="button"
                        class="secondary-action"
                        @click="copyMessage(message.strategyDraft.code || '')"
                      >
                        <el-icon><CopyDocument /></el-icon>
                        复制代码
                      </button>
                    </div>
                  </div>

                  <p v-if="message.strategyDraft.rationale" class="draft-rationale">
                    {{ message.strategyDraft.rationale }}
                  </p>

                  <p v-if="getStrategyDraftIssue(message.strategyDraft)" class="draft-warning">
                    {{ getStrategyDraftIssue(message.strategyDraft) }}
                  </p>

                  <div class="draft-stats">
                    <span>数据源 {{ getDraftDataSourceType(message.strategyDraft) }}</span>
                    <span>周期 {{ getDraftTimeframe(message.strategyDraft) }}</span>
                    <span>资金 {{ getDraftInitialCash(message.strategyDraft) }}</span>
                    <span>手续费 {{ getDraftCommission(message.strategyDraft) }}</span>
                  </div>

                  <div v-if="getDraftAssumptions(message.strategyDraft).length" class="draft-list">
                    <div class="draft-list-title">
                      <el-icon><CircleCheck /></el-icon>
                      关键假设
                    </div>
                    <div v-for="item in getDraftAssumptions(message.strategyDraft)" :key="item">{{ item }}</div>
                  </div>

                  <div v-if="getDraftRiskPoints(message.strategyDraft).length" class="draft-list warning">
                    <div class="draft-list-title">
                      <el-icon><Warning /></el-icon>
                      风险提示
                    </div>
                    <div v-for="item in getDraftRiskPoints(message.strategyDraft)" :key="item">{{ item }}</div>
                  </div>

                  <div v-if="workspaceExecutions[index]" class="execution-box">
                    <div class="execution-title">工作区执行状态</div>
                    <div>工作区：{{ workspaceExecutions[index].workspaceName }}</div>
                    <div>单元ID：{{ workspaceExecutions[index].unitId }}</div>
                    <div>回测状态：{{ workspaceExecutions[index].runStatus || '未运行' }}</div>
                    <div v-if="workspaceExecutions[index].lastTaskId">
                      任务ID：{{ workspaceExecutions[index].lastTaskId }}
                    </div>
                    <div v-if="workspaceExecutions[index].report" class="report-box">
                      <div class="execution-title">最新报告摘要</div>
                      <div>
                        完成单元：
                        {{ workspaceExecutions[index].report?.summary.completed_units }}
                        / {{ workspaceExecutions[index].report?.summary.total_units }}
                      </div>
                      <div>平均收益：{{ workspaceExecutions[index].report?.summary.avg_total_return ?? '-' }}</div>
                      <div>平均夏普：{{ workspaceExecutions[index].report?.summary.avg_sharpe_ratio ?? '-' }}</div>
                      <div>平均回撤：{{ workspaceExecutions[index].report?.summary.avg_max_drawdown ?? '-' }}</div>
                    </div>
                    <div v-if="workspaceExecutions[index].analysis" class="analysis-box">
                      <div class="execution-title">AI复盘建议</div>
                      <div>{{ workspaceExecutions[index].analysis?.summary }}</div>
                      <div class="mt-2 font-medium">{{ workspaceExecutions[index].analysis?.verdict }}</div>
                    </div>
                  </div>
                </section>

                <section v-if="message.role === 'assistant' && message.reasoning" class="reasoning-box">
                  <div class="section-kicker">分析摘要</div>
                  <div>{{ message.reasoning }}</div>
                </section>

                <section
                  v-if="message.role === 'assistant' && message.citations?.length"
                  class="citation-box"
                >
                  <div class="citation-head">
                    <span>参考文档</span>
                    <span>{{ message.citations.length }} 条引用</span>
                  </div>
                  <button
                    v-for="(citation, cIdx) in message.citations"
                    :key="getCitationKey(citation, cIdx)"
                    type="button"
                    class="citation-item"
                    :disabled="!citation.document_id"
                    @click="handleJumpToCitation(citation.document_id)"
                  >
                    <span class="citation-index">{{ cIdx + 1 }}</span>
                    <span class="citation-content">
                      <strong>{{ getCitationTitle(citation) }}</strong>
                      <small>
                        chunk #{{ getCitationChunkIndex(citation) }}
                        / {{ getCitationSimilarity(citation) }}%
                      </small>
                      <span v-if="citation.content">{{ citation.content }}</span>
                    </span>
                    <el-icon><Link /></el-icon>
                  </button>
                </section>
              </div>
            </article>

            <div v-if="chatStore.loading" class="typing-line">
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
            <textarea
              v-model="question"
              :maxlength="500"
              :disabled="!selectedKnowledgeBaseId || chatStore.loading"
              :placeholder="inputPlaceholder"
              @keydown.enter.exact.prevent="handleAsk"
            />
            <button
              type="button"
              class="send-button"
              :disabled="!selectedKnowledgeBaseId || !question.trim() || chatStore.loading"
              @click="handleAsk"
            >
              <el-icon><Promotion /></el-icon>
              {{ chatStore.loading ? '发送中' : '发送' }}
            </button>
          </div>
        </div>
      </main>

      <aside class="ai-panel insight-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">上下文</div>
            <div class="panel-subtitle">{{ currentModeMeta.label }}</div>
          </div>
          <span class="status-dot" :class="{ active: Boolean(selectedKnowledgeBaseId) }" />
        </div>

        <div class="kb-card">
          <div class="kb-name">{{ currentKnowledgeBaseName || '未选择知识库' }}</div>
          <div class="kb-desc">{{ currentKnowledgeBase?.description || '选择知识库后开始问答' }}</div>
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
          <div v-if="hasUnindexedDocuments" class="kb-index-warning">
            <div>
              当前知识库有未索引文档，AI 检索结果可能不完整。
              <span>{{ indexedDocumentCount }}/{{ knowledgeBaseDocuments.length }} 已索引</span>
            </div>
            <button type="button" class="inline-link" @click="goToReindex">
              前往重建索引
            </button>
          </div>
          <button
            type="button"
            class="wide-link"
            :disabled="!currentKnowledgeBaseId"
            @click="goToKnowledgeBase"
          >
            <el-icon><Reading /></el-icon>
            打开知识库
          </button>
        </div>

        <div class="tool-section">
          <div class="section-kicker">快捷工具</div>
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

    <el-dialog v-model="showAddToWorkspaceDialog" title="添加策略草稿到工作区" width="520px">
      <div class="dialog-form">
        <label>
          <span>研究工作区</span>
          <select v-model="workspaceDraftForm.workspaceId">
            <option value="">请选择工作区</option>
            <option v-for="workspace in researchWorkspaces" :key="workspace.id" :value="workspace.id">
              {{ workspace.name }}
            </option>
          </select>
        </label>

        <div class="dialog-grid">
          <label>
            <span>标的代码</span>
            <input v-model="workspaceDraftForm.symbol" placeholder="例如 600519.SH">
          </label>
          <label>
            <span>标的名称</span>
            <input v-model="workspaceDraftForm.symbolName" placeholder="例如 贵州茅台">
          </label>
        </div>

        <div class="dialog-grid">
          <label>
            <span>周期</span>
            <select v-model="workspaceDraftForm.timeframe">
              <option value="1m">1m</option>
              <option value="5m">5m</option>
              <option value="15m">15m</option>
              <option value="30m">30m</option>
              <option value="1h">1h</option>
              <option value="1d">1d</option>
              <option value="1w">1w</option>
            </select>
          </label>
          <label>
            <span>分组名</span>
            <input v-model="workspaceDraftForm.groupName" placeholder="例如 AI策略草稿">
          </label>
        </div>

        <div v-if="researchWorkspaces.length === 0" class="dialog-warning">
          当前没有可用的研究工作区，请先创建一个研究工作区。
        </div>
      </div>

      <template #footer>
        <div class="dialog-actions">
          <button
            v-if="researchWorkspaces.length === 0"
            type="button"
            class="secondary-action"
            @click="router.push({ name: 'WorkspaceList' })"
          >
            前往创建工作区
          </button>
          <button type="button" class="secondary-action" @click="resetWorkspaceDraftState">
            取消
          </button>
          <button
            type="button"
            class="primary-action"
            :disabled="addingToWorkspace"
            @click="handleConfirmAddToWorkspace()"
          >
            {{ addingToWorkspace ? '添加中...' : '确认添加' }}
          </button>
          <button
            type="button"
            class="primary-action accent"
            :disabled="addingToWorkspace"
            @click="handleConfirmAddToWorkspace(true)"
          >
            {{ addingToWorkspace ? '提交中...' : '添加并回测' }}
          </button>
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
  Aim,
  ChatDotRound,
  CircleCheck,
  Collection,
  Compass,
  CopyDocument,
  Cpu,
  DataAnalysis,
  Delete,
  Document,
  Link,
  MagicStick,
  Plus,
  Promotion,
  Reading,
  Refresh,
  Search,
  UserFilled,
  Warning,
} from '@element-plus/icons-vue'

import { getErrorMessage } from '@/api'
import type { KBAssistantMode, KBCitation, KBReasonCode, KBStrategyDraft } from '@/api/kbChat'
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

const assistantModeOptions: Array<{ value: KBAssistantMode; label: string }> = [
  { value: 'knowledge_qa', label: '知识问答' },
  { value: 'strategy_idea', label: '策略构思' },
  { value: 'backtrader_strategy', label: 'Backtrader策略生成' },
  { value: 'strategy_review', label: '策略审查' },
]

interface QuickTool {
  icon: string
  title: string
  description: string
  prompt: string
}

interface AssistantModeMeta {
  label: string
  emptyTitle: string
  emptyDescription: string
  inputHint: string
  inputPlaceholder: string
  suggestedPrompts: string[]
  quickTools: QuickTool[]
}

const assistantModeMetaMap: Record<KBAssistantMode, AssistantModeMeta> = {
  knowledge_qa: {
    label: '知识问答',
    emptyTitle: '从知识库开始提问',
    emptyDescription: '选择知识库后输入问题，回答会优先引用已经保存的文档内容。',
    inputHint: '输入问题，AI 将结合知识库回答',
    inputPlaceholder: '请输入问题... (Enter 发送，Shift+Enter 换行)',
    suggestedPrompts: [
      '这个知识库主要包含哪些内容？',
      '总结当前知识库的核心主题',
      '有哪些值得重点阅读的文档？',
    ],
    quickTools: [
      {
        icon: 'summary',
        title: '总结知识库',
        description: '快速生成核心主题摘要',
        prompt: '请总结这个知识库的核心主题与重点文档。',
      },
      {
        icon: 'docs',
        title: '提取关键文档',
        description: '找出最值得优先阅读的内容',
        prompt: '请列出这个知识库中最值得优先阅读的文档，并说明原因。',
      },
      {
        icon: 'path',
        title: '生成阅读路径',
        description: '给出推荐阅读顺序',
        prompt: '请为我生成这个知识库的推荐阅读路径。',
      },
    ],
  },
  strategy_idea: {
    label: '策略构思',
    emptyTitle: '拆解策略想法',
    emptyDescription: '把一句策略设想拆成信号、风控、数据需求和回测验证步骤。',
    inputHint: '输入一句话策略想法，AI 将生成结构化研究方案',
    inputPlaceholder: '例如：我想做一个基于均线突破和成交量放大的日线趋势策略',
    suggestedPrompts: [
      '把“均线突破 + 放量确认”的想法扩展成完整研究方案',
      '帮我设计一个适合 A 股日线回测的低频趋势策略',
      '把“回撤后反弹买入”整理成可验证的量化假设',
    ],
    quickTools: [
      {
        icon: 'expand',
        title: '一句话扩展',
        description: '把模糊策略想法拆成研究任务',
        prompt: '请把下面这句自然语言策略想法扩展成结构化研究方案：',
      },
      {
        icon: 'test',
        title: '生成回测计划',
        description: '补充样本区间、指标和验证步骤',
        prompt: '请基于这个策略想法生成详细的回测计划与验证步骤：',
      },
      {
        icon: 'risk',
        title: '补风控框架',
        description: '为策略添加仓位和止损框架',
        prompt: '请为这个策略补充仓位控制、止损止盈和风险暴露约束：',
      },
    ],
  },
  backtrader_strategy: {
    label: 'Backtrader策略生成',
    emptyTitle: '生成策略实现草案',
    emptyDescription: '输入自然语言策略需求，生成可保存、可加入工作区的 Backtrader 草稿。',
    inputHint: '输入自然语言需求，AI 将生成 Backtrader 策略草案',
    inputPlaceholder: '例如：帮我生成一个 RSI 超卖反弹 + ATR 止损的 Backtrader 策略骨架',
    suggestedPrompts: [
      '请生成一个“双均线 + ATR 止损”的 Backtrader 策略代码骨架',
      '请把“突破20日高点买入，跌破10日低点卖出”转成 Backtrader 策略',
      '请生成一个适合期货分钟级别的布林带均值回归策略草案',
    ],
    quickTools: [
      {
        icon: 'code',
        title: '生成代码骨架',
        description: '输出 Backtrader 类与关键参数',
        prompt: '请把下面的自然语言策略需求生成 Backtrader 策略代码骨架：',
      },
      {
        icon: 'platform',
        title: '生成接入建议',
        description: '补充平台参数与运行建议',
        prompt: '请为这个 Backtrader 策略补充在 Backtrader Web 中的接入建议：',
      },
      {
        icon: 'params',
        title: '生成参数表',
        description: '提炼可优化参数与默认值',
        prompt: '请为这个策略生成参数表、默认值以及建议优化区间：',
      },
    ],
  },
  strategy_review: {
    label: '策略审查',
    emptyTitle: '审查策略质量',
    emptyDescription: '粘贴策略描述或代码片段，从逻辑、风控、数据和回测偏差角度审查。',
    inputHint: '输入策略描述或代码，AI 将执行结构化审查',
    inputPlaceholder: '例如：请审查这个动量策略的风控设计是否充分...',
    suggestedPrompts: [
      '请审查一个“动量轮动 + 每周调仓”策略的主要风险',
      '请从回测偏差角度审查“财报因子选股”策略',
      '请检查这个趋势策略是否存在过拟合和数据窥探风险',
    ],
    quickTools: [
      {
        icon: 'logic',
        title: '审查策略逻辑',
        description: '识别核心假设和漏洞',
        prompt: '请从策略逻辑、风险和可执行性角度审查下面的策略：',
      },
      {
        icon: 'bias',
        title: '审查回测偏差',
        description: '检查未来函数、幸存者偏差等问题',
        prompt: '请重点审查下面策略是否存在未来函数、数据泄露或样本偏差：',
      },
      {
        icon: 'next',
        title: '给出优化顺序',
        description: '生成下一步修改建议',
        prompt: '请为这个策略生成按优先级排序的优化建议与验证顺序：',
      },
    ],
  },
}

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

function formatDate(value?: string | null) {
  if (!value) return '未知时间'
  return value.replace('T', ' ').slice(0, 16)
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function getDraftParamCount(draft?: KBStrategyDraft | null) {
  return isPlainRecord(draft?.params) ? Object.keys(draft.params).length : 0
}

function getDraftAssumptions(draft?: KBStrategyDraft | null) {
  return Array.isArray(draft?.assumptions) ? draft.assumptions : []
}

function getDraftRiskPoints(draft?: KBStrategyDraft | null) {
  return Array.isArray(draft?.risk_points) ? draft.risk_points : []
}

function getDraftDataSourceType(draft?: KBStrategyDraft | null) {
  return draft?.data_source?.type || '未设置'
}

function getDraftTimeframe(draft?: KBStrategyDraft | null) {
  return draft?.data_source?.timeframe || draft?.suggested_timeframe || '未设置'
}

function getDraftInitialCash(draft?: KBStrategyDraft | null) {
  return typeof draft?.backtest_defaults?.initial_cash === 'number'
    ? draft.backtest_defaults.initial_cash
    : '未设置'
}

function getDraftCommission(draft?: KBStrategyDraft | null) {
  return typeof draft?.backtest_defaults?.commission === 'number'
    ? draft.backtest_defaults.commission
    : '未设置'
}

function getStrategyDraftIssue(draft?: KBStrategyDraft | null) {
  if (!draft) return '当前回答未包含策略草稿'
  if (!draft.name?.trim()) return '策略草稿缺少名称，暂不能保存或执行'
  if (!draft.code?.trim()) return '策略草稿缺少 Backtrader 代码，暂不能保存或执行'
  if (!isPlainRecord(draft.params)) return '策略草稿参数格式异常，暂不能保存或执行'
  if (!draft.category?.trim()) return '策略草稿缺少策略分类，暂不能保存或执行'
  if (!draft.data_source || !draft.data_source.timeframe) {
    return '策略草稿缺少数据源周期，暂不能添加到工作区'
  }
  if (
    !draft.backtest_defaults
      || typeof draft.backtest_defaults.initial_cash !== 'number'
      || typeof draft.backtest_defaults.commission !== 'number'
  ) {
    return '策略草稿缺少回测默认参数，暂不能执行'
  }
  if (!draft.execution_plan || typeof draft.execution_plan.run_parallel !== 'boolean') {
    return '策略草稿缺少执行计划，暂不能添加到工作区'
  }
  return null
}

function getDiagnosticTitle(reasonCode?: KBReasonCode | null) {
  if (reasonCode === 'no_context_found') return '未找到相关上下文'
  if (reasonCode === 'ai_not_configured') return 'AI 模型未配置'
  if (reasonCode === 'ai_provider_failed') return 'AI 模型调用失败'
  return 'AI 助手诊断'
}

function getCitationTitle(citation: KBCitation) {
  const title = citation.document_title?.trim()
  return title || '未命名文档'
}

function getCitationKey(citation: KBCitation, index: number) {
  return citation.chunk_id || `${citation.document_id || 'missing-doc'}-${citation.chunk_index ?? index}`
}

function getCitationChunkIndex(citation: KBCitation) {
  return typeof citation.chunk_index === 'number' ? citation.chunk_index : '未知'
}

function getCitationSimilarity(citation: KBCitation) {
  const similarity = typeof citation.similarity === 'number' ? citation.similarity : 0
  return Math.round(Math.max(0, Math.min(1, similarity)) * 100)
}

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

<style scoped>
.ai-chat-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: #0f172a;
}

.ai-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 20px;
  align-items: end;
  padding: 20px;
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background:
    linear-gradient(135deg, rgba(236, 253, 245, 0.85), rgba(239, 246, 255, 0.92)),
    radial-gradient(circle at top right, rgba(20, 184, 166, 0.18), transparent 34%);
}

.eyebrow,
.section-kicker {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  color: #0f766e;
  text-transform: uppercase;
}

.ai-hero h2 {
  margin: 4px 0 6px;
  font-size: 28px;
  font-weight: 750;
  color: #0f172a;
}

.ai-hero p {
  max-width: 760px;
  margin: 0;
  color: #475569;
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
  color: #64748b;
}

select,
input,
textarea {
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
  color: #0f172a;
  outline: none;
}

select:focus,
input:focus,
textarea:focus {
  border-color: #0f766e;
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12);
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
  border-radius: 8px;
  font-weight: 650;
}

.ghost-button,
.toolbar-button,
.secondary-action,
.wide-link {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #334155;
}

.ghost-button {
  padding: 9px 12px;
}

.primary-action,
.send-button {
  border: 1px solid #0f766e;
  background: #0f766e;
  color: #fff;
}

.primary-action.accent {
  border-color: #2563eb;
  background: #2563eb;
}

.mode-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #fff;
}

.mode-tab,
.thinking-toggle {
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 14px;
  color: #475569;
}

.mode-tab.active {
  border-color: #99f6e4;
  background: #ccfbf1;
  color: #0f766e;
  font-weight: 700;
}

.thinking-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  background: #f8fafc;
}

.workspace-grid {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 300px;
  gap: 16px;
  align-items: stretch;
}

.ai-panel,
.chat-shell {
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #fff;
}

.ai-panel {
  min-height: 640px;
  padding: 14px;
}

.panel-header,
.chat-topbar,
.message-head,
.draft-head,
.citation-head,
.dialog-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-title {
  font-size: 15px;
  font-weight: 750;
  color: #0f172a;
}

.panel-subtitle {
  margin-top: 2px;
  font-size: 12px;
  color: #64748b;
}

.icon-button {
  display: inline-flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
  color: #334155;
}

.icon-button.subtle {
  width: 28px;
  height: 28px;
  border-color: transparent;
  color: #64748b;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 14px 0;
  padding: 9px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  color: #64748b;
}

.search-box input {
  width: 100%;
  border: 0;
  padding: 0;
  box-shadow: none;
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
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  text-align: left;
}

.conversation-item.active {
  border-color: #5eead4;
  background: #f0fdfa;
}

.conversation-title {
  overflow: hidden;
  color: #0f172a;
  font-size: 13px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-meta {
  font-size: 12px;
  color: #94a3b8;
}

.empty-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 0;
  color: #94a3b8;
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
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}

.chat-context {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}

.context-icon,
.message-avatar,
.empty-chat-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: #ccfbf1;
  color: #0f766e;
}

.context-icon {
  width: 36px;
  height: 36px;
}

.context-title {
  overflow: hidden;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-meta {
  margin-top: 2px;
  color: #64748b;
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
  color: #be123c;
}

.message-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px;
  background:
    linear-gradient(#fff, #fff),
    linear-gradient(135deg, rgba(236, 253, 245, 0.45), rgba(239, 246, 255, 0.45));
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
  font-weight: 750;
}

.empty-chat p {
  max-width: 460px;
  margin: 8px 0 0;
  color: #64748b;
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
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  background: #fff;
  color: #334155;
  text-align: left;
}

.prompt-grid button {
  padding: 10px 12px;
  line-height: 1.5;
}

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
  background: #e2e8f0;
  color: #334155;
}

.message-card.user .message-body {
  grid-column: 1;
  grid-row: 1;
}

.message-card.user .message-head {
  flex-direction: row-reverse;
}

.message-card.user .message-content {
  background: #f8fafc;
}

.message-avatar {
  width: 38px;
  height: 38px;
}

.message-body {
  min-width: 0;
}

.message-author {
  font-size: 13px;
  font-weight: 750;
  color: #0f172a;
}

.message-badge {
  margin-left: 8px;
  border-radius: 999px;
  background: #dbeafe;
  padding: 3px 8px;
  color: #1d4ed8;
  font-size: 12px;
}

.message-badge.success {
  background: #dcfce7;
  color: #15803d;
}

.message-badge.warning {
  background: #fef3c7;
  color: #92400e;
}

.message-content {
  margin-top: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
  padding: 13px 14px;
  color: #1e293b;
  font-size: 15px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

.strategy-draft,
.citation-box,
.diagnostic-box,
.reasoning-box,
.execution-box {
  margin-top: 12px;
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #fff;
  padding: 12px;
}

.strategy-draft {
  border-color: #bbf7d0;
  background: #f0fdf4;
}

.draft-title {
  font-weight: 750;
  color: #14532d;
}

.draft-meta,
.draft-rationale,
.draft-list,
.execution-box {
  margin-top: 6px;
  color: #166534;
  font-size: 12px;
  line-height: 1.6;
}

.draft-actions,
.dialog-actions {
  flex-wrap: wrap;
}

.primary-action,
.secondary-action {
  padding: 7px 10px;
  font-size: 12px;
}

.draft-stats,
.metric-grid {
  display: grid;
  gap: 8px;
}

.draft-stats {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: 10px;
}

.draft-stats span {
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
  padding: 8px;
  color: #14532d;
  font-size: 12px;
}

.draft-list {
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.82);
  padding: 9px;
}

.draft-list.warning {
  border-color: #fde68a;
  background: #fffbeb;
  color: #92400e;
}

.draft-warning {
  margin-top: 8px;
  border: 1px solid #fde68a;
  border-radius: 8px;
  background: #fffbeb;
  padding: 8px 10px;
  color: #92400e;
  font-size: 12px;
  line-height: 1.6;
}

.draft-list-title,
.execution-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 5px;
  font-weight: 750;
}

.report-box,
.analysis-box {
  margin-top: 10px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #eff6ff;
  padding: 10px;
  color: #1e3a8a;
}

.reasoning-box {
  background: #fffbeb;
  color: #92400e;
}

.diagnostic-box {
  border-color: #fde68a;
  background: #fffbeb;
  color: #92400e;
  font-size: 13px;
  line-height: 1.7;
}

.diagnostic-box.ai_provider_failed {
  border-color: #fecaca;
  background: #fef2f2;
  color: #991b1b;
}

.citation-head {
  margin-bottom: 8px;
  color: #334155;
  font-size: 12px;
  font-weight: 750;
}

.citation-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 20px;
  gap: 10px;
  width: 100%;
  align-items: start;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  padding: 10px;
  text-align: left;
}

.citation-item + .citation-item {
  margin-top: 8px;
}

.citation-index {
  display: inline-flex;
  width: 24px;
  height: 24px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 750;
}

.citation-content {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.citation-content strong {
  color: #0f172a;
  font-size: 13px;
}

.citation-content small,
.citation-content span {
  color: #64748b;
  font-size: 12px;
}

.typing-line {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid #dbe3ef;
  border-radius: 999px;
  background: #fff;
  padding: 8px 12px;
  color: #64748b;
  font-size: 13px;
}

.typing-line span {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: #0f766e;
  animation: pulse-dot 1.2s infinite ease-in-out;
}

.typing-line span:nth-child(2) {
  animation-delay: 0.12s;
}

.typing-line span:nth-child(3) {
  animation-delay: 0.24s;
}

.composer {
  border-top: 1px solid #e2e8f0;
  background: #fff;
  padding: 14px;
}

.composer-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: #64748b;
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

.send-button {
  min-width: 104px;
  padding: 0 16px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #cbd5e1;
}

.status-dot.active {
  background: #14b8a6;
}

.kb-card {
  margin-top: 14px;
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #f8fafc;
  padding: 12px;
}

.kb-name {
  font-weight: 750;
}

.kb-desc {
  margin-top: 5px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.metric-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 12px;
}

.metric-grid div {
  border-radius: 8px;
  background: #fff;
  padding: 8px;
}

.metric-grid span {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.metric-grid strong {
  display: block;
  margin-top: 2px;
  color: #0f172a;
}

.wide-link {
  width: 100%;
  margin-top: 12px;
  padding: 9px 12px;
}

.kb-index-warning {
  margin-top: 12px;
  border: 1px solid #fde68a;
  border-radius: 8px;
  background: #fffbeb;
  padding: 10px;
  color: #92400e;
  font-size: 12px;
  line-height: 1.6;
}

.kb-index-warning span {
  display: block;
  margin-top: 2px;
  color: #b45309;
}

.inline-link {
  margin-top: 8px;
  border: 0;
  background: transparent;
  padding: 0;
  color: #0f766e;
  font-size: 12px;
  font-weight: 750;
}

.tool-section {
  margin-top: 16px;
}

.tool-item {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 10px;
  width: 100%;
  margin-top: 8px;
  padding: 10px;
}

.tool-item strong,
.tool-item small {
  display: block;
}

.tool-item strong {
  font-size: 13px;
}

.tool-item small {
  margin-top: 3px;
  color: #64748b;
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
  border: 1px solid #fde68a;
  border-radius: 8px;
  background: #fffbeb;
  padding: 10px;
  color: #92400e;
  font-size: 13px;
}

@keyframes pulse-dot {
  0%,
  80%,
  100% {
    transform: scale(0.7);
    opacity: 0.45;
  }

  40% {
    transform: scale(1);
    opacity: 1;
  }
}

@media (max-width: 1280px) {
  .workspace-grid {
    grid-template-columns: 260px minmax(0, 1fr);
  }

  .insight-panel {
    grid-column: 1 / -1;
    min-height: auto;
  }
}

@media (max-width: 900px) {
  .ai-hero {
    grid-template-columns: 1fr;
  }

  .hero-controls {
    align-items: stretch;
    flex-direction: column;
  }

  .control-label select {
    min-width: 0;
    width: 100%;
  }

  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .ai-panel,
  .chat-shell {
    min-height: auto;
  }

  .conversation-panel {
    max-height: 360px;
    overflow: auto;
  }

  .prompt-grid,
  .draft-stats,
  .dialog-grid {
    grid-template-columns: 1fr;
  }

  .composer-row {
    grid-template-columns: 1fr;
  }

  .send-button {
    min-height: 44px;
  }
}
</style>
