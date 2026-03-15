/**
 * 行情报价 API
 */
import request from './index'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DataSourceInfo {
  source: string
  source_label: string
  status: 'available' | 'not_configured' | 'not_connected' | 'unavailable'
  status_message: string | null
  capabilities: string[]
}

export interface DataSourceListResponse {
  sources: DataSourceInfo[]
}

export interface QuoteTick {
  source: string
  source_label: string
  symbol: string
  name: string
  exchange: string
  category: string
  last_price: number | null
  change: number | null
  change_pct: number | null
  bid_price: number | null
  ask_price: number | null
  high_price: number | null
  low_price: number | null
  open_price: number | null
  prev_close: number | null
  volume: number | null
  turnover: number | null
  open_interest: number | null
  update_time: string | null
  status: string
  error_message: string | null
}

export interface QuoteListResponse {
  source: string
  source_label: string
  total: number
  ticks: QuoteTick[]
  update_time: string | null
  refresh_mode: string
}

export interface SymbolItem {
  symbol: string
  name: string
  exchange: string
  category: string
}

export interface SymbolSearchResponse {
  source: string
  keyword: string
  results: SymbolItem[]
}

export interface DefaultSymbolsResponse {
  source: string
  default_symbols: SymbolItem[]
  custom_symbols: string[]
}

export interface CustomSymbolsResponse {
  source: string
  symbols: string[]
}

export interface KlineBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface ChartDataResponse {
  source: string
  symbol: string
  timeframe: string
  bars: KlineBar[]
  total: number
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const quoteApi = {
  /** List all data sources with status */
  listSources(): Promise<DataSourceListResponse> {
    return request.get('/quote/sources')
  },

  /** Get default + custom symbols for a data source */
  getSymbols(source: string): Promise<DefaultSymbolsResponse> {
    return request.get('/quote/symbols', { params: { source } })
  },

  /** Add custom symbols */
  addSymbols(source: string, symbols: string[]): Promise<CustomSymbolsResponse> {
    return request.post('/quote/symbols/add', { source, symbols })
  },

  /** Remove custom symbols */
  removeSymbols(source: string, symbols: string[]): Promise<CustomSymbolsResponse> {
    return request.post('/quote/symbols/remove', { source, symbols })
  },

  /** Search symbols within a data source */
  searchSymbols(source: string, keyword: string): Promise<SymbolSearchResponse> {
    return request.get('/quote/symbols/search', { params: { source, keyword } })
  },

  /** Fetch quotes for a data source */
  getQuotes(source: string, symbols?: string[]): Promise<QuoteListResponse> {
    const params: Record<string, string> = { source }
    if (symbols && symbols.length > 0) {
      params.symbols = symbols.join(',')
    }
    return request.get('/quote/ticks', { params })
  },

  /** Fetch K-line / chart data for a symbol */
  getChartData(
    source: string,
    symbol: string,
    timeframe: string = 'M1',
    count: number = 200,
  ): Promise<ChartDataResponse> {
    return request.get('/quote/chart', {
      params: { source, symbol, timeframe, count },
    })
  },
}
