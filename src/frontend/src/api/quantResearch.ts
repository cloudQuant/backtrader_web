import api from './index'

export type AnalyticsStatus = 'ok' | 'degraded'

export interface VarCvarResult {
  status: AnalyticsStatus
  method: 'historical' | 'parametric' | 'monte_carlo'
  observation_count: number
  var_95?: number | null
  cvar_95?: number | null
  var_99?: number | null
  cvar_99?: number | null
  reason?: string | null
  backtest_id?: string | null
}

export interface StressTestRequest {
  scenarios?: Array<{ name: string; start_date: string; end_date: string; description?: string | null }>
}

export interface StressTestResult {
  status: AnalyticsStatus
  scenario_count: number
  results: Array<{
    name: string
    status: AnalyticsStatus
    max_loss?: number | null
    max_drawdown?: number | null
    recovery_days?: number | null
    reason?: string | null
  }>
  backtest_id?: string | null
}

export interface KellyResult {
  status: AnalyticsStatus
  trade_count: number
  win_rate?: number | null
  avg_win?: number | null
  avg_loss?: number | null
  payoff_ratio?: number | null
  full_kelly?: number | null
  half_kelly?: number | null
  quarter_kelly?: number | null
  recommendation?: string | null
  reason?: string | null
  backtest_id?: string | null
}

export interface PositionSizingResult {
  status: AnalyticsStatus
  method: 'volatility_target'
  observation_count: number
  annualized_volatility?: number | null
  target_volatility?: number | null
  recommended_position?: number | null
  max_position?: number | null
  reason?: string | null
  backtest_id?: string | null
}

export interface BenchmarkReturnsResult {
  status: AnalyticsStatus
  benchmark_id: string
  symbol?: string | null
  start_date: string
  end_date: string
  observation_count: number
  dates: string[]
  returns: number[]
  reason?: string | null
}

export interface BenchmarkMetricsResult {
  status: AnalyticsStatus
  benchmark_id: string
  observation_count: number
  alpha?: number | null
  beta?: number | null
  tracking_error?: number | null
  information_ratio?: number | null
  risk_free_rate: number
  reason?: string | null
  backtest_id?: string | null
}

export interface MarketRegimeResult {
  status: AnalyticsStatus
  observation_count: number
  volatility_regime?: 'low' | 'medium' | 'high' | null
  trend_regime?: 'bull' | 'sideways' | 'bear' | null
  overall_regime?: string | null
  annualized_volatility?: number | null
  trend_return?: number | null
  reason?: string | null
  backtest_id?: string | null
}

export interface FactorEvaluationRequest {
  factor_values: Array<number | null>
  future_returns: Array<number | null>
  quantiles?: number
}

export interface FactorEvaluationResult {
  status: AnalyticsStatus
  observation_count: number
  ic_mean?: number | null
  ic_std?: number | null
  ic_ir?: number | null
  ic_t_stat?: number | null
  long_short_return?: number | null
  reason?: string | null
}

export interface FactorCorrelationRequest {
  factor_values: Record<string, Array<number | null>>
  threshold?: number
}

export interface FactorCorrelationResult {
  status: AnalyticsStatus
  factor_count: number
  observation_count: number
  matrix: Record<string, Record<string, number>>
  high_correlation_pairs: Array<{ factor_a: string; factor_b: string; correlation: number }>
  reason?: string | null
}

export interface CustomFactorRequest {
  expression: string
  records: Array<Record<string, number | null>>
}

export interface CustomFactorResult {
  status: AnalyticsStatus
  values: Array<number | null>
  observation_count: number
  reason?: string | null
}

export interface BrinsonAttributionRequest {
  portfolio_weights: Record<string, number>
  benchmark_weights: Record<string, number>
  portfolio_returns: Record<string, number>
  benchmark_returns: Record<string, number>
}

export interface BrinsonAttributionResult {
  status: AnalyticsStatus
  asset_count: number
  allocation_effect?: number | null
  selection_effect?: number | null
  interaction_effect?: number | null
  total_excess_return?: number | null
  reason?: string | null
}

export interface FamaFrenchAttributionRequest {
  strategy_returns: number[]
  market_returns: number[]
  smb_returns: number[]
  hml_returns: number[]
}

export interface FamaFrenchAttributionResult {
  status: AnalyticsStatus
  observation_count: number
  alpha?: number | null
  market_beta?: number | null
  smb_beta?: number | null
  hml_beta?: number | null
  r_squared?: number | null
  reason?: string | null
}

export const quantResearchApi = {
  getVarCvar(backtestId: string, method: VarCvarResult['method'] = 'historical') {
    return api.get<VarCvarResult>(`/risk-analytics/var-cvar/${backtestId}`, { params: { method } })
  },

  runStressTest(backtestId: string, data: StressTestRequest = {}) {
    return api.post<StressTestResult, StressTestRequest>(`/risk-analytics/stress-test/${backtestId}`, data)
  },

  getKelly(backtestId: string) {
    return api.get<KellyResult>(`/risk-analytics/kelly/${backtestId}`)
  },

  getPositionSizing(backtestId: string, targetVolatility = 0.15, maxPosition = 1.0) {
    return api.get<PositionSizingResult>(`/risk-analytics/position-sizing/${backtestId}`, {
      params: { target_volatility: targetVolatility, max_position: maxPosition },
    })
  },

  getBenchmarkReturns(benchmarkId: string, startDate: string, endDate: string) {
    return api.get<BenchmarkReturnsResult>(`/risk-analytics/benchmark/${benchmarkId}`, {
      params: { start_date: startDate, end_date: endDate },
    })
  },

  getBenchmarkMetrics(backtestId: string, benchmarkId = 'hs300', riskFreeRate = 0) {
    return api.get<BenchmarkMetricsResult>(`/risk-analytics/benchmark-metrics/${backtestId}`, {
      params: { benchmark_id: benchmarkId, risk_free_rate: riskFreeRate },
    })
  },

  getMarketRegime(backtestId: string) {
    return api.get<MarketRegimeResult>(`/risk-analytics/market-regime/${backtestId}`)
  },

  evaluateFactor(data: FactorEvaluationRequest) {
    return api.post<FactorEvaluationResult, FactorEvaluationRequest>('/factor-lib/evaluate', data)
  },

  analyzeFactorCorrelation(data: FactorCorrelationRequest) {
    return api.post<FactorCorrelationResult, FactorCorrelationRequest>('/factor-lib/correlation', data)
  },

  calculateCustomFactor(data: CustomFactorRequest) {
    return api.post<CustomFactorResult, CustomFactorRequest>('/factor-lib/custom/calculate', data)
  },

  calculateBrinson(data: BrinsonAttributionRequest) {
    return api.post<BrinsonAttributionResult, BrinsonAttributionRequest>('/perf-attribution/brinson', data)
  },

  calculateFamaFrench(data: FamaFrenchAttributionRequest) {
    return api.post<FamaFrenchAttributionResult, FamaFrenchAttributionRequest>('/perf-attribution/fama-french', data)
  },
}
