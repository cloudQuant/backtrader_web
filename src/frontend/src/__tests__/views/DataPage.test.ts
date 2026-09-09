import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import DataPage from '@/views/DataPage.vue'
import { elStubs } from '@/test/stubs'
import type {
  MarketAssetType,
  MarketDataQueryBundle,
  MarketDataQueryResponse,
} from '@/api/marketData'

const apiMocks = vi.hoisted(() => ({
  getCapabilities: vi.fn(),
  lookupInstrument: vi.fn(),
  getQueryBundle: vi.fn(),
  getQueryContract: vi.fn(),
  queryLocalFirst: vi.fn(),
  listInstrumentOptions: vi.fn(),
  listCoverage: vi.fn(),
  refreshLocalCoverage: vi.fn(),
  refreshWarehouseCoverage: vi.fn(),
  listTables: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/api/marketData', () => ({
  hasMarketDataCapabilities: (value: unknown) => (
    Boolean(
      value
      && typeof value === 'object'
      && (value as { version?: unknown }).version === 'market-data-capabilities-v1'
      && typeof (value as { query_v2_enabled?: unknown }).query_v2_enabled === 'boolean'
      && typeof (value as { online_fetch_enabled?: unknown }).online_fetch_enabled === 'boolean'
      && typeof (value as { research_cache_fill_enabled?: unknown }).research_cache_fill_enabled === 'boolean'
      && typeof (value as { research_backtest_bridge_enabled?: unknown }).research_backtest_bridge_enabled === 'boolean',
    )
  ),
  hasMarketDataQueryBundle: (value: unknown) => (
    Boolean(
      value
      && typeof value === 'object'
      && (value as { version?: unknown }).version === 'market-data-family-bundle-v1'
      && (value as { requested_asset_type?: unknown }).requested_asset_type
      && Array.isArray((value as { families?: unknown }).families),
    )
  ),
  hasMarketDataQueryContract: (value: unknown) => (
    Boolean(
      value
      && typeof value === 'object'
      && (value as { version?: unknown }).version === 'market-data-v2'
      && (value as { request?: unknown }).request,
    )
  ),
  createMarketDataQueryFromContract: (
    contract: { request: Record<string, unknown> },
    options: Record<string, unknown>,
  ) => ({ ...contract.request, ...options }),
  marketDataFamilyObservationShape: (family: {
    data_kind?: unknown
    dimension_fields?: unknown
  }) => (
    (
      (Array.isArray(family.dimension_fields) && family.dimension_fields.length > 0)
      || ['option_chain', 'position_report', 'inventory_report', 'option_risk_surface']
        .includes(String(family.data_kind))
    )
      ? 'dimensioned_records'
      : 'single_record'
  ),
  isMarketDataQueryV2FallbackError: (error: { response?: { status?: unknown, data?: { details?: { code?: unknown } } } }) => (
    [404, 405, 501].includes(Number(error?.response?.status))
    || error?.response?.data?.details?.code === 'MARKET_DATA_QUERY_V2_DISABLED'
    || error?.response?.data?.details?.code === 'MARKET_DATA_QUERY_BUNDLE_UNAVAILABLE'
  ),
  marketDataApi: {
    getCapabilities: apiMocks.getCapabilities,
    listInstrumentOptions: apiMocks.listInstrumentOptions,
    lookupInstrument: apiMocks.lookupInstrument,
    getQueryBundle: apiMocks.getQueryBundle,
    getQueryContract: apiMocks.getQueryContract,
    queryLocalFirst: apiMocks.queryLocalFirst,
    listCoverage: apiMocks.listCoverage,
    refreshLocalCoverage: apiMocks.refreshLocalCoverage,
    refreshWarehouseCoverage: apiMocks.refreshWarehouseCoverage,
  },
}))

vi.mock('@/api/akshare', () => ({
  akshareTablesApi: {
    list: apiMocks.listTables,
  },
}))

const assetNames: Record<MarketAssetType, string> = {
  stock: '平安银行',
  futures: 'IM2606',
  bond: '电气转债',
  fund: '沪深300ETF',
  option: '中证1000期权主力合约',
  fx: '美元离岸人民币',
  crypto: 'BTCJPY',
}

const assetSymbols: Record<MarketAssetType, string> = {
  stock: '000001',
  futures: 'IM2606',
  bond: 'sh110074',
  fund: '510300',
  option: 'MO',
  fx: 'USDCNH',
  crypto: 'BTCJPY',
}
const MARKET_ASSET_SELECTIONS_STORAGE_KEY = 'ai_for_investor:market:asset_selections'
const LEGACY_MARKET_SELECTION_STORAGE_KEY = 'ai_for_investor:market:last_query'

function createLookupFixture(assetType: MarketAssetType) {
  const baseSnapshot = {
    data_source_table: 'akshare_data',
    price: assetType === 'crypto' ? 10000000 : 12.34,
    open: 12.1,
    high: 12.4,
    low: 12,
    volume: 1000,
    update_time: '2026-06-19T09:30:00',
  }
  const snapshots = {
    stock: {
      ...baseSnapshot,
      turnover: 186000000,
      market_cap: 320000000000,
      float_market_cap: 250000000000,
      pe: 8.1,
      pb: 0.9,
      change_pct: 0.98,
    },
    futures: {
      ...baseSnapshot,
      settle: 3250,
      previous_settle: 3220,
      open_interest: 280000,
      bid: 3251,
      ask: 3252,
    },
    bond: {
      ...baseSnapshot,
      turnover: 8200000,
      bid: 112.31,
      ask: 112.34,
      change_pct: -0.12,
    },
    fund: {
      ...baseSnapshot,
      turnover: 56000000,
      change_pct: 0.35,
    },
    option: {
      ...baseSnapshot,
      change: 0.08,
      change_pct: 2.1,
    },
    fx: {
      ...baseSnapshot,
      price: 7.2431,
      previous_close: 7.221,
      change_pct: 0.31,
      volume: null,
    },
    crypto: {
      ...baseSnapshot,
      open: null,
      change: 1250,
      change_pct: 1.8,
      market: 'CRYPTO',
    },
  }
  const cryptoRows = [
    { date: '2026-06-19', name: 'Asset Manager', volume: 2000, open_interest: 8000, change: 120 },
    { date: '2026-06-19', name: 'Leveraged Funds', volume: 1800, open_interest: 7600, change: -80 },
  ]
  const ohlcvRows = [
    {
      date: '2026-06-18',
      open: 12.1,
      high: 12.4,
      low: 12,
      close: 12.34,
      volume: 1000,
      turnover: assetType === 'stock' || assetType === 'fund' || assetType === 'bond' ? 8800000 : null,
      change_pct: 0.98,
      open_interest: assetType === 'futures' ? 275000 : null,
      settle: assetType === 'futures' ? 3230 : null,
    },
    {
      date: '2026-06-19',
      open: 12.3,
      high: 12.6,
      low: 12.2,
      close: 12.5,
      volume: 1200,
      turnover: assetType === 'stock' || assetType === 'fund' || assetType === 'bond' ? 9600000 : null,
      change_pct: 1.3,
      open_interest: assetType === 'futures' ? 280000 : null,
      settle: assetType === 'futures' ? 3250 : null,
    },
  ]

  return {
    asset_type: assetType,
    symbol: assetSymbols[assetType],
    name: assetNames[assetType],
    market: assetType === 'fx' ? 'FX' : 'CN',
    provider: 'akshare_data',
    snapshot: snapshots[assetType],
    history: {
      period: 'daily',
      total: assetType === 'crypto' ? cryptoRows.length : ohlcvRows.length,
      rows: assetType === 'crypto' ? cryptoRows : ohlcvRows,
    },
    indicators: {
      latest_close: assetType === 'crypto' ? null : 12.5,
      return_pct: assetType === 'crypto' ? null : 1.29,
      highest_close: assetType === 'crypto' ? null : 12.5,
      lowest_close: assetType === 'crypto' ? null : 12.34,
      avg_volume: assetType === 'crypto' ? 1900 : 1100,
      observation_count: 2,
    },
    warnings: [],
  }
}

function createInstrumentOptionsFixture(assetType: MarketAssetType) {
  return {
    asset_type: assetType,
    total: 2,
    items: [
      {
        asset_type: assetType,
        symbol: assetSymbols[assetType],
        name: assetNames[assetType],
        market: assetType === 'fx' ? 'FX' : assetType === 'crypto' ? 'CRYPTO' : 'CN',
        source_table: 'akshare_data',
        latest_date: '2026-06-19',
        has_snapshot: true,
        has_history: true,
        history_rows: 120,
      },
      {
        asset_type: assetType,
        symbol: `${assetSymbols[assetType]}X`,
        name: `${assetNames[assetType]}备选`,
        market: assetType === 'futures' ? 'CFFEX' : 'CN',
        source_table: 'akshare_data',
        latest_date: '2026-06-18',
        has_snapshot: true,
        has_history: false,
        history_rows: 0,
      },
    ],
  }
}

type FamilyBindingFixture = {
  family_id: string
  family_contract_version: 'market-data-family-v1'
}

function stockRealtimeFamilyBinding(): FamilyBindingFixture {
  return {
    family_id: 'stock.realtime',
    family_contract_version: 'market-data-family-v1',
  }
}

function createV2ContractFixture(
  familyBinding: FamilyBindingFixture = stockRealtimeFamilyBinding(),
) {
  return {
    version: 'market-data-v2',
    request: {
      identity: { canonical_id: 'instrument:stock:CN-SZSE:000001' },
      dataset_code: 'market.bars',
      data_kind: 'bars',
      frequency: '1d',
      required_fields: ['close'],
      adjustment: 'qfq',
      price_basis: 'close',
      currency: 'CNY',
      unit: 'share',
      source_policy_id: 'market-default-v1',
      ...familyBinding,
      mode: 'local_first',
    },
  }
}

function createV2ResponseFixture(
  familyBinding: FamilyBindingFixture = stockRealtimeFamilyBinding(),
): MarketDataQueryResponse {
  return {
    query_id: 'query-local-1',
    canonical_id: 'instrument:stock:CN-SZSE:000001',
    dataset_code: 'market.bars',
    asset_type: 'stock',
    instrument_metadata_version: 'stock-v1',
    data_kind: 'bars',
    frequency: '1d',
    source_policy_id: 'market-default-v1',
    ...familyBinding,
    knowledge_cutoff: '2026-06-19T16:00:00Z',
    identity_knowledge_cutoff: '2026-06-19T16:00:00Z',
    observations: [
      {
        revision_id: 'revision-1',
        source_snapshot_id: 'snapshot-1',
        event_at: '2026-06-19T00:00:00Z',
        available_at: '2026-06-19T15:00:00Z',
        committed_at: '2026-06-19T15:00:01Z',
        revision_number: 1,
        quality: 'pass',
        fields: { open: 12.1, high: 12.4, low: 12, close: 12.34, volume: 1000 },
      },
    ],
    next_cursor: null,
    coverage: {
      status: 'complete',
      expected_event_count: 1,
      accepted_event_count: 1,
      missing_event_count: 0,
      coverage_ratio: 1,
      gaps: [],
      rejection_counts: {},
      calendar_reason: null,
    },
    fetches: [],
    warnings: [],
    refresh_status: null,
    historical_status: null,
  }
}

function stockLiquidityFamilyBinding(): FamilyBindingFixture {
  return {
    family_id: 'stock.liquidity',
    family_contract_version: 'market-data-family-v1',
  }
}

function createStockLiquidityContractFixture() {
  return {
    version: 'market-data-v2' as const,
    request: {
      identity: { canonical_id: 'instrument:stock:CN-SZSE:000001' },
      dataset_code: 'market.liquidity',
      data_kind: 'reference_series' as const,
      frequency: '1d' as const,
      required_fields: ['volume', 'turnover', 'turnover_rate'],
      adjustment: 'none',
      price_basis: null,
      currency: 'CNY',
      unit: 'share',
      source_policy_id: 'market-default-v1',
      ...stockLiquidityFamilyBinding(),
      mode: 'local_first' as const,
    },
  }
}

function createStockLiquidityResponseFixture(): MarketDataQueryResponse {
  return {
    ...createV2ResponseFixture(stockLiquidityFamilyBinding()),
    dataset_code: 'market.liquidity',
    data_kind: 'reference_series',
    observations: [
      {
        revision_id: 'liquidity-revision-1',
        source_snapshot_id: 'liquidity-snapshot-1',
        event_at: '2026-06-18T00:00:00Z',
        available_at: '2026-06-18T15:00:00Z',
        committed_at: '2026-06-18T15:00:01Z',
        revision_number: 1,
        quality: 'pass',
        fields: {
          volume: 1000,
          turnover: 8800000,
          turnover_rate: 1.1,
          close: 9999,
        },
      },
      {
        revision_id: 'liquidity-revision-failed',
        source_snapshot_id: 'liquidity-snapshot-failed',
        event_at: '2026-06-19T00:00:00Z',
        available_at: '2026-06-19T15:00:00Z',
        committed_at: '2026-06-19T15:00:01Z',
        revision_number: 1,
        quality: 'failed',
        fields: {
          volume: 9999,
          turnover: 9999999,
          turnover_rate: 9.9,
          close: 9999,
        },
      },
      {
        revision_id: 'liquidity-revision-2',
        source_snapshot_id: 'liquidity-snapshot-2',
        event_at: '2026-06-20T00:00:00Z',
        available_at: '2026-06-20T15:00:00Z',
        committed_at: '2026-06-20T15:00:01Z',
        revision_number: 1,
        quality: 'pass',
        fields: {
          volume: 1200,
          turnover: 9600000,
          turnover_rate: 1.3,
          close: 10000,
        },
      },
    ],
  }
}

function configureReadyReferenceSeriesFamily(
  bundle: MarketDataQueryBundle,
  familyId: string,
  datasetCode: string,
  requiredFields: string[],
) {
  const family = bundle.families.find((candidate) => candidate.family_id === familyId)
  if (!family) throw new Error(`missing fixture family: ${familyId}`)
  family.status = 'ready'
  family.dataset_code = datasetCode
  family.data_kind = 'reference_series'
  family.frequency_semantics = 'calendar_grid'
  family.frequencies = ['1d']
  family.required_fields = requiredFields
  family.optional_fields = []
  family.dimension_fields = []
  family.coverage_model = 'calendar_grid'
  family.source_policy_id = 'market-default-v1'
  family.reason_code = null
}

function createStockLiquidityBundleFixture(): MarketDataQueryBundle {
  const bundle = createQueryBundleFixture('stock', {
    'stock.realtime': 'ready',
    'stock.liquidity': 'ready',
  })
  configureReadyReferenceSeriesFamily(
    bundle,
    'stock.liquidity',
    'market.liquidity',
    ['volume', 'turnover', 'turnover_rate'],
  )
  return bundle
}

function createDeferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

const dataFamilyIdsByAsset: Record<MarketAssetType, string[]> = {
  stock: ['stock.realtime', 'stock.valuation', 'stock.liquidity'],
  futures: ['futures.realtime', 'futures.settlement', 'futures.inventory'],
  bond: ['bond.realtime', 'bond.orderbook', 'bond.fixed_income'],
  fund: ['fund.realtime', 'fund.liquidity', 'fund.nav'],
  option: ['option.realtime', 'option.derivative', 'option.risk_surface'],
  fx: ['fx.realtime', 'fx.macro_fx', 'fx.range'],
  crypto: ['crypto.realtime', 'crypto.cme_position', 'crypto.range'],
}

type DataFamilyBundleStatus = 'ready' | 'unconfigured' | 'not_applicable'

function createQueryBundleFixture(
  assetType: MarketAssetType,
  statuses: Partial<Record<string, DataFamilyBundleStatus>> = {},
): MarketDataQueryBundle {
  return {
    version: 'market-data-family-bundle-v1',
    requested_asset_type: assetType,
    families: dataFamilyIdsByAsset[assetType].map((familyId) => {
      const status = statuses[familyId] || 'unconfigured'
      const ready = status === 'ready'
      return {
        family_id: familyId,
        family_contract_version: 'market-data-family-v1',
        asset_type: assetType,
        status,
        dataset_code: ready ? 'market.bars' : `market.${familyId.replace('.', '_')}`,
        data_kind: ready ? 'bars' : 'reference_series',
        frequency_semantics: 'calendar_grid',
        frequencies: ready && familyId === 'stock.realtime' ? ['1d', '1w', '1mo'] : ['1d'],
        field_profile_id: `${familyId.replace('.', '-')}-v1`,
        required_fields: ['close'],
        optional_fields: ready && familyId === 'stock.realtime'
          ? ['open', 'high', 'low', 'volume', 'turnover', 'change_pct', 'turnover_rate']
          : ['volume'],
        dimension_fields: [],
        coverage_model: 'calendar_grid',
        source_policy_id: ready ? 'market-default-v1' : null,
        reason_code: ready ? null : status === 'not_applicable'
          ? 'DATA_FAMILY_NOT_APPLICABLE'
          : 'DATA_FAMILY_UNCONFIGURED',
      }
    }),
  }
}

describe('DataPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Existing v2-path cases opt into the page rollout explicitly. Individual
    // default-off cases override this value and prove no v2 request escapes.
    vi.stubEnv('VITE_MARKET_DATA_QUERY_V2_ENABLED', 'true')
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'false')
    window.localStorage.removeItem(MARKET_ASSET_SELECTIONS_STORAGE_KEY)
    window.localStorage.removeItem(LEGACY_MARKET_SELECTION_STORAGE_KEY)
    apiMocks.getCapabilities.mockResolvedValue({
      version: 'market-data-capabilities-v1',
      query_v2_enabled: true,
      online_fetch_enabled: false,
      research_cache_fill_enabled: false,
      research_backtest_bridge_enabled: false,
    })
    apiMocks.lookupInstrument.mockImplementation(({ asset_type }: { asset_type: MarketAssetType }) => (
      Promise.resolve(createLookupFixture(asset_type))
    ))
    apiMocks.getQueryBundle.mockRejectedValue({ response: { status: 404 } })
    apiMocks.getQueryContract.mockRejectedValue({ response: { status: 404 } })
    apiMocks.queryLocalFirst.mockResolvedValue(undefined)
    apiMocks.listInstrumentOptions.mockImplementation(
      ({ asset_type }: { asset_type: MarketAssetType }) => Promise.resolve(createInstrumentOptionsFixture(asset_type)),
    )
    apiMocks.listCoverage.mockResolvedValue({
      total: 1,
      refreshed: false,
      items: [
        {
          id: 'coverage-1',
          asset_type: 'stock',
          symbol: '000001',
          timeframe: '1d',
          provider: 'akshare_data',
          start_date: '2026-01-01',
          end_date: '2026-06-19',
          row_count: 120,
          missing_count: 0,
          missing_ratio: 0,
          latest_bar_time: '2026-06-19',
          quality_status: 'pass',
          source_path: 'data/datas/000001.csv',
          updated_at: '2026-06-19T09:30:00',
        },
      ],
    })
    apiMocks.refreshLocalCoverage.mockResolvedValue({
      total: 0,
      refreshed: true,
      items: [],
    })
    apiMocks.refreshWarehouseCoverage.mockResolvedValue({
      total: 0,
      refreshed: true,
      items: [],
    })
    apiMocks.listTables.mockResolvedValue({
      items: [
        {
          id: 1,
          table_name: 'stock_zh_a_hist_000001',
          table_comment: 'A股历史行情',
          category: 'stocks',
          script_id: 'stock_zh_a_hist',
          row_count: 1200,
          last_update_time: '2026-06-19T09:30:00',
          last_update_status: 'success',
          data_start_date: '2026-01-01',
          data_end_date: '2026-06-19',
          symbol_raw: '000001',
          symbol_normalized: '000001',
          market: 'CN',
          asset_type: 'stock',
          metadata: {},
          created_at: '2026-06-19T09:30:00',
          updated_at: '2026-06-19T09:30:00',
        },
      ],
      total: 1,
      page: 1,
      page_size: 8,
    })
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  async function mountPage(path = '/data/market') {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/data/market', component: DataPage }],
    })
    await router.push(path)
    await router.isReady()
    const wrapper = mount(DataPage, {
      global: {
        plugins: [router],
        stubs: elStubs,
      },
    })
    await flushPromises()
    // Capability resolution adds one asynchronous control-plane stage before
    // an optional family-bundle request. Wait through that stage so each page
    // assertion observes the settled request path rather than a mid-flight
    // loading state.
    await flushPromises()
    return wrapper
  }

  it('keeps the complete v2 page path off when the server capability is disabled', async () => {
    // A browser build flag must never claim the receipt-backed path is live
    // while the authenticated server capability says it is disabled.
    apiMocks.getCapabilities.mockResolvedValue({
      version: 'market-data-capabilities-v1',
      query_v2_enabled: false,
      online_fetch_enabled: false,
      research_cache_fill_enabled: false,
      research_backtest_bridge_enabled: false,
    })

    const wrapper = await mountPage()

    expect(apiMocks.getQueryBundle).not.toHaveBeenCalled()
    expect(apiMocks.getQueryContract).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).toHaveBeenCalledWith(expect.objectContaining({
      asset_type: 'stock',
      symbol: '000001',
      refresh_online: false,
    }))
    expect((wrapper.vm as any).marketDataPlatformStatus.path).toBe('legacy')
    expect((wrapper.vm as any).marketDataPlatformStatus).toMatchObject({
      canonicalId: null,
      datasetCode: null,
      sourcePolicyId: null,
      instrumentMetadataVersion: null,
    })
    expect(wrapper.find('[data-test="market-data-platform-provenance"]').exists()).toBe(false)
  })

  it('uses the server capability even when the browser rollout variable is stale', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_V2_ENABLED', 'false')
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture())
    apiMocks.queryLocalFirst.mockResolvedValue(createV2ResponseFixture())

    await mountPage()

    expect(apiMocks.getCapabilities).toHaveBeenCalledTimes(1)
    expect(apiMocks.getQueryContract).toHaveBeenCalledTimes(1)
    expect(apiMocks.queryLocalFirst).toHaveBeenCalledTimes(1)
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
  })

  it('renders only public v2 response provenance identifiers in the market status', async () => {
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture())
    apiMocks.queryLocalFirst.mockResolvedValue({
      ...createV2ResponseFixture(),
      query_id: 'internal-query-receipt',
      knowledge_cutoff: '2026-06-19T16:00:00Z',
    })

    const wrapper = await mountPage()
    const provenance = wrapper.find('[data-test="market-data-platform-provenance"]')

    expect(provenance.exists()).toBe(true)
    expect(provenance.text()).toContain('规范标识：instrument:stock:CN-SZSE:000001')
    expect(provenance.text()).toContain('数据集：market.bars')
    expect(provenance.text()).toContain('数据族：stock.realtime')
    expect(provenance.text()).toContain('来源策略：market-default-v1')
    expect(provenance.text()).toContain('元数据版本：stock-v1')
    expect(provenance.text()).not.toContain('internal-query-receipt')
    expect((wrapper.vm as any).marketDataPlatformProvenance).toEqual([
      { label: '规范标识', value: 'instrument:stock:CN-SZSE:000001' },
      { label: '数据集', value: 'market.bars' },
      { label: '数据族', value: 'stock.realtime' },
      { label: '来源策略', value: 'market-default-v1' },
      { label: '元数据版本', value: 'stock-v1' },
    ])
  })

  it('keeps a schema-valid public canonical identity visible without accepting controls', async () => {
    const canonicalId = `instrument:stock:CN-SZSE:${'x'.repeat(180)}+class-A`
    const contract = createV2ContractFixture()
    contract.request.identity.canonical_id = canonicalId
    contract.request.dataset_code = 'market.bars\u0000internal'
    apiMocks.getQueryContract.mockResolvedValue(contract)
    apiMocks.queryLocalFirst.mockResolvedValue({
      ...createV2ResponseFixture(),
      canonical_id: canonicalId,
      dataset_code: 'market.bars\u0000internal',
    })

    const wrapper = await mountPage()

    expect((wrapper.vm as any).marketDataPlatformProvenance).toEqual([
      {
        label: '规范标识',
        value: canonicalId,
      },
      { label: '数据族', value: 'stock.realtime' },
      { label: '来源策略', value: 'market-default-v1' },
      { label: '元数据版本', value: 'stock-v1' },
    ])
  })

  it('does not fall back to legacy data after a v2 contract probe denies data-read access', async () => {
    apiMocks.getQueryContract.mockRejectedValue({
      response: { status: 403, data: { details: { code: 'MARKET_DATA_READ_ENTITLEMENT_DENIED' } } },
    })

    const wrapper = await mountPage()

    expect(apiMocks.getQueryContract).toHaveBeenCalledTimes(1)
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result).toBeNull()
    expect((wrapper.vm as any).marketDataPlatformStatus.path).toBe('error')
  })

  it('uses a single snapshot column on compact viewports', async () => {
    const originalWidth = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 700 })

    try {
      const wrapper = await mountPage()

      expect((wrapper.vm as any).snapshotDescriptionColumns).toBe(1)
      wrapper.unmount()
    } finally {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: originalWidth })
    }
  })

  it('renders snapshot values in self-contained metric cards', async () => {
    const wrapper = await mountPage()

    expect(wrapper.find('[data-test="market-snapshot-grid"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="market-snapshot-item"]').length).toBeGreaterThan(6)
  })

  it('orders historical table rows from newest to oldest without changing chart source order', async () => {
    const wrapper = await mountPage()

    expect((wrapper.vm as any).displayHistoryRows.map((row: { date: string }) => row.date)).toEqual([
      '2026-06-19',
      '2026-06-18',
    ])
    expect((wrapper.vm as any).historyRows.map((row: { date: string }) => row.date)).toEqual([
      '2026-06-18',
      '2026-06-19',
    ])
  })

  it('renders one historical data tab per supported asset type', async () => {
    const wrapper = await mountPage()

    expect(wrapper.text()).toContain('历史数据')
    expect(wrapper.text()).toContain('股票')
    expect(wrapper.text()).toContain('期货')
    expect(wrapper.text()).toContain('债券')
    expect(wrapper.text()).toContain('基金')
    expect(wrapper.text()).toContain('期权')
    expect(wrapper.text()).toContain('外汇')
    expect(wrapper.text()).toContain('数字货币')
    expect(wrapper.find('.options-card').exists()).toBe(false)
    expect(apiMocks.lookupInstrument).toHaveBeenCalledWith({
      asset_type: 'stock',
      symbol: '000001',
      period: 'daily',
      start_date: expect.any(String),
      end_date: expect.any(String),
      market: undefined,
      refresh_online: false,
    })
    expect((wrapper.vm as any).result.name).toBe('平安银行')
    expect((wrapper.vm as any).historyRows).toHaveLength(2)
    expect(wrapper.text()).toContain('+1.29%')
    expect(wrapper.find('[data-test="market-main-chart"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="market-instrument-overview"]').text()).toContain('平安银行')
    expect(wrapper.find('[data-test="market-instrument-select"]').exists()).toBe(true)
    expect(apiMocks.listInstrumentOptions).toHaveBeenCalledWith({
      asset_type: 'stock',
      search: '000001',
      limit: 80,
    })
    expect((wrapper.vm as any).instrumentOptions).toHaveLength(2)
    expect(apiMocks.listTables).toHaveBeenCalled()
  })

  it('rejects a legacy bridge contract whose product family differs from the current page', async () => {
    const mismatchedContract = createV2ContractFixture({
      family_id: 'stock.valuation',
      family_contract_version: 'market-data-family-v1',
    })
    apiMocks.lookupInstrument.mockResolvedValue({
      ...createLookupFixture('stock'),
      query_contract: mismatchedContract,
      query_contract_symbol: '000001',
      query_contract_canonical_id: mismatchedContract.request.identity.canonical_id,
    })

    const wrapper = await mountPage()

    expect(apiMocks.getQueryContract).toHaveBeenCalledTimes(1)
    expect(apiMocks.lookupInstrument).toHaveBeenCalledTimes(1)
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result).toBeNull()
    expect((wrapper.vm as any).marketDataPlatformStatus.path).toBe('error')
  })

  it('rejects a legacy bridge contract without an exact canonical-identity echo', async () => {
    const contract = createV2ContractFixture()
    apiMocks.lookupInstrument.mockResolvedValue({
      ...createLookupFixture('stock'),
      query_contract: contract,
      query_contract_symbol: '000001',
      query_contract_canonical_id: 'instrument:stock:CN-SZSE:000002',
    })

    const wrapper = await mountPage()

    expect(apiMocks.getQueryContract).toHaveBeenCalledTimes(1)
    expect(apiMocks.lookupInstrument).toHaveBeenCalledTimes(1)
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result).toBeNull()
    expect((wrapper.vm as any).marketDataPlatformStatus.path).toBe('error')
  })

  it('does not reuse a v2 contract across case-distinct exact market symbols', async () => {
    apiMocks.getQueryContract.mockImplementation(({ symbol }: { symbol: string }) => {
      const contract = createV2ContractFixture()
      contract.request.identity.canonical_id = `instrument:stock:CN-SZSE:${symbol}`
      return Promise.resolve(contract)
    })
    apiMocks.queryLocalFirst.mockImplementation((request: { identity: { canonical_id: string } }) => (
      Promise.resolve({
        ...createV2ResponseFixture(),
        canonical_id: request.identity.canonical_id,
      })
    ))

    const wrapper = await mountPage()
    apiMocks.getQueryContract.mockClear()
    apiMocks.queryLocalFirst.mockClear()
    const vm = wrapper.vm as any

    vm.form.symbol = 'rb0'
    await vm.lookupInstrument()
    await flushPromises()
    vm.form.symbol = 'RB0'
    await vm.lookupInstrument()
    await flushPromises()

    expect(apiMocks.getQueryContract).toHaveBeenNthCalledWith(1, {
      asset_type: 'stock',
      symbol: 'rb0',
      period: 'daily',
      family_id: 'stock.realtime',
    })
    expect(apiMocks.getQueryContract).toHaveBeenNthCalledWith(2, {
      asset_type: 'stock',
      symbol: 'RB0',
      period: 'daily',
      family_id: 'stock.realtime',
    })
    expect(apiMocks.queryLocalFirst).toHaveBeenNthCalledWith(2, expect.objectContaining({
      identity: { canonical_id: 'instrument:stock:CN-SZSE:RB0' },
    }), expect.any(Object))
  })

  it('uses a server-proven contract for the first local-first query without legacy lookup', async () => {
    apiMocks.getQueryContract.mockResolvedValue({
      version: 'market-data-v2',
      request: {
        identity: { canonical_id: 'instrument:stock:CN-SZSE:000001' },
        dataset_code: 'market.bars',
        data_kind: 'bars',
        frequency: '1d',
        required_fields: ['close'],
        adjustment: 'qfq',
        price_basis: 'close',
        currency: 'CNY',
        unit: 'share',
        source_policy_id: 'market-default-v1',
        family_id: 'stock.realtime',
        family_contract_version: 'market-data-family-v1',
        mode: 'local_first',
      },
    })
    apiMocks.queryLocalFirst.mockResolvedValue({
      query_id: 'query-local-1',
      canonical_id: 'instrument:stock:CN-SZSE:000001',
      dataset_code: 'market.bars',
      asset_type: 'stock',
      instrument_metadata_version: 'stock-v1',
      data_kind: 'bars',
      frequency: '1d',
      source_policy_id: 'market-default-v1',
      family_id: 'stock.realtime',
      family_contract_version: 'market-data-family-v1',
      knowledge_cutoff: '2026-06-19T16:00:00Z',
      identity_knowledge_cutoff: '2026-06-19T16:00:00Z',
      observations: [
        {
          revision_id: 'revision-1',
          source_snapshot_id: 'snapshot-1',
          event_at: '2026-06-19T00:00:00Z',
          available_at: '2026-06-19T15:00:00Z',
          committed_at: '2026-06-19T15:00:01Z',
          revision_number: 1,
          quality: 'pass',
          fields: { open: 12.1, high: 12.4, low: 12, close: 12.34, volume: 1000 },
        },
      ],
      next_cursor: null,
      coverage: {
        status: 'complete',
        expected_event_count: 1,
        accepted_event_count: 1,
        missing_event_count: 0,
        coverage_ratio: 1,
        gaps: [],
        rejection_counts: {},
        calendar_reason: null,
      },
      fetches: [],
      warnings: [],
      refresh_status: null,
      historical_status: null,
    })

    const wrapper = await mountPage()

    expect(apiMocks.getQueryBundle).toHaveBeenCalledWith({ asset_type: 'stock' })
    expect(apiMocks.getQueryContract).toHaveBeenCalledWith({
      asset_type: 'stock',
      symbol: '000001',
      period: 'daily',
      family_id: 'stock.realtime',
    })
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).toHaveBeenCalledWith(expect.objectContaining({
      identity: { canonical_id: 'instrument:stock:CN-SZSE:000001' },
      dataset_code: 'market.bars',
      family_id: 'stock.realtime',
      family_contract_version: 'market-data-family-v1',
      mode: 'local_first',
      purpose: 'display',
      consistency: 'display',
    }), expect.objectContaining({ suppressErrorMessage: true }))
    expect((wrapper.vm as any).result.history.rows).toHaveLength(1)
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('本地优先')
  })

  it('fails closed when the unbundled crypto realtime family is unconfigured', async () => {
    const wrapper = await mountPage()
    apiMocks.getQueryBundle.mockClear()
    apiMocks.getQueryContract.mockClear()
    apiMocks.queryLocalFirst.mockClear()
    apiMocks.lookupInstrument.mockClear()
    apiMocks.getQueryContract.mockRejectedValue({
      response: { status: 422, data: { details: { code: 'DATA_FAMILY_UNCONFIGURED' } } },
    })

    const cryptoTab = wrapper.findAll('.asset-tab').find((button) => button.text().includes('数字货币'))
    await cryptoTab?.trigger('click')
    await flushPromises()

    expect(apiMocks.getQueryBundle).toHaveBeenCalledWith({ asset_type: 'crypto' })
    expect(apiMocks.getQueryContract).toHaveBeenCalledWith({
      asset_type: 'crypto',
      symbol: 'BTCJPY',
      period: 'daily',
      family_id: 'crypto.realtime',
    })
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result).toBeNull()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据平台查询失败')
  })

  it('fails closed when a pass v2 bar omits a contract-required field', async () => {
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture())
    const response = createV2ResponseFixture()
    const validObservation = response.observations[0]
    response.observations = [
      validObservation,
      {
        ...validObservation,
        revision_id: 'revision-non-pass',
        quality: 'failed',
        fields: { ...validObservation.fields, close: 99 },
      },
      {
        ...validObservation,
        revision_id: 'revision-placeholder',
        quality: 'pass',
        fields: { ...validObservation.fields, close: '--' },
      },
    ]
    apiMocks.queryLocalFirst.mockResolvedValue(response)

    const wrapper = await mountPage()

    expect((wrapper.vm as any).result).toBeNull()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据平台查询失败')
    expect(() => (wrapper.vm as any).ohlcTuple({
      open: 12,
      high: 13,
      low: 11,
      close: '--',
    })).toThrow('MARKET_DATA_OHLC_INVALID')
  })

  it('uses a server-advertised family bundle even when the browser bundle variable is stale', async () => {
    // The server capability owns this control plane. A stale browser build
    // must not suppress a bundle that the authenticated server supplies.
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'false')
    apiMocks.getQueryBundle.mockResolvedValue(createQueryBundleFixture('stock', {
      'stock.realtime': 'ready',
      'stock.valuation': 'unconfigured',
      'stock.liquidity': 'not_applicable',
    }))
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture(stockRealtimeFamilyBinding()))
    apiMocks.queryLocalFirst.mockResolvedValue(createV2ResponseFixture(stockRealtimeFamilyBinding()))

    const wrapper = await mountPage()
    const families = (wrapper.vm as any).assetDataFamilies

    expect(apiMocks.getQueryBundle).toHaveBeenCalledWith({ asset_type: 'stock' })
    expect(apiMocks.getQueryContract).toHaveBeenCalledWith({
      asset_type: 'stock',
      symbol: '000001',
      period: 'daily',
      family_id: 'stock.realtime',
    })
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).toHaveBeenCalledWith(expect.objectContaining({
      family_id: 'stock.realtime',
      family_contract_version: 'market-data-family-v1',
    }), expect.objectContaining({ suppressErrorMessage: true }))
    expect(families.map((family: { label: string, statusLabel: string }) => [family.label, family.statusLabel])).toEqual([
      ['日线/周线/月线 K线兼容数据（仅声明字段）', '已配置'],
      ['估值指标', '未配置 · DATA_FAMILY_UNCONFIGURED'],
      ['流动性', '不适用 · DATA_FAMILY_NOT_APPLICABLE'],
    ])
    expect(families[0].description).toContain('market.bars')
    expect(families[0].description).toContain('服务端声明字段')
    const realtimeFamilyCard = wrapper.findAll('.data-family-card')[0]
    expect(realtimeFamilyCard?.text()).toContain('日线/周线/月线 K线兼容数据（仅声明字段）')
    expect(realtimeFamilyCard?.text()).not.toContain('实时行情')
    expect(families[0].fields.map((field: { name: string }) => field.name)).toEqual([
      'close', 'open', 'high', 'low', 'volume', 'turnover', 'change_pct', 'turnover_rate',
    ])
    expect(families[0].fields.map((field: { name: string }) => field.name)).not.toContain('price')
    expect(families[0].fields.map((field: { name: string }) => field.name)).not.toContain('bid')
    expect(families[0].fields.map((field: { name: string }) => field.name)).not.toContain('ask')
    expect(families[1].fields.every((field: { present: boolean }) => !field.present)).toBe(true)
    expect(families[2].fields.every((field: { present: boolean }) => !field.present)).toBe(true)
  })

  it('renders all seven asset tabs as unconfigured from a valid bundle without a legacy lookup', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockImplementation(({ asset_type }: { asset_type: MarketAssetType }) => (
      Promise.resolve(createQueryBundleFixture(asset_type))
    ))

    const wrapper = await mountPage()
    for (const assetType of Object.keys(dataFamilyIdsByAsset) as MarketAssetType[]) {
      if ((wrapper.vm as any).form.asset_type !== assetType) {
        ;(wrapper.vm as any).setAssetType(assetType)
        await flushPromises()
      }
      const families = (wrapper.vm as any).assetDataFamilies
      expect(families).toHaveLength(dataFamilyIdsByAsset[assetType].length)
      expect(families.every((family: { statusLabel: string }) => (
        family.statusLabel === '未配置 · DATA_FAMILY_UNCONFIGURED'
      ))).toBe(true)
    }

    expect(apiMocks.getQueryContract).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据族未配置')
  })

  it('does not select a different ready family when the asset realtime family is unconfigured', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createQueryBundleFixture('stock', {
      // This must not become executable merely because it is ready before the
      // designated stock.realtime family in a malformed or future bundle.
      'stock.valuation': 'ready',
    }))

    const wrapper = await mountPage()

    expect(apiMocks.getQueryContract).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result?.query_contract).toBeNull()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据族未配置')
  })

  it('uses an explicitly selected ready reference series contract and renders only its declared fields', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createStockLiquidityBundleFixture())
    apiMocks.getQueryContract.mockImplementation(({ family_id }: { family_id: string }) => (
      Promise.resolve(
        family_id === 'stock.liquidity'
          ? createStockLiquidityContractFixture()
          : createV2ContractFixture(stockRealtimeFamilyBinding()),
      )
    ))
    apiMocks.queryLocalFirst.mockImplementation(({ family_id }: { family_id: string }) => (
      Promise.resolve(
        family_id === 'stock.liquidity'
          ? createStockLiquidityResponseFixture()
          : createV2ResponseFixture(stockRealtimeFamilyBinding()),
      )
    ))

    const wrapper = await mountPage()
    const vm = wrapper.vm as any
    apiMocks.getQueryContract.mockClear()
    apiMocks.queryLocalFirst.mockClear()
    apiMocks.lookupInstrument.mockClear()

    expect(vm.selectedFamilyId).toBe('stock.realtime')
    expect(vm.selectableDataFamilies).toEqual([
      expect.objectContaining({ value: 'stock.realtime' }),
      expect.objectContaining({ value: 'stock.liquidity' }),
    ])

    vm.selectDataFamily('stock.liquidity')
    await flushPromises()
    expect(vm.selectedFamilyId).toBe('stock.liquidity')
    expect(vm.result).toBeNull()

    await vm.lookupInstrument()
    await flushPromises()

    expect(apiMocks.getQueryContract).toHaveBeenCalledWith({
      asset_type: 'stock',
      symbol: '000001',
      period: 'daily',
      family_id: 'stock.liquidity',
    })
    expect(apiMocks.queryLocalFirst).toHaveBeenCalledWith(expect.objectContaining({
      dataset_code: 'market.liquidity',
      data_kind: 'reference_series',
      family_id: 'stock.liquidity',
      family_contract_version: 'market-data-family-v1',
      required_fields: ['volume', 'turnover', 'turnover_rate'],
    }), expect.objectContaining({ suppressErrorMessage: true }))
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(vm.marketDataPlatformStatus.familyId).toBe('stock.liquidity')
    expect(wrapper.find('[data-test="market-data-platform-provenance"]').text())
      .toContain('数据族：stock.liquidity')
    expect(vm.referenceSeriesRows).toEqual([
      { date: '2026-06-20', volume: 1200, turnover: 9600000, turnover_rate: 1.3 },
      { date: '2026-06-18', volume: 1000, turnover: 8800000, turnover_rate: 1.1 },
    ])
    expect(vm.result.snapshot.price).toBeUndefined()
    expect(vm.result.snapshot.close).toBeUndefined()
    expect(vm.chartCanRender).toBe(false)
    expect(wrapper.find('[data-test="market-reference-series-table"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="market-reference-series-family"]').text()).toContain('stock.liquidity')
    expect(wrapper.find('.market-chart-card').exists()).toBe(false)

    const families = vm.assetDataFamilies
    const liquidity = families.find((family: { familyId: string }) => family.familyId === 'stock.liquidity')
    const realtime = families.find((family: { familyId: string }) => family.familyId === 'stock.realtime')
    expect(liquidity).toEqual(expect.objectContaining({
      readState: 'facts_loaded',
      readStatusLabel: '已执行受约束事实读取',
    }))
    expect(liquidity.fields).toEqual([
      expect.objectContaining({ name: 'volume', present: true }),
      expect.objectContaining({ name: 'turnover', present: true }),
      expect.objectContaining({ name: 'turnover_rate', present: true }),
    ])
    expect(realtime).toEqual(expect.objectContaining({ readState: 'bars_query_available' }))

    vm.selectDataFamily('stock.realtime')
    await flushPromises()
    expect(vm.result).toBeNull()
    expect(vm.referenceSeriesResult).toBeNull()
    expect(vm.chartCanRender).toBe(false)

    vm.applyAssetType('fund', false)
    expect(vm.selectedFamilyId).toBe('fund.realtime')
    expect(vm.referenceSeriesResult).toBeNull()
  })

  it('clears prior family facts from the select model update before a new family can be queried', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createStockLiquidityBundleFixture())
    apiMocks.getQueryContract.mockImplementation(({ family_id }: { family_id: string }) => (
      Promise.resolve(
        family_id === 'stock.liquidity'
          ? createStockLiquidityContractFixture()
          : createV2ContractFixture(stockRealtimeFamilyBinding()),
      )
    ))
    apiMocks.queryLocalFirst.mockImplementation(({ family_id }: { family_id: string }) => (
      Promise.resolve(
        family_id === 'stock.liquidity'
          ? createStockLiquidityResponseFixture()
          : createV2ResponseFixture(stockRealtimeFamilyBinding()),
      )
    ))

    const wrapper = await mountPage()
    const vm = wrapper.vm as any
    expect(vm.selectedFamilyId).toBe('stock.realtime')
    expect(vm.result).not.toBeNull()

    const familySelect = wrapper.findComponent('[data-test="market-data-family-select"]') as any
    expect(familySelect.exists()).toBe(true)
    familySelect.vm.$emit('update:modelValue', 'stock.liquidity')
    await flushPromises()

    expect(vm.selectedFamilyId).toBe('stock.liquidity')
    expect(vm.result).toBeNull()
    expect(vm.referenceSeriesResult).toBeNull()
    expect(vm.chartCanRender).toBe(false)
  })

  it('fails closed when the selected reference series contract does not match its bundle declaration', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createStockLiquidityBundleFixture())
    apiMocks.getQueryContract.mockImplementation(({ family_id }: { family_id: string }) => (
      Promise.resolve(
        family_id === 'stock.liquidity'
          ? createV2ContractFixture(stockLiquidityFamilyBinding())
          : createV2ContractFixture(stockRealtimeFamilyBinding()),
      )
    ))
    apiMocks.queryLocalFirst.mockImplementation(({ family_id }: { family_id: string }) => (
      Promise.resolve(
        family_id === 'stock.liquidity'
          ? createStockLiquidityResponseFixture()
          : createV2ResponseFixture(stockRealtimeFamilyBinding()),
      )
    ))

    const wrapper = await mountPage()
    const vm = wrapper.vm as any
    apiMocks.getQueryContract.mockClear()
    apiMocks.queryLocalFirst.mockClear()
    apiMocks.lookupInstrument.mockClear()
    vm.selectDataFamily('stock.liquidity')

    await vm.lookupInstrument()
    await flushPromises()

    expect(apiMocks.getQueryContract).toHaveBeenCalledWith(expect.objectContaining({
      family_id: 'stock.liquidity',
    }))
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(vm.result).toBeNull()
    expect(vm.referenceSeriesResult).toBeNull()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据平台查询失败')
  })

  it('fails closed when a reference response omits a contract-required field', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createStockLiquidityBundleFixture())
    apiMocks.getQueryContract.mockImplementation(({ family_id }: { family_id: string }) => (
      Promise.resolve(
        family_id === 'stock.liquidity'
          ? createStockLiquidityContractFixture()
          : createV2ContractFixture(stockRealtimeFamilyBinding()),
      )
    ))
    apiMocks.queryLocalFirst.mockImplementation(({ family_id }: { family_id: string }) => (
      Promise.resolve(
        family_id === 'stock.liquidity'
          ? createStockLiquidityResponseFixture()
          : createV2ResponseFixture(stockRealtimeFamilyBinding()),
      )
    ))

    const wrapper = await mountPage()
    const vm = wrapper.vm as any
    const malformedResponse = createStockLiquidityResponseFixture()
    malformedResponse.observations[2] = {
      ...malformedResponse.observations[2],
      fields: { volume: 1200, turnover: 9600000 },
    }
    apiMocks.queryLocalFirst.mockImplementation(({ family_id }: { family_id: string }) => (
      Promise.resolve(
        family_id === 'stock.liquidity'
          ? malformedResponse
          : createV2ResponseFixture(stockRealtimeFamilyBinding()),
      )
    ))
    apiMocks.lookupInstrument.mockClear()
    vm.selectDataFamily('stock.liquidity')

    await vm.lookupInstrument()
    await flushPromises()

    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(vm.result).toBeNull()
    expect(vm.referenceSeriesResult).toBeNull()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据平台查询失败')
  })

  it('invalidates an in-flight family response when the selected family changes', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createStockLiquidityBundleFixture())
    apiMocks.getQueryContract.mockImplementation(({ family_id }: { family_id: string }) => (
      Promise.resolve(
        family_id === 'stock.liquidity'
          ? createStockLiquidityContractFixture()
          : createV2ContractFixture(stockRealtimeFamilyBinding()),
      )
    ))
    apiMocks.queryLocalFirst.mockResolvedValue(createV2ResponseFixture(stockRealtimeFamilyBinding()))

    const wrapper = await mountPage()
    const vm = wrapper.vm as any
    const pendingRealtimeResponse = createDeferred<MarketDataQueryResponse>()
    apiMocks.queryLocalFirst.mockImplementation(({ family_id }: { family_id: string }) => (
      family_id === 'stock.realtime'
        ? pendingRealtimeResponse.promise
        : Promise.resolve(createStockLiquidityResponseFixture())
    ))
    apiMocks.lookupInstrument.mockClear()

    const staleLookup = vm.lookupInstrument()
    await flushPromises()
    vm.selectDataFamily('stock.liquidity')
    pendingRealtimeResponse.resolve(createV2ResponseFixture(stockRealtimeFamilyBinding()))
    await staleLookup
    await flushPromises()

    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(vm.selectedFamilyId).toBe('stock.liquidity')
    expect(vm.result).toBeNull()
    expect(vm.referenceSeriesResult).toBeNull()
    expect(vm.chartCanRender).toBe(false)
    expect(wrapper.find('[data-test="market-reference-series-table"]').exists()).toBe(true)
  })

  it('drops the initial lookup when every request selector changes during capability resolution', async () => {
    const pendingCapabilities = createDeferred<{
      version: string
      query_v2_enabled: boolean
      online_fetch_enabled: boolean
      research_cache_fill_enabled: boolean
      research_backtest_bridge_enabled: boolean
    }>()
    apiMocks.getCapabilities.mockReturnValueOnce(pendingCapabilities.promise)

    const wrapper = await mountPage()
    const vm = wrapper.vm as any

    expect(apiMocks.getCapabilities).toHaveBeenCalledTimes(1)
    vm.form.asset_type = 'futures'
    vm.form.symbol = 'RB0'
    vm.form.market = 'SHFE'
    vm.form.period = 'weekly'
    vm.dateRange = ['2026-06-01', '2026-06-20']
    vm.selectedFamilyId = 'futures.settlement'

    pendingCapabilities.resolve({
      version: 'market-data-capabilities-v1',
      query_v2_enabled: true,
      online_fetch_enabled: false,
      research_cache_fill_enabled: false,
      research_backtest_bridge_enabled: false,
    })
    await flushPromises()
    await flushPromises()

    // The pre-capability snapshot was stock/000001.  It must be discarded,
    // rather than issuing either a v2 or legacy provider request using the
    // later futures form values.
    expect(apiMocks.getQueryBundle).not.toHaveBeenCalled()
    expect(apiMocks.getQueryContract).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(vm.result).toBeNull()
  })

  it('treats a cleared date range as an omitted legacy window', async () => {
    apiMocks.getCapabilities.mockResolvedValue({
      version: 'market-data-capabilities-v1',
      query_v2_enabled: false,
      online_fetch_enabled: false,
      research_cache_fill_enabled: false,
      research_backtest_bridge_enabled: false,
    })
    const wrapper = await mountPage()
    const vm = wrapper.vm as any
    apiMocks.lookupInstrument.mockClear()

    vm.dateRange = null
    await vm.lookupInstrument()
    await flushPromises()

    expect(apiMocks.lookupInstrument).toHaveBeenCalledWith(expect.objectContaining({
      asset_type: 'stock',
      symbol: '000001',
      start_date: undefined,
      end_date: undefined,
    }))
    expect(vm.result?.symbol).toBe('000001')
  })

  it('rejects a cleared date range through the v2 window guard without falling back', async () => {
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture())
    apiMocks.queryLocalFirst.mockResolvedValue(createV2ResponseFixture())
    const wrapper = await mountPage()
    const vm = wrapper.vm as any
    apiMocks.getQueryContract.mockClear()
    apiMocks.queryLocalFirst.mockClear()
    apiMocks.lookupInstrument.mockClear()

    vm.dateRange = null
    await vm.lookupInstrument()
    await flushPromises()

    // The previously issued server contract is still exact for this symbol;
    // the frozen empty window is rejected before any local-first read.
    expect(apiMocks.getQueryContract).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(vm.result).toBeNull()
    expect((wrapper.vm as any).marketDataPlatformStatus.path).toBe('error')
  })

  it('drops an in-flight response when its symbol, period, or date window changes', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createQueryBundleFixture('stock', {
      'stock.realtime': 'ready',
    }))
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture(stockRealtimeFamilyBinding()))
    apiMocks.queryLocalFirst.mockResolvedValue(createV2ResponseFixture(stockRealtimeFamilyBinding()))

    const wrapper = await mountPage()
    const vm = wrapper.vm as any
    const originalDateRange = [...vm.dateRange]
    const changes: Array<() => void> = [
      () => { vm.form.symbol = '600000' },
      () => { vm.form.period = 'weekly' },
      () => { vm.dateRange = ['2026-06-01', '2026-06-20'] },
    ]

    for (const change of changes) {
      vm.form.symbol = '000001'
      vm.form.period = 'daily'
      vm.dateRange = [...originalDateRange]
      vm.result = null
      vm.referenceSeriesResult = null
      const pendingResponse = createDeferred<MarketDataQueryResponse>()
      apiMocks.queryLocalFirst.mockImplementationOnce(() => pendingResponse.promise)

      const staleLookup = vm.lookupInstrument()
      await flushPromises()
      change()
      pendingResponse.resolve(createV2ResponseFixture(stockRealtimeFamilyBinding()))
      await staleLookup
      await flushPromises()

      expect(vm.result).toBeNull()
      expect(vm.referenceSeriesResult).toBeNull()
      expect(vm.chartCanRender).toBe(false)
    }
  })

  it('does not retarget a selected reference series to realtime or legacy when its bundle fails', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createStockLiquidityBundleFixture())
    apiMocks.getQueryContract.mockImplementation(({ family_id }: { family_id: string }) => (
      Promise.resolve(
        family_id === 'stock.liquidity'
          ? createStockLiquidityContractFixture()
          : createV2ContractFixture(stockRealtimeFamilyBinding()),
      )
    ))
    apiMocks.queryLocalFirst.mockImplementation(({ family_id }: { family_id: string }) => (
      Promise.resolve(
        family_id === 'stock.liquidity'
          ? createStockLiquidityResponseFixture()
          : createV2ResponseFixture(stockRealtimeFamilyBinding()),
      )
    ))

    const wrapper = await mountPage()
    const vm = wrapper.vm as any
    vm.selectDataFamily('stock.liquidity')
    apiMocks.getQueryBundle.mockRejectedValue({ response: { status: 404 } })
    apiMocks.getQueryContract.mockClear()
    apiMocks.queryLocalFirst.mockClear()
    apiMocks.lookupInstrument.mockClear()

    await vm.lookupInstrument()
    await flushPromises()

    expect(apiMocks.getQueryContract).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(vm.result).toBeNull()
    expect(vm.referenceSeriesResult).toBeNull()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据平台查询失败')
  })

  it('keeps K-line rendering for an explicitly selected ready bars family', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    const stockBundle = createQueryBundleFixture('stock', { 'stock.realtime': 'ready' })
    const fxBundle = createQueryBundleFixture('fx', {
      'fx.realtime': 'ready',
      'fx.range': 'ready',
    })
    const fxRange = fxBundle.families.find((family) => family.family_id === 'fx.range')
    if (!fxRange) throw new Error('missing fx.range fixture')
    fxRange.dataset_code = 'market.fx_range'
    fxRange.data_kind = 'bars'
    fxRange.frequency_semantics = 'calendar_grid'
    fxRange.frequencies = ['1d']
    fxRange.required_fields = ['open', 'high', 'low', 'close']
    fxRange.optional_fields = ['volume']
    fxRange.dimension_fields = []
    fxRange.coverage_model = 'calendar_grid'
    fxRange.source_policy_id = 'market-default-v1'
    fxRange.reason_code = null

    const fxContract = (familyId: 'fx.realtime' | 'fx.range') => {
      const contract = createV2ContractFixture({
        family_id: familyId,
        family_contract_version: 'market-data-family-v1',
      })
      contract.request.identity.canonical_id = 'instrument:fx:FX:USDCNH'
      contract.request.dataset_code = familyId === 'fx.range' ? 'market.fx_range' : 'market.bars'
      contract.request.required_fields = familyId === 'fx.range'
        ? ['open', 'high', 'low', 'close']
        : ['close']
      return contract
    }
    const fxResponse = (familyId: 'fx.realtime' | 'fx.range'): MarketDataQueryResponse => {
      const response = createV2ResponseFixture({
        family_id: familyId,
        family_contract_version: 'market-data-family-v1',
      })
      response.canonical_id = 'instrument:fx:FX:USDCNH'
      response.dataset_code = familyId === 'fx.range' ? 'market.fx_range' : 'market.bars'
      response.asset_type = 'fx'
      response.observations = [{
        ...response.observations[0],
        fields: { open: 7.2, high: 7.3, low: 7.1, close: 7.25, volume: 1200 },
      }]
      return response
    }

    apiMocks.getQueryBundle.mockImplementation(({ asset_type }: { asset_type: MarketAssetType }) => (
      Promise.resolve(asset_type === 'fx' ? fxBundle : stockBundle)
    ))
    apiMocks.getQueryContract.mockImplementation(({
      asset_type,
      family_id,
    }: { asset_type: MarketAssetType, family_id: string }) => (
      Promise.resolve(
        asset_type === 'fx'
          ? fxContract(family_id as 'fx.realtime' | 'fx.range')
          : createV2ContractFixture(stockRealtimeFamilyBinding()),
      )
    ))
    apiMocks.queryLocalFirst.mockImplementation(({
      family_id,
      identity,
    }: { family_id: string, identity: { canonical_id: string } }) => (
      Promise.resolve(
        identity.canonical_id === 'instrument:fx:FX:USDCNH'
          ? fxResponse(family_id as 'fx.realtime' | 'fx.range')
          : createV2ResponseFixture(stockRealtimeFamilyBinding()),
      )
    ))

    const wrapper = await mountPage()
    const vm = wrapper.vm as any
    vm.applyAssetType('fx', false)
    await vm.lookupInstrument()
    await flushPromises()
    apiMocks.getQueryContract.mockClear()
    apiMocks.queryLocalFirst.mockClear()
    apiMocks.lookupInstrument.mockClear()

    expect(vm.selectedFamilyId).toBe('fx.realtime')
    expect(vm.selectableDataFamilies).toEqual([
      expect.objectContaining({ value: 'fx.realtime' }),
      expect.objectContaining({ value: 'fx.range' }),
    ])
    vm.selectDataFamily('fx.range')
    await vm.lookupInstrument()
    await flushPromises()

    expect(apiMocks.getQueryContract).toHaveBeenCalledWith({
      asset_type: 'fx',
      symbol: 'USDCNH',
      period: 'daily',
      family_id: 'fx.range',
    })
    expect(apiMocks.queryLocalFirst).toHaveBeenCalledWith(expect.objectContaining({
      family_id: 'fx.range',
      data_kind: 'bars',
      dataset_code: 'market.fx_range',
      required_fields: ['open', 'high', 'low', 'close'],
    }), expect.objectContaining({ suppressErrorMessage: true }))
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(vm.isReferenceSeriesSelected).toBe(false)
    expect(vm.chartCanRender).toBe(true)
    expect(vm.ohlcHistoryRows).toHaveLength(1)
    expect(wrapper.find('.market-chart-card').exists()).toBe(true)
    expect(vm.assetDataFamilies.find((family: { familyId: string }) => family.familyId === 'fx.range'))
      .toEqual(expect.objectContaining({ readState: 'facts_loaded' }))
  })

  it('renders declared snapshot, reference, and dimensioned families without issuing their facts', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    const bundle = createQueryBundleFixture('stock')
    bundle.families.push(
      {
        family_id: 'stock.quote_snapshot',
        family_contract_version: 'market-data-family-v1',
        asset_type: 'stock',
        status: 'ready',
        dataset_code: 'market.quote_snapshot',
        data_kind: 'quote_snapshot',
        frequency_semantics: 'snapshot',
        frequencies: ['snapshot'],
        field_profile_id: 'stock-quote-snapshot-v1',
        required_fields: ['price', 'update_time'],
        optional_fields: ['bid', 'ask'],
        dimension_fields: [],
        coverage_model: 'snapshot_freshness',
        source_policy_id: 'market-default-v1',
        reason_code: null,
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
    )
    apiMocks.getQueryBundle.mockResolvedValue(bundle)

    const wrapper = await mountPage()
    const families = (wrapper.vm as any).assetDataFamilies
    const quoteSnapshot = families.find((family: { familyId: string }) => (
      family.familyId === 'stock.quote_snapshot'
    ))
    const valuation = families.find((family: { familyId: string }) => (
      family.familyId === 'stock.valuation'
    ))
    const inventory = families.find((family: { familyId: string }) => (
      family.familyId === 'stock.inventory'
    ))

    expect(quoteSnapshot).toEqual(expect.objectContaining({
      statusLabel: '已配置',
      readState: 'control_plane_only',
      readStatusLabel: '控制面已声明；本页不发起事实请求',
      contract: expect.objectContaining({
        dataKind: 'quote_snapshot',
        frequencySemantics: 'snapshot',
        coverageModel: 'snapshot_freshness',
        observationShape: 'single_record',
      }),
    }))
    expect(valuation).toEqual(expect.objectContaining({
      readState: 'unconfigured',
      readStatusLabel: '未配置；不会发起事实请求',
    }))
    expect(inventory).toEqual(expect.objectContaining({
      readState: 'unconfigured',
      contract: expect.objectContaining({
        dataKind: 'inventory_report',
        frequencySemantics: 'reporting_period',
        observationShape: 'dimensioned_records',
      }),
    }))
    expect(quoteSnapshot.fields.every((field: { present: boolean }) => !field.present)).toBe(true)
    expect(valuation.fields.every((field: { present: boolean }) => !field.present)).toBe(true)
    expect(inventory.fields.every((field: { present: boolean }) => !field.present)).toBe(true)

    expect(wrapper.find('[data-test="market-data-family-stock.quote_snapshot"]').text())
      .toContain('quote_snapshot · snapshot')
    expect(wrapper.find('[data-test="market-data-family-stock.inventory"]').text())
      .toContain('dimensioned_records')
    expect((wrapper.vm as any).selectableDataFamilies).toEqual([])
    expect(apiMocks.getQueryContract).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result?.query_contract).toBeNull()
  })

  it('constrains weekly and monthly selection to the declared daily cadence for futures, bonds, options, and FX', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockImplementation(({ asset_type }: { asset_type: MarketAssetType }) => (
      Promise.resolve(createQueryBundleFixture(asset_type, {
        [`${asset_type}.realtime`]: 'ready',
      }))
    ))
    const wrapper = await mountPage()
    apiMocks.getQueryContract.mockClear()
    apiMocks.queryLocalFirst.mockClear()

    for (const assetType of ['futures', 'bond', 'option', 'fx'] as const) {
      ;(wrapper.vm as any).form.period = 'monthly'
      ;(wrapper.vm as any).setAssetType(assetType)
      await flushPromises()

      expect((wrapper.vm as any).form.period).toBe('daily')
      expect((wrapper.vm as any).periods.map((period: { value: string }) => period.value)).toEqual(['daily'])
      const status = wrapper.find('[data-test="market-data-platform-status"]').text()
      expect(status).toContain('数据族不支持所选周期')
      expect(status).toContain('已重置为日线，未执行查询')
      expect(status).toContain(`${assetType}.realtime 仅声明 日线`)
    }

    expect(apiMocks.getQueryContract).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
  })

  it('preserves an existing result when a bundle rejects the selected period', async () => {
    const wrapper = await mountPage()
    const priorResult = (wrapper.vm as any).result
    const dailyOnlyStockBundle = createQueryBundleFixture('stock', {
      'stock.realtime': 'ready',
    })
    dailyOnlyStockBundle.families[0].frequencies = ['1d']
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(dailyOnlyStockBundle)
    apiMocks.getQueryContract.mockClear()
    apiMocks.queryLocalFirst.mockClear()
    apiMocks.lookupInstrument.mockClear()
    ;(wrapper.vm as any).form.period = 'weekly'

    await (wrapper.vm as any).lookupInstrument()
    await flushPromises()

    expect((wrapper.vm as any).form.period).toBe('daily')
    expect((wrapper.vm as any).result).toBe(priorResult)
    expect(apiMocks.getQueryContract).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据族不支持所选周期')
  })

  it('rejects a bundle-selected contract whose declared family axes do not match', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createQueryBundleFixture('stock', {
      'stock.realtime': 'ready',
    }))
    const mismatchedContract = createV2ContractFixture(stockRealtimeFamilyBinding())
    mismatchedContract.request.required_fields = ['close', 'volume']
    apiMocks.getQueryContract.mockResolvedValue(mismatchedContract)

    const wrapper = await mountPage()

    expect(apiMocks.getQueryContract).toHaveBeenCalledWith({
      asset_type: 'stock',
      symbol: '000001',
      period: 'daily',
      family_id: 'stock.realtime',
    })
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result).toBeNull()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据平台查询失败')
  })

  it('rejects a first family-bound response whose echoed binding differs from the request', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createQueryBundleFixture('stock', {
      'stock.realtime': 'ready',
    }))
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture(stockRealtimeFamilyBinding()))
    apiMocks.queryLocalFirst.mockResolvedValue(createV2ResponseFixture({
      family_id: 'stock.valuation',
      family_contract_version: 'market-data-family-v1',
    }))

    const wrapper = await mountPage()

    expect(apiMocks.queryLocalFirst).toHaveBeenCalledTimes(1)
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result).toBeNull()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据平台查询失败')
  })

  it('rejects a later cursor page whose echoed family binding differs from the first request', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createQueryBundleFixture('stock', {
      'stock.realtime': 'ready',
    }))
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture(stockRealtimeFamilyBinding()))
    const firstPage = {
      ...createV2ResponseFixture(stockRealtimeFamilyBinding()),
      next_cursor: 'cursor-1',
    }
    const laterPage = {
      ...createV2ResponseFixture({
        family_id: 'stock.realtime',
        family_contract_version: 'market-data-family-v1',
      }),
      observations: [{
        ...createV2ResponseFixture(stockRealtimeFamilyBinding()).observations[0],
        revision_id: 'revision-2',
      }],
      family_contract_version: 'market-data-family-v2',
      next_cursor: null,
    }
    apiMocks.queryLocalFirst.mockImplementation(({ cursor }: { cursor?: string }) => (
      Promise.resolve(cursor ? laterPage : firstPage)
    ))

    const wrapper = await mountPage()

    expect(apiMocks.queryLocalFirst).toHaveBeenCalledTimes(2)
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result).toBeNull()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据平台查询失败')
  })

  it('does not fall back to legacy data after a valid bundle has issued a bars family', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createQueryBundleFixture('stock', {
      'stock.realtime': 'ready',
    }))
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture(stockRealtimeFamilyBinding()))
    apiMocks.queryLocalFirst.mockRejectedValue({
      response: { status: 503, data: { details: { code: 'MARKET_DATA_WRITE_FAILED' } } },
    })

    const wrapper = await mountPage()

    expect(apiMocks.getQueryBundle).toHaveBeenCalledTimes(1)
    expect(apiMocks.queryLocalFirst).toHaveBeenCalledTimes(1)
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result).toBeNull()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据平台查询失败')
  })

  it('does not use legacy data when a valid bundle cannot resolve its exact bars contract', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockResolvedValue(createQueryBundleFixture('stock', {
      'stock.realtime': 'ready',
    }))
    apiMocks.getQueryContract.mockRejectedValue({ response: { status: 404 } })

    const wrapper = await mountPage()

    expect(apiMocks.getQueryBundle).toHaveBeenCalledTimes(1)
    expect(apiMocks.getQueryContract).toHaveBeenCalledTimes(1)
    expect(apiMocks.queryLocalFirst).not.toHaveBeenCalled()
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result).toBeNull()
    expect(wrapper.find('[data-test="market-data-platform-status"]').text()).toContain('数据平台查询失败')
  })

  it('keeps the existing bars path when the optional bundle endpoint is unavailable', async () => {
    vi.stubEnv('VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED', 'true')
    apiMocks.getQueryBundle.mockRejectedValue({ response: { status: 404 } })
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture())
    apiMocks.queryLocalFirst.mockResolvedValue(createV2ResponseFixture())

    const wrapper = await mountPage()

    expect(apiMocks.getQueryBundle).toHaveBeenCalledWith({ asset_type: 'stock' })
    expect(apiMocks.getQueryContract).toHaveBeenCalledWith({
      asset_type: 'stock',
      symbol: '000001',
      period: 'daily',
      family_id: 'stock.realtime',
    })
    expect(apiMocks.queryLocalFirst).toHaveBeenCalledTimes(1)
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result.history.rows).toHaveLength(1)
  })

  it('does not fall back to legacy data after a valid v2 contract returns a write failure', async () => {
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture())
    apiMocks.queryLocalFirst.mockRejectedValue({
      response: { status: 503, data: { details: { code: 'MARKET_DATA_WRITE_FAILED' } } },
    })

    const wrapper = await mountPage()

    expect(apiMocks.queryLocalFirst).toHaveBeenCalledTimes(1)
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect((wrapper.vm as any).result).toBeNull()
    const status = wrapper.find('[data-test="market-data-platform-status"]').text()
    expect(status).toContain('数据平台查询失败')
    expect(status).toContain('查询未回退到传统接口')
    expect(status).not.toContain('传统本地查询')
  })

  it('uses the v2 refresh mode after a contract has been issued', async () => {
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture())
    apiMocks.queryLocalFirst.mockResolvedValue(createV2ResponseFixture())
    const wrapper = await mountPage()
    apiMocks.queryLocalFirst.mockClear()

    await (wrapper.vm as any).lookupInstrument(true)
    await flushPromises()

    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).toHaveBeenCalledWith(expect.objectContaining({
      mode: 'refresh',
      purpose: 'display',
      consistency: 'display',
    }), expect.objectContaining({ suppressErrorMessage: true }))
  })

  it('aggregates every v2 cursor page before rendering more than 500 historical observations', async () => {
    apiMocks.getQueryContract.mockResolvedValue({
      version: 'market-data-v2',
      request: {
        identity: { canonical_id: 'instrument:stock:CN-SZSE:000001' },
        dataset_code: 'market.bars',
        data_kind: 'bars',
        frequency: '1d',
        required_fields: ['close'],
        adjustment: 'qfq',
        price_basis: 'close',
        currency: 'CNY',
        unit: 'share',
        source_policy_id: 'market-default-v1',
        family_id: 'stock.realtime',
        family_contract_version: 'market-data-family-v1',
        mode: 'local_first',
      },
    })
    const pages = Array.from({ length: 17 }, (_, pageIndex) => ({
      query_id: 'query-cursor-pages',
      canonical_id: 'instrument:stock:CN-SZSE:000001',
      dataset_code: 'market.bars',
      asset_type: 'stock',
      instrument_metadata_version: 'stock-v1',
      data_kind: 'bars',
      frequency: '1d',
      source_policy_id: 'market-default-v1',
      family_id: 'stock.realtime',
      family_contract_version: 'market-data-family-v1',
      knowledge_cutoff: '2026-06-19T16:00:00Z',
      identity_knowledge_cutoff: '2026-06-19T16:00:00Z',
      observations: Array.from({ length: pageIndex === 0 ? 500 : 1 }, (_, rowIndex) => ({
        revision_id: `revision-${pageIndex}-${rowIndex}`,
        source_snapshot_id: `snapshot-${pageIndex}`,
        event_at: new Date(Date.UTC(2026, 0, 1, 0, pageIndex * 500 + rowIndex)).toISOString(),
        available_at: '2026-06-19T15:00:00Z',
        committed_at: '2026-06-19T15:00:01Z',
        revision_number: 1,
        quality: 'pass',
        fields: { open: 12.1, high: 12.4, low: 12, close: 12.34, volume: 1000 },
      })),
      next_cursor: pageIndex < 16 ? `cursor-${pageIndex + 1}` : null,
      coverage: {
        status: 'complete',
        expected_event_count: 516,
        accepted_event_count: 516,
        missing_event_count: 0,
        coverage_ratio: 1,
        gaps: [],
        rejection_counts: {},
        calendar_reason: null,
      },
      fetches: [],
      warnings: [],
      refresh_status: null,
      historical_status: null,
    }))
    apiMocks.queryLocalFirst.mockImplementation(({ cursor }: { cursor?: string }) => {
      const pageIndex = cursor ? Number(cursor.replace('cursor-', '')) : 0
      return Promise.resolve(pages[pageIndex])
    })

    const wrapper = await mountPage()

    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).toHaveBeenCalledTimes(17)
    expect(apiMocks.queryLocalFirst.mock.calls.map(([request]) => request.cursor)).toEqual([
      undefined,
      ...Array.from({ length: 16 }, (_, index) => `cursor-${index + 1}`),
    ])
    expect((wrapper.vm as any).result.history.total).toBe(516)
    expect((wrapper.vm as any).historyRows).toHaveLength(516)
  })

  it('remembers successful queries independently for each asset type', async () => {
    const wrapper = await mountPage()
    const futuresTab = wrapper.findAll('.asset-tab').find((button) => button.text().includes('期货'))

    await futuresTab?.trigger('click')
    await flushPromises()

    expect(JSON.parse(window.localStorage.getItem(MARKET_ASSET_SELECTIONS_STORAGE_KEY) || '{}')).toEqual({
      stock: { symbol: '000001' },
      futures: { symbol: 'IM2606', market: 'CF' },
    })
  })

  it('restores only the saved selection for the asset type being opened', async () => {
    window.localStorage.setItem(MARKET_ASSET_SELECTIONS_STORAGE_KEY, JSON.stringify({
      stock: { symbol: '600519' },
      futures: { symbol: 'IF2609', market: 'CFFEX' },
    }))

    const wrapper = await mountPage()
    expect((wrapper.vm as any).form.asset_type).toBe('stock')
    expect((wrapper.vm as any).form.symbol).toBe('600519')

    const futuresTab = wrapper.findAll('.asset-tab').find((button) => button.text().includes('期货'))
    await futuresTab?.trigger('click')
    await flushPromises()

    expect((wrapper.vm as any).form.asset_type).toBe('futures')
    expect((wrapper.vm as any).form.symbol).toBe('IF2609')
    expect(apiMocks.lookupInstrument).toHaveBeenCalledWith({
      asset_type: 'futures',
      symbol: 'IF2609',
      period: 'daily',
      start_date: expect.any(String),
      end_date: expect.any(String),
      market: 'CFFEX',
      refresh_online: false,
    })
  })

  it('shows a stock-specific valuation and liquidity panel', async () => {
    const wrapper = await mountPage()

    expect(wrapper.text()).toContain('估值与流动性')
    expect(wrapper.text()).toContain('总市值')
    expect(wrapper.text()).toContain('PE / PB')
    expect(wrapper.text()).not.toContain('合约监控')
    expect((wrapper.vm as any).assetKpiCards.map((card: { label: string }) => card.label)).toEqual([
      '最新价',
      '区间涨跌',
      '成交额',
      'PE / PB',
    ])
  })

  it('shows futures contract controls instead of stock valuation fields', async () => {
    const wrapper = await mountPage()
    const futuresTab = wrapper.findAll('.asset-tab').find((button) => button.text().includes('期货'))

    await futuresTab?.trigger('click')
    await flushPromises()

    expect(apiMocks.listInstrumentOptions).toHaveBeenLastCalledWith({
      asset_type: 'futures',
      search: 'IM2606',
      limit: 80,
    })
    expect(wrapper.text()).toContain('合约监控')
    expect(wrapper.text()).toContain('持仓量')
    expect(wrapper.text()).toContain('结算价')
    expect(wrapper.text()).toContain('买一 / 卖一')
    expect(wrapper.text()).not.toContain('总市值')
    expect(wrapper.find('[data-test="market-instrument-overview"]').text()).toContain('IM2606')
    expect((wrapper.vm as any).assetKpiCards.map((card: { label: string }) => card.label)).toEqual([
      '最新价',
      '持仓量',
      '结算价',
      '买卖价差',
    ])
  })

  it('uses crypto position columns when crypto history has no ohlc prices', async () => {
    const wrapper = await mountPage()
    const cryptoTab = wrapper.findAll('.asset-tab').find((button) => button.text().includes('数字货币'))

    await cryptoTab?.trigger('click')
    await flushPromises()

    const keys = (wrapper.vm as any).historyTableColumns.map((column: { key: string }) => column.key)
    expect(wrapper.text()).toContain('数字货币持仓')
    expect(keys).toEqual(['date', 'name', 'volume', 'open_interest', 'change'])
    expect(keys).not.toContain('open')
    expect(keys).not.toContain('close')
  })

  it('uses the options tab as its own historical asset query', async () => {
    const wrapper = await mountPage('/data/market?tab=options')

    await flushPromises()

    expect(apiMocks.lookupInstrument).toHaveBeenCalledWith({
      asset_type: 'option',
      symbol: 'MO',
      period: 'daily',
      start_date: expect.any(String),
      end_date: expect.any(String),
      market: undefined,
      refresh_online: false,
    })
    expect((wrapper.vm as any).form.asset_type).toBe('option')
    expect((wrapper.vm as any).result.asset_type).toBe('option')
  })

  it('queries only the selected tab asset when switching tabs', async () => {
    const wrapper = await mountPage()
    const optionsTab = wrapper.findAll('.asset-tab').find((button) => button.text().includes('期权'))

    await optionsTab?.trigger('click')
    await flushPromises()

    expect(apiMocks.lookupInstrument).toHaveBeenLastCalledWith({
      asset_type: 'option',
      symbol: 'MO',
      period: 'daily',
      start_date: expect.any(String),
      end_date: expect.any(String),
      market: undefined,
      refresh_online: false,
    })
    expect((wrapper.vm as any).result.asset_type).toBe('option')
    expect(wrapper.text()).not.toContain('Put / Call Ratio')
  })

  it('uses local-first rather than refresh when the standard query button is pressed', async () => {
    apiMocks.getQueryContract.mockResolvedValue(createV2ContractFixture())
    apiMocks.queryLocalFirst.mockResolvedValue(createV2ResponseFixture())
    const wrapper = await mountPage()
    const queryButton = wrapper.findAll('button').find((button) => button.text().includes('查询'))

    expect(queryButton).toBeDefined()
    apiMocks.getQueryContract.mockClear()
    apiMocks.queryLocalFirst.mockClear()
    apiMocks.lookupInstrument.mockClear()
    await queryButton?.trigger('click')
    await flushPromises()

    expect(apiMocks.getQueryContract).not.toHaveBeenCalled()
    expect(apiMocks.queryLocalFirst).toHaveBeenCalledWith(expect.objectContaining({
      mode: 'local_first',
      purpose: 'display',
      consistency: 'display',
    }), expect.objectContaining({ suppressErrorMessage: true }))
    expect(apiMocks.lookupInstrument).not.toHaveBeenCalled()
    expect((wrapper.vm as any).marketDataPlatformStatus.path).toBe('local_first')
  })
})
