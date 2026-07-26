import api from './index'

export type StockAnalysisExportFormat = 'markdown' | 'html' | 'docx' | 'pdf'
export type StockAnalysisModule = 'market' | 'social' | 'news' | 'fundamentals' | 'risk'

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
}
