/**
 * 组合管理 API
 */
import request from './index'

export interface StrategySummary {
  id: string
  strategy_id: string
  strategy_name: string
  status: string
  position_source?: string | null
  asset_spec_source?: string | null
  valuation_status?: string | null
  valuation_warnings?: string[]
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
  net_position_value?: number
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
  latest_price?: number | null
  market_value: number
  signed_market_value?: number
  long_market_value?: number
  short_market_value?: number
  position_pnl?: number
  gross_pnl?: number
  commission?: number
  commission_source?: string | null
  multiplier?: number
  margin_rate?: number
  leverage?: number
  margin_value?: number
  direction: string
  long_position?: number
  short_position?: number
  trading_mode?: string
  updated_at?: string | null
  data_time?: string | null
  position_source?: string | null
  asset_spec_source?: string | null
  valuation_status?: string | null
  valuation_warnings?: string[]
}

export interface PositionSummary {
  total_long_value: number
  total_short_value: number
  gross_market_value: number
  net_market_value: number
  total_pnl: number
  long_count: number
  short_count: number
  flat_count: number
}

export interface TradeItem {
  strategy_id: string
  strategy_name: string
  instance_id: string
  workspace_id?: string
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
  pnl_values?: number[]
  value_source?: string
}

export interface PortfolioEquity {
  dates: string[]
  total_equity: number[]
  cumulative_pnl: number[]
  total_drawdown: number[]
  strategies: EquityStrategy[]
}

export interface AllocationItem {
  asset: string
  value: number
  weight: number
  long_value: number
  short_value: number
  net_value: number
  position_count: number
}

export const portfolioApi = {
  getOverview(summaryOnly = false): Promise<PortfolioOverview> {
    if (!summaryOnly) return request.get('/portfolio/overview')
    return request.get('/portfolio/overview/summary')
  },

  getPositions(): Promise<{ total: number; positions: PositionItem[]; summary?: PositionSummary; warnings?: string[] }> {
    return request.get('/portfolio/positions')
  },

  getTrades(limit = 200, workspaceIds: string[] = [], includeInactive = false): Promise<{ total: number; trades: TradeItem[] }> {
    const ids = workspaceIds.filter(Boolean)
    const params: { limit: number; workspace_ids?: string; include_inactive?: boolean } = { limit }
    if (ids.length > 0) params.workspace_ids = ids.join(',')
    if (includeInactive) params.include_inactive = true
    return request.get('/portfolio/trades', { params })
  },

  getEquity(workspaceIds: string[] = [], includeInactive = false): Promise<PortfolioEquity> {
    const ids = workspaceIds.filter(Boolean)
    const params: { workspace_ids?: string; include_inactive?: boolean } = {}
    if (ids.length > 0) params.workspace_ids = ids.join(',')
    if (includeInactive) params.include_inactive = true
    return request.get('/portfolio/equity', { params })
  },

  getAllocation(workspaceIds: string[] = []): Promise<{ total: number; items: AllocationItem[] }> {
    const ids = workspaceIds.filter(Boolean)
    const params: { workspace_ids?: string } = {}
    if (ids.length > 0) params.workspace_ids = ids.join(',')
    return request.get('/portfolio/allocation', { params })
  },
}
