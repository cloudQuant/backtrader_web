import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getErrorMessage } from '@/api'
import i18n from '@/i18n'
import {
  kbChatApi,
  type KBAssistantMode,
  type KBCitation,
  type KBConversation,
  type KBHistoryMessage,
  type KBRetrievalDiagnostics,
  type KBReasonCode,
  type KBStrategyDraft,
  type KBStockAnalysisReport,
  type KBStockAnalysisParams,
  type KBStockAnalysisTask,
} from '@/api/kbChat'

function tt(key: string): string {
  return i18n.global.t(key)
}

function isTimeoutError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const candidate = error as { code?: unknown; message?: unknown }
  if (candidate.code === 'ECONNABORTED') return true
  return typeof candidate.message === 'string' && /timeout.*exceeded/i.test(candidate.message)
}

function getChatErrorMessage(error: unknown): string {
  if (isTimeoutError(error)) {
    return tt('kbChatStore.msgRequestTimeout')
  }
  return getErrorMessage(error, tt('kbChatStore.msgRequestFailed'))
}

export interface KBChatMessage {
  role: 'user' | 'assistant'
  content: string
  citations?: KBCitation[]
  assistantMode?: KBAssistantMode
  strategyDraft?: KBStrategyDraft | null
  stockAnalysisTask?: KBStockAnalysisTask | null
  stockAnalysisReport?: KBStockAnalysisReport | null
  reasoning?: string | null
  reasonCode?: KBReasonCode | null
  diagnosticMessage?: string | null
  diagnostics?: KBRetrievalDiagnostics | null
}

export const useKBChatStore = defineStore('kbChat', () => {
  const conversations = ref<KBConversation[]>([])
  const messages = ref<KBChatMessage[]>([])
  const currentConversationId = ref<string | null>(null)
  const loading = ref(false)

  async function fetchConversations(knowledgeBaseId?: string | null) {
    const response = await kbChatApi.listConversations(knowledgeBaseId)
    conversations.value = Array.isArray(response.items) ? response.items : []
    return response
  }

  async function fetchHistory(conversationId: string) {
    loading.value = true
    try {
      const response = await kbChatApi.getHistory(conversationId)
      currentConversationId.value = response.conversation_id ?? conversationId
      const historyMessages = Array.isArray(response.messages) ? response.messages : []
      messages.value = historyMessages.map((message: KBHistoryMessage) => ({
        role: message.role === 'assistant' ? 'assistant' : 'user',
        content: typeof message.content === 'string' ? message.content : '',
        citations: Array.isArray(message.citations) ? message.citations : undefined,
        assistantMode: message.assistant_mode ?? undefined,
        strategyDraft: message.strategy_draft ?? null,
        reasoning: message.reasoning ?? undefined,
        reasonCode: message.reason_code ?? undefined,
        diagnosticMessage: message.diagnostic_message ?? undefined,
        diagnostics: message.diagnostics ?? undefined,
        stockAnalysisTask: message.stock_analysis_task ?? null,
        stockAnalysisReport: message.stock_analysis_report ?? null,
      }))
      return response
    } finally {
      loading.value = false
    }
  }

  function resetConversationState() {
    currentConversationId.value = null
    messages.value = []
  }

  async function deleteConversation(conversationId: string) {
    const response = await kbChatApi.deleteConversation(conversationId)
    conversations.value = conversations.value.filter(conversation => conversation.id !== conversationId)
    if (currentConversationId.value === conversationId) {
      resetConversationState()
    }
    return response
  }

  async function sendMessage(
    knowledgeBaseId: string | null,
    question: string,
    options?: {
      assistantMode?: KBAssistantMode
      thinkingMode?: boolean
      modelId?: string
      stockAnalysisParams?: KBStockAnalysisParams
    },
  ) {
    loading.value = true
    try {
      messages.value.push({ role: 'user', content: question })
      const request: Parameters<typeof kbChatApi.send>[0] = {
        question,
        conversation_id: currentConversationId.value,
        model_id: options?.modelId,
        assistant_mode: options?.assistantMode,
        thinking_mode: options?.thinkingMode,
      }
      if (knowledgeBaseId) {
        request.knowledge_base_id = knowledgeBaseId
      }
      if (options?.stockAnalysisParams) {
        request.stock_analysis_params = options.stockAnalysisParams
      }
      const response = await kbChatApi.send(request)
      currentConversationId.value = response.conversation_id ?? currentConversationId.value
      messages.value.push({
        role: 'assistant',
        content: typeof response.answer === 'string' && response.answer
          ? response.answer
          : tt('kbChatStore.msgEmptyAnswer'),
        citations: Array.isArray(response.citations) ? response.citations : undefined,
        assistantMode: response.assistant_mode ?? options?.assistantMode,
        strategyDraft: response.strategy_draft ?? null,
        stockAnalysisTask: response.stock_analysis_task ?? null,
        stockAnalysisReport: response.stock_analysis_report ?? null,
        reasoning: response.reasoning ?? undefined,
        reasonCode: response.reason_code ?? undefined,
        diagnosticMessage: response.diagnostic_message ?? undefined,
        diagnostics: response.diagnostics ?? undefined,
      })
      try {
        await fetchConversations(knowledgeBaseId)
      } catch {
        conversations.value = Array.isArray(conversations.value) ? conversations.value : []
      }
      return response
    } catch (error) {
      messages.value.push({
        role: 'assistant',
        content: getChatErrorMessage(error),
      })
      throw error
    } finally {
      loading.value = false
    }
  }

  return {
    conversations,
    messages,
    currentConversationId,
    loading,
    fetchConversations,
    fetchHistory,
    resetConversationState,
    deleteConversation,
    sendMessage,
  }
})
