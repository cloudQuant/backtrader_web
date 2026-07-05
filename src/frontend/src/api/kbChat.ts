import api from './index'
import type { ParamSpec } from '@/types'

export const KB_CHAT_SEND_TIMEOUT_MS = 120000

export type KBAssistantMode =
  | 'knowledge_qa'
  | 'strategy_idea'
  | 'backtrader_strategy'
  | 'strategy_review'
  | 'trading_execution'
  | 'stock_analysis'

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
  knowledge_base_id?: string | null
  title: string
  model_id?: string | null
  created_at: string
  updated_at: string
}

export interface KBStockAnalysisParams {
  symbol: string
  market_type?: string
  analysis_date?: string
  research_depth?: string
  selected_modules?: string[]
  include_sentiment?: boolean
  include_risk?: boolean
  language?: string
  model_id?: string
}

export interface KBStockAnalysisTask {
  task_id: string
  symbol: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress: number
  current_step?: string | null
  message?: string | null
}

export interface KBStockAnalysisReport {
  report_id: string
  symbol: string
  summary: string
  decision_label: string
  risk_level: string
  confidence_score?: number | null
  export_formats: Array<'markdown' | 'html' | 'docx' | 'pdf'>
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
  score_breakdown?: Record<string, number> | null
}

export interface KBRetrievalDiagnostics {
  retrieval_profile: string
  search_mode: string
  search_query: string
  query_rewritten?: boolean
  applied_top_k: number
  applied_min_similarity: number
  history_messages_used?: number
  total_indexable_documents?: number
  indexed_documents?: number
  coverage_ratio?: number
}

export interface KBHistoryMessage {
  id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  citations?: KBCitation[] | null
  tokens_used?: number | null
  model_id?: string | null
  assistant_mode?: KBAssistantMode | null
  strategy_draft?: KBStrategyDraft | null
  reasoning?: string | null
  reason_code?: KBReasonCode | null
  diagnostic_message?: string | null
  diagnostics?: KBRetrievalDiagnostics | null
  stock_analysis_task?: KBStockAnalysisTask | null
  stock_analysis_report?: KBStockAnalysisReport | null
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
  stock_analysis_task?: KBStockAnalysisTask | null
  stock_analysis_report?: KBStockAnalysisReport | null
  reasoning?: string | null
  reason_code?: KBReasonCode | null
  diagnostic_message?: string | null
  diagnostics?: KBRetrievalDiagnostics | null
}

export const kbChatApi = {
  listConversations(knowledgeBaseId?: string | null, params?: { skip?: number; limit?: number }) {
    const requestParams: Record<string, unknown> = { ...params }
    if (knowledgeBaseId) {
      requestParams.knowledge_base_id = knowledgeBaseId
    }
    return api.get<KBConversationListResponse>('/kb-chat/conversations', {
      params: requestParams,
    })
  },
  getHistory(conversationId: string) {
    return api.get<KBHistoryResponse>(`/kb-chat/history/${conversationId}`)
  },
  send(data: {
    knowledge_base_id?: string | null
    question: string
    conversation_id?: string | null
    model_id?: string
    assistant_mode?: KBAssistantMode
    thinking_mode?: boolean
    stock_analysis_params?: KBStockAnalysisParams
  }) {
    const payload: Record<string, unknown> = {
      question: data.question,
      conversation_id: data.conversation_id,
      model_id: data.model_id,
      assistant_mode: data.assistant_mode,
      thinking_mode: data.thinking_mode,
    }
    if (data.knowledge_base_id) {
      payload.knowledge_base_id = data.knowledge_base_id
    }
    if (data.stock_analysis_params) {
      payload.stock_analysis_params = data.stock_analysis_params
    }
    return api.post<KBAskResponse>('/kb-chat/send', payload, {
      timeout: KB_CHAT_SEND_TIMEOUT_MS,
    })
  },
}
