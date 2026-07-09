export type DataQualityStatus = 'pass' | 'warning' | 'failed' | 'unknown' | string
export type QualityGateSeverity = 'error' | 'warning' | 'info' | string

export interface QualityGateEvaluation {
  key: string
  label: string
  actual?: number | string | boolean | null
  threshold?: number | string | boolean | null
  operator?: string
  passed: boolean
  severity?: QualityGateSeverity
  message?: string
}

export interface AssetSpecResponse {
  id: string
  asset_type: string
  symbol: string
  name: string
  exchange: string
  currency: string
  contract_multiplier?: number | null
  margin_rate?: number | null
  tick_size?: number | null
  lot_size?: number | null
  min_order_size?: number | null
  commission_rate?: number | null
  commission_fixed?: number | null
  slippage_model?: string
  trading_calendar?: string
  metadata?: Record<string, unknown>
  source?: string
  created_at?: string | null
  updated_at?: string | null
}

export interface MarketDataCoverageResponse {
  id: string
  asset_type: string
  symbol: string
  timeframe: string
  provider: string
  start_date?: string | null
  end_date?: string | null
  row_count: number
  missing_count: number
  missing_ratio: number
  latest_bar_time?: string | null
  quality_status: DataQualityStatus
  source_path?: string | null
  updated_at?: string | null
}

export interface MarketDataQualityReportResponse {
  id: string
  asset_type: string
  symbol: string
  timeframe: string
  provider: string
  issue_type: string
  severity: QualityGateSeverity
  issue_count: number
  sample_payload: Record<string, unknown>
  created_at?: string | null
}

export interface MarketDataCoverageMatrixResponse {
  total: number
  items: MarketDataCoverageResponse[]
  refreshed: boolean
}

export interface DataPrecheckRequest {
  asset_type?: string | null
  symbol: string
  timeframe?: string
  provider?: string | null
  start_date?: string | null
  end_date?: string | null
}

export interface DataPrecheckResponse {
  passed: boolean
  status: DataQualityStatus
  asset_type: string
  symbol: string
  timeframe: string
  provider: string
  reasons: string[]
  warnings: string[]
  asset_spec?: AssetSpecResponse | null
  coverage?: MarketDataCoverageResponse | null
  quality_reports: MarketDataQualityReportResponse[]
  gate_evaluations: QualityGateEvaluation[]
}

export interface ExecutionModelResponse {
  asset_type: string
  symbol: string
  commission_rate: number
  commission_fixed: number
  slippage_bps: number
  min_order_size: number
  lot_size: number
  contract_multiplier: number
  margin_rate?: number | null
  volume_limit_ratio?: number | null
  price_limit_policy: string
  suspended_policy: string
  source: string
}

export interface RobustnessValidationRequest {
  methods?: string[]
  min_robustness_score?: number
  require_no_high_risk?: boolean
  monte_carlo_iterations?: number
  random_seed?: number | null
  run_id?: string | null
  strategy_version_id?: string | null
}

export interface RobustnessTestResultResponse {
  id: string
  user_id: string
  run_id?: string | null
  strategy_version_id?: string | null
  backtest_id: string
  method: string
  status: string
  metrics: Record<string, unknown>
  gate_evaluations: QualityGateEvaluation[]
  report: Record<string, unknown>
  error_message?: string | null
  created_at?: string | null
}
