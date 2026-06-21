import request from './index'

export interface NewsArticleItem {
  id?: string
  headline: string
  url?: string
  canonical_url?: string
  source?: string
  tickers?: string[]
  priority?: string
  tier?: number
  source_flag?: string
  sentiment?: string
  impact?: string
  threat?: string
  cluster_id?: string
  summary?: string
  status?: string
}

export interface ScannerUniverseInstrument {
  symbol: string
  name?: string
  asset_type?: string
  exchange?: string
  source?: string
}

export interface ScannerMetricSnapshot {
  pool_id: string
  lookback_days: number
  timeframe: string
  computed_at?: string
  total: number
  cache_status?: string
}

export interface ScannerUniversePool {
  id: string
  name: string
  description?: string
  category?: string
  source?: string
  instrument_count: number
  updated_at?: string
  is_custom?: boolean
  refreshable?: boolean
  last_refresh_status?: string
  last_refresh_error?: string
  metric_snapshot?: ScannerMetricSnapshot
  instruments: ScannerUniverseInstrument[]
}

export interface ScannerIndicatorRule {
  id?: string
  metric: string
  operator: string
  value: number
  enabled: boolean
}

export interface ScannerPlan {
  id: string
  name: string
  universe_pool_id: string
  indicator_rules: ScannerIndicatorRule[]
  condition: string
  lookback_days: number
  timeframe: string
  schedule_enabled: boolean
  schedule_frequency: string
  status: string
  result_table_name?: string
  result_table_status?: string
  created_at?: string
  updated_at?: string
}

export interface ScannerPlanRun {
  id: string
  plan_id: string
  run_date: string
  status: string
  universe_pool_id?: string
  condition?: string
  lookback_days?: number
  timeframe?: string
  universe_count?: number
  match_count: number
  matches: Array<Record<string, unknown>>
  metrics?: Record<string, unknown>
  cache_status?: string
  started_at?: string
  completed_at?: string
}

export const marketIntelApi = {
  searchEquities(q: string) {
    return request.get<{ items: Array<Record<string, unknown>>; total: number }>('/equity-research/search', { params: { q } })
  },
  getEquityQuote(symbol: string) {
    return request.get<Record<string, unknown>>(`/equity-research/quote/${symbol}`)
  },
  getEquityInfo(symbol: string) {
    return request.get<Record<string, unknown>>(`/equity-research/info/${symbol}`)
  },
  getEquityHistory(symbol: string) {
    return request.get<{ symbol: string; rows: Array<Record<string, unknown>> }>(`/equity-research/history/${symbol}`)
  },
  getEquityFinancials(symbol: string) {
    return request.get<Record<string, unknown>>(`/equity-research/financials/${symbol}`)
  },
  getTechnicals(symbol: string) {
    return request.get<{ symbol: string; factors: Record<string, unknown> }>(`/equity-research/technicals/${symbol}`)
  },
  getEquityPeers(symbol: string) {
    return request.get<{ symbol: string; items: Array<Record<string, unknown>>; total: number }>(`/equity-research/peers/${symbol}`)
  },
  createNewsSource(payload: Record<string, unknown>) {
    return request.post<Record<string, unknown>>('/news-intelligence/sources', payload)
  },
  pullNewsSource(sourceName: string, limit = 20) {
    return request.post<{ source: string; status: string; fetched_count: number; inserted_count: number; total: number }>(`/news-intelligence/sources/${sourceName}/pull`, undefined, {
      params: { limit },
    })
  },
  ingestArticles(payload: { articles: Array<Record<string, unknown>> }) {
    return request.post<{ inserted_count: number; total: number }>('/news-intelligence/articles/ingest', payload)
  },
  listArticles(params: { sentiment?: string; source?: string; ticker?: string; cluster_id?: string } = {}) {
    return request.get<{ items: NewsArticleItem[]; total: number }>('/news-intelligence/articles', { params })
  },
  analyzeHeadline(payload: { headline: string; allow_ai?: boolean }) {
    return request.post<Record<string, unknown>>('/news-intelligence/analyze', payload)
  },
  getOptionsChain(symbol: string, expiry: string, provider = 'data_governance') {
    return request.get<Record<string, unknown>>(`/options-chain/${symbol}`, { params: { expiry, provider } })
  },
  listScannerUniversePools() {
    return request.get<{ items: ScannerUniversePool[]; total: number }>('/scanners/universe-pools')
  },
  refreshScannerUniversePool(poolId: string) {
    return request.post<ScannerUniversePool>(`/scanners/universe-pools/${poolId}/refresh`, undefined, { timeout: 300000 })
  },
  precomputeScannerUniversePool(poolId: string, payload: { lookback_days?: number; timeframe?: string }) {
    return request.post<ScannerMetricSnapshot>(`/scanners/universe-pools/${poolId}/precompute`, payload, { timeout: 300000 })
  },
  createScannerPlan(payload: {
    name: string
    universe_pool_id: string
    indicator_rules: ScannerIndicatorRule[]
    condition: string
    lookback_days?: number
    timeframe?: string
    schedule_enabled?: boolean
    schedule_frequency?: string
  }) {
    return request.post<ScannerPlan>('/scanners/plans', payload)
  },
  updateScannerPlan(planId: string, payload: {
    name: string
    universe_pool_id: string
    indicator_rules: ScannerIndicatorRule[]
    condition: string
    lookback_days?: number
    timeframe?: string
    schedule_enabled?: boolean
    schedule_frequency?: string
    status?: string
  }) {
    return request.patch<ScannerPlan>(`/scanners/plans/${planId}`, payload)
  },
  deleteScannerPlan(planId: string) {
    return request.delete<{ deleted: boolean }>(`/scanners/plans/${planId}`)
  },
  createScannerPlanResultTable(planId: string) {
    return request.post<ScannerPlan>(`/scanners/plans/${planId}/result-table`)
  },
  deleteScannerPlanResultTable(planId: string) {
    return request.delete<ScannerPlan>(`/scanners/plans/${planId}/result-table`)
  },
  listScannerPlans() {
    return request.get<{ items: ScannerPlan[]; total: number }>('/scanners/plans')
  },
  runScannerPlan(planId: string, payload: { run_date?: string; force?: boolean } = {}) {
    return request.post<ScannerPlanRun>(`/scanners/plans/${planId}/runs`, payload, { timeout: 300000 })
  },
  runDailyScannerPlans(payload: { run_date?: string } = {}) {
    return request.post<{ run_date: string; items: ScannerPlanRun[]; total: number }>('/scanners/plans/daily-runs', payload, { timeout: 300000 })
  },
  listScannerPlanRuns(planId: string) {
    return request.get<{ items: ScannerPlanRun[]; total: number }>(`/scanners/plans/${planId}/runs`)
  },
  saveCustomScannerUniversePool(payload: {
    id?: string
    name: string
    description?: string
    instruments: ScannerUniverseInstrument[]
  }) {
    return request.post<ScannerUniversePool>('/scanners/universe-pools/custom', payload)
  },
  runScanner(payload: { universe?: string[]; universe_pool_id?: string; condition: string; lookback_days?: number; timeframe?: string }) {
    return request.post<Record<string, unknown>>('/scanners/run', payload, { timeout: 300000 })
  },
  getScannerTask(taskId: string) {
    return request.get<Record<string, unknown>>(`/scanners/tasks/${taskId}`)
  },
  listQuantTools() {
    return request.get<{ tools: Array<Record<string, unknown>> }>('/quant-tools')
  },
  callQuantTool(payload: { tool_name: string; input: Record<string, unknown> }) {
    return request.post<Record<string, unknown>>('/quant-tools/call', payload)
  },
}
