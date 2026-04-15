/**
 * Workspace and StrategyUnit TypeScript types.
 * Iteration 124 - Strategy Research feature.
 */

export type UnitRunStatus = 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
export type WorkspaceStatus = 'idle' | 'running' | 'completed' | 'error'
export type ViewMode = 'card' | 'table'
export type WorkspaceDataSourceType = 'csv' | 'mysql' | 'postgresql' | 'mongodb'
export type WorkspaceType = 'research' | 'trading'
export type TradingMode = 'paper' | 'live'

export interface WorkspaceDataSourceConfig {
  type: WorkspaceDataSourceType
  csv: {
    directory_path: string
    delimiter: string
    encoding: string
    has_header: boolean
  }
  mysql: {
    host: string
    port: number
    database: string
    username: string
    password: string
    table: string
  }
  postgresql: {
    host: string
    port: number
    database: string
    schema: string
    username: string
    password: string
    table: string
  }
  mongodb: {
    uri: string
    database: string
    collection: string
    username: string
    password: string
    auth_source: string
  }
}

export interface WorkspaceSettings extends Record<string, unknown> {
  data_source?: WorkspaceDataSourceConfig
}

export interface GatewayConfig {
  preset_id?: string | null
  name?: string | null
  params?: Record<string, unknown>
}

export interface TradingPosition {
  data_name: string
  direction: string
  size: number
  price: number | null
  current_price: number | null
  market_value: number | null
  pnl: number | null
}

export interface TradingSnapshot {
  instance_id: string | null
  instance_status: string
  mode: TradingMode
  error: string | null
  started_at: string | null
  stopped_at: string | null
  gateway_summary: string | null
  long_position: number
  short_position: number
  today_pnl: number | null
  position_pnl: number | null
  latest_price: number | null
  change_pct: number | null
  long_market_value: number | null
  short_market_value: number | null
  leverage: number | null
  cumulative_pnl: number | null
  max_drawdown_rate: number | null
  trading_day: string | null
  updated_at: string | null
  detail_route: string | null
  positions: TradingPosition[]
}

export interface TradingAutoSession {
  name: string
  open: string
  close: string
}

export interface TradingAutoConfig {
  enabled: boolean
  buffer_minutes: number
  sessions: TradingAutoSession[]
  scope: string
}

export interface TradingAutoScheduleItem {
  session: string
  start: string
  stop: string
  market_open?: string | null
  market_close?: string | null
}

export interface TradingPositionManagerItem {
  unit_id: string
  unit_name: string
  symbol: string
  symbol_name: string | null
  trading_mode: TradingMode
  long_position: number
  short_position: number
  avg_price: number | null
  latest_price: number | null
  position_pnl: number
  market_value: number
}

export interface TradingPositionManagerResponse {
  positions: TradingPositionManagerItem[]
  total_long_value: number
  total_short_value: number
  total_pnl: number
}

export interface TradingDailySummaryItem {
  trading_date: string
  daily_pnl: number
  trade_count: number
  cumulative_pnl: number
  max_drawdown: number
}

export interface TradingDailySummaryResponse {
  summaries: TradingDailySummaryItem[]
}

export interface StrategyUnitRuntimeFile {
  name: string
  relative_path: string
  size: number
  kind: string
}

export interface StrategyUnitRuntimeInfo {
  unit_id: string
  runtime_dir: string
  log_dir: string | null
  files: StrategyUnitRuntimeFile[]
}

// ---------------------------------------------------------------------------
// Workspace
// ---------------------------------------------------------------------------

export interface Workspace {
  id: string
  user_id: string
  name: string
  description: string | null
  workspace_type: WorkspaceType
  settings: WorkspaceSettings
  trading_config: Record<string, unknown>
  unit_count: number
  completed_count: number
  status: WorkspaceStatus
  created_at: string
  updated_at: string
}

export interface WorkspaceCreate {
  name: string
  description?: string
  workspace_type?: WorkspaceType
  settings?: WorkspaceSettings
  trading_config?: Record<string, unknown>
}

export interface WorkspaceUpdate {
  name?: string
  description?: string
  workspace_type?: WorkspaceType
  settings?: WorkspaceSettings
  trading_config?: Record<string, unknown>
}

export interface WorkspaceListResponse {
  total: number
  items: Workspace[]
}

// ---------------------------------------------------------------------------
// Strategy Unit
// ---------------------------------------------------------------------------

export interface StrategyUnit {
  id: string
  workspace_id: string
  group_name: string
  strategy_id: string | null
  strategy_name: string
  symbol: string
  symbol_name: string
  timeframe: string
  timeframe_n: number
  category: string
  sort_order: number
  data_config: Record<string, unknown>
  unit_settings: Record<string, unknown>
  params: Record<string, unknown>
  optimization_config: Record<string, unknown>
  trading_mode: TradingMode
  gateway_config: GatewayConfig
  lock_trading: boolean
  lock_running: boolean
  trading_instance_id: string | null
  trading_snapshot: TradingSnapshot
  run_status: UnitRunStatus
  run_count: number
  last_run_time: number | null
  last_task_id: string | null
  last_optimization_task_id: string | null
  bar_count: number | null
  metrics_snapshot: Record<string, unknown>
  // Optimization progress (populated by polling)
  opt_status?: string | null
  opt_total?: number | null
  opt_completed?: number | null
  opt_progress?: number | null
  opt_elapsed_time?: number | null
  opt_remaining_time?: number | null
  opt_started_at_ms?: number | null
  opt_last_sync_at_ms?: number | null
  created_at: string
  updated_at: string
}

export interface StrategyUnitCreate {
  group_name?: string
  strategy_id?: string
  strategy_name?: string
  symbol?: string
  symbol_name?: string
  timeframe?: string
  timeframe_n?: number
  category?: string
  data_config?: Record<string, unknown>
  unit_settings?: Record<string, unknown>
  params?: Record<string, unknown>
  optimization_config?: Record<string, unknown>
  trading_mode?: TradingMode
  gateway_config?: GatewayConfig
  lock_trading?: boolean
  lock_running?: boolean
  trading_snapshot?: Partial<TradingSnapshot>
}

export interface StrategyUnitUpdate {
  group_name?: string
  strategy_id?: string
  strategy_name?: string
  symbol?: string
  symbol_name?: string
  timeframe?: string
  timeframe_n?: number
  category?: string
  data_config?: Record<string, unknown>
  unit_settings?: Record<string, unknown>
  params?: Record<string, unknown>
  optimization_config?: Record<string, unknown>
  trading_mode?: TradingMode
  gateway_config?: GatewayConfig
  lock_trading?: boolean
  lock_running?: boolean
  trading_instance_id?: string | null
  trading_snapshot?: Partial<TradingSnapshot>
}

export interface StrategyUnitListResponse {
  total: number
  items: StrategyUnit[]
}

// ---------------------------------------------------------------------------
// Bulk operations
// ---------------------------------------------------------------------------

export interface BulkDeleteRequest {
  ids: string[]
}

export interface SortRequest {
  unit_ids: string[]
}

export interface GroupRenameRequest {
  unit_ids: string[]
  mode: 'custom' | 'strategy' | 'symbol' | 'symbol_name' | 'category' | 'replace'
  value?: string
  search?: string
  replace?: string
}

export interface UnitRenameRequest {
  unit_id: string
  mode: 'custom' | 'strategy' | 'symbol' | 'symbol_name' | 'category' | 'replace'
  value?: string
  search?: string
  replace?: string
}

// ---------------------------------------------------------------------------
// Run orchestration
// ---------------------------------------------------------------------------

export interface RunUnitsRequest {
  unit_ids: string[]
  parallel?: boolean
}

export interface StopUnitsRequest {
  unit_ids: string[]
}

export interface UnitStatusResponse {
  id: string
  run_status: UnitRunStatus
  last_task_id: string | null
  metrics_snapshot: Record<string, unknown>
  run_count: number
  last_run_time: number | null
  bar_count: number | null
  trading_instance_id: string | null
  trading_snapshot: TradingSnapshot
  trading_mode: TradingMode
  lock_trading: boolean
  lock_running: boolean
  opt_status: string | null
  opt_total: number | null
  opt_completed: number | null
  opt_progress: number | null
  opt_elapsed_time: number | null
  opt_remaining_time: number | null
}

export interface RunUnitResult {
  unit_id: string
  task_id: string | null
  status: string
  error?: string
}

// ---------------------------------------------------------------------------
// Optimization (Phase 4)
// ---------------------------------------------------------------------------

export interface ParamRangeSpec {
  start: number
  end: number
  step: number
  type?: string
}

export interface UnitOptimizationRequest {
  unit_id: string
  param_ranges: Record<string, ParamRangeSpec>
  n_workers?: number
  mode?: string
  timeout?: number
}

export interface ApplyBestParamsRequest {
  unit_id: string
  optimization_task_id: string
  result_index?: number
}

export interface OptimizationSubmitResult {
  task_id: string
  unit_id: string
  total_combinations: number
  n_workers: number
}

export interface OptimizationArtifactResponse {
  artifact_path: string | null
  artifact_manifest_path: string | null
  artifact_summary_path: string | null
  artifact_status: string | null
  artifact_error: string | null
  optimization_task_id: string
  optimization_result_index: number
  trial_index: number | null
}
