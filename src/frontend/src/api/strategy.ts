import api from './index'
import type {
  ParamSpec,
  Strategy,
  StrategyCreate,
  StrategyListResponse,
  StrategyTemplate,
  StrategyConfig,
  StrategyType,
} from '@/types'
import type {
  StrategyUnit,
  UnitStatusResponse,
  WorkspaceReportCreateRequest,
  WorkspaceReportResponse,
} from '@/types/workspace'

export interface StrategyCopilotDataSource {
  type: string
  symbol?: string | null
  symbol_name?: string | null
  timeframe: string
  timeframe_n: number
  start_date?: string | null
  end_date?: string | null
  adjustment?: string | null
}

export interface StrategyCopilotBacktestDefaults {
  initial_cash: number
  commission: number
  annual_days: number
  calc_method: string
  weight_mode: string
}

export interface StrategyCopilotExecutionPlan {
  workspace_type: string
  group_name?: string | null
  run_parallel: boolean
}

export interface StrategyCopilotDraft {
  name: string
  description: string
  code: string
  params: Record<string, ParamSpec>
  category: string
  assumptions: string[]
  risk_points: string[]
  data_source: StrategyCopilotDataSource
  backtest_defaults: StrategyCopilotBacktestDefaults
  execution_plan: StrategyCopilotExecutionPlan
  rationale?: string | null
  next_steps?: string[]
  suggested_symbol?: string | null
  suggested_timeframe?: string | null
}

export interface StrategyCopilotDraftRequest {
  prompt: string
  knowledge_base_id?: string | null
  thinking_mode?: boolean
}

export interface StrategyCopilotDraftResponse {
  answer: string
  strategy_draft: StrategyCopilotDraft
  citations: Array<Record<string, unknown>>
  context_chunks_used: number
  tokens_used: number
  model_id?: string | null
  reasoning?: string | null
}

export interface StrategyCopilotWorkspaceAddRequest {
  strategy_draft: StrategyCopilotDraft
  strategy_id?: string | null
  symbol?: string
  symbol_name?: string
  timeframe?: string | null
  timeframe_n?: number
  group_name?: string
  data_config?: Record<string, unknown>
  unit_settings?: Record<string, unknown>
  optimization_config?: Record<string, unknown>
}

export interface StrategyCopilotWorkspaceAddResponse {
  workspace_id: string
  created_strategy: boolean
  strategy: Strategy
  unit: StrategyUnit
}

export interface StrategyCopilotBacktestRequest extends StrategyCopilotWorkspaceAddRequest {
  parallel?: boolean
  report_config?: WorkspaceReportCreateRequest | null
}

export interface StrategyCopilotRunResult {
  unit_id: string
  task_id?: string | null
  status: string
  error?: string | null
}

export interface StrategyCopilotBacktestResponse {
  workspace_id: string
  created_strategy: boolean
  strategy: Strategy
  unit: StrategyUnit
  run_result: StrategyCopilotRunResult
  unit_status?: UnitStatusResponse | null
  report_ready: boolean
  report?: WorkspaceReportResponse | null
}

export interface StrategyScoreDimension {
  key: string
  label: string
  score: number
  weight: number
  explanation: string
  sub_metrics: Record<string, unknown>
  degraded: boolean
}

export interface StrategyScoreRequest {
  backtest_id?: string
  backtest_result?: Record<string, unknown> | null
}

export interface StrategyScoreResponse {
  backtest_id: string
  total_score: number
  level: 'S' | 'A' | 'B' | 'C' | 'D'
  model_version: string
  disclaimer: string
  dimensions: StrategyScoreDimension[]
}

export type StrategyOverfittingMethod = 'walk_forward' | 'out_of_sample' | 'monte_carlo'
export type StrategyOverfittingRiskLevel = 'low' | 'medium' | 'high'

export interface StrategyOverfittingAnalysisRequest {
  methods: StrategyOverfittingMethod[]
  walk_forward_train_days?: number
  walk_forward_test_days?: number
  walk_forward_step_days?: number
  walk_forward_max_concurrency?: number
  out_of_sample_ratio?: number
  monte_carlo_iterations?: number
  random_seed?: number | null
}

export interface StrategyOverfittingMethodResult {
  method: StrategyOverfittingMethod
  status: string
  risk_level: StrategyOverfittingRiskLevel
  score: number
  explanation: string
  metrics: Record<string, unknown>
  degraded: boolean
}

export interface StrategyOverfittingTaskSubmission {
  task_id: string
  backtest_id: string
  status: string
  methods: StrategyOverfittingMethod[]
}

export interface StrategyOverfittingTaskResult {
  task_id: string
  backtest_id: string
  status: string
  overall_level: StrategyOverfittingRiskLevel
  robustness_score: number
  summary: string
  methods: StrategyOverfittingMethodResult[]
  error_message?: string | null
}

export interface StrategyIndicator {
  name: string
  alias?: string | null
  params: Record<string, unknown>
}

export interface StrategySignal {
  condition: string
  side: string
}

export interface StrategyRiskControl {
  type: string
  value?: unknown
  source?: string | null
}

export interface StrategyParamInfo {
  name: string
  default?: unknown
}

export interface StrategyStructure {
  parsable: boolean
  indicators: StrategyIndicator[]
  entry_signals: StrategySignal[]
  exit_signals: StrategySignal[]
  risk_controls: StrategyRiskControl[]
  params: StrategyParamInfo[]
  data_sources: string[]
  raw_code?: string | null
  parse_error?: string | null
}

export interface StrategyExplainRequest {
  code?: string | null
  strategy_id?: string | null
  backtest_id?: string | null
  strategy_name?: string | null
  category?: string | null
  params?: Record<string, unknown> | null
}

export interface StrategyExplanation {
  code_hash: string
  strategy_name: string
  summary: string
  indicators_explanation: string
  entry_explanation: string
  exit_explanation: string
  params_explanation: string
  market_fit: string
  risk_notes: string[]
  ast: StrategyStructure
  reason_code: string
  model_id?: string | null
  cached: boolean
  disclaimer: string
}

export const strategyApi = {
  async create(data: StrategyCreate): Promise<Strategy> {
    return api.post<Strategy, StrategyCreate>('/strategy/', data)
  },

  async generateCopilotDraft(data: StrategyCopilotDraftRequest): Promise<StrategyCopilotDraftResponse> {
    return api.post<StrategyCopilotDraftResponse, StrategyCopilotDraftRequest>('/strategy/copilot/draft', data)
  },

  async addCopilotDraftToWorkspace(
    workspaceId: string,
    data: StrategyCopilotWorkspaceAddRequest
  ): Promise<StrategyCopilotWorkspaceAddResponse> {
    return api.post<StrategyCopilotWorkspaceAddResponse, StrategyCopilotWorkspaceAddRequest>(
      `/strategy/copilot/workspaces/${workspaceId}/units`,
      data
    )
  },

  async backtestCopilotDraft(
    workspaceId: string,
    data: StrategyCopilotBacktestRequest
  ): Promise<StrategyCopilotBacktestResponse> {
    return api.post<StrategyCopilotBacktestResponse, StrategyCopilotBacktestRequest>(
      `/strategy/copilot/workspaces/${workspaceId}/backtest`,
      data
    )
  },

  async createScore(data: StrategyScoreRequest): Promise<StrategyScoreResponse> {
    return api.post<StrategyScoreResponse, StrategyScoreRequest>('/strategy/score', data)
  },

  async getScore(backtestId: string): Promise<StrategyScoreResponse> {
    return api.get<StrategyScoreResponse>(`/strategy/score/${backtestId}`)
  },

  async createOverfittingTask(
    backtestId: string,
    data: StrategyOverfittingAnalysisRequest
  ): Promise<StrategyOverfittingTaskSubmission> {
    return api.post<StrategyOverfittingTaskSubmission, StrategyOverfittingAnalysisRequest>(
      `/strategy/overfitting/${backtestId}`,
      data,
    )
  },

  async getOverfittingTask(taskId: string): Promise<StrategyOverfittingTaskResult> {
    return api.get<StrategyOverfittingTaskResult>(`/strategy/overfitting/task/${taskId}`)
  },

  async explainStrategy(data: StrategyExplainRequest): Promise<StrategyExplanation> {
    return api.post<StrategyExplanation, StrategyExplainRequest>('/strategy/explain', data)
  },

  async getCachedExplanation(codeHash: string): Promise<StrategyExplanation> {
    return api.get<StrategyExplanation>(`/strategy/explain/cached/${codeHash}`)
  },

  async get(id: string): Promise<Strategy> {
    return api.get<Strategy>(`/strategy/${id}`)
  },

  async update(id: string, data: Partial<StrategyCreate>): Promise<Strategy> {
    return api.put<Strategy, Partial<StrategyCreate>>(`/strategy/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    return api.delete<void>(`/strategy/${id}`)
  },

  async list(limit = 20, offset = 0, category?: string): Promise<StrategyListResponse> {
    return api.get<StrategyListResponse>('/strategy/', { params: { limit, offset, category } })
  },

  async getTemplates(strategyType?: StrategyType): Promise<{ templates: StrategyTemplate[]; total: number }> {
    return api.get<{ templates: StrategyTemplate[]; total: number }>('/strategy/templates', {
      params: { strategy_type: strategyType },
    })
  },

  async getTemplateDetail(id: string): Promise<StrategyTemplate> {
    return api.get<StrategyTemplate>(`/strategy/templates/${id}`)
  },

  async getTemplateReadme(id: string): Promise<{ template_id: string; content: string }> {
    return api.get<{ template_id: string; content: string }>(`/strategy/templates/${id}/readme`)
  },

  async getTemplateConfig(id: string): Promise<StrategyConfig> {
    return api.get<StrategyConfig>(`/strategy/templates/${id}/config`)
  },
}
