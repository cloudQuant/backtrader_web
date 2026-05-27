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
  getOptionsChain(symbol: string, expiry: string, provider = 'auto') {
    return request.get<Record<string, unknown>>(`/options-chain/${symbol}`, { params: { expiry, provider } })
  },
  runScanner(payload: { universe: string[]; condition: string; lookback_days?: number; timeframe?: string }) {
    return request.post<Record<string, unknown>>('/scanners/run', payload)
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
