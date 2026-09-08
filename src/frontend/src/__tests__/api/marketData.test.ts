import { beforeEach, describe, expect, it, vi } from 'vitest'

import api from '@/api/index'
import {
  createMarketDataQueryFromContract,
  hasMarketDataQueryBundle,
  hasMarketDataQueryContract,
  isMarketDataQueryV2FallbackError,
  marketDataApi,
  type MarketDataQueryContract,
} from '@/api/marketData'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

describe('marketDataApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('listInstrumentOptions calls the selectable instrument endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ items: [], total: 0 })

    await marketDataApi.listInstrumentOptions({
      asset_type: 'stock',
      search: '000',
      limit: 20,
    })

    expect(api.get).toHaveBeenCalledWith('/data/market-instruments/options', {
      params: {
        asset_type: 'stock',
        search: '000',
        limit: 20,
      },
    })
  })

  it('lookupInstrument calls the aggregated market instrument endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ symbol: 'RB2510' })

    await marketDataApi.lookupInstrument({
      asset_type: 'futures',
      symbol: 'RB2510',
      start_date: '2026-06-01',
      end_date: '2026-06-19',
      period: 'daily',
      market: 'CF',
    })

    expect(api.get).toHaveBeenCalledWith('/data/market-instruments/lookup', {
      params: {
        asset_type: 'futures',
        symbol: 'RB2510',
        start_date: '2026-06-01',
        end_date: '2026-06-19',
        period: 'daily',
        market: 'CF',
      },
    })
  })

  it('requests a read-only v2 contract before a first market-data query', async () => {
    vi.mocked(api.get).mockResolvedValue({ version: 'market-data-v2' })

    await marketDataApi.getQueryContract({
      asset_type: 'stock',
      symbol: '000001',
      period: 'daily',
    })

    expect(api.get).toHaveBeenCalledWith('/data/market-instruments/query-contract', expect.objectContaining({
      params: {
        asset_type: 'stock',
        symbol: '000001',
        period: 'daily',
      },
    }))
    const config = vi.mocked(api.get).mock.calls[0]?.[1]
    expect(config).toEqual(expect.objectContaining({
      suppressErrorMessage: true,
      skipRetry: true,
    }))
    expect(config?.validateStatus?.(200)).toBe(true)
    expect(config?.validateStatus?.(404)).toBe(false)
    expect(config?.validateStatus?.(503)).toBe(false)
    expect(config?.validateStatus?.(500)).toBe(false)
  })

  it('passes an explicitly selected family id to the server-owned contract resolver', async () => {
    vi.mocked(api.get).mockResolvedValue({ version: 'market-data-v2' })

    await marketDataApi.getQueryContract({
      asset_type: 'stock',
      symbol: '000001',
      period: 'daily',
      family_id: 'stock.realtime',
    })

    expect(api.get).toHaveBeenCalledWith('/data/market-instruments/query-contract', expect.objectContaining({
      params: {
        asset_type: 'stock',
        symbol: '000001',
        period: 'daily',
        family_id: 'stock.realtime',
      },
    }))
  })

  it('requests the static family control bundle without a symbol or provider selector', async () => {
    vi.mocked(api.get).mockResolvedValue({
      version: 'market-data-family-bundle-v1',
      requested_asset_type: 'stock',
      families: [],
    })

    await marketDataApi.getQueryBundle({ asset_type: 'stock' })

    expect(api.get).toHaveBeenCalledWith('/data/market-instruments/query-bundle', expect.objectContaining({
      params: { asset_type: 'stock' },
      suppressErrorMessage: true,
      skipRetry: true,
    }))
    const config = vi.mocked(api.get).mock.calls[0]?.[1]
    expect(config?.validateStatus?.(200)).toBe(true)
    expect(config?.validateStatus?.(404)).toBe(false)
    expect(config?.validateStatus?.(503)).toBe(false)
  })

  it('accepts only a complete server-issued family control bundle', () => {
    const bundle = {
      version: 'market-data-family-bundle-v1',
      requested_asset_type: 'stock',
      families: [
        {
          family_id: 'stock.realtime',
          family_contract_version: 'market-data-family-v1',
          asset_type: 'stock',
          status: 'ready',
          dataset_code: 'market.bars',
          data_kind: 'bars',
          frequency_semantics: 'calendar_grid',
          frequencies: ['1d'],
          field_profile_id: 'bars-close-v1',
          required_fields: ['close'],
          optional_fields: ['open', 'high', 'low', 'volume'],
          dimension_fields: [],
          coverage_model: 'calendar_grid',
          source_policy_id: 'market-default-v1',
          reason_code: null,
        },
        {
          family_id: 'stock.valuation',
          family_contract_version: 'market-data-family-v1',
          asset_type: 'stock',
          status: 'unconfigured',
          dataset_code: 'market.stock_valuation',
          data_kind: 'reference_series',
          frequency_semantics: 'reporting_period',
          frequencies: ['1d'],
          field_profile_id: 'stock-valuation-v1',
          required_fields: ['pe'],
          optional_fields: ['pb'],
          dimension_fields: [],
          coverage_model: 'report_completeness',
          source_policy_id: null,
          reason_code: 'DATA_FAMILY_UNCONFIGURED',
        },
      ],
    }

    expect(hasMarketDataQueryBundle(bundle)).toBe(true)
    expect(hasMarketDataQueryBundle({
      ...bundle,
      families: [{ ...bundle.families[0], source_policy_id: null }],
    })).toBe(false)
    expect(hasMarketDataQueryBundle({
      ...bundle,
      families: [{ ...bundle.families[0], family_contract_version: undefined }],
    })).toBe(false)
    expect(hasMarketDataQueryBundle({
      ...bundle,
      families: [{ ...bundle.families[0], family_contract_version: 'market-data-family-v2' }],
    })).toBe(false)
    expect(hasMarketDataQueryBundle({
      ...bundle,
      families: [{ ...bundle.families[1], source_policy_id: 'legacy-akshare' }],
    })).toBe(false)
    expect(hasMarketDataQueryBundle({
      ...bundle,
      requested_asset_type: 'stock',
      families: [{ ...bundle.families[0], family_id: 'futures.realtime' }],
    })).toBe(false)
    expect(hasMarketDataQueryBundle({
      ...bundle,
      requested_asset_type: 'stock',
      families: [{
        ...bundle.families[1],
        family_id: 'futures.inventory',
        asset_type: 'futures',
        status: 'not_applicable',
        reason_code: 'DATA_FAMILY_NOT_APPLICABLE',
      }],
    })).toBe(true)
  })

  it('posts only server-issued v2 request facts to the local-first endpoint', async () => {
    const contract: MarketDataQueryContract = {
      version: 'market-data-v2',
      request: {
        identity: { canonical_id: 'instrument:stock:CN-SZSE:000001' },
        dataset_code: 'market.stock_daily',
        data_kind: 'bars',
        frequency: '1d',
        required_fields: ['close', 'volume'],
        adjustment: 'qfq',
        price_basis: 'close',
        currency: 'CNY',
        unit: 'share',
        source_policy_id: 'market-default-v1',
        family_id: 'stock.realtime',
        family_contract_version: 'market-data-family-v1',
        mode: 'local_first',
      },
    }
    const request = createMarketDataQueryFromContract(contract, {
      start: '2026-01-01T00:00:00.000Z',
      end: '2026-01-02T00:00:00.000Z',
      mode: 'local_first',
      purpose: 'display',
      consistency: 'display',
    })
    vi.mocked(api.post).mockResolvedValue({ query_id: 'query-1' })

    await marketDataApi.queryLocalFirst(request)

    expect(hasMarketDataQueryContract(contract)).toBe(true)
    expect(request.identity).toEqual({ canonical_id: 'instrument:stock:CN-SZSE:000001' })
    expect(request.dataset_code).toBe('market.stock_daily')
    expect(request.family_id).toBe('stock.realtime')
    expect(request.family_contract_version).toBe('market-data-family-v1')
    expect(api.post).toHaveBeenCalledWith('/data/queries', request)
  })

  it('rejects a contract that omits or splits the required family binding axes', () => {
    const contract = {
      version: 'market-data-v2',
      request: {
        identity: { canonical_id: 'instrument:stock:CN-SZSE:000001' },
        dataset_code: 'market.stock_daily',
        data_kind: 'bars',
        frequency: '1d',
        required_fields: ['close'],
        source_policy_id: 'market-default-v1',
        family_id: 'stock.realtime',
        mode: 'local_first',
      },
    }

    expect(hasMarketDataQueryContract(contract)).toBe(false)
    expect(() => createMarketDataQueryFromContract(contract as MarketDataQueryContract, {
      start: '2026-01-01T00:00:00.000Z',
      end: '2026-01-02T00:00:00.000Z',
    })).toThrow('MARKET_DATA_QUERY_CONTRACT_INVALID')

    expect(hasMarketDataQueryContract({
      ...contract,
      request: {
        ...contract.request,
        family_id: undefined,
      },
    })).toBe(false)
  })

  it('recognizes only deployment and bootstrap failures as legacy-fallback errors', () => {
    expect(isMarketDataQueryV2FallbackError({ response: { status: 404 } })).toBe(true)
    expect(isMarketDataQueryV2FallbackError({ response: { status: 503 } })).toBe(false)
    expect(isMarketDataQueryV2FallbackError({
      response: { status: 503, data: { details: { code: 'MARKET_DATA_QUERY_V2_DISABLED' } } },
    })).toBe(true)
    expect(isMarketDataQueryV2FallbackError({
      response: { status: 503, data: { details: { code: 'MARKET_DATA_QUERY_BUNDLE_UNAVAILABLE' } } },
    })).toBe(true)
    expect(isMarketDataQueryV2FallbackError({
      response: { status: 503, data: { details: { code: 'MARKET_DATA_WRITE_FAILED' } } },
    })).toBe(false)
    expect(isMarketDataQueryV2FallbackError({ response: { status: 422, data: { details: { code: 'CURSOR_INVALID' } } } })).toBe(false)
    expect(isMarketDataQueryV2FallbackError({ response: { status: 422, data: { details: { code: 'IDENTITY_NOT_FOUND' } } } })).toBe(false)
    expect(isMarketDataQueryV2FallbackError({ response: { status: 422, data: { details: { code: 'OTHER' } } } })).toBe(false)
  })

  it('listCoverage calls the data trust coverage endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ items: [], total: 0, refreshed: false })

    await marketDataApi.listCoverage({ asset_type: 'stock', timeframe: '1d', provider: 'local_csv' })

    expect(api.get).toHaveBeenCalledWith('/data/trust/coverage', {
      params: { asset_type: 'stock', timeframe: '1d', provider: 'local_csv' },
    })
  })

  it('refreshWarehouseCoverage posts to the warehouse coverage endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({ items: [], total: 0, refreshed: true })

    await marketDataApi.refreshWarehouseCoverage({ asset_type: 'stock', timeframe: '1d' })

    expect(api.post).toHaveBeenCalledWith('/data/trust/coverage/refresh-warehouse', undefined, {
      params: { asset_type: 'stock', timeframe: '1d' },
    })
  })

  it('runPrecheck posts to the data trust precheck endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({ passed: true })

    await marketDataApi.runPrecheck({ asset_type: 'stock', symbol: '000001', timeframe: '1d' })

    expect(api.post).toHaveBeenCalledWith('/data/trust/precheck', {
      asset_type: 'stock',
      symbol: '000001',
      timeframe: '1d',
    })
  })
})
