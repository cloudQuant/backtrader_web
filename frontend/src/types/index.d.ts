// 用户相关类型
export interface UserInfo {
  id: string
  username: string
  email: string
  is_active: boolean
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

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed'

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

export interface StrategyListResponse {
  total: number
  items: Strategy[]
}

// K线数据类型
export interface KlineData {
  dates: string[]
  ohlc: number[][] // [open, close, low, high]
  volumes: number[]
}

export interface Signal {
  date: string
  type: 'buy' | 'sell'
  price: number
}
