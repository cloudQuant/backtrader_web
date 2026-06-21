/**
 * 组合管理 API
 */
import request from './index'

export interface StrategySummary {
  id: string
  strategy_id: string
  strategy_name: string
  status: string
  total_assets: number
  initial_capital: number
  pnl: number
  pnl_pct: number
  total_trades: number
  win_rate: number
}

export interface PortfolioOverview {
  total_assets: number
  total_cash: number
  total_position_value: number
  total_initial_capital: number
  total_pnl: number
  total_pnl_pct: number
  strategy_count: number
  running_count: number
  strategies: StrategySummary[]
}

export interface PositionItem {
  strategy_id: string
  strategy_name: string
  instance_id: string
  data_name: string
  size: number
  price: number
  market_value: number
  direction: string
}

export interface TradeItem {
  strategy_id: string
  strategy_name: string
  instance_id: string
  ref: number
  datetime: string
  dtopen: string
  dtclose: string
  data_name: string
  direction: string
  size: number
  price: number
  value: number
  commission: number
  pnl: number
  pnlcomm: number
  barlen: number
}

export interface EquityStrategy {
  strategy_id: string
  strategy_name: string
  instance_id: string
  values: number[]
}

export interface PortfolioEquity {
  dates: string[]
  total_equity: number[]
  total_drawdown: number[]
  strategies: EquityStrategy[]
}

export interface AllocationItem {
  strategy_id: string
  strategy_name: string
  instance_id: string
  value: number
  weight: number
}

export const portfolioApi = {
  getOverview(): Promise<PortfolioOverview> {
    return request.get('/portfolio/overview')
  },

  getPositions(): Promise<{ total: number; positions: PositionItem[] }> {
    return request.get('/portfolio/positions')
  },

  getTrades(limit = 200): Promise<{ total: number; trades: TradeItem[] }> {
    return request.get('/portfolio/trades', { params: { limit } })
  },

  getEquity(): Promise<PortfolioEquity> {
    return request.get('/portfolio/equity')
  },

  getAllocation(): Promise<{ total: number; items: AllocationItem[] }> {
    return request.get('/portfolio/allocation')
  },
}
