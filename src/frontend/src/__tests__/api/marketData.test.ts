import { beforeEach, describe, expect, it, vi } from 'vitest'

import api from '@/api/index'
import {
  createMarketDataQueryFromContract,
  hasMarketDataCapabilities,
  hasMarketDataQueryBundle,
  hasMarketDataQueryContract,
  isMarketDataQueryBundleFamilyExecutable,
  isMarketDataQueryV2FallbackError,
  marketDataFamilyObservationShape,
  marketDataApi,
  type MarketDataQueryContract,
  type MarketDataQueryBundle,
  type MarketDataCapabilitiesResponse,
  type MarketDataQueryDataKind,
  type MarketDataQueryFrequency,
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

  it('reads only the authenticated server-owned market-data capability document', async () => {
    const capability: MarketDataCapabilitiesResponse = {
      version: 'market-data-capabilities-v1',
      query_v2_enabled: true,
      online_fetch_enabled: false,
      research_cache_fill_enabled: false,
      research_backtest_bridge_enabled: true,
    }
    vi.mocked(api.get).mockResolvedValue(capability)

    await marketDataApi.getCapabilities()

    expect(api.get).toHaveBeenCalledWith('/data/market-data/capabilities', {
      suppressErrorMessage: true,
      skipRetry: true,
      validateStatus: expect.any(Function),
    })
    const config = vi.mocked(api.get).mock.calls[0]?.[1]
    expect(config?.validateStatus?.(200)).toBe(true)
    expect(config?.validateStatus?.(403)).toBe(false)
    expect(config?.validateStatus?.(503)).toBe(false)
  })

  it('accepts only a complete market-data capability document', () => {
    const capability: MarketDataCapabilitiesResponse = {
      version: 'market-data-capabilities-v1',
      query_v2_enabled: true,
      online_fetch_enabled: true,
      research_cache_fill_enabled: true,
      research_backtest_bridge_enabled: true,
    }

    expect(hasMarketDataCapabilities(capability)).toBe(true)
    expect(hasMarketDataCapabilities({
      ...capability,
      research_cache_fill_enabled: 'true',
    })).toBe(false)
    expect(hasMarketDataCapabilities({
      ...capability,
      version: 'market-data-capabilities-v2',
    })).toBe(false)
    expect(hasMarketDataCapabilities({
      version: 'market-data-capabilities-v1',
      query_v2_enabled: true,
    })).toBe(false)
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
    const bundle: MarketDataQueryBundle = {
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
          frequency_semantics: 'calendar_grid',
          frequencies: ['1d'],
          field_profile_id: 'stock-valuation-v1',
          required_fields: ['pe'],
          optional_fields: ['pb'],
          dimension_fields: [],
          coverage_model: 'calendar_grid',
          source_policy_id: null,
          reason_code: 'DATA_FAMILY_UNCONFIGURED',
        },
        {
          family_id: 'stock.quote_snapshot',
          family_contract_version: 'market-data-family-v1',
          asset_type: 'stock',
          status: 'unconfigured',
          dataset_code: 'market.quote_snapshot',
          data_kind: 'quote_snapshot',
          frequency_semantics: 'snapshot',
          frequencies: ['snapshot'],
          field_profile_id: 'stock-quote-snapshot-v1',
          required_fields: ['price', 'update_time'],
          optional_fields: ['bid', 'ask'],
          dimension_fields: [],
          coverage_model: 'snapshot_freshness',
          source_policy_id: null,
          reason_code: 'DATA_FAMILY_UNCONFIGURED',
        },
        {
          family_id: 'stock.inventory',
          family_contract_version: 'market-data-family-v1',
          asset_type: 'stock',
          status: 'unconfigured',
          dataset_code: 'market.inventory',
          data_kind: 'inventory_report',
          frequency_semantics: 'reporting_period',
          frequencies: ['1d'],
          field_profile_id: 'stock-inventory-v1',
          required_fields: ['inventory_quantity'],
          optional_fields: [],
          dimension_fields: ['report_date', 'warehouse'],
          coverage_model: 'report_completeness',
          source_policy_id: null,
          reason_code: 'DATA_FAMILY_UNCONFIGURED',
        },
      ],
    }

    expect(hasMarketDataQueryBundle(bundle)).toBe(true)
    expect(marketDataFamilyObservationShape(bundle.families[1])).toBe('single_record')
    expect(marketDataFamilyObservationShape(bundle.families[2])).toBe('single_record')
    expect(marketDataFamilyObservationShape(bundle.families[3])).toBe('dimensioned_records')
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
    expect(hasMarketDataQueryBundle({
      ...bundle,
      families: [{
        ...bundle.families[2],
        frequency_semantics: 'calendar_grid',
      }],
    })).toBe(false)
    expect(hasMarketDataQueryBundle({
      ...bundle,
      families: [{
        ...bundle.families[3],
        status: 'ready',
        source_policy_id: 'market-default-v1',
        reason_code: null,
      }],
    })).toBe(false)
    expect(isMarketDataQueryBundleFamilyExecutable({
      ...bundle.families[3],
      status: 'ready',
      source_policy_id: 'market-default-v1',
      reason_code: null,
    })).toBe(false)
    expect(hasMarketDataQueryBundle({
      ...bundle,
      families: [{
        ...bundle.families[2],
        data_kind: 'valuation_snapshot',
        dataset_code: 'market.valuation_snapshot',
        status: 'ready',
        source_policy_id: 'market-default-v1',
        reason_code: null,
      }],
    })).toBe(false)
    // The browser accepts B2 wire shapes only while their explicit NO-GO
    // state remains intact. A forged ready status cannot make them selectable.
    expect(hasMarketDataQueryBundle({
      ...bundle,
      families: [{
        ...bundle.families[0],
        frequency_semantics: 'snapshot',
        frequencies: ['snapshot'],
        coverage_model: 'snapshot_freshness',
      }],
    })).toBe(false)
    expect(hasMarketDataQueryBundle({
      ...bundle,
      families: [{
        ...bundle.families[2],
        coverage_model: 'calendar_grid',
      }],
    })).toBe(false)
    expect(hasMarketDataQueryBundle({
      ...bundle,
      families: [{
        ...bundle.families[3],
        dimension_fields: [],
      }],
    })).toBe(false)
  })

  it('keeps a server-issued single-record snapshot contract representable without inferring facts', () => {
    const contract: MarketDataQueryContract = {
      version: 'market-data-v2',
      request: {
        identity: { canonical_id: 'instrument:stock:CN-SZSE:000001' },
        dataset_code: 'market.quote_snapshot',
        data_kind: 'quote_snapshot',
        frequency: 'snapshot',
        required_fields: ['price', 'update_time'],
        source_policy_id: 'market-default-v1',
        family_id: 'stock.quote_snapshot',
        family_contract_version: 'market-data-family-v1',
        mode: 'local_first',
      },
    }

    const request = createMarketDataQueryFromContract(contract, {
      start: '2026-01-01T00:00:00.000Z',
      end: '2026-01-02T00:00:00.000Z',
      mode: 'local_only',
      purpose: 'display',
      consistency: 'display',
    })

    expect(hasMarketDataQueryContract(contract)).toBe(true)
    expect(request.data_kind).toBe('quote_snapshot')
    expect(request.frequency).toBe('snapshot')
    expect(request.family_id).toBe('stock.quote_snapshot')
    expect(hasMarketDataQueryContract({
      ...contract,
      request: { ...contract.request, frequency: '1d' },
    })).toBe(false)
    expect(hasMarketDataQueryContract({
      ...contract,
      request: { ...contract.request, required_fields: ['price', 'price'] },
    })).toBe(false)
  })

  it.each([
    {
      dataKind: 'bars' as const,
      validFrequencies: ['5min', '30min', '1h', '1d', '1w', '1mo'] as const,
      invalidFrequency: 'snapshot' as const,
    },
    {
      dataKind: 'reference_series' as const,
      validFrequencies: ['5min', '30min', '1h', '1d', '1w', '1mo'] as const,
      invalidFrequency: 'snapshot' as const,
    },
    {
      dataKind: 'quote_snapshot' as const,
      validFrequencies: ['snapshot'] as const,
      invalidFrequency: '1d' as const,
    },
    {
      dataKind: 'valuation_snapshot' as const,
      validFrequencies: ['snapshot'] as const,
      invalidFrequency: '1d' as const,
    },
    {
      dataKind: 'option_chain' as const,
      validFrequencies: ['snapshot'] as const,
      invalidFrequency: '1d' as const,
    },
    {
      dataKind: 'option_risk_surface' as const,
      validFrequencies: ['snapshot'] as const,
      invalidFrequency: '1d' as const,
    },
    {
      dataKind: 'position_report' as const,
      validFrequencies: ['5min', '30min', '1h', '1d', '1w', '1mo'] as const,
      invalidFrequency: 'snapshot' as const,
    },
    {
      dataKind: 'inventory_report' as const,
      validFrequencies: ['5min', '30min', '1h', '1d', '1w', '1mo'] as const,
      invalidFrequency: 'snapshot' as const,
    },
  ])('validates the $dataKind frequency shape without asserting backend route readiness', ({
    dataKind,
    validFrequencies,
    invalidFrequency,
  }: {
    dataKind: MarketDataQueryDataKind
    validFrequencies: readonly MarketDataQueryFrequency[]
    invalidFrequency: MarketDataQueryFrequency
  }) => {
    const request = {
      identity: { canonical_id: 'instrument:stock:CN-SZSE:000001' },
      dataset_code: `market.${dataKind}`,
      data_kind: dataKind,
      frequency: validFrequencies[0],
      required_fields: ['value'],
      source_policy_id: 'market-default-v1',
      family_id: `stock.${dataKind}`,
      family_contract_version: 'market-data-family-v1' as const,
      mode: 'local_first' as const,
    }

    for (const frequency of validFrequencies) {
      expect(hasMarketDataQueryContract({
        version: 'market-data-v2',
        request: { ...request, frequency },
      })).toBe(true)
    }
    expect(hasMarketDataQueryContract({
      version: 'market-data-v2',
      request: { ...request, frequency: invalidFrequency },
    })).toBe(false)
  })

  it('validates every supported v2 wire shape while keeping unsupported ready families fail-closed', () => {
    const families: MarketDataQueryBundle['families'] = [
      {
        family_id: 'stock.bars', family_contract_version: 'market-data-family-v1', asset_type: 'stock',
        status: 'ready', dataset_code: 'market.bars', data_kind: 'bars',
        frequency_semantics: 'calendar_grid', frequencies: ['1d'], field_profile_id: 'bars-v1',
        required_fields: ['close'], optional_fields: [], dimension_fields: [],
        coverage_model: 'calendar_grid', source_policy_id: 'market-default-v1', reason_code: null,
      },
      {
        family_id: 'stock.quote', family_contract_version: 'market-data-family-v1', asset_type: 'stock',
        status: 'ready', dataset_code: 'market.quote_snapshot', data_kind: 'quote_snapshot',
        frequency_semantics: 'snapshot', frequencies: ['snapshot'], field_profile_id: 'quote-v1',
        required_fields: ['price'], optional_fields: [], dimension_fields: [],
        coverage_model: 'snapshot_freshness', source_policy_id: 'market-default-v1', reason_code: null,
      },
      {
        family_id: 'stock.valuation_snapshot', family_contract_version: 'market-data-family-v1', asset_type: 'stock',
        status: 'unconfigured', dataset_code: 'market.valuation', data_kind: 'valuation_snapshot',
        frequency_semantics: 'snapshot', frequencies: ['snapshot'], field_profile_id: 'valuation-v1',
        required_fields: ['pe'], optional_fields: [], dimension_fields: [],
        coverage_model: 'snapshot_freshness', source_policy_id: null, reason_code: 'DATA_FAMILY_UNCONFIGURED',
      },
      {
        family_id: 'stock.option_chain', family_contract_version: 'market-data-family-v1', asset_type: 'stock',
        status: 'unconfigured', dataset_code: 'market.option_chain', data_kind: 'option_chain',
        frequency_semantics: 'snapshot', frequencies: ['snapshot'], field_profile_id: 'option-chain-v1',
        required_fields: ['price'], optional_fields: [], dimension_fields: ['expiry', 'strike'],
        coverage_model: 'slice_completeness', source_policy_id: null, reason_code: 'DATA_FAMILY_UNCONFIGURED',
      },
      {
        family_id: 'stock.position', family_contract_version: 'market-data-family-v1', asset_type: 'stock',
        status: 'unconfigured', dataset_code: 'market.position', data_kind: 'position_report',
        frequency_semantics: 'reporting_period', frequencies: ['1d'], field_profile_id: 'position-v1',
        required_fields: ['net_position'], optional_fields: [], dimension_fields: ['report_date'],
        coverage_model: 'report_completeness', source_policy_id: null, reason_code: 'DATA_FAMILY_UNCONFIGURED',
      },
      {
        family_id: 'stock.reference', family_contract_version: 'market-data-family-v1', asset_type: 'stock',
        status: 'ready', dataset_code: 'market.reference', data_kind: 'reference_series',
        frequency_semantics: 'calendar_grid', frequencies: ['1d'], field_profile_id: 'reference-v1',
        required_fields: ['value'], optional_fields: [], dimension_fields: [],
        coverage_model: 'calendar_grid', source_policy_id: 'market-default-v1', reason_code: null,
      },
      {
        family_id: 'stock.inventory', family_contract_version: 'market-data-family-v1', asset_type: 'stock',
        status: 'unconfigured', dataset_code: 'market.inventory', data_kind: 'inventory_report',
        frequency_semantics: 'reporting_period', frequencies: ['1d'], field_profile_id: 'inventory-v1',
        required_fields: ['inventory_quantity'], optional_fields: [], dimension_fields: ['warehouse'],
        coverage_model: 'report_completeness', source_policy_id: null, reason_code: 'DATA_FAMILY_UNCONFIGURED',
      },
      {
        family_id: 'stock.option_surface', family_contract_version: 'market-data-family-v1', asset_type: 'stock',
        status: 'unconfigured', dataset_code: 'market.option_surface', data_kind: 'option_risk_surface',
        frequency_semantics: 'snapshot', frequencies: ['snapshot'], field_profile_id: 'option-surface-v1',
        required_fields: ['implied_volatility'], optional_fields: [], dimension_fields: ['expiry', 'delta'],
        coverage_model: 'slice_completeness', source_policy_id: null, reason_code: 'DATA_FAMILY_UNCONFIGURED',
      },
    ]
    const bundle: MarketDataQueryBundle = {
      version: 'market-data-family-bundle-v1',
      requested_asset_type: 'stock',
      families,
    }

    expect(hasMarketDataQueryBundle(bundle)).toBe(true)
    expect(families.map((family) => family.data_kind)).toEqual([
      'bars', 'quote_snapshot', 'valuation_snapshot', 'option_chain',
      'position_report', 'reference_series', 'inventory_report', 'option_risk_surface',
    ])
    expect(families.map(marketDataFamilyObservationShape)).toEqual([
      'single_record', 'single_record', 'single_record', 'dimensioned_records',
      'dimensioned_records', 'single_record', 'dimensioned_records', 'dimensioned_records',
    ])
    expect(hasMarketDataQueryBundle({
      ...bundle,
      families: [{ ...families[3], coverage_model: 'snapshot_freshness' }],
    })).toBe(false)
    expect(hasMarketDataQueryBundle({
      ...bundle,
      families: [{ ...families[4], frequency_semantics: 'calendar_grid' }],
    })).toBe(false)
    for (const family of [families[2], families[3], families[4], families[6], families[7]]) {
      expect(hasMarketDataQueryBundle({
        ...bundle,
        families: [{
          ...family,
          status: 'ready',
          source_policy_id: 'market-default-v1',
          reason_code: null,
        }],
      })).toBe(false)
      expect(isMarketDataQueryBundleFamilyExecutable({
        ...family,
        status: 'ready',
        source_policy_id: 'market-default-v1',
        reason_code: null,
      })).toBe(false)
    }
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

  it('preserves explicit null semantic axes from an FX family contract over JSON', () => {
    const contract: MarketDataQueryContract = {
      version: 'market-data-v2',
      request: {
        identity: { canonical_id: 'instrument:fx:CN-OTC:USDCNH' },
        dataset_code: 'market.bars',
        data_kind: 'bars',
        frequency: '1d',
        required_fields: ['open', 'high', 'low', 'close'],
        adjustment: 'unadjusted',
        price_basis: 'close',
        currency: null,
        unit: null,
        source_policy_id: 'market-default-v1',
        family_id: 'fx.range',
        family_contract_version: 'market-data-family-v1',
        mode: 'local_first',
      },
    }

    const request = createMarketDataQueryFromContract(contract, {
      start: '2026-01-01T00:00:00.000Z',
      end: '2026-01-02T00:00:00.000Z',
    })

    expect(request).toHaveProperty('currency', null)
    expect(request).toHaveProperty('unit', null)
    expect(JSON.parse(JSON.stringify(request))).toMatchObject({
      adjustment: 'unadjusted',
      price_basis: 'close',
      currency: null,
      unit: null,
    })
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
