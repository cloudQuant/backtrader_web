/** Strategy API contracts shared by views, composables, and API clients. */

import type {
  ParamSpec,
  Strategy,
} from '@/types'
import type {
  StrategyUnit,
  UnitStatusResponse,
  Workspace,
  WorkspaceReportCreateRequest,
  WorkspaceReportResponse,
} from '@/types/workspace'
import type {
  QualityGateEvaluation,
  RobustnessTestResultResponse,
} from '@/types/trust'

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
  prompt?: string
  workflow_mode?: 'auto' | 'prompt'
  workflow_steps?: Array<
    | 'ideation'
    | 'generation'
    | 'backtest'
    | 'review'
    | 'optimization'
    | 'validation'
    | 'robustness'
    | 'paper_trading'
  >
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
  require_out_of_sample_validation?: boolean
  out_of_sample_ratio?: number
  min_out_of_sample_sharpe?: number | null
  min_out_of_sample_trades?: number | null
  robustness_validation?: boolean
  require_robustness_validation?: boolean
  robustness_methods?: string[]
  min_robustness_score?: number
  robustness_monte_carlo_iterations?: number
  robustness_random_seed?: number | null
  backtest_timeout_seconds?: number
  poll_interval_seconds?: number
  initial_cash?: number
  commission?: number
  annual_days?: number
  calc_method?: string
  weight_mode?: string
  research_workspace_id?: string | null
  mandate_id?: string | null
  trading_workspace_id?: string | null
  seed_strategy_id?: string | null
  continue_from_run_id?: string | null
  start_paper_trading?: boolean
  min_paper_trading_days?: number
  paper_workspace_name?: string | null
  group_name?: string | null
  knowledge_base_id?: string | null
  thinking_mode?: boolean
  data_config?: Record<string, unknown>
  unit_settings?: Record<string, unknown>
  optimization_config?: Record<string, unknown>
  gateway_config?: Record<string, unknown>
  continuation_context?: Record<string, unknown>
}

export interface InvestmentMandateCreateRequest {
  raw_prompt: string
  symbol?: string | null
  symbol_name?: string | null
  timeframe?: string | null
  objective?: string | null
  risk_constraints?: Record<string, unknown>
  trading_constraints?: Record<string, unknown>
  quality_gates?: Record<string, unknown>
}

export interface InvestmentMandateResponse {
  id: string
  raw_prompt: string
  structured_goal: Record<string, unknown>
  asset_scope: Record<string, unknown>
  timeframe?: string | null
  objective?: string | null
  risk_constraints: Record<string, unknown>
  trading_constraints: Record<string, unknown>
  quality_gates: Record<string, unknown>
  status: string
  source: string
  created_at: string
  updated_at: string
}

export interface AIStrategyResearchConfigProfile {
  id: string
  name: string
  description: string
  config: Record<string, unknown>
  created_at?: string | null
  updated_at?: string | null
}

export interface AIStrategyResearchConfigProfileListResponse {
  file_path: string
  total: number
  items: AIStrategyResearchConfigProfile[]
}

export interface AIStrategyResearchConfigProfileCreateRequest {
  id?: string | null
  name: string
  description?: string
  config: Record<string, unknown>
}

export interface AIStrategyResearchConfigProfileUpdateRequest {
  name?: string
  description?: string
  config?: Record<string, unknown>
}

export interface AIStrategyResearchConfigProfileImportRequest {
  raw_yaml: string
  name?: string | null
  profile_id?: string | null
}

export interface AIStrategyResearchConfigProfileImportResponse {
  file_path: string
  total: number
  items: AIStrategyResearchConfigProfile[]
}

export interface AIStrategyQualityGateEvaluation {
  key: string
  label: string
  actual?: number | null
  target: number
  direction: 'min' | 'max'
  passed: boolean
  score: number
  margin?: number | null
  gap?: number | null
  gap_ratio?: number | null
  distance_to_pass?: number | null
  status?: string
}

export interface AIStrategyGateGap {
  key?: string
  label?: string
  actual?: number | null
  target?: number | null
  direction?: 'min' | 'max' | string
  gap?: number | null
  gap_ratio?: number | null
  distance_to_pass?: number | null
  score?: number | null
  status?: string
}

export interface AIStrategyResearchDiagnostics {
  summary?: string
  metric_snapshot?: Record<string, number | null>
  iteration_progress?: AIStrategyIterationProgress
  failure_categories?: string[]
  strengths?: string[]
  weaknesses?: string[]
  gate_gaps?: AIStrategyGateGap[]
  improvement_plan?: string[]
  promotion_ready?: boolean
  out_of_sample_validation?: AIStrategyOutOfSampleValidation
  robustness_validation?: Record<string, unknown>
}

export interface AIStrategyIterationProgress {
  status?: 'baseline' | 'improved' | 'regressed' | 'stalled' | string
  previous_iteration?: number | null
  quality_score_delta?: number | null
  sharpe_delta?: number | null
  total_trades_delta?: number | null
  max_drawdown_delta?: number | null
  summary?: string
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
  margin?: number | null
  gap?: number | null
  gap_ratio?: number | null
  distance_to_pass?: number | null
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
  robustness_status?: string | null
  robustness_result?: RobustnessTestResultResponse | Record<string, unknown>
  robustness_gate_evaluations?: Array<QualityGateEvaluation | AIStrategyQualityGateEvaluation>
  robustness_failures?: string[]
  robustness_failure_reason?: string | null
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
  run_record?: AIStrategyResearchRunRecord | null
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

export interface AIStrategyPromotionAuditItem {
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
  workflow_mode?: 'auto' | 'prompt'
  workflow_steps?: NonNullable<AIStrategyResearchRunRequest['workflow_steps']>
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
  group_name?: string | null
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
  robustness_validation?: Record<string, unknown>
  best_diagnostics?: AIStrategyResearchDiagnostics
  best_metrics: Record<string, unknown>
  best_strategy_id?: string | null
  best_strategy_name?: string | null
  research_workspace_id: string
  mandate_id?: string | null
  seed_strategy_id?: string | null
  continued_from_run_id?: string | null
  continuation_source?: string | null
  continuation_context?: Record<string, unknown>
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
  live_handoff?: AIStrategyLiveHandoffPackage | null
  live_handoff_approval?: AIStrategyLiveHandoffApprovalRecord | null
  live_workspace_id?: string | null
  live_workspace_name?: string | null
  live_unit_id?: string | null
  live_trading_prepared?: boolean
  live_trading_prepared_at?: string | null
  pipeline?: AIStrategyPipelineSummary
  promotion_audit?: AIStrategyPromotionAuditItem[]
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
  robustness_validation?: Record<string, unknown>
  best_diagnostics?: AIStrategyResearchDiagnostics
  best_metrics: Record<string, unknown>
  research_workspace: Workspace
  mandate_id?: string | null
  iterations: AIStrategyResearchIteration[]
  best_strategy?: Strategy | null
  paper_trading?: AIStrategyPaperTradingStart | null
  paper_monitoring_plan?: AIStrategyPaperMonitoringRule[]
  pipeline?: AIStrategyPipelineSummary
  promotion_audit?: AIStrategyPromotionAuditItem[]
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
  mandate_id?: string | null
  request_snapshot?: AIStrategyResearchRunRequest & Record<string, unknown>
  request_explicit_fields?: string[]
  continued_from_run_id?: string | null
  continuation_source?: string | null
  continuation_context?: Record<string, unknown>
  current_stage: string
  progress: number
  current_iteration?: number | null
  iteration_count: number
  max_iterations?: number | null
  latest_iteration?: Record<string, unknown> | null
  best_iteration_payload?: Record<string, unknown> | null
  run_status?: string | null
  achieved?: boolean | null
  target_sharpe?: number | null
  best_iteration?: number | null
  best_sharpe?: number | null
  best_quality_score?: number | null
  best_quality_gate_evaluations?: AIStrategyQualityGateEvaluation[]
  robustness_validation?: Record<string, unknown>
  best_diagnostics?: AIStrategyResearchDiagnostics
  best_metrics?: Record<string, unknown>
  best_strategy_id?: string | null
  best_strategy_name?: string | null
  asset_specs?: Record<string, Record<string, unknown>>
  backtest_environment?: Record<string, unknown>
  paper_workspace_id?: string | null
  paper_workspace_name?: string | null
  paper_unit_id?: string | null
  paper_trading_started?: boolean
  paper_monitoring_plan?: AIStrategyPaperMonitoringRule[]
  paper_handoff?: Record<string, unknown>
  paper_review_status?: string | null
  paper_review_ready_for_live?: boolean
  paper_reviewed_at?: string | null
  paper_review_evaluations?: AIStrategyPaperTradingRuleEvaluation[]
  paper_review_next_actions?: string[]
  live_readiness_checklist?: AIStrategyLiveReadinessItem[]
  live_readiness_expires_at?: string | null
  live_handoff?: AIStrategyLiveHandoffPackage | null
  live_handoff_approval?: AIStrategyLiveHandoffApprovalRecord | null
  live_workspace_id?: string | null
  live_workspace_name?: string | null
  live_unit_id?: string | null
  live_trading_prepared?: boolean
  live_trading_prepared_at?: string | null
  pipeline?: AIStrategyPipelineSummary
  promotion_audit?: AIStrategyPromotionAuditItem[]
  next_actions?: string[]
  current_backtest_task_id?: string | null
  cancelled_backtest_task_id?: string | null
  child_cancelled?: boolean
  error?: string | null
  message: string
  result?: AIStrategyResearchRunResponse | null
}

export interface ResearchPipelineEvent {
  id: string
  run_id: string
  workspace_id?: string | null
  mandate_id?: string | null
  stage: string
  status: string
  iteration?: number | null
  summary?: string | null
  input_payload: Record<string, unknown>
  output_payload: Record<string, unknown>
  metrics: Record<string, unknown>
  error?: string | null
  created_at: string
}

export interface ResearchTimelineResponse {
  run_id: string
  total: number
  items: ResearchPipelineEvent[]
}

export interface AIStrategyResearchVersion {
  id: string
  run_id: string
  workspace_id?: string | null
  mandate_id?: string | null
  strategy_id?: string | null
  unit_id?: string | null
  backtest_task_id?: string | null
  version_no: number
  version_name: string
  parent_version_id?: string | null
  strategy_name?: string | null
  code: string
  params: Record<string, unknown>
  ai_rationale?: string | null
  change_summary?: string | null
  backtest_metrics: Record<string, unknown>
  quality_gate_evaluations: AIStrategyQualityGateEvaluation[]
  quality_gate_status: string
  review: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface AIStrategyResearchVersionListResponse {
  run_id: string
  total: number
  items: AIStrategyResearchVersion[]
}

export interface AIStrategyResearchVersionCompareResponse {
  run_id: string
  left: AIStrategyResearchVersion
  right: AIStrategyResearchVersion
  metric_deltas: Record<string, unknown>
  gate_deltas: Record<string, unknown>
  code_diff: string
  verdict: string
  summary: string
}

export interface AIStrategyResearchTaskListResponse {
  total: number
  items: AIStrategyResearchTaskResponse[]
}

export interface AIStrategyResearchTaskContinueRequest {
  overrides?: Partial<AIStrategyResearchRunRequest> & Record<string, unknown>
}

export interface AIStrategyResearchRunContinueRequest {
  overrides?: Partial<AIStrategyResearchRunRequest> & Record<string, unknown>
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
  live_handoff?: AIStrategyLiveHandoffPackage | null
}

export interface AIStrategyPaperReviewLock {
  run_id?: string | null
  research_workspace_id?: string | null
  paper_workspace_id?: string | null
  paper_unit_id?: string | null
  status?: string | null
  reviewed_at?: string | null
  failed_rules?: AIStrategyPaperTradingRuleEvaluation[]
  stop_results?: Record<string, unknown>[]
  next_actions?: string[]
  reason?: string | null
}

export interface AIStrategyLiveHandoffApprovalRequest {
  decision: 'approved' | 'rejected'
  approver?: string | null
  comment?: string | null
  account_confirmed?: boolean
  risk_limit_confirmed?: boolean
  deployment_window?: string | null
}

export interface AIStrategyLiveHandoffApprovalRecord {
  run_id: string
  research_workspace_id: string
  decision: string
  approved: boolean
  decided_at: string
  decided_by: string
  comment?: string | null
  account_confirmed: boolean
  risk_limit_confirmed: boolean
  deployment_window?: string | null
  handoff_status_at_decision: string
  blockers: string[]
}

export interface AIStrategyLiveHandoffPackage {
  run_id: string
  research_workspace_id: string
  generated_at: string
  ready_for_live: boolean
  status: string
  approval_required: boolean
  expires_at?: string | null
  paper_workspace_id?: string | null
  paper_unit_id?: string | null
  best_strategy_id?: string | null
  best_strategy_name?: string | null
  symbol: string
  symbol_name?: string
  timeframe: string
  timeframe_n: number
  target_sharpe: number
  best_sharpe: number
  best_metrics: Record<string, unknown>
  asset_specs: Record<string, unknown>
  backtest_environment: Record<string, unknown>
  robustness_validation?: Record<string, unknown>
  paper_review_status?: string | null
  paper_reviewed_at?: string | null
  paper_review_evaluations: AIStrategyPaperTradingRuleEvaluation[]
  paper_monitoring_plan: AIStrategyPaperMonitoringRule[]
  live_readiness_checklist: AIStrategyLiveReadinessItem[]
  approvals_required: AIStrategyLiveReadinessItem[]
  deployment_blockers: string[]
  approval_status?: string | null
  approval?: AIStrategyLiveHandoffApprovalRecord | null
  handoff: Record<string, unknown>
  pipeline: AIStrategyPipelineSummary
  next_actions: string[]
}

export interface AIStrategyLiveTradingPrepareRequest {
  research_workspace_id?: string | null
  trading_workspace_id?: string | null
  live_workspace_name?: string | null
  gateway_config?: Record<string, unknown>
}

export interface AIStrategyLiveTradingPrepare {
  workspace: Workspace
  unit: StrategyUnit
  prepared: boolean
  handoff?: Record<string, unknown> | null
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
  validation_status?: string | null
  robustness_status?: string | null
  live_trading_prepared?: boolean
  live_workspace_id?: string | null
  live_unit_id?: string | null
  live_unit_locked?: boolean
  prepared_at?: string | null
}

export interface AIStrategyPipelineSummary {
  current_stage: string
  status: string
  progress: number
  ready_for_live: boolean
  paper_trading_error?: string | null
  live_readiness_checklist?: AIStrategyLiveReadinessItem[]
  live_readiness_expires_at?: string | null
  live_handoff_status?: string | null
  live_handoff_generated_at?: string | null
  live_handoff_ready_for_live?: boolean
  live_handoff_approval_required?: boolean
  live_handoff_blocker_count?: number
  live_handoff_approval_status?: string | null
  live_handoff_approved?: boolean | null
  live_handoff_approved_at?: string | null
  live_handoff_rejected_at?: string | null
  paper_review_lock?: AIStrategyPaperReviewLock | null
  paper_unit_locked?: boolean
  paper_unit_stopped?: boolean
  live_trading_prepared?: boolean
  live_trading_prepared_at?: string | null
  live_workspace_id?: string | null
  live_unit_id?: string | null
  live_unit_locked?: boolean
  workflow_mode?: AIStrategyResearchRunRequest['workflow_mode']
  workflow_steps?: AIStrategyResearchRunRequest['workflow_steps']
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

export type StrategyOverfittingMethod =
  | 'walk_forward'
  | 'out_of_sample'
  | 'monte_carlo'
  | 'parameter_sensitivity'
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
