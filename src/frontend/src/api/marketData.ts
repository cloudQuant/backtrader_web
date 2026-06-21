import request from './index'

export type MarketAssetType = 'stock' | 'futures' | 'bond' | 'fund' | 'option' | 'fx' | 'crypto'

export interface MarketInstrumentLookupParams {
  asset_type: MarketAssetType
  symbol: string
  start_date?: string
  end_date?: string
  period?: string
  market?: string
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
  open_interest?: number | null
  market_cap?: number | null
  float_market_cap?: number | null
  pe?: number | null
  pb?: number | null
  update_time?: string | null
  [key: string]: unknown
}

export interface MarketHistoryRow {
  date: string
  open?: number | null
  high?: number | null
  low?: number | null
  close?: number | null
  volume?: number | null
  turnover?: number | null
  change?: number | null
  change_pct?: number | null
  turnover_rate?: number | null
  open_interest?: number | null
  settle?: number | null
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

export const marketDataApi = {
  lookupInstrument(params: MarketInstrumentLookupParams) {
    return request.get<MarketInstrumentLookupResponse>('/data/market-instruments/lookup', {
      params,
    })
  },
}
