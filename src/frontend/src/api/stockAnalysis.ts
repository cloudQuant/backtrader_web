import api from './index'

export type StockAnalysisExportFormat = 'markdown' | 'html' | 'docx' | 'pdf'
export type StockAnalysisModule = 'market' | 'social' | 'news' | 'fundamentals' | 'risk'
export type StockSignalAction = 'BUY' | 'SELL' | 'WATCH'
export type StockSignalEligibility = 'eligible' | 'degraded' | 'rejected'
export type StockSignalOutcomeStatus = 'pending' | 'partial' | 'scored' | 'unscorable'

export interface StockAnalysisCreateTaskParams {
  symbol: string
  market_type: string
  analysis_date?: string | null
  research_depth: string
  selected_modules: StockAnalysisModule[]
  include_sentiment: boolean
  include_risk: boolean
  language: string
  model_id?: string | null
}

export interface StockAnalysisTask {
  task_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  symbol: string
  symbol_name?: string | null
  market_type: string
  analysis_date: string
  research_depth: string
  selected_modules: string[]
  progress: number
  current_step?: string | null
  message?: string | null
  error_message?: string | null
  report_id?: string | null
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

export interface StockAnalysisResult {
  task_id: string
  report_id?: string | null
  status: StockAnalysisTask['status']
  report?: Record<string, unknown> | null
}

export interface StockAnalysisLatestResult {
  task: StockAnalysisTask
  report: Record<string, unknown>
}

export interface StockAnalysisSavedDocument {
  document_id: string
  knowledge_base_id: string
  report_id: string
  title: string
  content_type: string
  status: string
  index_status: string
  created_at: string
}

export interface StockAnalysisSavedWorkspaceReport {
  workspace_id: string
  report_id: string
  task_id: string
  title: string
  symbol: string
  decision_label: string
  risk_level: string
  saved_at: string
}

export interface StockSignalRecord {
  id: string
  source: string
  universe_code: string
  symbol: string
  symbol_name?: string | null
  market_type: string
  as_of_date: string
  available_at: string
  next_trading_date?: string | null
  signal_action: StockSignalAction
  action_label: string
  confidence_score: number
  risk_score: number
  expected_excess_return?: number | null
  eligibility_status: StockSignalEligibility
  quality_reasons: string[]
  feature_version: string
  decision_policy_version: string
  model_version: string
  outcome_status: StockSignalOutcomeStatus
  outcome_reason?: string | null
  entry_date?: string | null
  entry_price?: number | null
  horizon_1d_return?: number | null
  horizon_5d_return?: number | null
  horizon_20d_return?: number | null
  benchmark_20d_return?: number | null
  excess_20d_return?: number | null
  buy_is_correct_20d?: boolean | null
  sell_is_correct_20d?: boolean | null
}

export interface StockSignalHistory {
  items: StockSignalRecord[]
  next_cursor?: string | null
}

export interface StockSignalActionSummary {
  action: StockSignalAction
  generated_count: number
  scorable_count: number
  success_count: number
  success_rate?: number | null
  average_return?: number | null
  median_return?: number | null
  average_excess_return?: number | null
}

export interface StockSignalSummary {
  symbol: string
  horizon: 1 | 5 | 20
  actioned_generated_count: number
  actioned_scorable_count: number
  actioned_success_count: number
  actioned_success_rate?: number | null
  coverage_rate?: number | null
  maturity_rate?: number | null
  actions: StockSignalActionSummary[]
  confidence_bins: Array<{
    label: string
    lower: number
    upper: number
    scorable_count: number
    success_rate?: number | null
  }>
}

export interface StockSignalRun {
  id: string
  source: string
  universe_code: string
  as_of_date: string
  status: string
  expected_count: number
  created_count: number
  eligible_count: number
  degraded_count: number
  failed_count: number
  started_at?: string | null
  finished_at?: string | null
}

export interface OpeningActionPreview {
  execution_disabled: true
  as_of_date: string
  next_trading_date?: string | null
  actions: Array<{
    prediction_id: string
    symbol: string
    symbol_name?: string | null
    signal_action: StockSignalAction
    action_label: string
    suggested_action: 'BUY_AT_OPEN' | 'SELL_AT_OPEN' | 'NO_ACTION'
    next_trading_date?: string | null
    decision_policy_version: string
    model_version: string
    eligibility_status: StockSignalEligibility
  }>
}

export const stockAnalysisApi = {
  createTask(data: StockAnalysisCreateTaskParams) {
    return api.post<StockAnalysisTask>('/stock-analysis/tasks', data)
  },
  getTask(taskId: string) {
    return api.get<StockAnalysisTask>(`/stock-analysis/tasks/${taskId}`)
  },
  getTaskResult(taskId: string) {
    return api.get<StockAnalysisResult>(`/stock-analysis/tasks/${taskId}/result`)
  },
  getLatestResult() {
    return api.get<StockAnalysisLatestResult | null>('/stock-analysis/reports/latest')
  },
  cancelTask(taskId: string) {
    return api.post<StockAnalysisTask>(`/stock-analysis/tasks/${taskId}/cancel`)
  },
  retryTask(taskId: string) {
    return api.post<StockAnalysisTask>(`/stock-analysis/tasks/${taskId}/retry`)
  },
  exportReport(reportId: string, format: StockAnalysisExportFormat) {
    return api.get<Blob>(`/stock-analysis/reports/${reportId}/export`, {
      params: { format },
      responseType: 'blob',
    })
  },
  saveToKnowledgeBase(reportId: string, knowledgeBaseId: string, title?: string) {
    return api.post<StockAnalysisSavedDocument>(
      `/stock-analysis/reports/${reportId}/save-to-knowledge-base`,
      {
        knowledge_base_id: knowledgeBaseId,
        ...(title ? { title } : {}),
      },
    )
  },
  saveToWorkspace(reportId: string, workspaceId: string, title?: string) {
    return api.post<StockAnalysisSavedWorkspaceReport>(
      `/stock-analysis/reports/${reportId}/save-to-workspace`,
      {
        workspace_id: workspaceId,
        ...(title ? { title } : {}),
      },
    )
  },
  getSignalHistory(symbol: string, params?: { source?: string; limit?: number; cursor?: string }) {
    return api.get<StockSignalHistory>('/stock-analysis/signals', {
      params: { symbol, ...params },
    })
  },
  getSignalSummary(symbol: string, horizon: 1 | 5 | 20 = 20) {
    return api.get<StockSignalSummary>('/stock-analysis/signals/summary', {
      params: { symbol, horizon },
    })
  },
  getLatestSignalRun() {
    return api.get<StockSignalRun | null>('/stock-analysis/signals/runs/latest')
  },
  previewOpeningActions(heldSymbols: string[], asOfDate?: string) {
    return api.post<OpeningActionPreview>('/stock-analysis/signals/opening-actions/preview', {
      held_symbols: heldSymbols,
      ...(asOfDate ? { as_of_date: asOfDate } : {}),
    })
  },
}
