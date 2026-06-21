import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

import { getErrorMessage } from '@/api'
import { aiObservabilityApi, type AIModelOption } from '@/api/aiObservability'
import type { KBAssistantMode, KBStockAnalysisParams, KBStrategyDraft } from '@/api/kbChat'
import type { KnowledgeBaseSettings } from '@/api/knowledgeBase'
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

type StockMarketCode = 'cn_a' | 'hk' | 'us'
type StockResearchDepthCode = 'quick' | 'basic' | 'standard' | 'deep' | 'full'

// i18n-ignore-next-line
// i18n-reason: Internal API value map encoded with unicode escapes, not user-facing literals.
const STOCK_MARKET_VALUES: Record<StockMarketCode, string> = { cn_a: 'A\u80a1', hk: '\u6e2f\u80a1', us: '\u7f8e\u80a1' }
// i18n-ignore-next-line
// i18n-reason: Internal API value map encoded with unicode escapes, not user-facing literals.
const STOCK_DEPTH_VALUES: Record<StockResearchDepthCode, string> = { quick: '\u5feb\u901f', basic: '\u57fa\u7840', standard: '\u6807\u51c6', deep: '\u6df1\u5ea6', full: '\u5168\u9762' }
// i18n-ignore-next-line
// i18n-reason: Internal prompt map encoded with unicode escapes, not user-facing literals.
const STOCK_MODULE_PROMPT_LABELS: Record<string, string> = { market: '\u6280\u672f\u9762', social: '\u60c5\u7eea', news: '\u65b0\u95fb', fundamentals: '\u57fa\u672c\u9762', risk: '\u98ce\u9669' }
// i18n-ignore-next-line
// i18n-reason: Internal prompt map encoded with unicode escapes, not user-facing literals.
const STOCK_DEPTH_PROMPT_LABELS: Record<string, string> = { quick: '\u5feb\u901f\u5206\u6790', basic: '\u57fa\u7840\u6df1\u5ea6', standard: '\u6807\u51c6\u6df1\u5ea6', deep: '\u6df1\u5ea6\u7814\u7a76', full: '\u5168\u9762\u7814\u7a76' }
const STOCK_PROMPT_DEFAULT_FOCUS = '\u6280\u672f\u9762\u3001\u57fa\u672c\u9762\u3001\u65b0\u95fb\u98ce\u9669'

export function useAIChatPage() {
  const { t } = useI18n()
  const router = useRouter()
  const route = useRoute()
  const kbStore = useKnowledgeBaseStore()
  const chatStore = useKBChatStore()

  const selectedKnowledgeBaseId = ref('')
  const selectedAssistantMode = ref<KBAssistantMode>('knowledge_qa')
  const thinkingMode = ref(false)
  const leftPanelCollapsed = ref(false)
  const rightPanelCollapsed = ref(false)
  const conversationSearch = ref('')
  const question = ref('')
  const selectedSessionModelKey = ref('')
  const stockAnalysisForm = ref({
    symbol: '000001.SZ',
    marketType: 'cn_a' as StockMarketCode,
    analysisDate: new Date().toISOString().slice(0, 10),
    researchDepth: 'standard' as StockResearchDepthCode,
    modules: ['market', 'social', 'news', 'fundamentals', 'risk'],
  })
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

  const currentModeMeta = computed(() => assistantModeMetaMap.value[selectedAssistantMode.value])
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

  function handleContinueFromStockAnalysis(mode: 'strategy_idea' | 'backtrader_strategy', prompt: string) {
    selectedAssistantMode.value = mode
    question.value = prompt
  }

  function buildStockAnalysisParams(): KBStockAnalysisParams {
    const modules = stockAnalysisForm.value.modules.length > 0
      ? stockAnalysisForm.value.modules
      : ['market', 'social', 'news', 'fundamentals', 'risk']
    return {
      symbol: stockAnalysisForm.value.symbol.trim().toUpperCase(),
      market_type: STOCK_MARKET_VALUES[stockAnalysisForm.value.marketType] ?? STOCK_MARKET_VALUES.cn_a,
      analysis_date: stockAnalysisForm.value.analysisDate || undefined,
      research_depth: STOCK_DEPTH_VALUES[stockAnalysisForm.value.researchDepth] ?? STOCK_DEPTH_VALUES.standard,
      selected_modules: modules,
      include_sentiment: modules.includes('social'),
      include_risk: modules.includes('risk'),
      language: 'zh-CN',
      model_id: selectedSessionModelKey.value || undefined,
    }
  }

  function buildStockAnalysisQuestion(params: KBStockAnalysisParams): string {
    const focus = (params.selected_modules ?? [])
      .map(module => STOCK_MODULE_PROMPT_LABELS[module] ?? module)
      .join('\u3001')
    const depth = Object.values(STOCK_DEPTH_PROMPT_LABELS).includes(String(params.research_depth))
      ? String(params.research_depth)
      : STOCK_DEPTH_PROMPT_LABELS[stockAnalysisForm.value.researchDepth] ?? STOCK_DEPTH_PROMPT_LABELS.standard
    return `\u5206\u6790 ${params.symbol}\uff0c${params.market_type ?? STOCK_MARKET_VALUES.cn_a}\uff0c${depth}\uff0c\u91cd\u70b9\u770b${focus || STOCK_PROMPT_DEFAULT_FOCUS}\u548c\u4ea4\u6613\u5efa\u8bae`
  }

  function toggleLeftPanel() {
    leftPanelCollapsed.value = !leftPanelCollapsed.value
  }

  function toggleRightPanel() {
    rightPanelCollapsed.value = !rightPanelCollapsed.value
  }

  function copyMessage(content: string) {
    navigator.clipboard.writeText(content).then(() => {
      ElMessage.success(t('aiChat.msgCopiedToClipboard'))
    })
  }

  function copyConversation() {
    const text = chatStore.messages
      .map(m => `${m.role === 'user' ? t('aiChat.rolePrefix') : 'AI'}:\n${m.content}`)
      .join('\n\n')
    navigator.clipboard.writeText(text).then(() => {
      ElMessage.success(t('aiChat.msgConversationCopied'))
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
      ElMessage.success(t('aiChat.msgStrategySaved', { name: created.name }))
    } catch {
      ElMessage.error(t('aiChat.msgStrategySaveFailed'))
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
      ElMessage.error(t('aiChat.msgLoadWorkspaceFailed'))
    }
  }

  async function handleConfirmAddToWorkspace(runBacktest = false) {
    if (!pendingWorkspaceDraft.value || pendingWorkspaceDraftIndex.value === null) return
    if (!workspaceDraftForm.value.workspaceId) {
      ElMessage.warning(t('aiChat.selectWorkspacePrompt'))
      return
    }
    if (!workspaceDraftForm.value.symbol.trim()) {
      ElMessage.warning(t('aiChat.msgEnterSymbol'))
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
        ElMessage.success(t('aiChat.msgAddedAndBacktest', { name: response.unit.strategy_name }))
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
      ElMessage.success(t('aiChat.msgAddedToWorkspace', { name: response.unit.strategy_name }))
    } catch {
      addingToWorkspace.value = false
      ElMessage.error(t('aiChat.msgAddToWorkspaceFailed'))
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

  async function sendQuestion(q: string, stockAnalysisParams?: KBStockAnalysisParams) {
    if (!selectedKnowledgeBaseId.value || !q.trim()) return
    question.value = ''
    try {
      const options: {
        assistantMode?: KBAssistantMode
        thinkingMode?: boolean
        modelId?: string
        stockAnalysisParams?: KBStockAnalysisParams
      } = {
        assistantMode: selectedAssistantMode.value,
        thinkingMode: thinkingMode.value,
        modelId: selectedSessionModelKey.value || undefined,
      }
      if (stockAnalysisParams) {
        options.stockAnalysisParams = stockAnalysisParams
      }
      await chatStore.sendMessage(selectedKnowledgeBaseId.value, q, options)
    } catch (error) {
      ElMessage.error(getErrorMessage(error, t('aiChat.msgSendFailedKbOrModel')))
    }
  }

  async function handleAsk() {
    if (!selectedKnowledgeBaseId.value || !question.value.trim()) return
    const stockAnalysisParams = selectedAssistantMode.value === 'stock_analysis'
      ? buildStockAnalysisParams()
      : undefined
    await sendQuestion(question.value.trim(), stockAnalysisParams)
  }

  async function handleStockAnalysisSubmit() {
    if (!stockAnalysisForm.value.symbol.trim()) {
      ElMessage.warning(t('aiChat.stockSymbolRequired'))
      return
    }
    const params = buildStockAnalysisParams()
    await sendQuestion(buildStockAnalysisQuestion(params), params)
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
      ElMessage.warning(t('aiChat.msgCitationMissingDoc'))
      return
    }
    if (!currentKnowledgeBaseId.value) {
      ElMessage.warning(t('aiChat.selectKnowledgeBaseFirst'))
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
        ElMessage.error(getErrorMessage(error, t('aiChat.msgLoadKbDocsFailed')))
      }
      try {
        await chatStore.fetchConversations(value)
      } catch (error) {
        ElMessage.error(getErrorMessage(error, t('aiChat.msgLoadConversationsFailed')))
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
    if (mode && typeof mode === 'string' && mode in assistantModeMetaMap.value) {
      selectedAssistantMode.value = mode as KBAssistantMode
    }
  })

  return {
    // Stores
    kbStore,
    chatStore,
    router,
    // Refs
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
    // Workspace execution
    workspaceExecutions,
    runningBacktestIndex,
    refreshingStatusIndex,
    generatingReportIndex,
    // Computed
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
    // Re-exported rendering helpers
    assistantModeOptions,
    formatDate,
    retrievalProfileLabel,
    // Functions
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
  }
}
