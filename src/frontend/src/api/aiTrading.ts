/**
 * AI Trading API client.
 *
 * Provides methods for natural language trading execution,
 * trade confirmation, configuration, and history.
 */

import request from './index'

const API_BASE = '/ai-trading'

export interface TradingIntent {
  action: string
  symbol: string | null
  exchange: string | null
  quantity: number | null
  price: number | null
  order_type: string
  stop_loss: number | null
  take_profit: number | null
  reason: string
  confidence: number
  risk_level: string
  raw_input: string
}

export interface RiskAssessment {
  approved: boolean
  risk_level: string
  warnings: string[]
  blocked_reasons: string[]
  requires_confirmation: boolean
  max_loss_estimate: number | null
  position_impact: string | null
}

export interface AITradingGatewayOption {
  gateway_id: string
  exchange_type: string
  account_id: string
  connected: boolean
}

export interface AITradingAccountOption {
  account_id: string
  name: string
  total_equity?: number | null
  current_cash?: number | null
  is_active: boolean
  source?: 'paper' | 'gateway' | string
  gateway_id?: string | null
  exchange_type?: string | null
  connected?: boolean
}

export interface AITradingResponse {
  trade_id: string
  intent: TradingIntent
  risk_assessment: RiskAssessment
  status: string
  message: string
  execution_result: Record<string, unknown> | null
  ai_reasoning: string
  suggestions: string[]
  requires_confirmation: boolean
  degraded: boolean
  diagnostic_message: string | null
}

export interface AITradingConfig {
  enabled: boolean
  default_mode: string
  max_single_trade_amount: number
  max_daily_trades: number
  max_position_ratio: number
  require_confirmation_above: number
  blocked_symbols: string[]
  available_gateways: AITradingGatewayOption[]
  available_accounts: AITradingAccountOption[]
}

export interface TradeHistoryItem {
  trade_id: string
  user_input: string
  action: string
  symbol: string | null
  quantity: number | null
  price: number | null
  status: string
  confidence: number | null
  risk_level: string | null
  ai_reasoning: string | null
  dry_run: boolean
  created_at: string | null
  executed_at: string | null
}

/**
 * Send a natural language trading instruction.
 */
export async function executeTrade(params: {
  message: string
  gateway_id?: string
  account_id?: string
  dry_run?: boolean
  auto_confirm?: boolean
}): Promise<AITradingResponse> {
  return request.post<AITradingResponse>(`${API_BASE}/execute`, {
    message: params.message,
    gateway_id: params.gateway_id || null,
    account_id: params.account_id || null,
    dry_run: params.dry_run ?? true,
    auto_confirm: params.auto_confirm ?? false,
  })
}

/**
 * Confirm or reject a pending trade.
 */
export async function confirmTrade(params: {
  trade_id: string
  confirmed: boolean
  user_note?: string
}): Promise<{ trade_id: string; status: string; message: string }> {
  return request.post(`${API_BASE}/confirm`, params)
}

/**
 * Get AI trading configuration.
 */
export async function getTradingConfig(): Promise<AITradingConfig> {
  return request.get<AITradingConfig>(`${API_BASE}/config`)
}

/**
 * Get AI trading history.
 */
export async function getTradingHistory(limit = 20): Promise<{
  total: number
  items: TradeHistoryItem[]
}> {
  return request.get(`${API_BASE}/history`, { params: { limit } })
}


/**
 * Generate AI reflection on a completed trade.
 */
export async function reflectOnTrade(tradeId: string): Promise<{
  success: boolean
  trade_id?: string
  reflection?: string
  message?: string
}> {
  return request.post(`${API_BASE}/reflect/${tradeId}`)
}
