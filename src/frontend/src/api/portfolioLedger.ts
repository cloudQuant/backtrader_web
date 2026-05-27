import request from './index'

export interface PortfolioLedgerSummary {
  id: string
  name: string
  base_currency: string
  source_type: string
  benchmark_symbol?: string | null
  transaction_count?: number
}

export interface PortfolioHolding {
  symbol: string
  quantity: number
  cost_basis: number
}

export interface PortfolioTransaction {
  symbol: string
  trade_type: string
  quantity: number
  price: number
  trade_date: string
}

export interface PortfolioSnapshot {
  date: string
  snapshot_index: number
  cash_flow: number
  nav: number
}

export interface PortfolioLedgerExportPayload {
  schema_version: string
  portfolio: PortfolioLedgerSummary
  transactions: PortfolioTransaction[]
}

export interface PortfolioLedgerVarCvarResult {
  portfolio_id: string
  status: 'ok' | 'degraded'
  method: 'historical' | 'parametric' | 'monte_carlo'
  observation_count: number
  var_95?: number | null
  var_99?: number | null
  cvar_95?: number | null
  cvar_99?: number | null
  reason?: string | null
}

export interface PortfolioLedgerPositionSizingResult {
  portfolio_id: string
  status: 'ok' | 'degraded'
  method: 'volatility_target'
  observation_count: number
  annualized_volatility?: number | null
  target_volatility?: number | null
  recommended_position?: number | null
  max_position?: number | null
  reason?: string | null
}

export interface PortfolioLedgerBenchmarkMetricsResult {
  portfolio_id: string
  status: 'ok' | 'degraded'
  benchmark_id: string
  observation_count: number
  alpha?: number | null
  beta?: number | null
  tracking_error?: number | null
  information_ratio?: number | null
  risk_free_rate: number
  reason?: string | null
}

export interface PortfolioLedgerBrinsonRequest {
  benchmark_weights: Record<string, number>
  benchmark_returns: Record<string, number>
}

export interface PortfolioLedgerBrinsonResult {
  portfolio_id: string
  status: 'ok' | 'degraded'
  asset_count: number
  allocation_effect?: number | null
  selection_effect?: number | null
  interaction_effect?: number | null
  total_excess_return?: number | null
  reason?: string | null
}

export interface PortfolioLedgerFamaFrenchRequest {
  market_returns?: number[]
  smb_returns: number[]
  hml_returns: number[]
  benchmark_id?: string
}

export interface PortfolioLedgerFamaFrenchResult {
  portfolio_id: string
  status: 'ok' | 'degraded'
  observation_count: number
  alpha?: number | null
  market_beta?: number | null
  smb_beta?: number | null
  hml_beta?: number | null
  r_squared?: number | null
  benchmark_id?: string | null
  reason?: string | null
}

export const portfolioLedgerApi = {
  create(payload: { name: string; base_currency?: string; source_type?: string }) {
    return request.post<PortfolioLedgerSummary>('/portfolio-ledger', payload)
  },
  importTransactions(portfolioId: string, payload: { format: string; idempotency_key: string; transactions: Array<Record<string, unknown>> }) {
    return request.post<{ duplicate: boolean; imported_count: number }>(`/portfolio-ledger/${portfolioId}/import`, payload)
  },
  getDetail(portfolioId: string) {
    return request.get<PortfolioLedgerSummary>(`/portfolio-ledger/${portfolioId}`)
  },
  getHoldings(portfolioId: string) {
    return request.get<{ items: PortfolioHolding[]; total: number }>(`/portfolio-ledger/${portfolioId}/holdings`)
  },
  getTransactions(portfolioId: string) {
    return request.get<{ items: PortfolioTransaction[]; total: number }>(`/portfolio-ledger/${portfolioId}/transactions`)
  },
  backfillSnapshots(portfolioId: string) {
    return request.post<{ items: PortfolioSnapshot[]; total: number }>(`/portfolio-ledger/${portfolioId}/snapshots/backfill`)
  },
  getSnapshots(portfolioId: string) {
    return request.get<{ items: PortfolioSnapshot[]; total: number }>(`/portfolio-ledger/${portfolioId}/snapshots`)
  },
  exportPortfolio(portfolioId: string, format: 'json' = 'json') {
    return request.get<PortfolioLedgerExportPayload>(`/portfolio-ledger/${portfolioId}/export`, { params: { format } })
  },
  getVarCvar(portfolioId: string, method: PortfolioLedgerVarCvarResult['method'] = 'historical') {
    return request.get<PortfolioLedgerVarCvarResult>(`/portfolio-ledger/${portfolioId}/analytics/var-cvar`, {
      params: { method },
    })
  },
  getPositionSizing(portfolioId: string, targetVolatility = 0.15, maxPosition = 1.0) {
    return request.get<PortfolioLedgerPositionSizingResult>(`/portfolio-ledger/${portfolioId}/analytics/position-sizing`, {
      params: { target_volatility: targetVolatility, max_position: maxPosition },
    })
  },
  getBenchmarkMetrics(portfolioId: string, benchmarkId?: string, riskFreeRate = 0) {
    return request.get<PortfolioLedgerBenchmarkMetricsResult>(`/portfolio-ledger/${portfolioId}/analytics/benchmark-metrics`, {
      params: { benchmark_id: benchmarkId, risk_free_rate: riskFreeRate },
    })
  },
  calculateBrinson(portfolioId: string, payload: PortfolioLedgerBrinsonRequest) {
    return request.post<PortfolioLedgerBrinsonResult, PortfolioLedgerBrinsonRequest>(`/portfolio-ledger/${portfolioId}/analytics/brinson`, payload)
  },
  calculateFamaFrench(portfolioId: string, payload: PortfolioLedgerFamaFrenchRequest) {
    return request.post<PortfolioLedgerFamaFrenchResult, PortfolioLedgerFamaFrenchRequest>(`/portfolio-ledger/${portfolioId}/analytics/fama-french`, payload)
  },
}
