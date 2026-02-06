/**
 * 回测分析类型定义
 */

export interface PerformanceMetrics {
  initial_capital: number
  final_assets: number
  total_return: number
  annualized_return: number
  max_drawdown: number
  max_drawdown_duration: number
  sharpe_ratio: number | null
  sortino_ratio: number | null
  calmar_ratio: number | null
  win_rate: number
  profit_factor: number
  trade_count: number
  avg_trade_return: number
  avg_holding_days: number
  avg_win: number
  avg_loss: number
  max_consecutive_wins: number
  max_consecutive_losses: number
}

export interface EquityPoint {
  date: string
  total_assets: number
  cash: number
  position_value: number
  benchmark?: number
}

export interface DrawdownPoint {
  date: string
  drawdown: number
  peak: number
  trough: number
}

export interface TradeRecord {
  id: number
  datetime: string
  symbol: string
  direction: 'buy' | 'sell'
  price: number
  size: number
  value: number
  commission: number
  pnl: number | null
  return_pct: number | null
  holding_days: number | null
  cumulative_pnl: number
}

export interface TradeSignal {
  date: string
  type: 'buy' | 'sell'
  price: number
  size: number
  reason?: string
}

export interface KlineData {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  change_pct?: number
}

export interface MonthlyReturn {
  year: number
  month: number
  return_pct: number
}

export interface OptimizationResultItem {
  params: Record<string, any>
  total_return: number
  max_drawdown: number
  sharpe_ratio: number | null
  trade_count: number
  rank: number
  is_best: boolean
}

export interface BacktestDetailResponse {
  task_id: string
  strategy_name: string
  symbol: string
  start_date: string
  end_date: string
  metrics: PerformanceMetrics
  equity_curve: EquityPoint[]
  drawdown_curve: DrawdownPoint[]
  trades: TradeRecord[]
  created_at: string
}

export interface KlineWithSignalsResponse {
  symbol: string
  klines: KlineData[]
  signals: TradeSignal[]
  indicators: Record<string, (number | null)[]>
}

export interface OptimizationResponse {
  task_id: string
  parameters: string[]
  results: OptimizationResultItem[]
  best: OptimizationResultItem | null
}

export interface MonthlyReturnsResponse {
  returns: MonthlyReturn[]
  years: number[]
  summary: Record<number, number>
}
