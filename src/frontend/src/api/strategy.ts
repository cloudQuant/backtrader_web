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
  Workspace,
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

export interface AIStrategyResearchRunRequest {
  prompt: string
  symbol: string
  symbol_name?: string
  timeframe?: string
  timeframe_n?: number
  start_date?: string | null
  end_date?: string | null
  target_sharpe?: number
  min_total_trades?: number
  max_drawdown_limit?: number | null
  min_total_return?: number | null
  min_annual_return?: number | null
  min_win_rate?: number | null
  max_iterations?: number
  out_of_sample_validation?: boolean
  out_of_sample_ratio?: number
  min_out_of_sample_sharpe?: number | null
  min_out_of_sample_trades?: number | null
  backtest_timeout_seconds?: number
  poll_interval_seconds?: number
  initial_cash?: number
  commission?: number
  annual_days?: number
  calc_method?: string
  weight_mode?: string
  research_workspace_id?: string | null
  trading_workspace_id?: string | null
  seed_strategy_id?: string | null
  continue_from_run_id?: string | null
  start_paper_trading?: boolean
  paper_workspace_name?: string | null
  group_name?: string | null
  knowledge_base_id?: string | null
  thinking_mode?: boolean
  data_config?: Record<string, unknown>
  unit_settings?: Record<string, unknown>
  optimization_config?: Record<string, unknown>
  gateway_config?: Record<string, unknown>
}

export interface AIStrategyQualityGateEvaluation {
  key: string
  label: string
  actual?: number | null
  target: number
  direction: 'min' | 'max'
  passed: boolean
  score: number
}

export interface AIStrategyResearchDiagnostics {
  summary?: string
  metric_snapshot?: Record<string, number | null>
  failure_categories?: string[]
  strengths?: string[]
  weaknesses?: string[]
  improvement_plan?: string[]
  promotion_ready?: boolean
  out_of_sample_validation?: AIStrategyOutOfSampleValidation
}

export interface AIStrategyPaperMonitoringRule {
  key: string
  label: string
  metric: string
  window: string
  direction: 'min' | 'max'
  threshold: number
  action: string
}

export interface AIStrategyPaperTradingRuleEvaluation extends AIStrategyPaperMonitoringRule {
  actual?: number | null
  source?: string | null
  status: string
  passed: boolean
}

export interface AIStrategyResearchIteration {
  iteration: number
  strategy: Strategy
  unit: StrategyUnit
  run_result: StrategyCopilotRunResult
  unit_status?: UnitStatusResponse | null
  metrics: Record<string, unknown>
  sharpe_ratio: number
  total_trades: number
  validation_unit?: StrategyUnit | null
  validation_run_result?: StrategyCopilotRunResult | null
  validation_unit_status?: UnitStatusResponse | null
  validation_status?: string | null
  validation_window?: Record<string, string> | null
  validation_metrics?: Record<string, unknown>
  validation_gate_evaluations?: AIStrategyQualityGateEvaluation[]
  validation_failures?: string[]
  validation_failure_reason?: string | null
  quality_score: number
  quality_gate_evaluations: AIStrategyQualityGateEvaluation[]
  passed: boolean
  failure_reason?: string | null
  quality_gate_failures: string[]
  diagnostics?: AIStrategyResearchDiagnostics
  improvement_plan?: string[]
  improvement_notes: string[]
  next_actions: string[]
}

export interface AIStrategyOutOfSampleValidation {
  status?: string | null
  window?: Record<string, string> | null
  metrics?: Record<string, unknown>
  gate_evaluations?: AIStrategyQualityGateEvaluation[]
  failures?: string[]
  failure_reason?: string | null
}

export interface AIStrategyPaperTradingStart {
  workspace: Workspace
  unit: StrategyUnit
  run_result?: StrategyCopilotRunResult | null
  started: boolean
  handoff?: Record<string, unknown> | null
}

export interface AIStrategyPaperTradingStartRequest {
  research_workspace_id?: string | null
  trading_workspace_id?: string | null
  paper_workspace_name?: string | null
  gateway_config?: Record<string, unknown>
}

export interface AIStrategyLiveReadinessItem {
  key: string
  label: string
  status: string
  evidence: string
  action: string
  details?: Record<string, unknown>
}

export interface AIStrategyResearchRunRecord {
  run_id: string
  prompt: string
  symbol: string
  symbol_name: string
  timeframe: string
  timeframe_n: number
  start_date?: string | null
  end_date?: string | null
  initial_cash?: number
  commission?: number
  annual_days?: number
  calc_method?: string
  weight_mode?: string
  asset_specs?: Record<string, Record<string, unknown>>
  backtest_environment?: Record<string, unknown>
  knowledge_base_id?: string | null
  thinking_mode?: boolean
  status: string
  achieved: boolean
  target_sharpe: number
  quality_gates: Record<string, unknown>
  min_total_trades: number
  max_iterations: number
  backtest_timeout_seconds?: number
  poll_interval_seconds?: number
  iteration_count: number
  best_iteration?: number | null
  best_sharpe: number
  best_quality_score: number
  best_quality_gate_evaluations: AIStrategyQualityGateEvaluation[]
  best_diagnostics?: AIStrategyResearchDiagnostics
  best_metrics: Record<string, unknown>
  best_strategy_id?: string | null
  best_strategy_name?: string | null
  research_workspace_id: string
  seed_strategy_id?: string | null
  continued_from_run_id?: string | null
  paper_workspace_id?: string | null
  paper_workspace_name?: string | null
  paper_unit_id?: string | null
  paper_trading_started: boolean
  paper_monitoring_plan?: AIStrategyPaperMonitoringRule[]
  paper_handoff?: Record<string, unknown>
  paper_review_status?: string | null
  paper_review_ready_for_live?: boolean
  paper_reviewed_at?: string | null
  paper_review_evaluations?: AIStrategyPaperTradingRuleEvaluation[]
  paper_review_next_actions?: string[]
  live_readiness_checklist?: AIStrategyLiveReadinessItem[]
  live_readiness_expires_at?: string | null
  pipeline?: AIStrategyPipelineSummary
  next_actions: string[]
  started_at: string
  completed_at: string
  iterations: Record<string, unknown>[]
}

export interface AIStrategyResearchRunListResponse {
  total: number
  items: AIStrategyResearchRunRecord[]
}

export interface AIStrategyResearchRunResponse {
  run_id: string
  status: string
  achieved: boolean
  target_sharpe: number
  started_at: string
  completed_at: string
  best_iteration?: number | null
  best_quality_score: number
  best_quality_gate_evaluations: AIStrategyQualityGateEvaluation[]
  best_diagnostics?: AIStrategyResearchDiagnostics
  best_metrics: Record<string, unknown>
  research_workspace: Workspace
  iterations: AIStrategyResearchIteration[]
  best_strategy?: Strategy | null
  paper_trading?: AIStrategyPaperTradingStart | null
  paper_monitoring_plan?: AIStrategyPaperMonitoringRule[]
  pipeline?: AIStrategyPipelineSummary
  run_record?: AIStrategyResearchRunRecord | null
  next_actions: string[]
  message: string
}

export interface AIStrategyResearchTaskResponse {
  task_id: string
  status: string
  submitted_at: string
  started_at?: string | null
  completed_at?: string | null
  run_id?: string | null
  research_workspace_id?: string | null
  current_stage: string
  progress: number
  current_iteration?: number | null
  iteration_count: number
  max_iterations?: number | null
  latest_iteration?: Record<string, unknown> | null
  current_backtest_task_id?: string | null
  cancelled_backtest_task_id?: string | null
  child_cancelled?: boolean
  error?: string | null
  message: string
  result?: AIStrategyResearchRunResponse | null
}

export interface AIStrategyResearchTaskListResponse {
  total: number
  items: AIStrategyResearchTaskResponse[]
}

export interface AIStrategyPaperTradingReview {
  run_id: string
  research_workspace_id: string
  paper_workspace_id?: string | null
  paper_unit_id?: string | null
  paper_trading_started: boolean
  workspace?: Workspace | null
  unit?: StrategyUnit | null
  unit_status?: UnitStatusResponse | null
  monitoring_plan: AIStrategyPaperMonitoringRule[]
  evaluations: AIStrategyPaperTradingRuleEvaluation[]
  ready_for_live: boolean
  status: string
  reviewed_at?: string | null
  live_readiness_checklist?: AIStrategyLiveReadinessItem[]
  live_readiness_expires_at?: string | null
  pipeline?: AIStrategyPipelineSummary
  next_actions: string[]
}

export interface AIStrategyPipelineStep {
  key: string
  label: string
  status: string
  error?: string | null
  iteration_count?: number
  max_iterations?: number
  review_status?: string | null
}

export interface AIStrategyPipelineSummary {
  current_stage: string
  status: string
  progress: number
  ready_for_live: boolean
  paper_trading_error?: string | null
  live_readiness_checklist?: AIStrategyLiveReadinessItem[]
  live_readiness_expires_at?: string | null
  steps: AIStrategyPipelineStep[]
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

  async runAIResearchLoop(
    data: AIStrategyResearchRunRequest
  ): Promise<AIStrategyResearchRunResponse> {
    return api.post<AIStrategyResearchRunResponse, AIStrategyResearchRunRequest>(
      '/strategy/ai-research/run',
      data
    )
  },

  async submitAIResearchTask(
    data: AIStrategyResearchRunRequest
  ): Promise<AIStrategyResearchTaskResponse> {
    return api.post<AIStrategyResearchTaskResponse, AIStrategyResearchRunRequest>(
      '/strategy/ai-research/tasks',
      data
    )
  },

  async getAIResearchTask(taskId: string): Promise<AIStrategyResearchTaskResponse> {
    return api.get<AIStrategyResearchTaskResponse>(`/strategy/ai-research/tasks/${taskId}`)
  },

  async listAIResearchTasks(activeOnly = false, limit = 20): Promise<AIStrategyResearchTaskListResponse> {
    return api.get<AIStrategyResearchTaskListResponse>('/strategy/ai-research/tasks', {
      params: { active_only: activeOnly, limit },
    })
  },

  async cancelAIResearchTask(taskId: string): Promise<AIStrategyResearchTaskResponse> {
    return api.post<AIStrategyResearchTaskResponse, undefined>(
      `/strategy/ai-research/tasks/${taskId}/cancel`,
      undefined
    )
  },

  async listAIResearchRuns(
    researchWorkspaceId?: string | null,
    limit = 20
  ): Promise<AIStrategyResearchRunListResponse> {
    return api.get<AIStrategyResearchRunListResponse>('/strategy/ai-research/runs', {
      params: { research_workspace_id: researchWorkspaceId || undefined, limit },
    })
  },

  async startAIResearchPaperTrading(
    runId: string,
    data: AIStrategyPaperTradingStartRequest
  ): Promise<AIStrategyPaperTradingStart> {
    return api.post<AIStrategyPaperTradingStart, AIStrategyPaperTradingStartRequest>(
      `/strategy/ai-research/runs/${runId}/paper-trading`,
      data
    )
  },

  async reviewAIResearchPaperTrading(
    runId: string,
    researchWorkspaceId?: string | null
  ): Promise<AIStrategyPaperTradingReview> {
    return api.get<AIStrategyPaperTradingReview>(
      `/strategy/ai-research/runs/${runId}/paper-trading/review`,
      {
        params: { research_workspace_id: researchWorkspaceId || undefined },
      }
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
