import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getErrorMessage } from '@/api'
import {
  kbChatApi,
  type KBAssistantMode,
  type KBCitation,
  type KBConversation,
  type KBHistoryMessage,
  type KBRetrievalDiagnostics,
  type KBReasonCode,
  type KBStrategyDraft,
} from '@/api/kbChat'

export interface KBChatMessage {
  role: 'user' | 'assistant'
  content: string
  citations?: KBCitation[]
  assistantMode?: KBAssistantMode
  strategyDraft?: KBStrategyDraft | null
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

  async function fetchConversations(knowledgeBaseId: string) {
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
        reasoning: message.reasoning ?? undefined,
        reasonCode: message.reason_code ?? undefined,
        diagnosticMessage: message.diagnostic_message ?? undefined,
        diagnostics: message.diagnostics ?? undefined,
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

  async function sendMessage(
    knowledgeBaseId: string,
    question: string,
    options?: {
      assistantMode?: KBAssistantMode
      thinkingMode?: boolean
    },
  ) {
    loading.value = true
    try {
      messages.value.push({ role: 'user', content: question })
      const response = await kbChatApi.send({
        knowledge_base_id: knowledgeBaseId,
        question,
        conversation_id: currentConversationId.value,
        assistant_mode: options?.assistantMode,
        thinking_mode: options?.thinkingMode,
      })
      currentConversationId.value = response.conversation_id ?? currentConversationId.value
      messages.value.push({
        role: 'assistant',
        content: typeof response.answer === 'string' && response.answer
          ? response.answer
          : 'AI 未返回可展示内容。',
        citations: Array.isArray(response.citations) ? response.citations : undefined,
        assistantMode: response.assistant_mode ?? options?.assistantMode,
        strategyDraft: response.strategy_draft ?? null,
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
        content: getErrorMessage(error, '本次 AI 请求失败，请检查知识库索引或 AI 模型配置后重试。'),
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
    sendMessage,
  }
})
