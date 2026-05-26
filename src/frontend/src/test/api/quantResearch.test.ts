import { describe, it, expect, vi, beforeEach } from 'vitest'
import api from '@/api/index'
import { quantResearchApi } from '@/api/quantResearch'

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

describe('quantResearchApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('getVarCvar calls risk analytics endpoint with method', async () => {
    vi.mocked(api.get).mockResolvedValue({ status: 'ok' })
    await quantResearchApi.getVarCvar('bt1', 'parametric')
    expect(api.get).toHaveBeenCalledWith('/risk-analytics/var-cvar/bt1', { params: { method: 'parametric' } })
  })

  it('runStressTest posts scenarios', async () => {
    vi.mocked(api.post).mockResolvedValue({ status: 'ok' })
    const data = { scenarios: [{ name: 'shock', start_date: '2024-01-01', end_date: '2024-01-10' }] }
    await quantResearchApi.runStressTest('bt1', data)
    expect(api.post).toHaveBeenCalledWith('/risk-analytics/stress-test/bt1', data)
  })

  it('getKelly calls kelly endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ status: 'ok' })
    await quantResearchApi.getKelly('bt1')
    expect(api.get).toHaveBeenCalledWith('/risk-analytics/kelly/bt1')
  })

  it('getPositionSizing passes volatility params', async () => {
    vi.mocked(api.get).mockResolvedValue({ status: 'ok' })
    await quantResearchApi.getPositionSizing('bt1', 0.2, 1.5)
    expect(api.get).toHaveBeenCalledWith('/risk-analytics/position-sizing/bt1', {
      params: { target_volatility: 0.2, max_position: 1.5 },
    })
  })

  it('getBenchmarkReturns passes date range', async () => {
    vi.mocked(api.get).mockResolvedValue({ status: 'ok' })
    await quantResearchApi.getBenchmarkReturns('hs300', '2024-01-01', '2024-02-01')
    expect(api.get).toHaveBeenCalledWith('/risk-analytics/benchmark/hs300', {
      params: { start_date: '2024-01-01', end_date: '2024-02-01' },
    })
  })

  it('getBenchmarkMetrics passes benchmark params', async () => {
    vi.mocked(api.get).mockResolvedValue({ status: 'ok' })
    await quantResearchApi.getBenchmarkMetrics('bt1', 'csi500', 0.02)
    expect(api.get).toHaveBeenCalledWith('/risk-analytics/benchmark-metrics/bt1', {
      params: { benchmark_id: 'csi500', risk_free_rate: 0.02 },
    })
  })

  it('getMarketRegime calls market regime endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ status: 'ok' })
    await quantResearchApi.getMarketRegime('bt1')
    expect(api.get).toHaveBeenCalledWith('/risk-analytics/market-regime/bt1')
  })

  it('evaluateFactor posts factor data', async () => {
    vi.mocked(api.post).mockResolvedValue({ status: 'ok' })
    const data = { factor_values: [1, 2], future_returns: [0.01, 0.02] }
    await quantResearchApi.evaluateFactor(data)
    expect(api.post).toHaveBeenCalledWith('/factor-lib/evaluate', data)
  })

  it('analyzeFactorCorrelation posts factor matrix input', async () => {
    vi.mocked(api.post).mockResolvedValue({ status: 'ok' })
    const data = { factor_values: { a: [1, 2], b: [2, 4] }, threshold: 0.9 }
    await quantResearchApi.analyzeFactorCorrelation(data)
    expect(api.post).toHaveBeenCalledWith('/factor-lib/correlation', data)
  })

  it('calculateCustomFactor posts expression records', async () => {
    vi.mocked(api.post).mockResolvedValue({ status: 'ok' })
    const data = { expression: '(close - open) / open', records: [{ open: 100, close: 110 }] }
    await quantResearchApi.calculateCustomFactor(data)
    expect(api.post).toHaveBeenCalledWith('/factor-lib/custom/calculate', data)
  })

  it('calculateBrinson posts attribution inputs', async () => {
    vi.mocked(api.post).mockResolvedValue({ status: 'ok' })
    const data = {
      portfolio_weights: { tech: 0.6 },
      benchmark_weights: { tech: 0.5 },
      portfolio_returns: { tech: 0.1 },
      benchmark_returns: { tech: 0.08 },
    }
    await quantResearchApi.calculateBrinson(data)
    expect(api.post).toHaveBeenCalledWith('/perf-attribution/brinson', data)
  })

  it('calculateFamaFrench posts factor return series', async () => {
    vi.mocked(api.post).mockResolvedValue({ status: 'ok' })
    const data = {
      strategy_returns: [0.01],
      market_returns: [0.01],
      smb_returns: [0.001],
      hml_returns: [0.002],
    }
    await quantResearchApi.calculateFamaFrench(data)
    expect(api.post).toHaveBeenCalledWith('/perf-attribution/fama-french', data)
  })
})
