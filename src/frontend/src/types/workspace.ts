/**
 * Workspace and StrategyUnit TypeScript types.
 * Iteration 124 - Strategy Research feature.
 */

export type UnitRunStatus = 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
export type WorkspaceStatus = 'idle' | 'running' | 'completed' | 'error'
export type ViewMode = 'card' | 'table'
export type WorkspaceDataSourceType = 'csv' | 'mysql' | 'postgresql' | 'mongodb'

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

// ---------------------------------------------------------------------------
// Workspace
// ---------------------------------------------------------------------------

export interface Workspace {
  id: string
  user_id: string
  name: string
  description: string | null
  settings: WorkspaceSettings
  unit_count: number
  completed_count: number
  status: WorkspaceStatus
  created_at: string
  updated_at: string
}

export interface WorkspaceCreate {
  name: string
  description?: string
  settings?: WorkspaceSettings
}

export interface WorkspaceUpdate {
  name?: string
  description?: string
  settings?: WorkspaceSettings
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
  run_status: UnitRunStatus
  run_count: number
  last_run_time: number | null
  last_task_id: string | null
  last_optimization_task_id: string | null
  bar_count: number | null
  metrics_snapshot: Record<string, unknown>
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
