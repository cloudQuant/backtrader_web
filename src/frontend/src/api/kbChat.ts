import api from './index'
import type { ParamSpec } from '@/types'

export type KBAssistantMode =
  | 'knowledge_qa'
  | 'strategy_idea'
  | 'backtrader_strategy'
  | 'strategy_review'

export type KBReasonCode =
  | 'no_context_found'
  | 'ai_not_configured'
  | 'ai_provider_failed'
  | string

export interface KBStrategyDraftDataSource {
  type: string
  symbol?: string | null
  symbol_name?: string | null
  timeframe: string
  timeframe_n: number
  start_date?: string | null
  end_date?: string | null
  adjustment?: string | null
}

export interface KBStrategyDraftBacktestDefaults {
  initial_cash: number
  commission: number
  annual_days: number
  calc_method: string
  weight_mode: string
}

export interface KBStrategyDraftExecutionPlan {
  workspace_type: string
  group_name?: string | null
  run_parallel: boolean
}

export interface KBStrategyDraft {
  name: string
  description: string
  code: string
  params: Record<string, ParamSpec>
  category: string
  assumptions: string[]
  risk_points: string[]
  data_source: KBStrategyDraftDataSource
  backtest_defaults: KBStrategyDraftBacktestDefaults
  execution_plan: KBStrategyDraftExecutionPlan
  rationale?: string | null
  next_steps?: string[]
  suggested_symbol?: string | null
  suggested_timeframe?: string | null
}

export interface KBConversation {
  id: string
  knowledge_base_id: string
  title: string
  model_id?: string | null
  created_at: string
  updated_at: string
}

export interface KBConversationListResponse {
  total: number
  items: KBConversation[]
}

export interface KBCitation {
  document_id?: string | null
  document_title?: string | null
  chunk_id?: string | null
  chunk_index?: number | null
  similarity?: number | null
  content?: string | null
}

export interface KBHistoryMessage {
  id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  citations?: KBCitation[] | null
  tokens_used?: number | null
  model_id?: string | null
  reasoning?: string | null
  reason_code?: KBReasonCode | null
  diagnostic_message?: string | null
  created_at: string
}

export interface KBHistoryResponse {
  conversation_id: string
  messages: KBHistoryMessage[]
}

export interface KBAskResponse {
  conversation_id: string
  answer: string
  citations: KBCitation[]
  context_chunks_used: number
  tokens_used: number
  model_id?: string | null
  assistant_mode?: KBAssistantMode
  strategy_draft?: KBStrategyDraft | null
  reasoning?: string | null
  reason_code?: KBReasonCode | null
  diagnostic_message?: string | null
}

export const kbChatApi = {
  listConversations(knowledgeBaseId: string, params?: { skip?: number; limit?: number }) {
    return api.get<KBConversationListResponse>('/kb-chat/conversations', {
      params: {
        knowledge_base_id: knowledgeBaseId,
        ...params,
      },
    })
  },
  getHistory(conversationId: string) {
    return api.get<KBHistoryResponse>(`/kb-chat/history/${conversationId}`)
  },
  send(data: {
    knowledge_base_id: string
    question: string
    conversation_id?: string | null
    model_id?: string
    assistant_mode?: KBAssistantMode
    thinking_mode?: boolean
  }) {
    return api.post<KBAskResponse>('/kb-chat/send', {
      knowledge_base_id: data.knowledge_base_id,
      question: data.question,
      conversation_id: data.conversation_id,
      model_id: data.model_id,
      assistant_mode: data.assistant_mode,
      thinking_mode: data.thinking_mode,
    })
  },
}
