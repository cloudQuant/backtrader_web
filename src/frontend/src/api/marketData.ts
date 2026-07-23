import request from './index'
import type {
  AssetSpecResponse,
  DataPrecheckRequest,
  DataPrecheckResponse,
  ExecutionModelResponse,
  MarketDataCoverageMatrixResponse,
} from '@/types/trust'

export type MarketAssetType = 'stock' | 'futures' | 'bond' | 'fund' | 'option' | 'fx' | 'crypto'

export interface MarketInstrumentLookupParams {
  asset_type: MarketAssetType
  symbol: string
  start_date?: string
  end_date?: string
  period?: string
  market?: string
}

export interface MarketInstrumentOption {
  asset_type: MarketAssetType
  symbol: string
  name: string
  market?: string | null
  source_table?: string | null
  latest_date?: string | null
  has_snapshot: boolean
  has_history: boolean
  history_rows: number
}

export interface MarketInstrumentOptionsParams {
  asset_type: MarketAssetType
  search?: string
  limit?: number
}

export interface MarketInstrumentOptionsResponse {
  asset_type: MarketAssetType
  items: MarketInstrumentOption[]
  total: number
}

export interface MarketSnapshot {
  symbol?: string
  name?: string
  price?: number | null
  change?: number | null
  change_pct?: number | null
  open?: number | null
  high?: number | null
  low?: number | null
  previous_close?: number | null
  settle?: number | null
  previous_settle?: number | null
  bid?: number | null
  ask?: number | null
  volume?: number | null
  turnover?: number | null
  turnover_rate?: number | null
  open_interest?: number | null
  strike?: number | null
  days_to_expiry?: number | null
  market_cap?: number | null
  float_market_cap?: number | null
  pe?: number | null
  pb?: number | null
  update_time?: string | null
  data_source_table?: string | null
  history_currency?: string | null
  [key: string]: unknown
}

export interface MarketHistoryRow {
  date: string
  name?: string | null
  open?: number | null
  high?: number | null
  low?: number | null
  close?: number | null
  price?: number | null
  volume?: number | null
  turnover?: number | null
  change?: number | null
  change_pct?: number | null
  turnover_rate?: number | null
  open_interest?: number | null
  settle?: number | null
  strike?: number | null
  days_to_expiry?: number | null
  [key: string]: unknown
}

export interface MarketInstrumentIndicators {
  latest_close?: number | null
  return_pct?: number | null
  highest_close?: number | null
  lowest_close?: number | null
  avg_volume?: number | null
  observation_count?: number
}

export interface MarketInstrumentLookupResponse {
  asset_type: MarketAssetType
  symbol: string
  name: string
  market?: string | null
  provider?: string | null
  snapshot: MarketSnapshot
  history: {
    period: string
    rows: MarketHistoryRow[]
    total: number
  }
  indicators: MarketInstrumentIndicators
  warnings: string[]
}

export interface MarketDataCoverageQuery {
  asset_type?: MarketAssetType | string | null
  symbol?: string | null
  timeframe?: string | null
  provider?: string | null
  refresh_if_empty?: boolean
  limit?: number
}

export interface MarketDataCoverageRefreshQuery {
  asset_type?: MarketAssetType | string | null
  symbol?: string | null
  timeframe?: string | null
  limit?: number
}

export const marketDataApi = {
  listInstrumentOptions(params: MarketInstrumentOptionsParams) {
    return request.get<MarketInstrumentOptionsResponse>('/data/market-instruments/options', {
      params,
    })
  },
  lookupInstrument(params: MarketInstrumentLookupParams) {
    return request.get<MarketInstrumentLookupResponse>('/data/market-instruments/lookup', {
      params,
    })
  },
  getAssetSpec(symbol: string, params?: { asset_type?: MarketAssetType | string | null }) {
    return request.get<AssetSpecResponse>(`/data/trust/asset-specs/${encodeURIComponent(symbol)}`, {
      params,
    })
  },
  getExecutionModel(symbol: string, params?: { asset_type?: MarketAssetType | string | null }) {
    return request.get<ExecutionModelResponse>(
      `/data/trust/asset-specs/${encodeURIComponent(symbol)}/execution-model`,
      { params },
    )
  },
  listCoverage(params: MarketDataCoverageQuery = {}) {
    return request.get<MarketDataCoverageMatrixResponse>('/data/trust/coverage', {
      params,
    })
  },
  refreshLocalCoverage(params: MarketDataCoverageRefreshQuery = {}) {
    return request.post<MarketDataCoverageMatrixResponse>('/data/trust/coverage/refresh-local', undefined, {
      params,
    })
  },
  refreshWarehouseCoverage(params: MarketDataCoverageRefreshQuery = {}) {
    return request.post<MarketDataCoverageMatrixResponse>(
      '/data/trust/coverage/refresh-warehouse',
      undefined,
      { params },
    )
  },
  runPrecheck(data: DataPrecheckRequest, options: { signal?: AbortSignal } = {}) {
    return request.post<DataPrecheckResponse, DataPrecheckRequest>('/data/trust/precheck', data, options)
  },
}
