// 用户相关类型
export interface UserInfo {
  id: string
  username: string
  email: string
  is_active: boolean
  is_admin?: boolean
  created_at: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
}

export interface Token {
  access_token: string
  token_type: string
  expires_in: number
}

// 回测相关类型
export interface BacktestRequest {
  strategy_id: string
  symbol: string
  start_date: string
  end_date: string
  initial_cash?: number
  commission?: number
  params?: Record<string, number | string>
}

export interface BacktestResponse {
  task_id: string
  status: TaskStatus
  message?: string
}

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface BacktestStatusResponse {
  task_id: string
  status: TaskStatus
}

export interface BacktestResult {
  task_id: string
  strategy_id: string
  symbol: string
  start_date: string
  end_date: string
  status: TaskStatus
  total_return: number
  annual_return: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  total_trades: number
  profitable_trades: number
  losing_trades: number
  equity_curve: number[]
  equity_dates: string[]
  drawdown_curve: number[]
  trades: TradeRecord[]
  created_at: string
  error_message?: string
}

export interface TradeRecord {
  date: string
  type: 'buy' | 'sell'
  price: number
  size: number
  value: number
  pnl?: number
}

export interface BacktestListResponse {
  total: number
  items: BacktestResult[]
}

export interface BacktestConnectedEvent {
  type: 'connected'
  task_id: string
  client_id: string
  message: string
}

export interface BacktestTaskCreatedEvent {
  type: 'task_created'
  task_id: string
  status: 'pending'
  message: string
}

export interface BacktestProgressEvent {
  type: 'progress'
  task_id: string
  status: 'running'
  progress: number
  message: string
  data?: Record<string, unknown>
}

export interface BacktestCompletedEvent {
  type: 'completed'
  task_id: string
  status: 'completed'
  progress: number
  message: string
  result?: BacktestResult | null
}

export interface BacktestFailedEvent {
  type: 'failed'
  task_id: string
  status: 'failed'
  message: string
  error: string
}

export interface BacktestCancelledEvent {
  type: 'cancelled'
  task_id: string
  status: 'cancelled'
  message: string
}

export type BacktestRuntimeEvent =
  | BacktestConnectedEvent
  | BacktestTaskCreatedEvent
  | BacktestProgressEvent
  | BacktestCompletedEvent
  | BacktestFailedEvent
  | BacktestCancelledEvent
  | { type: 'pong' }

// 策略相关类型
export interface ParamSpec {
  type: 'int' | 'float' | 'string' | 'enum'
  default: number | string
  min?: number
  max?: number
  options?: (number | string)[]
  description?: string
}

export interface Strategy {
  id: string
  user_id: string
  name: string
  description?: string
  code: string
  params: Record<string, ParamSpec>
  category: string
  created_at: string
  updated_at: string
}

export interface StrategyCreate {
  name: string
  description?: string
  code: string
  params?: Record<string, ParamSpec>
  category?: string
}

export interface StrategyTemplate {
  id: string
  name: string
  description: string
  code: string
  params: Record<string, ParamSpec>
  category: string
}

export type StrategyType = 'backtest' | 'simulate' | 'live'

export interface StrategyListResponse {
  total: number
  items: Strategy[]
}

// 策略配置（从 config.yaml 读取）
export interface StrategyConfig {
  strategy_id: string
  strategy: {
    name?: string
    description?: string
    author?: string
  }
  params: Record<string, number | string>
  data: {
    symbol?: string
    data_type?: string
  }
  backtest: {
    initial_cash?: number
    commission?: number
  }
}

// K线数据类型
export interface KlineData {
  dates: string[]
  ohlc: number[][] // [open, close, low, high]
  volumes: number[]
}

/** Single kline record from /data/kline API (flat for table display). */
export interface KlineRecord {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  change?: number
}

/** Response from /data/kline API. */
export interface KlineResponse {
  symbol: string
  count: number
  kline: KlineData
  records: KlineRecord[]
}

export interface Signal {
  date: string
  type: 'buy' | 'sell'
  price: number
}

export interface PaginationQuery {
  page?: number
  page_size?: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface ScriptStatsResponse {
  total_scripts: number
  active_scripts: number
  custom_scripts: number
  categories: string[]
}

export type ScriptFrequency =
  | 'hourly'
  | 'daily'
  | 'weekly'
  | 'monthly'
  | 'once'
  | 'manual'

export interface DataScript {
  id: number
  script_id: string
  script_name: string
  category: string
  sub_category: string | null
  frequency: ScriptFrequency | null
  description: string | null
  source: string
  target_table: string | null
  module_path: string | null
  function_name: string | null
  dependencies: Record<string, unknown> | null
  estimated_duration: number
  timeout: number
  is_active: boolean
  is_custom: boolean
  created_by: string | null
  updated_by: string | null
  created_at: string
  updated_at: string
}

export interface DataScriptFormPayload {
  script_id: string
  script_name: string
  category: string
  sub_category?: string | null
  frequency?: ScriptFrequency | null
  description?: string | null
  source?: string
  target_table?: string | null
  module_path?: string | null
  function_name?: string | null
  dependencies?: Record<string, unknown> | null
  estimated_duration?: number
  timeout?: number
  is_active?: boolean
}

export interface ScriptRunRequest {
  parameters: Record<string, unknown>
}

export interface ExecutionTriggerResponse {
  execution_id: string
  status: string
  task_id?: number | null
}

export type ScheduleTypeValue = 'once' | 'daily' | 'weekly' | 'monthly' | 'cron' | 'interval'

export interface ScheduledTask {
  id: number
  name: string
  description: string | null
  user_id: string
  script_id: string
  schedule_type: ScheduleTypeValue
  schedule_expression: string
  parameters: Record<string, unknown>
  is_active: boolean
  retry_on_failure: boolean
  max_retries: number
  timeout: number
  last_execution_at: string | null
  next_execution_at: string | null
  created_at: string
  updated_at: string
}

export interface ScheduledTaskFormPayload {
  name: string
  description?: string | null
  script_id: string
  schedule_type: ScheduleTypeValue
  schedule_expression: string
  parameters?: Record<string, unknown>
  is_active?: boolean
  retry_on_failure?: boolean
  max_retries?: number
  timeout?: number
}

export interface ScheduleTemplateResponse {
  value: string
  label: string
  description: string
  cron_expression: string
}

export type AkshareTaskStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'timeout'
  | 'cancelled'

export type TriggeredByType = 'scheduler' | 'manual' | 'api'

export interface TaskExecution {
  id: number
  execution_id: string
  task_id: number | null
  script_id: string
  params: Record<string, unknown> | null
  status: AkshareTaskStatus
  start_time: string | null
  end_time: string | null
  duration: number | null
  result: Record<string, unknown> | null
  error_message: string | null
  error_trace: string | null
  rows_before: number | null
  rows_after: number | null
  retry_count: number
  triggered_by: TriggeredByType
  operator_id: string | null
  created_at: string
  updated_at: string
}

export interface ExecutionStatsResponse {
  total_count: number
  success_count: number
  failed_count: number
  running_count: number
  success_rate: number
  avg_duration: number
}

export interface DataTable {
  id: number
  table_name: string
  table_comment: string | null
  category: string | null
  script_id: string | null
  row_count: number
  last_update_time: string | null
  last_update_status: string | null
  data_start_date: string | null
  data_end_date: string | null
  symbol_raw: string | null
  symbol_normalized: string | null
  market: string | null
  asset_type: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface DataTableSchemaColumn {
  name: string
  type: string
  nullable: boolean
  default: unknown
}

export interface DataTableSchemaResponse {
  table_name: string
  columns: DataTableSchemaColumn[]
  row_count: number
  last_update_time: string | null
}

export interface DataTableRowsResponse {
  table_name: string
  columns: string[]
  rows: Record<string, unknown>[]
  page: number
  page_size: number
  total: number
}

export interface InterfaceCategory {
  id: number
  name: string
  description: string | null
  icon: string | null
  sort_order: number
}

export interface InterfaceParameter {
  id: number
  name: string
  display_name: string
  param_type: string
  description: string | null
  default_value: string | null
  required: boolean
  options: string[] | null
  sort_order: number
}

export interface DataInterface {
  id: number
  name: string
  display_name: string
  description: string | null
  category_id: number
  module_path: string | null
  function_name: string | null
  parameters: Record<string, unknown>
  extra_config: Record<string, unknown>
  return_type: string
  example: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  params: InterfaceParameter[]
}

export interface DataInterfaceFormPayload {
  name: string
  display_name: string
  description?: string | null
  category_id: number
  module_path?: string | null
  function_name?: string | null
  parameters?: Record<string, unknown>
  extra_config?: Record<string, unknown>
  return_type?: string
  example?: string | null
  is_active?: boolean
}
