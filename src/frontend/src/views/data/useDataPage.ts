/** State, data loading, and chart orchestration for the historical data page. */

import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Coin,
  DataAnalysis,
  DataLine,
  Money,
  PieChart,
  Tickets,
  TrendCharts,
} from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { akshareTablesApi } from '@/api/akshare'
import {
  createMarketDataQueryFromContract,
  hasMarketDataCapabilities,
  hasMarketDataQueryBundle,
  hasMarketDataQueryContract,
  isMarketDataQueryBundleFamilyExecutable,
  isMarketDataQueryV2FallbackError,
  marketDataFamilyObservationShape,
  marketDataApi,
  type MarketAssetType,
  type MarketDataCapabilitiesResponse,
  type MarketDataFamilyObservationShape,
  type MarketHistoryRow,
  type MarketInstrumentOption,
  type MarketInstrumentLookupResponse,
  type MarketDataQueryBundle,
  type MarketDataQueryBundleFamily,
  type MarketDataQueryBundleFamilyStatus,
  type MarketDataQueryContract,
  type MarketDataQueryContractParams,
  type MarketDataQueryDataKind,
  type MarketDataQueryFrequency,
  type MarketDataQueryMode,
  type MarketDataQueryObservation,
  type MarketDataQueryResponse,
} from '@/api/marketData'
import { CANDLE_DOWN_COLOR, CANDLE_ITEM_STYLE, CANDLE_UP_COLOR } from '@/constants/chartColors'
import type { DataTable } from '@/types'
import type { MarketDataCoverageResponse } from '@/types/trust'

const MARKET_ASSET_SELECTIONS_STORAGE_KEY = 'ai_for_investor:market:asset_selections'

type SavedMarketAssetSelection = {
  symbol: string
  market?: string
}

type MarketAssetSelections = Partial<Record<MarketAssetType, SavedMarketAssetSelection>>

const V2_MARKET_DATA_PAGE_SIZE = 2000
/**
 * The public v2 DTO limits every non-bar/reference request to a seven-day
 * half-open interval. The date picker has an inclusive end date, so a generic
 * observation family may display at most seven calendar dates.
 */
const GENERIC_OBSERVATION_MAX_WINDOW_DAYS = 7

/** The authenticated server capability is the rollout authority for v2 reads. */
function isMarketDataQueryV2FeatureEnabled(
  capabilities: MarketDataCapabilitiesResponse | null,
): boolean {
  return capabilities?.query_v2_enabled === true
}

/**
 * A family bundle is part of the authenticated server control plane. Once
 * v2 is server-enabled, the client probes it and uses the explicit v2
 * compatibility fallback only when an older server has no bundle endpoint.
 * A browser build variable must not hide or grant a server-owned contract.
 */
function isMarketDataQueryBundleFeatureEnabled(
  capabilities: MarketDataCapabilitiesResponse | null,
): boolean {
  return isMarketDataQueryV2FeatureEnabled(capabilities)
}

export function useDataPage() {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()

  const today = new Date()
  const ninetyDaysAgo = new Date(today)
  ninetyDaysAgo.setDate(today.getDate() - 90)

  type AssetTab = {
    key: MarketAssetType
    labelKey: string
    placeholderKey: string
    defaultSymbol: string
    icon: Component
  }

  type FieldFormat = 'number' | 'percent' | 'text' | 'pair' | 'bidAsk' | 'valuation'

  type DetailFieldSpec = {
    labelKey: string
    fields: string[]
    format?: FieldFormat
    tone?: boolean
  }

  type HistoryColumnSpec = {
    key: string
    labelKey: string
    width?: number
    minWidth?: number
    align?: 'left' | 'center' | 'right'
    fixed?: 'left' | 'right'
    format?: 'number' | 'percent' | 'text'
    tone?: boolean
  }

  type AssetDisplayConfig = {
    titleKey: string
    descKey: string
    detailTitleKey: string
    detailNoteKey: string
    detailFields: DetailFieldSpec[]
    historyColumns: HistoryColumnSpec[]
  }

  type DetailRow = {
    label: string
    value: string
    tone: string
  }

  type KpiCard = {
    label: string
    value: string
    tone: string
  }

  type SnapshotMetric = {
    key: string
    label: string
    value: string
    tone?: string
  }

  type HistoryTableColumn = Omit<HistoryColumnSpec, 'labelKey'> & {
    label: string
  }

  type ReferenceSeriesResult = {
    familyId: string
    requiredFields: string[]
    rows: MarketHistoryRow[]
  }

  /**
   * A contract-driven presentation for v2 product families that are neither
   * bars nor reference series.  It intentionally preserves observation
   * provenance and exposes only server-declared required fields, so a new
   * snapshot, chain, surface, or report never needs to masquerade as OHLCV.
   */
  type GenericObservationResult = {
    familyId: string
    dataKind: MarketDataQueryDataKind
    requiredFields: string[]
    dimensionFields: string[]
    observations: MarketDataQueryObservation[]
  }

  type GenericObservationColumn = {
    key: string
    label: string
    source: 'metadata' | 'field'
  }

  type V2LookupResult = {
    lookup: MarketInstrumentLookupResponse
    response: MarketDataQueryResponse
    referenceSeries: ReferenceSeriesResult | null
    genericObservations: GenericObservationResult | null
  }

  type MarketLookupRequestSnapshot = {
    assetType: MarketAssetType
    symbol: string
    market: string
    period: string
    dateRange: readonly [string | undefined, string | undefined]
    familyId: string
  }

  /**
   * Keep automatic reads distinct from a user-requested cache fill.
   *
   * ``local_only`` is the safe default for page lifecycle work: opening a
   * route, switching a route tab, or changing the displayed asset must never
   * start a provider fetch. ``local_first`` is reserved for the explicit
   * query button and remains subject to the server-owned v2 capability and
   * online-fetch gate. ``refresh`` is retained for existing explicit refresh
   * callers; it never falls through to the legacy endpoint.
   */
  type MarketLookupIntent = MarketDataQueryMode | boolean

  type DataFamilyOption = {
    value: string
    label: string
  }

  type ChartMode = 'price' | 'return' | 'liquidity' | 'structure'

  type ChartModeOption = {
    value: ChartMode
    label: string
  }

  type RangeStat = {
    label: string
    value: string
    tone: string
  }

  type CoverageRow = {
    label: string
    value: string
    coverage: number
  }

  type MarketDataPlatformStatus = {
    path: (
      | 'legacy'
      | 'local_only'
      | 'local_first'
      | 'local_coverage_incomplete'
      | 'provider_persisted'
      | 'provider_persisted_incomplete'
      | 'legacy_fallback'
      | 'family_selection_pending'
      | 'bundle_unconfigured'
      | 'bundle_period_unsupported'
      | 'error'
    )
    provider: string | null
    coverageStatus: string | null
    coverageRatio: number | null
    fetchedProviderCount: number
    fallbackReason: string | null
    queryId: string | null
    canonicalId: string | null
    datasetCode: string | null
    sourcePolicyId: string | null
    instrumentMetadataVersion: string | null
    familyId: string | null
    periodConstraint: {
      familyId: string
      requestedFrequency: string
      declaredFrequencies: string[]
      resetPeriod: string | null
    } | null
  }

  type DataFamilySpec = {
    familyId: string
    labelKey: string
    descKey: string
    fields: string[]
    historyFields?: string[]
    tableKeywords: string[]
  }

  type DataFamilyReadState = (
    | 'facts_loaded'
    | 'bars_query_available'
    | 'reference_series_query_available'
    | 'generic_query_available'
    | 'control_plane_only'
    | 'unconfigured'
    | 'not_applicable'
  )

  type DataFamilyView = {
    familyId: string
    label: string
    description: string
    statusLabel: string
    tagType: 'success' | 'warning' | 'info'
    contract: {
      dataKind: MarketDataQueryBundleFamily['data_kind']
      frequencySemantics: MarketDataQueryBundleFamily['frequency_semantics']
      coverageModel: MarketDataQueryBundleFamily['coverage_model']
      observationShape: MarketDataFamilyObservationShape
    } | null
    readState: DataFamilyReadState | null
    readStatusLabel: string | null
    fields: Array<{
      name: string
      label: string
      present: boolean
    }>
  }

  type MarketDataPlatformProvenance = {
    label: string
    value: string
  }

  type MarketChartOptionDraft = Omit<echarts.EChartsOption, 'legend'> & {
    legend: string[]
  }

  const assetTabs: AssetTab[] = [
    {
      key: 'stock',
      labelKey: 'dataMgmt.tabStock',
      placeholderKey: 'dataMgmt.stockSymbolPlaceholder',
      defaultSymbol: '000001',
      icon: TrendCharts,
    },
    {
      key: 'futures',
      labelKey: 'dataMgmt.tabFutures',
      placeholderKey: 'dataMgmt.futuresSymbolPlaceholder',
      defaultSymbol: 'IM2606',
      icon: DataLine,
    },
    {
      key: 'bond',
      labelKey: 'dataMgmt.tabBond',
      placeholderKey: 'dataMgmt.bondSymbolPlaceholder',
      defaultSymbol: 'sh110074',
      icon: Tickets,
    },
    {
      key: 'fund',
      labelKey: 'dataMgmt.tabFund',
      placeholderKey: 'dataMgmt.fundSymbolPlaceholder',
      defaultSymbol: '510300',
      icon: PieChart,
    },
    {
      key: 'option',
      labelKey: 'dataMgmt.tabOptions',
      placeholderKey: 'dataMgmt.optionSymbolPlaceholder',
      defaultSymbol: 'MO',
      icon: DataAnalysis,
    },
    {
      key: 'fx',
      labelKey: 'dataMgmt.tabFx',
      placeholderKey: 'dataMgmt.fxSymbolPlaceholder',
      defaultSymbol: 'USDCNH',
      icon: Money,
    },
    {
      key: 'crypto',
      labelKey: 'dataMgmt.tabCrypto',
      placeholderKey: 'dataMgmt.cryptoSymbolPlaceholder',
      defaultSymbol: 'BTCJPY',
      icon: Coin,
    },
  ]

  const assetDisplayConfigs: Record<MarketAssetType, AssetDisplayConfig> = {
    stock: {
      titleKey: 'dataMgmt.assetTitleStock',
      descKey: 'dataMgmt.assetDescStock',
      detailTitleKey: 'dataMgmt.assetDetailStock',
      detailNoteKey: 'dataMgmt.assetNoteStock',
      detailFields: [
        { labelKey: 'dataMgmt.fieldMarketCap', fields: ['market_cap'] },
        { labelKey: 'dataMgmt.fieldFloatMarketCap', fields: ['float_market_cap'] },
        { labelKey: 'dataMgmt.metricPePb', fields: ['pe', 'pb'], format: 'valuation' },
        { labelKey: 'dataMgmt.fieldTurnover', fields: ['turnover'] },
      ],
      historyColumns: [
        { key: 'open', labelKey: 'dataMgmt.colOpen', width: 110, align: 'right' },
        { key: 'high', labelKey: 'dataMgmt.colHigh', width: 110, align: 'right' },
        { key: 'low', labelKey: 'dataMgmt.colLow', width: 110, align: 'right' },
        { key: 'close', labelKey: 'dataMgmt.colClose', width: 110, align: 'right' },
        { key: 'change_pct', labelKey: 'dataMgmt.colChange', width: 120, align: 'right', format: 'percent', tone: true },
        { key: 'volume', labelKey: 'dataMgmt.colVolume', width: 130, align: 'right' },
        { key: 'turnover', labelKey: 'dataMgmt.fieldTurnover', width: 140, align: 'right' },
        { key: 'turnover_rate', labelKey: 'dataMgmt.fieldTurnoverRate', width: 120, align: 'right', format: 'percent' },
      ],
    },
    futures: {
      titleKey: 'dataMgmt.assetTitleFutures',
      descKey: 'dataMgmt.assetDescFutures',
      detailTitleKey: 'dataMgmt.assetDetailFutures',
      detailNoteKey: 'dataMgmt.assetNoteFutures',
      detailFields: [
        { labelKey: 'dataMgmt.fieldOpenInterest', fields: ['open_interest'] },
        { labelKey: 'dataMgmt.fieldSettle', fields: ['settle'] },
        { labelKey: 'dataMgmt.fieldPreviousSettle', fields: ['previous_settle'] },
        { labelKey: 'dataMgmt.fieldBidAsk', fields: ['bid', 'ask'], format: 'bidAsk' },
      ],
      historyColumns: [
        { key: 'open', labelKey: 'dataMgmt.colOpen', width: 110, align: 'right' },
        { key: 'high', labelKey: 'dataMgmt.colHigh', width: 110, align: 'right' },
        { key: 'low', labelKey: 'dataMgmt.colLow', width: 110, align: 'right' },
        { key: 'close', labelKey: 'dataMgmt.colClose', width: 110, align: 'right' },
        { key: 'settle', labelKey: 'dataMgmt.fieldSettle', width: 110, align: 'right' },
        { key: 'volume', labelKey: 'dataMgmt.colVolume', width: 130, align: 'right' },
        { key: 'open_interest', labelKey: 'dataMgmt.fieldOpenInterest', width: 130, align: 'right' },
        { key: 'change', labelKey: 'dataMgmt.colChangeValue', width: 120, align: 'right', tone: true },
      ],
    },
    bond: {
      titleKey: 'dataMgmt.assetTitleBond',
      descKey: 'dataMgmt.assetDescBond',
      detailTitleKey: 'dataMgmt.assetDetailBond',
      detailNoteKey: 'dataMgmt.assetNoteBond',
      detailFields: [
        { labelKey: 'dataMgmt.fieldPrice', fields: ['price'] },
        { labelKey: 'dataMgmt.colChange', fields: ['change_pct'], format: 'percent', tone: true },
        { labelKey: 'dataMgmt.fieldTurnover', fields: ['turnover'] },
        { labelKey: 'dataMgmt.fieldBidAsk', fields: ['bid', 'ask'], format: 'bidAsk' },
      ],
      historyColumns: [
        { key: 'open', labelKey: 'dataMgmt.colOpen', width: 110, align: 'right' },
        { key: 'high', labelKey: 'dataMgmt.colHigh', width: 110, align: 'right' },
        { key: 'low', labelKey: 'dataMgmt.colLow', width: 110, align: 'right' },
        { key: 'close', labelKey: 'dataMgmt.colClose', width: 110, align: 'right' },
        { key: 'change_pct', labelKey: 'dataMgmt.colChange', width: 120, align: 'right', format: 'percent', tone: true },
        { key: 'volume', labelKey: 'dataMgmt.colVolume', width: 130, align: 'right' },
        { key: 'turnover', labelKey: 'dataMgmt.fieldTurnover', width: 140, align: 'right' },
      ],
    },
    fund: {
      titleKey: 'dataMgmt.assetTitleFund',
      descKey: 'dataMgmt.assetDescFund',
      detailTitleKey: 'dataMgmt.assetDetailFund',
      detailNoteKey: 'dataMgmt.assetNoteFund',
      detailFields: [
        { labelKey: 'dataMgmt.fieldPrice', fields: ['price'] },
        { labelKey: 'dataMgmt.colChange', fields: ['change_pct'], format: 'percent', tone: true },
        { labelKey: 'dataMgmt.fieldTurnover', fields: ['turnover'] },
        { labelKey: 'dataMgmt.fieldHighLow', fields: ['high', 'low'], format: 'pair' },
      ],
      historyColumns: [
        { key: 'open', labelKey: 'dataMgmt.colOpen', width: 110, align: 'right' },
        { key: 'high', labelKey: 'dataMgmt.colHigh', width: 110, align: 'right' },
        { key: 'low', labelKey: 'dataMgmt.colLow', width: 110, align: 'right' },
        { key: 'close', labelKey: 'dataMgmt.colClose', width: 110, align: 'right' },
        { key: 'change_pct', labelKey: 'dataMgmt.colChange', width: 120, align: 'right', format: 'percent', tone: true },
        { key: 'volume', labelKey: 'dataMgmt.colVolume', width: 130, align: 'right' },
        { key: 'turnover', labelKey: 'dataMgmt.fieldTurnover', width: 140, align: 'right' },
      ],
    },
    option: {
      titleKey: 'dataMgmt.assetTitleOption',
      descKey: 'dataMgmt.assetDescOption',
      detailTitleKey: 'dataMgmt.assetDetailOption',
      detailNoteKey: 'dataMgmt.assetNoteOption',
      detailFields: [
        { labelKey: 'dataMgmt.metricPremium', fields: ['price'] },
        { labelKey: 'dataMgmt.colChangeValue', fields: ['change'], tone: true },
        { labelKey: 'dataMgmt.colChange', fields: ['change_pct'], format: 'percent', tone: true },
        { labelKey: 'dataMgmt.fieldVolume', fields: ['volume'] },
        { labelKey: 'dataMgmt.fieldOpenInterest', fields: ['open_interest'] },
        { labelKey: 'dataMgmt.fieldStrike', fields: ['strike'] },
        { labelKey: 'dataMgmt.fieldDaysToExpiry', fields: ['days_to_expiry'] },
      ],
      historyColumns: [
        { key: 'name', labelKey: 'dataMgmt.fieldName', minWidth: 170, align: 'left', format: 'text' },
        { key: 'price', labelKey: 'dataMgmt.fieldPrice', width: 110, align: 'right' },
        { key: 'volume', labelKey: 'dataMgmt.colVolume', width: 130, align: 'right' },
        { key: 'turnover', labelKey: 'dataMgmt.fieldTurnover', width: 140, align: 'right' },
        { key: 'open_interest', labelKey: 'dataMgmt.fieldOpenInterest', width: 130, align: 'right' },
        { key: 'strike', labelKey: 'dataMgmt.fieldStrike', width: 120, align: 'right' },
        { key: 'days_to_expiry', labelKey: 'dataMgmt.fieldDaysToExpiry', width: 120, align: 'right' },
        { key: 'change', labelKey: 'dataMgmt.colChangeValue', width: 120, align: 'right', tone: true },
        { key: 'change_pct', labelKey: 'dataMgmt.colChange', width: 120, align: 'right', format: 'percent', tone: true },
      ],
    },
    fx: {
      titleKey: 'dataMgmt.assetTitleFx',
      descKey: 'dataMgmt.assetDescFx',
      detailTitleKey: 'dataMgmt.assetDetailFx',
      detailNoteKey: 'dataMgmt.assetNoteFx',
      detailFields: [
        { labelKey: 'dataMgmt.fieldPrice', fields: ['price'] },
        { labelKey: 'dataMgmt.colChange', fields: ['change_pct'], format: 'percent', tone: true },
        { labelKey: 'dataMgmt.fieldHighLow', fields: ['high', 'low'], format: 'pair' },
        { labelKey: 'dataMgmt.fieldPreviousClose', fields: ['previous_close'] },
      ],
      historyColumns: [
        { key: 'open', labelKey: 'dataMgmt.colOpen', width: 110, align: 'right' },
        { key: 'high', labelKey: 'dataMgmt.colHigh', width: 110, align: 'right' },
        { key: 'low', labelKey: 'dataMgmt.colLow', width: 110, align: 'right' },
        { key: 'close', labelKey: 'dataMgmt.colClose', width: 110, align: 'right' },
        { key: 'change_pct', labelKey: 'dataMgmt.colChange', width: 120, align: 'right', format: 'percent', tone: true },
      ],
    },
    crypto: {
      titleKey: 'dataMgmt.assetTitleCrypto',
      descKey: 'dataMgmt.assetDescCrypto',
      detailTitleKey: 'dataMgmt.assetDetailCrypto',
      detailNoteKey: 'dataMgmt.assetNoteCrypto',
      detailFields: [
        { labelKey: 'dataMgmt.fieldPrice', fields: ['price'] },
        { labelKey: 'dataMgmt.colChange', fields: ['change_pct'], format: 'percent', tone: true },
        { labelKey: 'dataMgmt.metric24hVolume', fields: ['volume'] },
        { labelKey: 'dataMgmt.metric24hHighLow', fields: ['high', 'low'], format: 'pair' },
      ],
      historyColumns: [
        { key: 'name', labelKey: 'dataMgmt.fieldName', minWidth: 150, align: 'left', format: 'text' },
        { key: 'volume', labelKey: 'dataMgmt.colVolume', width: 130, align: 'right' },
        { key: 'open_interest', labelKey: 'dataMgmt.fieldOpenInterest', width: 140, align: 'right' },
        { key: 'change', labelKey: 'dataMgmt.colChangeValue', width: 120, align: 'right', tone: true },
      ],
    },
  }

  const assetDataFamilySpecs: Record<MarketAssetType, DataFamilySpec[]> = {
    stock: [
      {
        familyId: 'stock.realtime',
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'change_pct', 'open', 'high', 'low', 'volume', 'turnover'],
        historyFields: ['open', 'high', 'low', 'close', 'volume', 'turnover', 'turnover_rate'],
        tableKeywords: ['stock_zh_a_spot', 'stock_zh_a_hist', 'stock_market'],
      },
      {
        familyId: 'stock.valuation',
        labelKey: 'dataMgmt.familyValuation',
        descKey: 'dataMgmt.familyValuationDesc',
        fields: ['market_cap', 'float_market_cap', 'pe', 'pb'],
        tableKeywords: ['stock_market_pe', 'stock_market_pb', 'stock_individual_info'],
      },
      {
        familyId: 'stock.liquidity',
        labelKey: 'dataMgmt.familyLiquidity',
        descKey: 'dataMgmt.familyLiquidityDesc',
        fields: ['volume', 'turnover'],
        historyFields: ['volume', 'turnover', 'turnover_rate'],
        tableKeywords: ['stock_market_fund_flow', 'stock_individual_fund_flow'],
      },
    ],
    futures: [
      {
        familyId: 'futures.realtime',
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'bid', 'ask', 'volume', 'open_interest'],
        historyFields: ['open', 'high', 'low', 'close', 'volume', 'open_interest'],
        tableKeywords: ['futures_zh_spot', 'daily_market_data', 'minute_market'],
      },
      {
        familyId: 'futures.settlement',
        labelKey: 'dataMgmt.familySettlement',
        descKey: 'dataMgmt.familySettlementDesc',
        fields: ['settle', 'previous_settle', 'open_interest'],
        historyFields: ['settle', 'open_interest'],
        tableKeywords: ['settle', 'delivery', 'member_position'],
      },
      {
        familyId: 'futures.inventory',
        labelKey: 'dataMgmt.familyInventory',
        descKey: 'dataMgmt.familyInventoryDesc',
        fields: ['volume', 'open_interest'],
        historyFields: ['volume', 'open_interest'],
        tableKeywords: ['inventory', 'receipt', 'warehouse'],
      },
    ],
    bond: [
      {
        familyId: 'bond.realtime',
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'change_pct', 'bid', 'ask', 'turnover'],
        historyFields: ['open', 'high', 'low', 'close', 'volume', 'turnover'],
        tableKeywords: ['bond_zh_hs_cov_spot', 'bond_zh_hs_cov_daily'],
      },
      {
        familyId: 'bond.orderbook',
        labelKey: 'dataMgmt.familyOrderBook',
        descKey: 'dataMgmt.familyOrderBookDesc',
        fields: ['bid', 'ask', 'volume', 'turnover'],
        tableKeywords: ['bond_spot', 'bond_info', 'bond_quote'],
      },
      {
        familyId: 'bond.fixed_income',
        labelKey: 'dataMgmt.familyFixedIncome',
        descKey: 'dataMgmt.familyFixedIncomeDesc',
        fields: ['price', 'previous_close'],
        historyFields: ['close', 'change_pct'],
        tableKeywords: ['bond_info_cm', 'bond_market'],
      },
    ],
    fund: [
      {
        familyId: 'fund.realtime',
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'change_pct', 'volume', 'turnover'],
        historyFields: ['open', 'high', 'low', 'close', 'volume', 'turnover'],
        tableKeywords: ['fund_etf_spot', 'fund_etf_hist'],
      },
      {
        familyId: 'fund.liquidity',
        labelKey: 'dataMgmt.familyLiquidity',
        descKey: 'dataMgmt.familyLiquidityDesc',
        fields: ['volume', 'turnover'],
        historyFields: ['volume', 'turnover'],
        tableKeywords: ['fund_flow', 'fund_scale', 'fund_industry_allocation'],
      },
      {
        familyId: 'fund.nav',
        labelKey: 'dataMgmt.familyNav',
        descKey: 'dataMgmt.familyNavDesc',
        // NAV is a reference series with its own audited field profile. Do
        // not describe it through an ETF quote's price/previous-close fields.
        fields: ['nav', 'cumulative_nav', 'daily_growth_rate'],
        tableKeywords: ['fund_open_fund', 'fund_net_value', 'reits_hist'],
      },
    ],
    option: [
      {
        familyId: 'option.realtime',
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'change', 'change_pct', 'volume'],
        historyFields: ['name', 'price', 'volume', 'turnover'],
        tableKeywords: ['option_sse_daily', 'option_cffex'],
      },
      {
        familyId: 'option.derivative',
        labelKey: 'dataMgmt.familyDerivative',
        descKey: 'dataMgmt.familyDerivativeDesc',
        fields: ['price', 'volume', 'open_interest', 'strike', 'days_to_expiry'],
        historyFields: ['volume', 'open_interest', 'strike', 'days_to_expiry'],
        tableKeywords: ['option_base', 'option_finance_board', 'options_stock'],
      },
      {
        familyId: 'option.risk_surface',
        labelKey: 'dataMgmt.familyRiskSurface',
        descKey: 'dataMgmt.familyRiskSurfaceDesc',
        fields: ['change_pct', 'bid', 'ask'],
        historyFields: ['change_pct', 'change'],
        tableKeywords: ['option_minute', 'option_sse_minute', 'option_iv'],
      },
    ],
    fx: [
      {
        familyId: 'fx.realtime',
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'change_pct', 'open', 'high', 'low', 'previous_close'],
        historyFields: ['open', 'high', 'low', 'close', 'change_pct'],
        tableKeywords: ['forex_spot', 'forex_hist', 'fx_quote'],
      },
      {
        familyId: 'fx.macro_fx',
        labelKey: 'dataMgmt.familyMacroFx',
        descKey: 'dataMgmt.familyMacroFxDesc',
        fields: ['price', 'previous_close'],
        historyFields: ['close', 'change_pct'],
        tableKeywords: ['macro', 'fx_quote_baidu', 'currency'],
      },
      {
        familyId: 'fx.range',
        labelKey: 'dataMgmt.familyRange',
        descKey: 'dataMgmt.familyRangeDesc',
        fields: ['high', 'low', 'open'],
        historyFields: ['high', 'low', 'open'],
        tableKeywords: ['forex', 'fx'],
      },
    ],
    crypto: [
      {
        familyId: 'crypto.realtime',
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'change', 'change_pct', 'high', 'low', 'volume'],
        tableKeywords: ['crypto_js_spot', 'crypto'],
      },
      {
        familyId: 'crypto.cme_position',
        labelKey: 'dataMgmt.familyCmePosition',
        descKey: 'dataMgmt.familyCmePositionDesc',
        fields: ['volume', 'open_interest', 'change'],
        historyFields: ['volume', 'open_interest', 'change'],
        tableKeywords: ['crypto_bitcoin_cme', 'bitcoin_cme'],
      },
      {
        familyId: 'crypto.range',
        labelKey: 'dataMgmt.familyRange',
        descKey: 'dataMgmt.familyRangeDesc',
        fields: ['high', 'low', 'volume'],
        historyFields: ['volume', 'open_interest'],
        tableKeywords: ['crypto', 'bitcoin'],
      },
    ],
  }

  const assetTableSearchKeywords: Record<MarketAssetType, string[]> = {
    stock: ['stock', 'stock_zh_a', 'market'],
    futures: ['futures', 'future', 'receipt'],
    bond: ['bond', 'convertible'],
    fund: ['fund', 'etf', 'reits'],
    option: ['option', 'options'],
    fx: ['forex', 'fx', 'currency'],
    crypto: ['crypto', 'bitcoin', 'cme'],
  }

  const fieldLabelKeys: Record<string, string> = {
    price: 'dataMgmt.fieldPrice',
    change: 'dataMgmt.colChangeValue',
    change_pct: 'dataMgmt.colChange',
    open: 'dataMgmt.colOpen',
    high: 'dataMgmt.colHigh',
    low: 'dataMgmt.colLow',
    close: 'dataMgmt.colClose',
    previous_close: 'dataMgmt.fieldPreviousClose',
    settle: 'dataMgmt.fieldSettle',
    previous_settle: 'dataMgmt.fieldPreviousSettle',
    bid: 'dataMgmt.fieldBid',
    ask: 'dataMgmt.fieldAsk',
    volume: 'dataMgmt.fieldVolume',
    turnover: 'dataMgmt.fieldTurnover',
    turnover_rate: 'dataMgmt.fieldTurnoverRate',
    open_interest: 'dataMgmt.fieldOpenInterest',
    strike: 'dataMgmt.fieldStrike',
    days_to_expiry: 'dataMgmt.fieldDaysToExpiry',
    market_cap: 'dataMgmt.fieldMarketCap',
    float_market_cap: 'dataMgmt.fieldFloatMarketCap',
    pe: 'dataMgmt.fieldPe',
    pb: 'dataMgmt.fieldPb',
  }

  const basePeriods = [
    { value: 'daily', labelKey: 'dataMgmt.periodDaily' },
    { value: 'weekly', labelKey: 'dataMgmt.periodWeekly' },
    { value: 'monthly', labelKey: 'dataMgmt.periodMonthly' },
  ]

  // The selected product is explicit state. A bundle can describe more than
  // one ready family, but it may never retarget a page merely by changing its
  // order or by adding a new family.
  const selectedFamilyId = ref('stock.realtime')

  const periods = computed(() => {
    const bundle = marketDataQueryBundle.value
    if (!bundle || bundle.requested_asset_type !== form.asset_type) return basePeriods
    const family = selectedMarketPageFamilyFromQueryBundle(
      bundle,
      form.asset_type,
      selectedFamilyId.value,
    )
    if (!family) return basePeriods
    return family.frequencies
      .map((frequency) => ({
        value: marketPagePeriodForV2Frequency(frequency),
        labelKey: periodLabelKey(frequency),
      }))
  })

  const routeTabMap: Record<string, MarketAssetType> = {
    stock: 'stock',
    futures: 'futures',
    bond: 'bond',
    fund: 'fund',
    option: 'option',
    options: 'option',
    fx: 'fx',
    crypto: 'crypto',
  }

  const form = reactive({
    asset_type: 'stock' as MarketAssetType,
    symbol: '000001',
    period: 'daily',
    market: 'CF',
  })
  const dateRange = ref<[string, string]>([toDateInput(ninetyDaysAgo), toDateInput(today)])
  const loading = ref(false)
  const result = ref<MarketInstrumentLookupResponse | null>(null)
  const chartMode = ref<ChartMode>('price')
  const marketChartRef = ref<HTMLDivElement>()
  const instrumentOptions = ref<MarketInstrumentOption[]>([])
  const instrumentOptionsLoading = ref(false)
  const relatedTablesLoading = ref(false)
  const relatedTables = ref<DataTable[]>([])
  const relatedTablesError = ref('')
  const coverageRows = ref<MarketDataCoverageResponse[]>([])
  const coverageLoading = ref(false)
  const coverageRefreshing = ref(false)
  const coverageError = ref('')
  const coverageTimeframe = ref('1d')
  const coverageProvider = ref('akshare_data')
  const marketDataPlatformStatus = ref<MarketDataPlatformStatus>({
    path: 'legacy',
    provider: null,
    coverageStatus: null,
    coverageRatio: null,
    fetchedProviderCount: 0,
    fallbackReason: null,
    queryId: null,
    canonicalId: null,
    datasetCode: null,
    sourcePolicyId: null,
    instrumentMetadataVersion: null,
    familyId: null,
    periodConstraint: null,
  })
  // A valid bundle is an authoritative capability declaration for the current
  // asset tab. Do not infer a missing entry from legacy payloads or catalog
  // table names while it is present.
  const marketDataQueryBundle = ref<MarketDataQueryBundle | null>(null)
  const marketDataCapabilities = ref<MarketDataCapabilitiesResponse | null>(null)
  const referenceSeriesResult = ref<ReferenceSeriesResult | null>(null)
  const genericObservationResult = ref<GenericObservationResult | null>(null)
  const viewportWidth = ref(window.innerWidth)
  let marketChart: echarts.ECharts | null = null
  let instrumentOptionsRequestId = 0
  let relatedTableRequestId = 0
  let coverageRequestId = 0
  let lookupRequestId = 0
  let activeMarketDataQueryAbortController: AbortController | null = null
  let activeMarketDataQuerySelectionKey: string | null = null
  let marketDataCapabilitiesResolved = false
  let marketDataCapabilitiesRequest: Promise<MarketDataCapabilitiesResponse | null> | null = null

  const snapshot = computed<Record<string, unknown>>(() => result.value?.snapshot || {})
  const historyRows = computed(() => result.value?.history.rows || [])
  const selectedMarketPageFamily = computed(() => {
    const bundle = marketDataQueryBundle.value
    if (!bundle || bundle.requested_asset_type !== form.asset_type) return null
    return selectedMarketPageFamilyFromQueryBundle(bundle, form.asset_type, selectedFamilyId.value)
  })
  const selectableDataFamilies = computed<DataFamilyOption[]>(() => {
    const bundle = marketDataQueryBundle.value
    if (!bundle || bundle.requested_asset_type !== form.asset_type) return []
    return bundle.families
      .filter((family) => isMarketPageSelectableFamily(family, form.asset_type))
      .map((family) => ({
        value: family.family_id,
        label: marketPageFamilyLabel(family),
      }))
  })
  const isReferenceSeriesSelected = computed(() => (
    selectedMarketPageFamily.value?.data_kind === 'reference_series'
    || referenceSeriesResult.value?.familyId === selectedFamilyId.value
  ))
  const isGenericObservationSelected = computed(() => (
    (selectedMarketPageFamily.value !== null
      && selectedMarketPageFamily.value.data_kind !== 'bars'
      && selectedMarketPageFamily.value.data_kind !== 'reference_series')
    || genericObservationResult.value?.familyId === selectedFamilyId.value
  ))
  const isFundNavReferenceSeries = computed(() => {
    const presentation = referenceSeriesResult.value
    const request = result.value?.query_contract?.request
    return form.asset_type === 'fund'
      && selectedFamilyId.value === 'fund.nav'
      && presentation?.familyId === 'fund.nav'
      && request?.family_id === 'fund.nav'
      && request.dataset_code === 'market.fund_nav'
      && request.data_kind === 'reference_series'
      && sameDeclaredFields(presentation.requiredFields, request.required_fields)
  })
  const fundNavReferenceFields = computed(() => {
    if (!isFundNavReferenceSeries.value) return []
    return [...(referenceSeriesResult.value?.requiredFields || [])]
  })
  const referenceSeriesRows = computed(() => {
    const presentation = referenceSeriesResult.value
    if (!presentation || presentation.familyId !== selectedFamilyId.value) return []
    return [...presentation.rows].sort((left, right) => historyRowTimestamp(right) - historyRowTimestamp(left))
  })
  const referenceSeriesTableColumns = computed<HistoryTableColumn[]>(() => {
    const presentation = referenceSeriesResult.value
    if (!presentation || presentation.familyId !== selectedFamilyId.value) return []
    return [
      {
        key: 'date',
        label: t('dataMgmt.colDate'),
        width: 120,
        align: 'left',
        fixed: 'left',
        format: 'text',
      },
      ...presentation.requiredFields.map((field) => ({
        key: field,
        label: fieldLabel(field),
        minWidth: 130,
        align: 'right' as const,
        // A reference-series percentage must use the same formatter as its
        // overview/KPI presentation.  Rendering it as a generic number would
        // silently remove the percent unit from ETF NAV daily growth.
        format: field === 'daily_growth_rate' ? 'percent' as const : 'number' as const,
      })),
    ]
  })
  const referenceSeriesEmptyText = computed(() => (
    referenceSeriesResult.value ? t('dataMgmt.emptyNoRows') : t('dataMgmt.emptyQueryFirst')
  ))
  const genericObservationRows = computed(() => {
    const presentation = genericObservationResult.value
    if (!presentation || presentation.familyId !== selectedFamilyId.value) return []
    return [...presentation.observations].sort((left, right) => (
      Date.parse(right.event_at) - Date.parse(left.event_at)
    ))
  })
  const genericObservationColumns = computed<GenericObservationColumn[]>(() => {
    const presentation = genericObservationResult.value
    if (!presentation || presentation.familyId !== selectedFamilyId.value) return []
    return [
      { key: 'event_at', label: t('dataMgmt.genericObservationColumnEventAt'), source: 'metadata' },
      { key: 'quality', label: t('dataMgmt.genericObservationColumnQuality'), source: 'metadata' },
      {
        key: 'source_snapshot_id',
        label: t('dataMgmt.genericObservationColumnSourceSnapshotId'),
        source: 'metadata',
      },
      { key: 'revision_id', label: t('dataMgmt.genericObservationColumnRevisionId'), source: 'metadata' },
      { key: 'available_at', label: t('dataMgmt.genericObservationColumnAvailableAt'), source: 'metadata' },
      { key: 'committed_at', label: t('dataMgmt.genericObservationColumnCommittedAt'), source: 'metadata' },
      {
        key: 'revision_number',
        label: t('dataMgmt.genericObservationColumnRevisionNumber'),
        source: 'metadata',
      },
      ...presentation.dimensionFields.map((field) => ({
        key: field,
        label: fieldLabel(field),
        source: 'field' as const,
      })),
      ...presentation.requiredFields.map((field) => ({
        key: field,
        label: fieldLabel(field),
        source: 'field' as const,
      })),
    ]
  })
  const genericObservationEmptyText = computed(() => {
    if (!genericObservationResult.value) return t('dataMgmt.emptyQueryFirst')
    return t('dataMgmt.genericObservationEmpty')
  })
  const displayHistoryRows = computed(() => (
    [...historyRows.value].sort((left, right) => historyRowTimestamp(right) - historyRowTimestamp(left))
  ))
  const ohlcHistoryRows = computed(() => historyRows.value.filter((row) => (
    hasValue(row.date)
    && isFiniteNumber(numericValue(row.open, null))
    && isFiniteNumber(numericValue(row.high, null))
    && isFiniteNumber(numericValue(row.low, null))
    && isFiniteNumber(numericValue(row.close, null))
  )))
  const hasOhlcChart = computed(() => ohlcHistoryRows.value.length > 0)
  const hasStructureChart = computed(() => historyRows.value.some((row) => (
    hasValue(row.name) || hasValue(row.open_interest) || hasValue(row.volume)
  )))
  const chartCanRender = computed(() => (
    !isReferenceSeriesSelected.value
    && !isGenericObservationSelected.value
    && (hasOhlcChart.value || hasStructureChart.value)
  ))
  const activeAssetConfig = computed(() => assetDisplayConfigs[form.asset_type])
  const activeAssetIcon = computed<Component>(() => currentAssetTab().icon)
  const symbolPlaceholder = computed(() => t(currentAssetTab().placeholderKey))
  const emptyHistoryText = computed(() => (
    result.value ? t('dataMgmt.emptyNoRows') : t('dataMgmt.emptyQueryFirst')
  ))
  const chartEmptyText = computed(() => (
    result.value ? t('dataMgmt.chartEmpty') : t('dataMgmt.emptyQueryFirst')
  ))
  const chartSubtitle = computed(() => {
    const symbol = result.value?.symbol || form.symbol || '-'
    const rows = result.value?.history.total || 0
    return t('dataMgmt.chartSubtitle', { symbol, rows })
  })
  const chartAriaLabel = computed(() => t('dataMgmt.chartAria', {
    asset: assetLabel(form.asset_type),
    symbol: result.value?.symbol || form.symbol || '-',
  }))
  const hasSnapshotChange = computed(() => hasValue(snapshot.value.change) || hasValue(snapshot.value.change_pct))
  const marketOverviewPrimaryLabel = computed(() => (
    isFundNavReferenceSeries.value ? fieldLabel('nav') : t('dataMgmt.fieldPrice')
  ))
  const marketOverviewPrimaryValue = computed(() => (
    isFundNavReferenceSeries.value
      ? formatReferenceSeriesField('nav', snapshot.value.nav)
      : formatNumber(snapshot.value.price)
  ))
  const marketOverviewTone = computed(() => (
    isFundNavReferenceSeries.value
      ? toneClass(snapshot.value.daily_growth_rate)
      : toneClass(snapshot.value.change_pct ?? snapshot.value.change)
  ))
  const marketOverviewSecondaryText = computed(() => {
    if (isFundNavReferenceSeries.value) {
      return hasValue(snapshot.value.daily_growth_rate)
        ? `${fieldLabel('daily_growth_rate')} ${formatReferenceSeriesField('daily_growth_rate', snapshot.value.daily_growth_rate)}`
        : null
    }
    if (!hasSnapshotChange.value) return null
    return `${formatNumber(snapshot.value.change)} / ${formatPercent(snapshot.value.change_pct)}`
  })
  const assetOverviewDescription = computed(() => (
    isFundNavReferenceSeries.value
      ? t('dataMgmt.familyNavDesc', { count: 0 })
      : t(activeAssetConfig.value.descKey)
  ))
  const assetDetailTitle = computed(() => (
    isFundNavReferenceSeries.value
      ? t('dataMgmt.familyNav')
      : t(activeAssetConfig.value.detailTitleKey)
  ))
  const assetDetailNote = computed(() => (
    isFundNavReferenceSeries.value
      ? t('dataMgmt.familyNavDesc', { count: 0 })
      : t(activeAssetConfig.value.detailNoteKey)
  ))
  const hasSnapshotTurnover = computed(() => hasValue(snapshot.value.turnover))
  const hasSnapshotBidAsk = computed(() => hasValue(snapshot.value.bid) || hasValue(snapshot.value.ask))
  const hasSnapshotOpenInterest = computed(() => hasValue(snapshot.value.open_interest))
  const hasSnapshotSettle = computed(() => hasValue(snapshot.value.settle))
  const hasSnapshotValuation = computed(() => hasValue(snapshot.value.pe) || hasValue(snapshot.value.pb))
  const hasSnapshotDataSource = computed(() => hasValue(snapshot.value.data_source_table))
  const snapshotDescriptionColumns = computed(() => (viewportWidth.value >= 720 ? 2 : 1))
  const snapshotMetrics = computed<SnapshotMetric[]>(() => {
    const metrics: SnapshotMetric[] = [
      { key: 'symbol', label: t('dataMgmt.fieldSymbol'), value: formatText(result.value?.symbol) },
      { key: 'name', label: t('dataMgmt.fieldName'), value: formatText(result.value?.name) },
      { key: 'market', label: t('dataMgmt.fieldMarket'), value: formatText(result.value?.market) },
    ]

    if (hasSnapshotDataSource.value) {
      metrics.push({
        key: 'data_source_table',
        label: t('dataMgmt.fieldDataSourceTable'),
        value: formatText(snapshot.value.data_source_table),
      })
    }

    if (isFundNavReferenceSeries.value) {
      metrics.push(...fundNavReferenceFields.value.map((field) => ({
        key: field,
        label: fieldLabel(field),
        value: formatReferenceSeriesField(field, snapshot.value[field]),
        tone: referenceSeriesFieldTone(field, snapshot.value[field]),
      })))
      metrics.push({ key: 'updated', label: t('dataMgmt.fieldUpdated'), value: formatText(snapshot.value.update_time) })
      return metrics
    }

    metrics.push({ key: 'price', label: t('dataMgmt.fieldPrice'), value: formatNumber(snapshot.value.price) })
    if (hasSnapshotChange.value) {
      metrics.push({
        key: 'change',
        label: t('dataMgmt.colChange'),
        value: `${formatNumber(snapshot.value.change)} / ${formatPercent(snapshot.value.change_pct)}`,
        tone: toneClass(snapshot.value.change_pct ?? snapshot.value.change),
      })
    }
    metrics.push(
      { key: 'open', label: t('dataMgmt.fieldOpen'), value: formatNumber(snapshot.value.open) },
      {
        key: 'high_low',
        label: t('dataMgmt.fieldHighLow'),
        value: formatPair(snapshot.value.high, snapshot.value.low),
      },
      { key: 'volume', label: t('dataMgmt.fieldVolume'), value: formatNumber(snapshot.value.volume) },
    )

    if (hasSnapshotTurnover.value) {
      metrics.push({ key: 'turnover', label: t('dataMgmt.fieldTurnover'), value: formatNumber(snapshot.value.turnover) })
    }
    if (hasSnapshotBidAsk.value) {
      metrics.push({ key: 'bid_ask', label: t('dataMgmt.fieldBidAsk'), value: formatPair(snapshot.value.bid, snapshot.value.ask) })
    }
    if (hasSnapshotOpenInterest.value) {
      metrics.push({
        key: 'open_interest',
        label: t('dataMgmt.fieldOpenInterest'),
        value: formatNumber(snapshot.value.open_interest),
      })
    }
    if (hasSnapshotSettle.value) {
      metrics.push({ key: 'settle', label: t('dataMgmt.fieldSettle'), value: formatNumber(snapshot.value.settle) })
    }
    if (hasSnapshotValuation.value) {
      metrics.push({ key: 'valuation', label: t('dataMgmt.fieldValuation'), value: formatValuation() })
    }

    metrics.push({ key: 'updated', label: t('dataMgmt.fieldUpdated'), value: formatText(snapshot.value.update_time) })
    return metrics
  })
  const assetKpiCards = computed<KpiCard[]>(() => buildAssetKpiCards())
  const chartModeOptions = computed<ChartModeOption[]>(() => {
    if (hasOhlcChart.value) {
      return [
        { value: 'price', label: t('dataMgmt.chartModePrice') },
        { value: 'return', label: t('dataMgmt.chartModeReturn') },
        { value: 'liquidity', label: t('dataMgmt.chartModeLiquidity') },
      ]
    }
    if (hasStructureChart.value) {
      return [
        { value: 'structure', label: t('dataMgmt.chartModeStructure') },
        { value: 'liquidity', label: t('dataMgmt.chartModeLiquidity') },
      ]
    }
    return [{ value: 'price', label: t('dataMgmt.chartModePrice') }]
  })
  const rangeStats = computed<RangeStat[]>(() => buildRangeStats())
  const dataCoverageRows = computed<CoverageRow[]>(() => buildCoverageRows())
  const coverageScore = computed(() => {
    if (!dataCoverageRows.value.length) return 0
    const total = dataCoverageRows.value.reduce((sum, item) => sum + item.coverage, 0)
    return Math.round(total / dataCoverageRows.value.length)
  })
  const displayedObservationCount = computed(() => (
    genericObservationResult.value?.familyId === selectedFamilyId.value
      ? genericObservationResult.value.observations.length
      : result.value?.history.total
  ))
  const heroStats = computed<KpiCard[]>(() => [
    metricCard('dataMgmt.heroStatAsset', assetLabel(form.asset_type)),
    metricCard('dataMgmt.heroStatSymbol', result.value?.symbol || form.symbol || '-'),
    metricCard('dataMgmt.heroStatRows', formatNumber(displayedObservationCount.value)),
    metricCard('dataMgmt.heroStatCoverage', `${coverageScore.value}%`),
  ])
  const marketDataPlatformSourceText = computed(() => {
    const status = marketDataPlatformStatus.value
    if (status.path === 'provider_persisted') {
      return status.provider
        ? t('dataMgmt.marketDataSourceProviderPersistedWithProvider', { provider: status.provider })
        : t('dataMgmt.marketDataSourceProviderPersisted')
    }
    if (status.path === 'provider_persisted_incomplete') {
      const receipts = t('dataMgmt.marketDataSourceProviderPersistedIncomplete', {
        count: status.fetchedProviderCount,
      })
      return status.fallbackReason === 'ONLINE_FETCH_DISABLED'
        ? t('dataMgmt.marketDataSourceOnlineFetchDisabled', { receipts })
        : receipts
    }
    if (status.path === 'local_only') return t('dataMgmt.marketDataSourceLocalOnly')
    if (status.path === 'local_first') {
      return status.provider
        ? t('dataMgmt.marketDataSourceLocalFirstWithProvider', { provider: status.provider })
        : t('dataMgmt.marketDataSourceLocalFirst')
    }
    if (status.path === 'local_coverage_incomplete') {
      return status.fallbackReason === 'ONLINE_FETCH_DISABLED'
        ? t('dataMgmt.marketDataSourceCoverageIncompleteOnlineDisabled')
        : status.fallbackReason === 'LOCAL_ONLY_COVERAGE_INCOMPLETE'
          ? t('dataMgmt.marketDataSourceCoverageIncompleteLocalOnly')
          : t('dataMgmt.marketDataSourceCoverageIncomplete')
    }
    if (status.path === 'legacy_fallback') return t('dataMgmt.marketDataSourceLegacyFallback')
    if (status.path === 'family_selection_pending') return t('dataMgmt.marketDataSourceFamilySelectionPending')
    if (status.path === 'bundle_unconfigured') return t('dataMgmt.marketDataSourceBundleUnconfigured')
    if (status.path === 'bundle_period_unsupported') return t('dataMgmt.marketDataSourceBundlePeriodUnsupported')
    if (status.path === 'error') return t('dataMgmt.marketDataSourceError')
    return t('dataMgmt.marketDataSourceLegacy')
  })
  const marketDataPlatformCacheText = computed(() => {
    const status = marketDataPlatformStatus.value
    if (status.path === 'provider_persisted') {
      return t('dataMgmt.marketDataCacheProviderPersisted', { count: status.fetchedProviderCount })
    }
    if (status.path === 'provider_persisted_incomplete') {
      return t('dataMgmt.marketDataCacheProviderPersistedIncomplete', {
        count: status.fetchedProviderCount,
      })
    }
    if (status.path === 'local_only') return t('dataMgmt.marketDataCacheLocalOnly')
    if (status.path === 'local_first') return t('dataMgmt.marketDataCacheLocalFirst')
    if (status.path === 'local_coverage_incomplete') return t('dataMgmt.marketDataCacheCoverageIncomplete')
    if (status.path === 'legacy_fallback') return t('dataMgmt.marketDataCacheLegacyFallback')
    if (status.path === 'family_selection_pending') return t('dataMgmt.marketDataCacheFamilySelectionPending')
    if (status.path === 'bundle_unconfigured') return t('dataMgmt.marketDataCacheBundleUnconfigured')
    if (status.path === 'bundle_period_unsupported') {
      const resetPeriod = status.periodConstraint?.resetPeriod
      return resetPeriod
        ? t('dataMgmt.marketDataCachePeriodReset', { period: t(periodLabelKey(resetPeriod)) })
        : t('dataMgmt.marketDataCacheNoQuery')
    }
    if (status.path === 'error') return t('dataMgmt.marketDataCacheError')
    return t('dataMgmt.marketDataCacheLegacy')
  })
  const marketDataPlatformCoverageText = computed(() => {
    const status = marketDataPlatformStatus.value
    if (status.path === 'family_selection_pending') {
      return t('dataMgmt.marketDataCoverageFamilySelectionPending')
    }
    if (status.path === 'bundle_unconfigured') {
      return t('dataMgmt.marketDataCoverageBundleUnconfigured')
    }
    if (status.path === 'bundle_period_unsupported') {
      const constraint = status.periodConstraint
      if (!constraint) return t('dataMgmt.marketDataCoverageNoDeclaredFrequency')
      const declaredPeriods = constraint.declaredFrequencies
        .map((frequency) => t(periodLabelKey(frequency)))
      return t('dataMgmt.marketDataCoverageDeclaredFrequencies', {
        familyId: constraint.familyId,
        periods: declaredPeriods.join('/'),
      })
    }
    if (!status.coverageStatus) return t('dataMgmt.marketDataCoverageUnavailable')
    const ratio = status.coverageRatio === null ? '-' : `${(status.coverageRatio * 100).toFixed(2)}%`
    return `${status.coverageStatus} · ${ratio}`
  })
  const marketDataPlatformTagType = computed<'success' | 'warning' | 'info'>(() => {
    const path = marketDataPlatformStatus.value.path
    if (path === 'local_only' || path === 'local_first' || path === 'provider_persisted') return 'success'
    if (
      path === 'local_coverage_incomplete'
      || path === 'provider_persisted_incomplete'
      ||
      path === 'legacy_fallback'
      || path === 'family_selection_pending'
      || path === 'bundle_unconfigured'
      || path === 'bundle_period_unsupported'
      || path === 'error'
    ) return 'warning'
    return 'info'
  })
  const marketDataPlatformProvenance = computed<MarketDataPlatformProvenance[]>(() => {
    const status = marketDataPlatformStatus.value
    const entries: Array<MarketDataPlatformProvenance | null> = [
      status.canonicalId ? { label: t('dataMgmt.marketDataProvenanceCanonicalId'), value: status.canonicalId } : null,
      status.datasetCode ? { label: t('dataMgmt.marketDataProvenanceDataset'), value: status.datasetCode } : null,
      // familyId is set only after assertMarketDataResponseEcho accepts the
      // response. Showing it makes the displayed facts auditable against the
      // exact selected family rather than a generic realtime presentation.
      status.familyId ? { label: t('dataMgmt.marketDataProvenanceFamily'), value: status.familyId } : null,
      status.sourcePolicyId ? { label: t('dataMgmt.marketDataProvenanceSourcePolicy'), value: status.sourcePolicyId } : null,
      status.instrumentMetadataVersion
        ? { label: t('dataMgmt.marketDataProvenanceMetadataVersion'), value: status.instrumentMetadataVersion }
        : null,
    ]
    return entries.filter((entry): entry is MarketDataPlatformProvenance => entry !== null)
  })
  const coverageMatrixSubtitle = computed(() => {
    const provider = coverageProvider.value.trim() || t('dataMgmt.coverageAllProviders')
    return `${assetLabel(form.asset_type)} · ${coverageTimeframe.value} · ${provider}`
  })
  const coverageSummaryCards = computed<KpiCard[]>(() => {
    const rows = coverageRows.value
    const passed = rows.filter((row) => row.quality_status === 'pass').length
    const warnings = rows.filter((row) => row.quality_status === 'warning').length
    const failed = rows.filter((row) => row.quality_status === 'failed').length
    const totalRows = rows.reduce((sum, row) => sum + (row.row_count || 0), 0)
    return [
      { label: t('dataMgmt.coverageSymbols'), value: formatNumber(rows.length), tone: '' },
      { label: t('dataMgmt.coveragePassed'), value: formatNumber(passed), tone: passed ? 'is-positive' : '' },
      { label: t('dataMgmt.coverageWarning'), value: formatNumber(warnings), tone: warnings ? 'is-warning' : '' },
      { label: t('dataMgmt.coverageFailed'), value: formatNumber(failed), tone: failed ? 'is-negative' : '' },
      { label: t('dataMgmt.coverageTotalRows'), value: formatNumber(totalRows), tone: '' },
    ]
  })
  const assetDataFamilies = computed<DataFamilyView[]>(() => buildAssetDataFamilies())
  const relatedTablesBadge = computed(() => {
    if (relatedTablesError.value) return t('dataMgmt.relatedTablesUnavailable')
    return t('dataMgmt.relatedTablesBadge', { count: relatedTables.value.length })
  })
  const relatedTableSummary = computed(() => {
    const totalRows = relatedTables.value.reduce((sum, table) => sum + (table.row_count || 0), 0)
    return t('dataMgmt.relatedTablesSummary', {
      count: relatedTables.value.length,
      rows: formatNumber(totalRows),
    })
  })
  const assetDetailRows = computed<DetailRow[]>(() => {
    if (isFundNavReferenceSeries.value) {
      return fundNavReferenceFields.value.map((field) => ({
        label: fieldLabel(field),
        value: formatReferenceSeriesField(field, snapshot.value[field]),
        tone: referenceSeriesFieldTone(field, snapshot.value[field]),
      }))
    }
    return activeAssetConfig.value.detailFields.map((field) => ({
      label: t(field.labelKey),
      value: formatDetailValue(field),
      tone: field.tone ? toneClass(snapshot.value[field.fields[0]]) : '',
    }))
  })
  const historyTableColumns = computed<HistoryTableColumn[]>(() => [
    {
      key: 'date',
      label: t('dataMgmt.colDate'),
      width: 120,
      align: 'left',
      fixed: 'left',
      format: 'text',
    },
    ...activeAssetConfig.value.historyColumns
      .filter((column) => shouldShowHistoryColumn(column.key))
      .map((column) => ({
        ...column,
        label: t(column.labelKey),
      })),
  ])

  onMounted(() => {
    const routeAssetType = routeTabMap[String(route.query.tab || '').toLowerCase()]
    if (routeAssetType) {
      applyAssetType(routeAssetType, false)
    } else {
      restoreAssetSelection(form.asset_type)
    }
    void loadInstrumentOptions(formSymbolText())
    void loadCoverageMatrix()
    void lookupInstrument('local_only')
    window.addEventListener('resize', handleViewportResize)
  })

  onUnmounted(() => {
    abortActiveMarketDataQueryLifecycle()
    window.removeEventListener('resize', handleViewportResize)
    disposeMarketChart()
  })

  watch(
    () => marketDataQuerySelectionKey(),
    (selectionKey) => {
      if (
        activeMarketDataQueryAbortController
        && activeMarketDataQuerySelectionKey !== selectionKey
      ) {
        invalidateMarketDataQueryLifecycle()
      }
    },
  )

  watch(
    () => route.query.tab,
    (tab) => {
      if (applyRouteTab(tab, true)) {
        void loadInstrumentOptions(formSymbolText())
        void loadCoverageMatrix()
        void lookupInstrument('local_only')
      }
    },
  )

  watch(
    chartModeOptions,
    (options) => {
      if (!options.some((option) => option.value === chartMode.value)) {
        chartMode.value = options[0]?.value || 'price'
      }
    },
    { immediate: true },
  )

  watch(
    () => {
      const rows = historyRows.value
      const firstDate = rows[0]?.date || ''
      const lastDate = rows[rows.length - 1]?.date || ''
      return `${form.asset_type}:${result.value?.symbol || ''}:${chartMode.value}:${rows.length}:${firstDate}:${lastDate}`
    },
    () => {
      void nextTick(renderMarketChart)
    },
    { flush: 'post' },
  )

  function currentAssetTab() {
    return assetTabs.find((asset) => asset.key === form.asset_type) || {
      key: 'stock',
      labelKey: 'dataMgmt.tabStock',
      placeholderKey: 'dataMgmt.stockSymbolPlaceholder',
      defaultSymbol: '000001',
      icon: TrendCharts,
    }
  }

  function marketDataQuerySelectionKey(): string {
    const currentDateRange = Array.isArray(dateRange.value) ? dateRange.value : []
    return JSON.stringify([
      form.asset_type,
      formSymbolText(),
      formMarketText(),
      form.period,
      currentDateRange[0] || '',
      currentDateRange[1] || '',
      selectedFamilyId.value,
    ])
  }

  function releaseMarketDataQueryLifecycle(controller: AbortController): void {
    if (activeMarketDataQueryAbortController !== controller) return
    activeMarketDataQueryAbortController = null
    activeMarketDataQuerySelectionKey = null
  }

  function abortActiveMarketDataQueryLifecycle(): void {
    const controller = activeMarketDataQueryAbortController
    if (!controller) return
    if (!controller.signal.aborted) controller.abort()
    releaseMarketDataQueryLifecycle(controller)
  }

  function invalidateMarketDataQueryLifecycle(): void {
    abortActiveMarketDataQueryLifecycle()
    lookupRequestId += 1
    loading.value = false
  }

  function beginMarketDataQueryLifecycle(): {
    controller: AbortController
    requestId: number
    selectionKey: string
  } {
    abortActiveMarketDataQueryLifecycle()
    const controller = new AbortController()
    const selectionKey = marketDataQuerySelectionKey()
    activeMarketDataQueryAbortController = controller
    activeMarketDataQuerySelectionKey = selectionKey
    return {
      controller,
      requestId: ++lookupRequestId,
      selectionKey,
    }
  }

  async function resolveMarketDataCapabilities(): Promise<MarketDataCapabilitiesResponse | null> {
    if (marketDataCapabilitiesResolved) return marketDataCapabilities.value
    if (marketDataCapabilitiesRequest) return marketDataCapabilitiesRequest

    marketDataCapabilitiesRequest = marketDataApi.getCapabilities()
      .then((response) => {
        marketDataCapabilities.value = hasMarketDataCapabilities(response) ? response : null
        return marketDataCapabilities.value
      })
      .catch(() => {
        // A pre-197 or temporarily unavailable server cannot grant v2 access.
        // The existing legacy local read remains the only compatibility path.
        marketDataCapabilities.value = null
        return null
      })
      .finally(() => {
        marketDataCapabilitiesResolved = true
        marketDataCapabilitiesRequest = null
      })
    return marketDataCapabilitiesRequest
  }

  function assetLabel(assetType: MarketAssetType) {
    return t(assetTabs.find((asset) => asset.key === assetType)?.labelKey || 'dataMgmt.assetStock')
  }

  function setAssetType(assetType: MarketAssetType) {
    if (applyAssetType(assetType)) {
      void loadInstrumentOptions(formSymbolText())
      void loadCoverageMatrix()
      void lookupInstrument('local_only')
    }
  }

  function applyRouteTab(tabValue: unknown, resetResult: boolean) {
    const assetType = routeTabMap[String(tabValue || '').toLowerCase()]
    if (!assetType) return false
    return applyAssetType(assetType, resetResult)
  }

  function applyAssetType(assetType: MarketAssetType, resetResult = true) {
    const changed = form.asset_type !== assetType
    if (changed) invalidateMarketDataQueryLifecycle()
    form.asset_type = assetType
    restoreAssetSelection(assetType)
    if (changed) {
      // Product selection never crosses asset tabs. Keeping it explicit avoids
      // a ready family on the next tab silently inheriting a prior tab's mode.
      selectedFamilyId.value = defaultFamilyId(assetType)
      referenceSeriesResult.value = null
      genericObservationResult.value = null
      clearMarketDataFamilyScopedState(selectedFamilyId.value)
      if (resetResult) result.value = null
    }
    return changed
  }

  function restoreAssetSelection(assetType: MarketAssetType): void {
    const selection = readMarketAssetSelections()[assetType]
    const defaultSymbol = assetTabs.find((tab) => tab.key === assetType)?.defaultSymbol || ''
    form.symbol = selection?.symbol || defaultSymbol
    form.market = assetType === 'futures' ? selection?.market || 'CF' : 'CF'
  }

  function readMarketAssetSelections(): MarketAssetSelections {
    try {
      const raw = localStorage.getItem(MARKET_ASSET_SELECTIONS_STORAGE_KEY)
      if (!raw) return {}
      const parsed = JSON.parse(raw) as Record<string, { symbol?: unknown; market?: unknown }>
      const selections: MarketAssetSelections = {}
      for (const tab of assetTabs) {
        const candidate = parsed[tab.key]
        const symbol = typeof candidate?.symbol === 'string' ? candidate.symbol.trim() : ''
        if (!symbol) continue
        selections[tab.key] = {
          symbol,
          market: typeof candidate?.market === 'string' ? candidate.market.trim() : undefined,
        }
      }
      return selections
    } catch {
      return {}
    }
  }

  function rememberMarketAssetSelection(assetType: MarketAssetType, symbol: string, market?: string): void {
    try {
      const selections = readMarketAssetSelections()
      selections[assetType] = {
        symbol,
        ...(assetType === 'futures' && market ? { market } : {}),
      }
      localStorage.setItem(MARKET_ASSET_SELECTIONS_STORAGE_KEY, JSON.stringify(selections))
    } catch {
      // Persistence may be unavailable in private browsing; the query still succeeds.
    }
  }

  function v2FrequencyForLegacyPeriod(period: string): MarketDataQueryFrequency {
    if (period === 'weekly') return '1w'
    if (period === 'monthly') return '1mo'
    if (['5min', '30min', '1h', '1d', '1w', '1mo', 'snapshot'].includes(period)) {
      return period as MarketDataQueryFrequency
    }
    return '1d'
  }

  function marketPagePeriodForV2Frequency(frequency: MarketDataQueryFrequency): string {
    return legacyPeriodForV2Frequency(frequency) || frequency
  }

  function legacyPeriodForV2Frequency(frequency: string): string | null {
    if (frequency === '1d') return 'daily'
    if (frequency === '1w') return 'weekly'
    if (frequency === '1mo') return 'monthly'
    if (frequency === '5min' || frequency === '30min' || frequency === '1h' || frequency === 'snapshot') {
      return frequency
    }
    return null
  }

  function periodLabelKey(period: string): string {
    const keys: Record<string, string> = {
      daily: 'dataMgmt.periodDaily',
      weekly: 'dataMgmt.periodWeekly',
      monthly: 'dataMgmt.periodMonthly',
      '5min': 'dataMgmt.periodFiveMinutes',
      '30min': 'dataMgmt.periodThirtyMinutes',
      '1h': 'dataMgmt.periodHourly',
      '1d': 'dataMgmt.periodDaily',
      '1w': 'dataMgmt.periodWeekly',
      '1mo': 'dataMgmt.periodMonthly',
      snapshot: 'dataMgmt.periodSnapshot',
    }
    return keys[period] || period
  }

  function resetToDeclaredPeriod(
    family: MarketDataQueryBundleFamily,
  ): string | null {
    for (const frequency of family.frequencies) {
      const period = legacyPeriodForV2Frequency(frequency)
      if (period) return period
    }
    return null
  }

  function queryWindowFromDateRange(
    requestedDateRange: readonly [string | undefined, string | undefined] = dateRange.value,
  ): { start: string; end: string } | null {
    const [startDate, endDate] = requestedDateRange
    if (!startDate || !endDate) return null
    const start = new Date(`${startDate}T00:00:00.000Z`)
    const endInclusive = new Date(`${endDate}T00:00:00.000Z`)
    if (Number.isNaN(start.getTime()) || Number.isNaN(endInclusive.getTime()) || start > endInclusive) {
      return null
    }
    endInclusive.setUTCDate(endInclusive.getUTCDate() + 1)
    return { start: start.toISOString(), end: endInclusive.toISOString() }
  }

  function isGenericObservationFamily(
    family: Pick<MarketDataQueryBundleFamily, 'data_kind'> | null | undefined,
  ): boolean {
    return family != null
      && family.data_kind !== 'bars'
      && family.data_kind !== 'reference_series'
  }

  function parseDateInputAsUtc(value: string | undefined): Date | null {
    if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
    const parsed = new Date(`${value}T00:00:00.000Z`)
    if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) return null
    return parsed
  }

  function utcDateInput(value: Date): string {
    return value.toISOString().slice(0, 10)
  }

  /**
   * Keep generic snapshot/report windows within the current public API cap.
   * The UI uses inclusive dates while the request uses [start, end), hence a
   * seven-day API interval is represented by end minus six calendar days.
   */
  function boundedGenericObservationDateRange(
    requestedDateRange: readonly [string | undefined, string | undefined],
  ): [string, string] {
    const end = parseDateInputAsUtc(requestedDateRange[1]) || new Date()
    end.setUTCHours(0, 0, 0, 0)
    let start = parseDateInputAsUtc(requestedDateRange[0])
    if (!start || start > end) start = new Date(end)

    const earliestAllowedStart = new Date(end)
    earliestAllowedStart.setUTCDate(
      earliestAllowedStart.getUTCDate() - (GENERIC_OBSERVATION_MAX_WINDOW_DAYS - 1),
    )
    if (start < earliestAllowedStart) start = earliestAllowedStart

    return [utcDateInput(start), utcDateInput(end)]
  }

  function constrainDateRangeForFamily(
    family: Pick<MarketDataQueryBundleFamily, 'data_kind'> | null | undefined,
    requestedDateRange: readonly [string | undefined, string | undefined] = dateRange.value,
  ): readonly [string | undefined, string | undefined] {
    if (!isGenericObservationFamily(family)) return requestedDateRange
    const bounded = boundedGenericObservationDateRange(requestedDateRange)
    if (dateRange.value?.[0] !== bounded[0] || dateRange.value?.[1] !== bounded[1]) {
      dateRange.value = bounded
    }
    return bounded
  }

  function queryContractForCurrentLookup(
    lookupResult: MarketInstrumentLookupResponse | null,
    assetType: MarketAssetType,
    symbol: string,
    period = form.period,
  ): MarketDataQueryContract | null {
    if (!lookupResult || lookupResult.asset_type !== assetType) return null
    const expectedSymbol = symbol.trim()
    if (lookupResult.symbol.trim() !== expectedSymbol) return null
    const contract = queryContractForCurrentPeriod(
      lookupResult.query_contract,
      `${assetType}.realtime`,
      'bars',
      period,
    )
    if (!contract) return null
    if (
      typeof lookupResult.query_contract_symbol !== 'string'
      || lookupResult.query_contract_symbol.trim() !== expectedSymbol
      || typeof lookupResult.query_contract_canonical_id !== 'string'
      || lookupResult.query_contract_canonical_id !== contract.request.identity.canonical_id
    ) {
      return null
    }
    return contract
  }

  function queryContractForCurrentPeriod(
    contract: unknown,
    expectedFamilyId: string,
    expectedDataKind: MarketDataQueryBundleFamily['data_kind'] = 'bars',
    period = form.period,
  ): MarketDataQueryContract | null {
    if (!hasMarketDataQueryContract(contract)) return null
    const request = contract.request
    if (
      request.data_kind !== expectedDataKind
      || request.frequency !== v2FrequencyForLegacyPeriod(period)
      || request.family_id !== expectedFamilyId
      || request.family_contract_version !== 'market-data-family-v1'
    ) {
      return null
    }
    return contract
  }

  function familyFromQueryBundle(
    bundle: MarketDataQueryBundle,
    familyId: string,
  ): MarketDataQueryBundleFamily | null {
    return bundle.families.find((family) => family.family_id === familyId) || null
  }

  function defaultFamilyId(assetType: MarketAssetType): string {
    return `${assetType}.realtime`
  }

  function isMarketPageSelectableFamily(
    family: MarketDataQueryBundleFamily,
    assetType: MarketAssetType,
  ): boolean {
    return family.asset_type === assetType
      && isMarketDataQueryBundleFamilyExecutable(family)
  }

  function selectedMarketPageFamilyFromQueryBundle(
    bundle: MarketDataQueryBundle,
    assetType: MarketAssetType,
    familyId: string,
  ): MarketDataQueryBundleFamily | null {
    // A bundle is only a static control plane. The current choice must match
    // a safe, exact family ID; a new ready entry cannot take over by ordering.
    const family = familyFromQueryBundle(bundle, familyId)
    return family && isMarketPageSelectableFamily(family, assetType) ? family : null
  }

  function marketPageFamilyLabel(family: MarketDataQueryBundleFamily): string {
    const spec = assetDataFamilySpecs[family.asset_type].find(
      (candidate) => candidate.familyId === family.family_id,
    )
    return spec ? t(spec.labelKey) : family.family_id
  }

  function selectDataFamily(familyId: string): void {
    const bundle = marketDataQueryBundle.value
    const family = bundle && bundle.requested_asset_type === form.asset_type
      ? selectedMarketPageFamilyFromQueryBundle(bundle, form.asset_type, familyId)
      : null
    if (!family) {
      // The DOM exposes only server-issued executable choices. Retain a
      // defensive fallback for programmatic/stale values without inferring
      // another ready family from the bundle.
      const fallbackFamilyId = defaultFamilyId(form.asset_type)
      const changed = selectedFamilyId.value !== fallbackFamilyId
      selectedFamilyId.value = fallbackFamilyId
      referenceSeriesResult.value = null
      genericObservationResult.value = null
      if (changed) {
        invalidateMarketDataQueryLifecycle()
        result.value = null
        clearMarketDataFamilyScopedState(fallbackFamilyId)
      }
      return
    }

    const changed = selectedFamilyId.value !== family.family_id
    selectedFamilyId.value = family.family_id
    referenceSeriesResult.value = null
    genericObservationResult.value = null
    if (changed) {
      // Results are evidence for one exact family. Clearing on every product
      // change prevents prior rows from reaching a different family
      // presentation, including generic snapshot/report tables.
      invalidateMarketDataQueryLifecycle()
      result.value = null
      clearMarketDataFamilyScopedState(family.family_id)
    }

    const requestedFrequency = v2FrequencyForLegacyPeriod(form.period)
    if (!family.frequencies.includes(requestedFrequency)) {
      const resetPeriod = resetToDeclaredPeriod(family)
      if (resetPeriod) form.period = resetPeriod
    }
    // A manual date-picker edit can broaden this again, so lookupInstrument
    // applies the same bound before it freezes a request.
    constrainDateRangeForFamily(family)
  }

  function sameDeclaredFields(left: readonly string[], right: readonly string[]): boolean {
    return left.length === right.length && left.every((field, index) => field === right[index])
  }

  function contractMatchesDeclaredFamily(
    contract: MarketDataQueryContract,
    family: MarketDataQueryBundleFamily,
    period = form.period,
  ): boolean {
    const request = contract.request
    return request.family_id === family.family_id
      && request.family_contract_version === family.family_contract_version
      && request.dataset_code === family.dataset_code
      && request.data_kind === family.data_kind
      && request.frequency === v2FrequencyForLegacyPeriod(period)
      && family.frequencies.includes(request.frequency)
      && sameDeclaredFields(request.required_fields, family.required_fields)
      && family.source_policy_id !== null
      && request.source_policy_id === family.source_policy_id
  }

  async function resolveV2QueryBundle(
    assetType: MarketAssetType,
    enabled: boolean,
  ): Promise<{ bundle: MarketDataQueryBundle | null; fellBack: boolean }> {
    if (!enabled) {
      return { bundle: null, fellBack: false }
    }
    try {
      const bundle = await marketDataApi.getQueryBundle({ asset_type: assetType })
      if (
        !hasMarketDataQueryBundle(bundle)
        || bundle.requested_asset_type !== assetType
        || bundle.families.some((family) => family.asset_type !== assetType)
      ) {
        throw new Error('MARKET_DATA_QUERY_BUNDLE_INVALID')
      }
      return { bundle, fellBack: false }
    } catch (error) {
      if (isMarketDataQueryV2FallbackError(error)) {
        return { bundle: null, fellBack: true }
      }
      throw error
    }
  }

  async function resolveV2QueryContract(
    assetType: MarketAssetType,
    symbol: string,
    period: string,
    declaredFamily: MarketDataQueryBundleFamily | null = null,
  ): Promise<{ contract: MarketDataQueryContract | null; fellBack: boolean }> {
    const expectedFamilyId = declaredFamily?.family_id || `${assetType}.realtime`
    try {
      const contract = await marketDataApi.getQueryContract({
        asset_type: assetType,
        symbol,
        period: period as MarketDataQueryContractParams['period'],
        family_id: expectedFamilyId,
      })
      const currentContract = queryContractForCurrentPeriod(
        contract,
        expectedFamilyId,
        declaredFamily?.data_kind || 'bars',
        period,
      )
      if (
        !currentContract
        || (declaredFamily && !contractMatchesDeclaredFamily(currentContract, declaredFamily, period))
      ) {
        throw new Error('MARKET_DATA_QUERY_CONTRACT_INVALID')
      }
      return { contract: currentContract, fellBack: false }
    } catch (error) {
      if (isMarketDataQueryV2FallbackError(error)) {
        return { contract: null, fellBack: true }
      }
      throw error
    }
  }

  function lookupShellForV2Query(
    assetType: MarketAssetType,
    symbol: string,
    market: string,
    contract: MarketDataQueryContract | null,
    period = form.period,
  ): MarketInstrumentLookupResponse {
    return {
      asset_type: assetType,
      symbol,
      name: symbol,
      market: market || null,
      provider: contract ? 'local_market_data' : null,
      query_contract: contract,
      query_contract_symbol: contract ? symbol : null,
      query_contract_canonical_id: contract ? contract.request.identity.canonical_id : null,
      snapshot: {},
      history: {
        period,
        rows: [],
        total: 0,
      },
      indicators: {},
      warnings: [],
    }
  }

  function v2HistoryRows(
    response: MarketDataQueryResponse,
    requiredFields: readonly string[] = ['close'],
  ): MarketHistoryRow[] {
    return response.observations
      // The API must already enforce this invariant.  Keep the display
      // boundary fail-closed as well so a malformed intermediary response can
      // never turn a missing required bar field into a synthetic chart value.
      .filter((observation) => (
        observation.quality === 'pass'
        && requiredFields.every((field) => (
          isFiniteNumber(numericValue(observation.fields[field], null))
        ))
      ))
      .map((observation) => ({
        ...observation.fields,
        date: v2EventTimeLabel(observation.event_at, response.frequency),
      }))
      .sort((left, right) => historyRowTimestamp(left) - historyRowTimestamp(right))
  }

  function referenceSeriesRowsFromV2Response(
    response: MarketDataQueryResponse,
    requiredFields: readonly string[],
  ): MarketHistoryRow[] {
    if (response.data_kind !== 'reference_series') {
      throw new Error('MARKET_DATA_REFERENCE_SERIES_KIND_INVALID')
    }
    return response.observations
      // Reference series are not bars. Keep only passing observations, then
      // project exactly the server-issued required fields rather than relying
      // on a close price or carrying provider-only extras into the UI.
      .filter((observation) => (
        observation.quality === 'pass'
        && requiredFields.every((field) => isUsableReferenceSeriesValue(observation.fields[field]))
      ))
      .map((observation) => ({
        date: v2EventTimeLabel(observation.event_at, response.frequency),
        ...Object.fromEntries(requiredFields.map((field) => [field, observation.fields[field]])),
      }))
      .sort((left, right) => historyRowTimestamp(left) - historyRowTimestamp(right))
  }

  function genericObservationResultFromV2Response(
    response: MarketDataQueryResponse,
    family: MarketDataQueryBundleFamily,
  ): GenericObservationResult {
    if (response.data_kind === 'bars' || response.data_kind === 'reference_series') {
      throw new Error('MARKET_DATA_GENERIC_PRESENTATION_KIND_INVALID')
    }
    if (
      !isGenericObservationFamily(family)
      || family.status !== 'ready'
      || family.source_policy_id === null
      || family.reason_code !== null
      || response.family_id !== family.family_id
      || response.data_kind !== family.data_kind
      || response.dataset_code !== family.dataset_code
      || response.source_policy_id !== family.source_policy_id
    ) {
      throw new Error('MARKET_DATA_GENERIC_FAMILY_BINDING_INVALID')
    }
    const allowedFields = [...family.dimension_fields, ...family.required_fields]
    if (new Set(allowedFields).size !== allowedFields.length) {
      throw new Error('MARKET_DATA_GENERIC_FIELD_DECLARATION_INVALID')
    }
    const observations = response.observations.map((observation) => ({
      ...observation,
      // The result transport can retain source-specific fields for audit
      // tooling. The generic market page must never display them: every field
      // cell comes from the reviewed family dimensions/required-fields only.
      fields: Object.fromEntries(
        allowedFields
          .filter((field) => Object.prototype.hasOwnProperty.call(observation.fields, field))
          .map((field) => [field, observation.fields[field]]),
      ),
    }))
    for (const observation of observations) {
      if (observation.quality !== 'pass') continue
      if (!allowedFields.every((field) => isUsableReferenceSeriesValue(observation.fields[field]))) {
        throw new Error('MARKET_DATA_GENERIC_DECLARED_FIELDS_INVALID')
      }
    }
    return {
      familyId: response.family_id,
      dataKind: response.data_kind,
      requiredFields: [...family.required_fields],
      dimensionFields: [...family.dimension_fields],
      observations,
    }
  }

  function isUsableReferenceSeriesValue(value: unknown): boolean {
    if (!hasValue(value)) return false
    if (typeof value === 'number') return Number.isFinite(value)
    return typeof value !== 'string' || value.trim() !== '--'
  }

  function assertResponseRequiredFields(
    response: MarketDataQueryResponse,
    requiredFields: readonly string[],
  ): void {
    for (const observation of response.observations) {
      if (observation.quality !== 'pass') continue
      const valid = requiredFields.every((field) => (
        response.data_kind === 'bars'
          ? isFiniteNumber(numericValue(observation.fields[field], null))
          : isUsableReferenceSeriesValue(observation.fields[field])
      ))
      if (!valid) throw new Error('MARKET_DATA_QUERY_REQUIRED_FIELDS_INVALID')
    }
  }

  function v2EventTimeLabel(value: string, frequency: string): string {
    const timestamp = new Date(value)
    if (Number.isNaN(timestamp.getTime())) return value
    const iso = timestamp.toISOString()
    return ['1d', '1w', '1mo'].includes(frequency) ? iso.slice(0, 10) : iso
  }

  function lookupFromV2Response(
    response: MarketDataQueryResponse,
    legacyLookup: MarketInstrumentLookupResponse,
    requiredFields: readonly string[] = ['close'],
  ): MarketInstrumentLookupResponse {
    const rows = v2HistoryRows(response, requiredFields)
    const latestRow = rows[rows.length - 1]
    const latestFields: Record<string, unknown> = latestRow ? { ...latestRow } : {}
    delete latestFields.date
    const closeValues = numericSeries(rows, 'close')
    const volumeValues = numericSeries(rows, 'volume')
    const latestClose = closeValues[closeValues.length - 1] ?? null
    const lastFetch = response.fetches[response.fetches.length - 1]
    const lastObservation = response.observations[response.observations.length - 1]
    const provider = lastFetch?.provider_id || legacyLookup.provider || 'local_market_data'
    const warnings = response.warnings.map((warning) => warning.code)

    return {
      ...legacyLookup,
      asset_type: response.asset_type,
      provider,
      snapshot: {
        ...legacyLookup.snapshot,
        ...latestFields,
        price: numericValue(latestFields.price ?? latestFields.close, legacyLookup.snapshot.price ?? null),
        update_time: lastObservation?.available_at || legacyLookup.snapshot.update_time,
        data_source_table: response.dataset_code,
      },
      history: {
        period: form.period,
        rows,
        total: rows.length,
      },
      indicators: {
        latest_close: latestClose,
        return_pct: periodReturnPct(closeValues),
        highest_close: closeValues.length ? Math.max(...closeValues) : null,
        lowest_close: closeValues.length ? Math.min(...closeValues) : null,
        avg_volume: averageNumbers(volumeValues),
        observation_count: rows.length,
      },
      warnings,
    }
  }

  function lookupFromReferenceSeriesResponse(
    response: MarketDataQueryResponse,
    legacyLookup: MarketInstrumentLookupResponse,
    rows: MarketHistoryRow[],
  ): MarketInstrumentLookupResponse {
    const latestRow = rows[rows.length - 1]
    const latestFields: Record<string, unknown> = latestRow ? { ...latestRow } : {}
    delete latestFields.date
    const lastFetch = response.fetches[response.fetches.length - 1]
    const lastObservation = response.observations
      .filter((observation) => observation.quality === 'pass')
      .sort((left, right) => Date.parse(left.event_at) - Date.parse(right.event_at))
      .at(-1)
    const provider = lastFetch?.provider_id || 'local_market_data'
    const warnings = response.warnings.map((warning) => warning.code)

    return {
      ...legacyLookup,
      asset_type: response.asset_type,
      provider,
      snapshot: {
        ...latestFields,
        // This presentation is intentionally derived from the exact
        // reference-series response. In particular, do not retain an earlier
        // legacy price or snapshot timestamp as evidence for this family.
        update_time: lastObservation?.available_at,
        data_source_table: response.dataset_code,
      },
      history: {
        period: form.period,
        rows,
        total: rows.length,
      },
      indicators: {
        observation_count: rows.length,
        avg_volume: averageNumbers(numericSeries(rows, 'volume')),
      },
      warnings,
    }
  }

  function lookupFromGenericObservationResponse(
    response: MarketDataQueryResponse,
    legacyLookup: MarketInstrumentLookupResponse,
  ): MarketInstrumentLookupResponse {
    const lastFetch = response.fetches[response.fetches.length - 1]
    const lastPassingObservation = response.observations
      .filter((observation) => observation.quality === 'pass')
      .sort((left, right) => Date.parse(left.event_at) - Date.parse(right.event_at))
      .at(-1)
    const provider = lastFetch?.provider_id || 'local_market_data'

    return {
      ...legacyLookup,
      asset_type: response.asset_type,
      provider,
      // Do not derive a generic product's snapshot, price, or K-line history
      // from similarly named provider fields. The generic table is the only
      // presentation of those facts until a reviewed product renderer exists.
      snapshot: {
        update_time: lastPassingObservation?.available_at,
        data_source_table: response.dataset_code,
      },
      history: {
        period: form.period,
        rows: [],
        total: 0,
      },
      indicators: {
        observation_count: response.observations.length,
      },
      warnings: response.warnings.map((warning) => warning.code),
    }
  }

  /**
   * The v2 response schema already exposes these as public provenance fields.
   * Vue escapes rendered text, but control characters would make the status
   * panel misleading. Keep the canonical-identity length accepted by the API
   * instead of imposing a narrower presentation-only identifier grammar.
   */
  function publicMarketDataProvenanceValue(value: unknown): string | null {
    if (typeof value !== 'string') return null
    const normalized = value.trim()
    if (!normalized || normalized.length > 512) return null
    const containsControlCharacter = Array.from(normalized).some(character => {
      const codePoint = character.codePointAt(0) || 0
      return codePoint <= 31 || codePoint === 127
    })
    return containsControlCharacter ? null : normalized
  }

  function setLegacyMarketDataPlatformStatus(fallbackReason: string | null = null) {
    marketDataPlatformStatus.value = {
      path: fallbackReason ? 'legacy_fallback' : 'legacy',
      provider: null,
      coverageStatus: null,
      coverageRatio: null,
      fetchedProviderCount: 0,
      fallbackReason,
      queryId: null,
      canonicalId: null,
      datasetCode: null,
      sourcePolicyId: null,
      instrumentMetadataVersion: null,
      familyId: null,
      periodConstraint: null,
    }
  }

  function setMarketDataPlatformErrorStatus() {
    marketDataPlatformStatus.value = {
      path: 'error',
      provider: null,
      coverageStatus: null,
      coverageRatio: null,
      fetchedProviderCount: 0,
      fallbackReason: null,
      queryId: null,
      canonicalId: null,
      datasetCode: null,
      sourcePolicyId: null,
      instrumentMetadataVersion: null,
      familyId: null,
      periodConstraint: null,
    }
  }

  /**
   * Query facts and provenance are scoped to one immutable family binding.
   * Clear every prior receipt-derived axis as soon as the family changes so a
   * previous bars/snapshot response cannot be displayed as evidence for the
   * newly selected product.
   */
  function clearMarketDataFamilyScopedState(familyId: string | null) {
    marketDataPlatformStatus.value = {
      path: 'family_selection_pending',
      provider: null,
      coverageStatus: null,
      coverageRatio: null,
      fetchedProviderCount: 0,
      fallbackReason: null,
      queryId: null,
      canonicalId: null,
      datasetCode: null,
      sourcePolicyId: null,
      instrumentMetadataVersion: null,
      familyId,
      periodConstraint: null,
    }
  }

  function setMarketDataBundleUnconfiguredStatus(familyId: string | null = null) {
    marketDataPlatformStatus.value = {
      path: 'bundle_unconfigured',
      provider: null,
      coverageStatus: null,
      coverageRatio: null,
      fetchedProviderCount: 0,
      fallbackReason: null,
      queryId: null,
      canonicalId: null,
      datasetCode: null,
      sourcePolicyId: null,
      instrumentMetadataVersion: null,
      familyId,
      periodConstraint: null,
    }
  }

  function setMarketDataBundlePeriodUnsupportedStatus(
    family: MarketDataQueryBundleFamily,
    requestedFrequency: string,
    resetPeriod: string | null,
  ) {
    marketDataPlatformStatus.value = {
      path: 'bundle_period_unsupported',
      provider: null,
      coverageStatus: null,
      coverageRatio: null,
      fetchedProviderCount: 0,
      fallbackReason: null,
      queryId: null,
      canonicalId: null,
      datasetCode: null,
      sourcePolicyId: null,
      instrumentMetadataVersion: null,
      familyId: family.family_id,
      periodConstraint: {
        familyId: family.family_id,
        requestedFrequency,
        declaredFrequencies: [...family.frequencies],
        resetPeriod,
      },
    }
  }

  function hasIncompleteCoverageStatus(path: MarketDataPlatformStatus['path']): boolean {
    return path === 'local_coverage_incomplete' || path === 'provider_persisted_incomplete'
  }

  function setV2MarketDataPlatformStatus(
    response: MarketDataQueryResponse,
    queryMode: MarketDataQueryMode,
    capabilities: MarketDataCapabilitiesResponse | null,
  ) {
    const fetches = response.fetches || []
    const incompleteLocalCoverage = response.coverage.status !== 'complete'
    const onlineFetchDisabled = capabilities?.online_fetch_enabled === false
      && response.warnings.some((warning) => warning.code === 'ONLINE_FETCH_DISABLED')
    const incompleteFallbackReason = queryMode === 'local_only'
      ? 'LOCAL_ONLY_COVERAGE_INCOMPLETE'
      : onlineFetchDisabled ? 'ONLINE_FETCH_DISABLED' : 'LOCAL_COVERAGE_INCOMPLETE'
    marketDataPlatformStatus.value = {
      path: incompleteLocalCoverage
        ? fetches.length ? 'provider_persisted_incomplete' : 'local_coverage_incomplete'
        : queryMode === 'local_only'
          ? 'local_only'
          : fetches.length ? 'provider_persisted' : 'local_first',
      provider: fetches[fetches.length - 1]?.provider_id || null,
      coverageStatus: response.coverage.status,
      coverageRatio: response.coverage.coverage_ratio,
      fetchedProviderCount: fetches.length,
      fallbackReason: incompleteLocalCoverage
        ? incompleteFallbackReason
        : null,
      queryId: response.query_id,
      canonicalId: publicMarketDataProvenanceValue(response.canonical_id),
      datasetCode: publicMarketDataProvenanceValue(response.dataset_code),
      sourcePolicyId: publicMarketDataProvenanceValue(response.source_policy_id),
      instrumentMetadataVersion: publicMarketDataProvenanceValue(response.instrument_metadata_version),
      familyId: publicMarketDataProvenanceValue(response.family_id),
      periodConstraint: null,
    }
  }

  async function queryV2FromLookupContract(
    contract: MarketDataQueryContract,
    legacyLookup: MarketInstrumentLookupResponse,
    queryMode: MarketDataQueryMode = 'local_first',
    requestedDateRange: readonly [string | undefined, string | undefined] = dateRange.value,
    declaredFamily: MarketDataQueryBundleFamily | null = null,
    signal?: AbortSignal,
  ): Promise<V2LookupResult> {
    const window = queryWindowFromDateRange(requestedDateRange)
    if (!window) throw new Error('MARKET_DATA_QUERY_WINDOW_INVALID')

    const response = await queryAllV2MarketDataPages(
      createMarketDataQueryFromContract(contract, {
        ...window,
        mode: queryMode,
        purpose: 'display',
        consistency: 'display',
        page_size: V2_MARKET_DATA_PAGE_SIZE,
      }),
      legacyLookup.asset_type,
      signal,
    )
    assertResponseRequiredFields(response, contract.request.required_fields)
    if (contract.request.data_kind === 'reference_series') {
      const rows = referenceSeriesRowsFromV2Response(response, contract.request.required_fields)
      return {
        response,
        referenceSeries: {
          familyId: contract.request.family_id,
          requiredFields: [...contract.request.required_fields],
          rows,
        },
        lookup: lookupFromReferenceSeriesResponse(response, legacyLookup, rows),
        genericObservations: null,
      }
    }
    if (contract.request.data_kind === 'bars') {
      return {
        response,
        referenceSeries: null,
        genericObservations: null,
        lookup: lookupFromV2Response(response, legacyLookup, contract.request.required_fields),
      }
    }
    // Generic observations need the bundle's declared dimension fields. A
    // standalone contract has no such axis, so refusing it prevents a
    // response from choosing arbitrary browser columns through provider data.
    if (!declaredFamily || !contractMatchesDeclaredFamily(contract, declaredFamily)) {
      throw new Error('MARKET_DATA_GENERIC_FAMILY_CONTRACT_UNAVAILABLE')
    }
    const genericObservations = genericObservationResultFromV2Response(response, declaredFamily)
    return {
      response,
      referenceSeries: null,
      genericObservations,
      lookup: lookupFromGenericObservationResponse(response, legacyLookup),
    }
  }

  function assertMarketDataResponseEcho(
    response: MarketDataQueryResponse,
    request: ReturnType<typeof createMarketDataQueryFromContract>,
    expectedAssetType: MarketAssetType,
  ): void {
    if (
      response.family_id !== request.family_id
      || response.family_contract_version !== request.family_contract_version
      || response.canonical_id !== request.identity.canonical_id
      || response.dataset_code !== request.dataset_code
      || response.asset_type !== expectedAssetType
      || response.data_kind !== request.data_kind
      || response.frequency !== request.frequency
      || response.source_policy_id !== request.source_policy_id
    ) {
      throw new Error('MARKET_DATA_QUERY_RESPONSE_INTEGRITY')
    }
  }

  async function queryAllV2MarketDataPages(
    initialRequest: ReturnType<typeof createMarketDataQueryFromContract>,
    expectedAssetType: MarketAssetType,
    signal?: AbortSignal,
  ): Promise<MarketDataQueryResponse> {
    /**
     * Read every frozen cursor page or fail visibly instead of truncating history.
     *
     * The server fixes a cursor to the first page's local knowledge cutoff and
     * never fetches a provider for cursor pages. Keeping the original request
     * semantics while adding only the cursor therefore preserves the local-first
     * result without silently dropping history past the first response page.
     */
    const first = await marketDataApi.queryLocalFirst(
      initialRequest,
      { signal, suppressErrorMessage: true },
    )
    throwIfMarketDataQueryAborted(signal)
    assertMarketDataResponseEcho(first, initialRequest, expectedAssetType)
    const observations = [...first.observations]
    const warnings = [...first.warnings]
    const observationIds = new Set(first.observations.map((item) => item.revision_id))
    const cursors = new Set<string>()
    let cursor = first.next_cursor

    while (cursor) {
      throwIfMarketDataQueryAborted(signal)
      if (cursors.has(cursor)) {
        throw new Error('MARKET_DATA_CURSOR_PAGINATION_INTEGRITY')
      }
      cursors.add(cursor)
      const page = await marketDataApi.queryLocalFirst(
        { ...initialRequest, cursor },
        { signal, suppressErrorMessage: true },
      )
      throwIfMarketDataQueryAborted(signal)
      assertMarketDataResponseEcho(page, initialRequest, expectedAssetType)
      if (
        page.query_id !== first.query_id
        || page.knowledge_cutoff !== first.knowledge_cutoff
        || page.identity_knowledge_cutoff !== first.identity_knowledge_cutoff
      ) {
        throw new Error('MARKET_DATA_CURSOR_PAGINATION_INTEGRITY')
      }
      for (const observation of page.observations) {
        if (observationIds.has(observation.revision_id)) {
          throw new Error('MARKET_DATA_CURSOR_PAGINATION_INTEGRITY')
        }
        observationIds.add(observation.revision_id)
        observations.push(observation)
      }
      warnings.push(...page.warnings)
      cursor = page.next_cursor
    }

    return {
      ...first,
      observations,
      next_cursor: null,
      warnings,
    }
  }

  function throwIfMarketDataQueryAborted(signal?: AbortSignal): void {
    if (signal?.aborted) throw new Error('MARKET_DATA_QUERY_ABORTED')
  }

  async function lookupInstrument(intent: MarketLookupIntent = 'local_first') {
    // ``true``/``false`` were the pre-197 exposed refresh argument. Preserve
    // that boundary for existing callers while making lifecycle/UI calls name
    // their exact query intent.
    const queryMode: MarketDataQueryMode = intent === true
      ? 'refresh'
      : intent === false ? 'local_first' : intent
    const refreshOnline = queryMode === 'refresh'
    const requestedSymbol = formSymbolText()
    if (!requestedSymbol) {
      ElMessage.error(t('dataMgmt.msgSymbolRequired'))
      return
    }
    // The current bundle is only a presentation control plane, but it is
    // sufficient to prevent a user-edited 90-day picker range from reaching
    // the public seven-day cap for a selected generic snapshot/report family.
    constrainDateRangeForFamily(selectedMarketPageFamily.value)
    const {
      controller: lifecycleController,
      requestId,
      selectionKey,
    } = beginMarketDataQueryLifecycle()
    const { signal } = lifecycleController
    // Element Plus may set the bound range to null when the picker is
    // cleared. Preserve that as an invalid v2 window / omitted legacy range
    // rather than indexing it while freezing the request.
    const currentDateRange = Array.isArray(dateRange.value) ? dateRange.value : []
    const requestSnapshot: MarketLookupRequestSnapshot = {
      assetType: form.asset_type,
      symbol: requestedSymbol,
      market: form.asset_type === 'futures' ? formMarketText() : '',
      period: form.period,
      dateRange: [currentDateRange[0], currentDateRange[1]],
      familyId: selectedFamilyId.value,
    }
    const {
      assetType: queryAssetType,
      symbol,
      market: queryMarket,
      period: queryPeriod,
      familyId: requestedFamilyId,
    } = requestSnapshot
    let queryStartDate = requestSnapshot.dateRange[0]
    let queryEndDate = requestSnapshot.dateRange[1]
    const requestedNonDefaultFamily = requestedFamilyId !== defaultFamilyId(queryAssetType)
    // A response is evidence for the exact request, not merely its asset and
    // family. If any visible selector changes while an async stage is pending,
    // discard the result instead of relabelling it as the new request.
    const isCurrentFamilyLookup = () => (
      requestId === lookupRequestId
      && activeMarketDataQueryAbortController === lifecycleController
      && activeMarketDataQuerySelectionKey === selectionKey
      && !signal.aborted
      && form.asset_type === queryAssetType
      && formSymbolText() === symbol
      && (queryAssetType !== 'futures' || formMarketText() === queryMarket)
      && form.period === queryPeriod
      && dateRange.value?.[0] === queryStartDate
      && dateRange.value?.[1] === queryEndDate
      && selectedFamilyId.value === requestedFamilyId
    )
    // Capability lookup is an asynchronous control-plane request. Freeze the
    // data request before awaiting it so edits made during initial page load
    // cannot turn the old lookup into a provider request for the new form.
    const capabilities = await resolveMarketDataCapabilities()
    if (!isCurrentFamilyLookup()) {
      if (!signal.aborted) lifecycleController.abort()
      releaseMarketDataQueryLifecycle(lifecycleController)
      return
    }
    const v2FeatureEnabled = isMarketDataQueryV2FeatureEnabled(capabilities)
    if (isReferenceSeriesSelected.value || isGenericObservationSelected.value) {
      // A newly requested non-bar family must never leave a prior K-line or
      // generic observation table visible while its own exact contract is
      // being resolved.
      result.value = null
      referenceSeriesResult.value = null
      genericObservationResult.value = null
    }
    const existingContract = v2FeatureEnabled
      ? queryContractForCurrentLookup(result.value, queryAssetType, symbol, queryPeriod)
      : null
    const bundleFeatureEnabled = isMarketDataQueryBundleFeatureEnabled(capabilities)
    if (bundleFeatureEnabled) marketDataQueryBundle.value = null
    loading.value = true
    try {
      let directContract = existingContract
      let directLookup = existingContract && result.value
        ? result.value
        : null
      let v2Fallback = false
      let bundleIssued = false
      let declaredFamily: MarketDataQueryBundleFamily | null = null

      // The family bundle is a server-owned control-plane declaration. Once
      // accepted, missing/unconfigured families must not be inferred from a
      // legacy lookup, and a failed v2 bridge remains visible rather than
      // activating that compatibility path.
      if (bundleFeatureEnabled) {
        const bundleResolution = await resolveV2QueryBundle(queryAssetType, bundleFeatureEnabled)
        if (!isCurrentFamilyLookup()) return
        v2Fallback = bundleResolution.fellBack
        if (!bundleResolution.bundle && requestedNonDefaultFamily) {
          // A non-default family exists only because a prior server-owned
          // bundle explicitly declared it. If that control plane disappears,
          // never silently retarget the request to asset.realtime or legacy.
          throw new Error('MARKET_DATA_QUERY_BUNDLE_UNAVAILABLE_AFTER_FAMILY_SELECTION')
        }
        if (bundleResolution.bundle) {
          bundleIssued = true
          marketDataQueryBundle.value = bundleResolution.bundle
          declaredFamily = selectedMarketPageFamilyFromQueryBundle(
            bundleResolution.bundle,
            queryAssetType,
            requestedFamilyId,
          )
          if (!declaredFamily) {
            result.value = lookupShellForV2Query(
              queryAssetType,
              symbol,
              queryMarket,
              null,
              queryPeriod,
            )
            relatedTables.value = []
            setMarketDataBundleUnconfiguredStatus(requestedFamilyId)
            rememberMarketAssetSelection(queryAssetType, symbol, queryMarket)
            return
          }
          if (isGenericObservationFamily(declaredFamily)) {
            // Reapply the bound against the freshly issued family document in
            // case the prior bundle was stale while a lookup was in flight.
            const boundedRange = constrainDateRangeForFamily(
              declaredFamily,
              requestSnapshot.dateRange,
            )
            requestSnapshot.dateRange = [boundedRange[0], boundedRange[1]]
            queryStartDate = boundedRange[0]
            queryEndDate = boundedRange[1]
          }
          const requestedFrequency = v2FrequencyForLegacyPeriod(queryPeriod)
          if (!declaredFamily.frequencies.includes(requestedFrequency)) {
            const resetPeriod = resetToDeclaredPeriod(declaredFamily)
            if (resetPeriod) form.period = resetPeriod
            // Preserve the existing result. The user can see the declared
            // cadence and issue a new query after the selector has been
            // constrained; this must never use a legacy fallback merely to
            // satisfy an unsupported weekly/monthly request.
            setMarketDataBundlePeriodUnsupportedStatus(
              declaredFamily,
              requestedFrequency,
              resetPeriod,
            )
            rememberMarketAssetSelection(queryAssetType, symbol, queryMarket)
            return
          }
          // Re-resolve the exact symbol contract after the static control
          // plane has been issued. A contract attached to an earlier legacy
          // response may have been created under an older capability state.
          directContract = null
          directLookup = null
        }
      }

      // The contract endpoint is intentionally read-only: it verifies an
      // exact imported canonical identity and active dataset without asking a
      // provider for data. This lets the first page request enter v2 without
      // an online legacy lookup.
      if (v2FeatureEnabled && !directContract) {
        const resolution = await resolveV2QueryContract(
          queryAssetType,
          symbol,
          queryPeriod,
          declaredFamily,
        )
        if (!isCurrentFamilyLookup()) return
        directContract = resolution.contract
        v2Fallback = v2Fallback || resolution.fellBack
        if (directContract) {
          directLookup = lookupShellForV2Query(
            queryAssetType,
            symbol,
            queryMarket,
            directContract,
            queryPeriod,
          )
        }
      }

      if (v2FeatureEnabled && directContract && directLookup) {
        const v2Result = await queryV2FromLookupContract(
          directContract,
          directLookup,
          queryMode,
          requestSnapshot.dateRange,
          declaredFamily,
          signal,
        )
        if (!isCurrentFamilyLookup()) return
        // A local-only lifecycle request is proof-bound to the local store.
        // A response claiming a new fetch would contradict that immutable
        // request mode, so do not render it as a cache hit.
        if (queryMode === 'local_only' && v2Result.response.fetches.length > 0) {
          throw new Error('MARKET_DATA_LOCAL_ONLY_FETCH_EVIDENCE')
        }
        setV2MarketDataPlatformStatus(v2Result.response, queryMode, capabilities)
        referenceSeriesResult.value = v2Result.referenceSeries
        genericObservationResult.value = v2Result.genericObservations
        result.value = v2Result.lookup
        rememberMarketAssetSelection(queryAssetType, symbol, queryMarket)
        void loadRelatedTables(v2Result.lookup)
        if (!hasIncompleteCoverageStatus(marketDataPlatformStatus.value.path)) {
          ElMessage.success(t('dataMgmt.msgQueriedCount', {
            count: v2Result.genericObservations?.observations.length ?? v2Result.lookup.history.total,
          }))
        }
        return
      }

      if (bundleIssued) {
        throw new Error('MARKET_DATA_QUERY_CONTRACT_UNAVAILABLE_AFTER_BUNDLE')
      }

      // A legacy online refresh returns an in-memory AkShare payload without
      // the normalized source receipt and re-read required by the local-first
      // contract.  Keep the existing legacy *local* display available during
      // rollout, but never let the page use that non-persistent route for a
      // refresh when no server-issued v2 contract exists.
      if (refreshOnline) {
        setMarketDataPlatformErrorStatus()
        ElMessage.error(t('dataMgmt.msgQueryFail'))
        return
      }

      const legacyResponse = await marketDataApi.lookupInstrument({
        asset_type: queryAssetType,
        symbol,
        period: queryPeriod,
        start_date: queryStartDate,
        end_date: queryEndDate,
        market: queryMarket || undefined,
        // The compatibility facade is a local display read only. A legacy
        // online refresh would return an in-memory payload without the v2
        // persistence receipt, so it is never a fallback for any intent.
        refresh_online: false,
      })
      if (!isCurrentFamilyLookup()) return

      let response = legacyResponse
      // Compatibility bridge for a server that returns a typed contract from
      // the legacy response but has not yet deployed the read-only contract
      // endpoint. The legacy read has already completed; only the v2 call may
      // decide whether this intent is a local-only re-read or a bounded
      // local-first gap fill.
      const bootstrapContract = v2FeatureEnabled && !directContract && !refreshOnline
        ? queryContractForCurrentLookup(legacyResponse, queryAssetType, symbol, queryPeriod)
        : null
      if (
        v2FeatureEnabled
        && !directContract
        && !refreshOnline
        && legacyResponse.query_contract != null
        && !bootstrapContract
      ) {
        throw new Error('MARKET_DATA_LEGACY_QUERY_CONTRACT_INVALID')
      }
      if (bootstrapContract) {
        const v2Result = await queryV2FromLookupContract(
          bootstrapContract,
          legacyResponse,
          queryMode,
          requestSnapshot.dateRange,
          declaredFamily,
          signal,
        )
        if (!isCurrentFamilyLookup()) return
        if (queryMode === 'local_only' && v2Result.response.fetches.length > 0) {
          throw new Error('MARKET_DATA_LOCAL_ONLY_FETCH_EVIDENCE')
        }
        setV2MarketDataPlatformStatus(v2Result.response, queryMode, capabilities)
        referenceSeriesResult.value = v2Result.referenceSeries
        genericObservationResult.value = v2Result.genericObservations
        response = v2Result.lookup
      }
      if (!bootstrapContract && !directContract) {
        setLegacyMarketDataPlatformStatus(v2Fallback ? 'MARKET_DATA_QUERY_V2_UNAVAILABLE' : null)
      }

      result.value = response
      rememberMarketAssetSelection(queryAssetType, symbol, queryMarket)
      void loadRelatedTables(response)
      if (!hasIncompleteCoverageStatus(marketDataPlatformStatus.value.path)) {
        ElMessage.success(t('dataMgmt.msgQueriedCount', { count: response.history.total }))
      }
    } catch {
      if (signal.aborted) return
      if (!isCurrentFamilyLookup()) return
      result.value = null
      referenceSeriesResult.value = null
      genericObservationResult.value = null
      relatedTables.value = []
      setMarketDataPlatformErrorStatus()
      ElMessage.error(t('dataMgmt.msgQueryFail'))
    } finally {
      if (requestId === lookupRequestId) loading.value = false
      releaseMarketDataQueryLifecycle(lifecycleController)
    }
  }

  async function loadCoverageMatrix() {
    const requestId = ++coverageRequestId
    coverageLoading.value = true
    coverageError.value = ''
    try {
      const response = await marketDataApi.listCoverage({
        asset_type: form.asset_type,
        timeframe: coverageTimeframe.value || undefined,
        provider: coverageProvider.value.trim() || undefined,
        limit: 200,
      })
      if (requestId !== coverageRequestId) return
      coverageRows.value = response.items
    } catch {
      if (requestId === coverageRequestId) {
        coverageRows.value = []
        coverageError.value = t('dataMgmt.coverageLoadFailed')
      }
    } finally {
      if (requestId === coverageRequestId) {
        coverageLoading.value = false
      }
    }
  }

  async function refreshCoverageMatrix() {
    coverageRefreshing.value = true
    coverageError.value = ''
    try {
      const response = await marketDataApi.refreshWarehouseCoverage({
        asset_type: form.asset_type,
        timeframe: coverageTimeframe.value || undefined,
        limit: 500,
      })
      coverageRows.value = response.items
      ElMessage.success(t('dataMgmt.coverageRefreshed'))
    } catch {
      coverageError.value = t('dataMgmt.coverageRefreshFailed')
      ElMessage.error(coverageError.value)
    } finally {
      coverageRefreshing.value = false
    }
  }

  function searchInstrumentOptions(query: string) {
    void loadInstrumentOptions(query)
  }

  function handleInstrumentDropdownVisible(visible: boolean) {
    if (visible && !instrumentOptions.value.length) {
      void loadInstrumentOptions(formSymbolText())
    }
  }

  async function loadInstrumentOptions(search = '') {
    const requestId = ++instrumentOptionsRequestId
    const normalizedSearch = String(search || '').trim()
    instrumentOptionsLoading.value = true
    try {
      const response = await marketDataApi.listInstrumentOptions({
        asset_type: form.asset_type,
        search: normalizedSearch,
        limit: 80,
      })
      if (requestId !== instrumentOptionsRequestId) return
      instrumentOptions.value = ensureCurrentInstrumentOption(response.items)
    } catch {
      if (requestId === instrumentOptionsRequestId) {
        instrumentOptions.value = ensureCurrentInstrumentOption([])
      }
    } finally {
      if (requestId === instrumentOptionsRequestId) {
        instrumentOptionsLoading.value = false
      }
    }
  }

  function ensureCurrentInstrumentOption(options: MarketInstrumentOption[]) {
    const currentSymbol = formSymbolText()
    if (!currentSymbol) return options
    if (options.some((option) => option.symbol === currentSymbol)) return options
    return [
      {
        asset_type: form.asset_type,
        symbol: currentSymbol,
        name: currentSymbol,
        market: form.asset_type === 'futures' ? formMarketText() || 'CF' : undefined,
        source_table: null,
        latest_date: null,
        has_snapshot: false,
        has_history: false,
        history_rows: 0,
      },
      ...options,
    ]
  }

  function formSymbolText() {
    return String(form.symbol || '').trim()
  }

  function formMarketText() {
    return String(form.market || '').trim()
  }

  function instrumentOptionLabel(option: MarketInstrumentOption) {
    const name = option.name && option.name !== option.symbol ? ` ${option.name}` : ''
    const market = option.market ? ` · ${option.market}` : ''
    return `${option.symbol}${name}${market}`
  }

  function formatInstrumentHistoryStatus(option: MarketInstrumentOption) {
    return option.has_history ? formatNumber(option.history_rows) : '0'
  }

  function historyRowTimestamp(row: MarketHistoryRow): number {
    const timestamp = Date.parse(String(row.date ?? ''))
    return Number.isFinite(timestamp) ? timestamp : Number.NEGATIVE_INFINITY
  }

  function toDateInput(value: Date) {
    const year = value.getFullYear()
    const month = String(value.getMonth() + 1).padStart(2, '0')
    const day = String(value.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }

  async function loadRelatedTables(lookupResult: MarketInstrumentLookupResponse | null = result.value) {
    const requestId = ++relatedTableRequestId
    const keywords = buildRelatedTableKeywords(lookupResult)
    relatedTablesLoading.value = true
    relatedTablesError.value = ''

    try {
      const responses = await Promise.allSettled(
        keywords.map((keyword) => akshareTablesApi.list({
          search: keyword,
          page: 1,
          page_size: 8,
        })),
      )
      if (requestId !== relatedTableRequestId) return

      const tableMap = new Map<number, DataTable>()
      responses.forEach((response) => {
        if (response.status !== 'fulfilled') return
        response.value.items.forEach((table) => tableMap.set(table.id, table))
      })
      relatedTables.value = Array.from(tableMap.values())
        .sort((left, right) => relatedTableScore(right) - relatedTableScore(left))
        .slice(0, 12)

      if (responses.every((response) => response.status === 'rejected')) {
        relatedTablesError.value = t('dataMgmt.relatedTablesLoadFailed')
      }
    } catch {
      if (requestId === relatedTableRequestId) {
        relatedTables.value = []
        relatedTablesError.value = t('dataMgmt.relatedTablesLoadFailed')
      }
    } finally {
      if (requestId === relatedTableRequestId) {
        relatedTablesLoading.value = false
      }
    }
  }

  function buildRelatedTableKeywords(lookupResult: MarketInstrumentLookupResponse | null) {
    const keywords = new Set<string>(assetTableSearchKeywords[form.asset_type])
    const symbol = lookupResult?.symbol || form.symbol
    const plainSymbol = String(symbol || '').trim()
    if (plainSymbol) {
      keywords.add(plainSymbol)
      keywords.add(plainSymbol.toLowerCase())
      keywords.add(plainSymbol.replace(/^[a-z]+/i, ''))
      keywords.add(plainSymbol.replace(/[^A-Za-z0-9]+/g, '_').toLowerCase())
    }
    assetDataFamilySpecs[form.asset_type].forEach((family) => {
      family.tableKeywords.forEach((keyword) => keywords.add(keyword))
    })
    return Array.from(keywords).filter(Boolean).slice(0, 10)
  }

  function relatedTableScore(table: DataTable) {
    const haystack = `${table.table_name} ${table.table_comment || ''} ${table.script_id || ''}`.toLowerCase()
    const assetKeywords = assetTableSearchKeywords[form.asset_type]
    const keywordScore = assetKeywords.reduce(
      (score, keyword) => score + (haystack.includes(keyword.toLowerCase()) ? 10 : 0),
      0,
    )
    const symbol = (result.value?.symbol || form.symbol || '').replace(/[^A-Za-z0-9]+/g, '').toLowerCase()
    const symbolScore = symbol && haystack.includes(symbol) ? 18 : 0
    const rowScore = Math.min(Math.log10(Math.max(table.row_count || 0, 1)), 8)
    return keywordScore + symbolScore + rowScore
  }

  function goTableDetail(tableId: number) {
    void router.push({ name: 'DataTableDetail', params: { id: tableId } })
  }

  function buildRangeStats(): RangeStat[] {
    const rows = historyRows.value
    if (!rows.length) {
      return [
        statRow('dataMgmt.metricHigh', '-'),
        statRow('dataMgmt.metricLow', '-'),
        statRow('dataMgmt.metricReturn', '-'),
        statRow('dataMgmt.metricAvgVolume', '-'),
      ]
    }

    const closes = numericSeries(rows, 'close')
    const highs = numericSeries(rows, 'high')
    const lows = numericSeries(rows, 'low')
    const volumes = numericSeries(rows, 'volume')
    const turnovers = numericSeries(rows, 'turnover')
    const openInterests = numericSeries(rows, 'open_interest')
    const changes = numericSeries(rows, 'change')
    const returnPct = result.value?.indicators.return_pct ?? periodReturnPct(closes)
    const volatility = closeVolatilityPct(closes)

    if (!closes.length && openInterests.length) {
      return [
        statRow('dataMgmt.metricCmeOpenInterest', formatNumber(sumNumbers(openInterests))),
        statRow('dataMgmt.metric24hVolume', formatNumber(sumNumbers(volumes))),
        statRow('dataMgmt.colChangeValue', formatNumber(sumNumbers(changes)), toneClass(sumNumbers(changes))),
        statRow('dataMgmt.metricSampleCount', formatNumber(rows.length)),
      ]
    }

    return [
      statRow('dataMgmt.metricHigh', formatNumber(highs.length ? Math.max(...highs) : result.value?.indicators.highest_close)),
      statRow('dataMgmt.metricLow', formatNumber(lows.length ? Math.min(...lows) : result.value?.indicators.lowest_close)),
      statRow('dataMgmt.metricReturn', formatPercent(returnPct), toneClass(returnPct)),
      statRow('dataMgmt.metricVolatility', formatPercent(volatility)),
      statRow('dataMgmt.metricAvgVolume', formatNumber(averageNumbers(volumes) ?? result.value?.indicators.avg_volume)),
      statRow('dataMgmt.fieldTurnover', formatNumber(sumNumbers(turnovers) || snapshot.value.turnover)),
    ]
  }

  function statRow(labelKey: string, value: string, tone = ''): RangeStat {
    return { label: t(labelKey), value, tone }
  }

  function buildCoverageRows(): CoverageRow[] {
    const snapshotFields = ['price', 'change_pct', 'open', 'high', 'low', 'volume', 'turnover', 'bid', 'ask']
    const historyFields = ['open', 'high', 'low', 'close', 'volume', 'turnover', 'change_pct', 'open_interest']
    const assetFields = assetDataFamilySpecs[form.asset_type].flatMap((family) => [
      ...family.fields,
      ...(family.historyFields || []),
    ])
    const uniqueAssetFields = Array.from(new Set(assetFields))

    return [
      coverageRow(
        'dataMgmt.coverageSnapshot',
        countSnapshotFields(snapshotFields),
        snapshotFields.length,
      ),
      coverageRow(
        'dataMgmt.coverageHistory',
        countHistoryFields(historyFields),
        historyFields.length,
      ),
      coverageRow(
        'dataMgmt.coverageAssetSpecific',
        countAvailableAssetFields(uniqueAssetFields),
        uniqueAssetFields.length,
      ),
      {
        label: t('dataMgmt.coverageWarehouse'),
        value: t('dataMgmt.coverageTablesValue', { count: relatedTables.value.length }),
        coverage: Math.min(100, relatedTables.value.length * 20),
      },
    ]
  }

  function coverageRow(labelKey: string, available: number, total: number): CoverageRow {
    return {
      label: t(labelKey),
      value: `${available}/${total}`,
      coverage: total ? Math.round((available / total) * 100) : 0,
    }
  }

  function countSnapshotFields(fields: string[]) {
    return fields.filter((field) => hasValue(snapshot.value[field])).length
  }

  function countHistoryFields(fields: string[]) {
    return fields.filter((field) => hasHistoryValue(field)).length
  }

  function countAvailableAssetFields(fields: string[]) {
    return fields.filter((field) => hasValue(snapshot.value[field]) || hasHistoryValue(field)).length
  }

  function dataFamilyBundleStatusLabel(
    status: MarketDataQueryBundleFamilyStatus,
    reasonCode: string | null,
  ): string {
    const label = status === 'ready'
      ? t('dataMgmt.dataFamilyStatusReady')
      : status === 'not_applicable'
        ? t('dataMgmt.dataFamilyStatusNotApplicable')
        : t('dataMgmt.dataFamilyStatusUnconfigured')
    return reasonCode ? `${label} · ${reasonCode}` : label
  }

  function dataFamilyBundleTagType(
    status: MarketDataQueryBundleFamilyStatus,
  ): DataFamilyView['tagType'] {
    if (status === 'ready') return 'success'
    if (status === 'unconfigured') return 'warning'
    return 'info'
  }

  function declaredFamilyFields(family: MarketDataQueryBundleFamily): string[] {
    return Array.from(new Set([
      ...family.required_fields,
      ...family.optional_fields,
      ...family.dimension_fields,
    ]))
  }

  function declaredKlineCompatibilityLabel(family: MarketDataQueryBundleFamily): string {
    const declaredCadences = family.frequencies
      .map((frequency) => t(periodLabelKey(frequency)))
    return t('dataMgmt.klineCompatibilityLabel', {
      cadences: declaredCadences.join('/'),
    })
  }

  function dataFamilyBundleDescription(family: MarketDataQueryBundleFamily): string {
    const declaredFields = declaredFamilyFields(family).map(fieldLabel)
    const fieldsLabel = declaredFields.length
      ? declaredFields.join(' / ')
      : t('dataMgmt.dataFamilyNoDeclaredFields')
    return t('dataMgmt.dataFamilyBundleDescription', {
      datasetCode: family.dataset_code,
      frequencySemantics: family.frequency_semantics,
      fields: fieldsLabel,
    })
  }

  function isCurrentPageExecutableFamily(family: MarketDataQueryBundleFamily): boolean {
    return family.family_id === selectedFamilyId.value
      && isMarketPageSelectableFamily(family, form.asset_type)
  }

  function hasRequiredFactRows(family: MarketDataQueryBundleFamily): boolean {
    if (family.data_kind === 'reference_series') {
      const presentation = referenceSeriesResult.value
      return Boolean(
        presentation
        && presentation.familyId === family.family_id
        && sameDeclaredFields(presentation.requiredFields, family.required_fields)
        && presentation.rows.some((row) => (
          family.required_fields.every((field) => isUsableReferenceSeriesValue(row[field]))
        )),
      )
    }
    if (family.data_kind !== 'bars') {
      const presentation = genericObservationResult.value
      return Boolean(
        presentation
        && presentation.familyId === family.family_id
        && sameDeclaredFields(presentation.requiredFields, family.required_fields)
        && sameDeclaredFields(presentation.dimensionFields, family.dimension_fields)
        && presentation.observations.some((observation) => (
          observation.quality === 'pass'
          && [...family.dimension_fields, ...family.required_fields]
            .every((field) => isUsableReferenceSeriesValue(observation.fields[field]))
        )),
      )
    }
    return historyRows.value.some((row) => (
      family.required_fields.every((field) => (
        isFiniteNumber(numericValue(row[field], null))
      ))
    ))
  }

  function hasDeclaredFactValue(family: MarketDataQueryBundleFamily, field: string): boolean {
    if (family.data_kind !== 'bars' && family.data_kind !== 'reference_series') {
      const presentation = genericObservationResult.value
      return Boolean(
        presentation
        && presentation.familyId === family.family_id
        && sameDeclaredFields(presentation.dimensionFields, family.dimension_fields)
        && presentation.observations.some((observation) => (
          observation.quality === 'pass' && isUsableReferenceSeriesValue(observation.fields[field])
        )),
      )
    }
    return hasValue(snapshot.value[field]) || hasHistoryValue(field)
  }

  function hasActiveV2FactsForFamily(family: MarketDataQueryBundleFamily): boolean {
    const status = marketDataPlatformStatus.value
    const contract = result.value?.query_contract
    return (
      (
        status.path === 'local_only'
        || status.path === 'local_first'
        || status.path === 'provider_persisted'
      )
      && status.familyId === family.family_id
      && result.value?.asset_type === form.asset_type
      && contract?.request.family_id === family.family_id
      && contract.request.family_contract_version === family.family_contract_version
      && hasRequiredFactRows(family)
    )
  }

  function dataFamilyReadState(family: MarketDataQueryBundleFamily): DataFamilyReadState {
    if (family.status === 'unconfigured') return 'unconfigured'
    if (family.status === 'not_applicable') return 'not_applicable'
    if (!isMarketPageSelectableFamily(family, form.asset_type)) return 'control_plane_only'
    if (isCurrentPageExecutableFamily(family) && hasActiveV2FactsForFamily(family)) {
      return 'facts_loaded'
    }
    if (family.data_kind === 'bars') return 'bars_query_available'
    if (family.data_kind === 'reference_series') return 'reference_series_query_available'
    return 'generic_query_available'
  }

  function dataFamilyReadStateLabel(readState: DataFamilyReadState): string {
    if (readState === 'facts_loaded') return t('dataMgmt.dataFamilyReadStateFactsLoaded')
    if (readState === 'bars_query_available') return t('dataMgmt.dataFamilyReadStateBarsQueryAvailable')
    if (readState === 'reference_series_query_available') {
      return t('dataMgmt.dataFamilyReadStateReferenceSeriesQueryAvailable')
    }
    if (readState === 'generic_query_available') {
      return t('dataMgmt.dataFamilyReadStateGenericQueryAvailable')
    }
    if (readState === 'control_plane_only') return t('dataMgmt.dataFamilyReadStateControlPlaneOnly')
    if (readState === 'unconfigured') return t('dataMgmt.dataFamilyReadStateUnconfigured')
    return t('dataMgmt.dataFamilyReadStateNotApplicable')
  }

  function dataFamilySpecForCurrentAsset(familyId: string): DataFamilySpec | null {
    return assetDataFamilySpecs[form.asset_type].find((family) => family.familyId === familyId) || null
  }

  function buildIssuedDataFamilyView(
    family: MarketDataQueryBundleFamily,
    familySpec: DataFamilySpec | null,
  ): DataFamilyView {
    const readState = dataFamilyReadState(family)
    const hasActiveFacts = readState === 'facts_loaded'
    const fields = declaredFamilyFields(family).map((field) => ({
      name: field,
      label: fieldLabel(field),
      // A `ready` control-plane declaration is not evidence that this page has
      // read its facts. Only the explicitly selected exact family can mark its
      // own declared fields as present.
      present: hasActiveFacts && hasDeclaredFactValue(family, field),
    }))

    return {
      familyId: family.family_id,
      // The default K-line contract keeps its current presentation. Other
      // products retain their own labels even when explicitly selected.
      label: family.family_id === defaultFamilyId(form.asset_type)
        && family.data_kind === 'bars'
        ? declaredKlineCompatibilityLabel(family)
        : familySpec
          ? t(familySpec.labelKey)
          : family.family_id,
      description: dataFamilyBundleDescription(family),
      statusLabel: dataFamilyBundleStatusLabel(family.status, family.reason_code),
      tagType: dataFamilyBundleTagType(family.status),
      contract: {
        dataKind: family.data_kind,
        frequencySemantics: family.frequency_semantics,
        coverageModel: family.coverage_model,
        observationShape: marketDataFamilyObservationShape(family),
      },
      readState,
      readStatusLabel: dataFamilyReadStateLabel(readState),
      fields,
    }
  }

  function buildMissingIssuedDataFamilyView(family: DataFamilySpec): DataFamilyView {
    return {
      familyId: family.familyId,
      label: t(family.labelKey),
      description: t('dataMgmt.dataFamilyMissingDescription'),
      statusLabel: t('dataMgmt.dataFamilyMissingStatus'),
      tagType: 'warning',
      contract: null,
      readState: 'unconfigured',
      readStatusLabel: dataFamilyReadStateLabel('unconfigured'),
      fields: Array.from(new Set([
        ...family.fields,
        ...(family.historyFields || []),
      ])).map((field) => ({
        name: field,
        label: fieldLabel(field),
        present: false,
      })),
    }
  }

  function buildAssetDataFamilies(): DataFamilyView[] {
    const bundle = marketDataQueryBundle.value
    if (bundle?.requested_asset_type === form.asset_type) {
      // The control plane owns issued product details. Known current cards
      // missing from a complete response stay visibly unconfigured, while
      // newly issued snapshot/reference/report families are appended without
      // reconstructing either class into a fact request.
      const knownSpecs = assetDataFamilySpecs[form.asset_type]
      const issuedById = new Map(bundle.families.map((family) => [family.family_id, family]))
      const knownFamilyIds = new Set(knownSpecs.map((family) => family.familyId))
      const knownFamilyViews = knownSpecs.map((family) => {
        const issuedFamily = issuedById.get(family.familyId)
        return issuedFamily
          ? buildIssuedDataFamilyView(issuedFamily, family)
          : buildMissingIssuedDataFamilyView(family)
      })
      const additionalFamilyViews = bundle.families
        .filter((family) => !knownFamilyIds.has(family.family_id))
        .map((family) => buildIssuedDataFamilyView(family, dataFamilySpecForCurrentAsset(family.family_id)))
      return [...knownFamilyViews, ...additionalFamilyViews]
    }

    return assetDataFamilySpecs[form.asset_type].map((family) => {
      const fields = Array.from(new Set([
        ...family.fields,
        ...(family.historyFields || []),
      ])).map((field) => ({
        name: field,
        label: fieldLabel(field),
        present: hasValue(snapshot.value[field]) || hasHistoryValue(field),
      }))

      const presentFields = fields.filter((field) => field.present).length
      const relatedTableCount = countMatchingTables(family.tableKeywords)
      const denominator = fields.length + 1
      const score = presentFields + (relatedTableCount ? 1 : 0)
      const status = score >= Math.ceil(denominator * 0.72)
        ? 'available'
        : score > 0 ? 'partial' : 'missing'

      return {
        familyId: family.familyId,
        label: t(family.labelKey),
        description: t(family.descKey, { count: relatedTableCount }),
        statusLabel: t(`dataMgmt.familyStatus${capitalize(status)}`),
        tagType: status === 'available' ? 'success' : status === 'partial' ? 'warning' : 'info',
        contract: null,
        readState: null,
        readStatusLabel: null,
        fields,
      }
    })
  }

  function countMatchingTables(keywords: string[]) {
    return relatedTables.value.filter((table) => {
      const haystack = `${table.table_name} ${table.table_comment || ''} ${table.script_id || ''}`.toLowerCase()
      return keywords.some((keyword) => haystack.includes(keyword.toLowerCase()))
    }).length
  }

  function fieldLabel(field: string) {
    const labelKey = fieldLabelKeys[field]
    // Unmapped fields keep their server-issued names. This is particularly
    // important for reference products such as `market.fund_nav`, whose NAV
    // axes are not interchangeable with a generic quote field.
    return labelKey ? t(labelKey) : field
  }

  function capitalize(value: string) {
    return value.charAt(0).toUpperCase() + value.slice(1)
  }

  function renderMarketChart() {
    if (!chartCanRender.value || !marketChartRef.value) {
      disposeMarketChart()
      return
    }
    if (!marketChart) {
      marketChart = echarts.init(marketChartRef.value)
    }
    marketChart.setOption(buildMarketChartOption(), true)
    marketChart.resize()
  }

  function resizeMarketChart() {
    marketChart?.resize()
  }

  function handleViewportResize() {
    viewportWidth.value = window.innerWidth
    resizeMarketChart()
  }

  function disposeMarketChart() {
    marketChart?.dispose()
    marketChart = null
  }

  function buildMarketChartOption(): echarts.EChartsOption {
    if (!hasOhlcChart.value || chartMode.value === 'structure') {
      return buildStructureChartOption()
    }
    if (chartMode.value === 'return') {
      return buildReturnChartOption()
    }
    if (chartMode.value === 'liquidity') {
      return buildLiquidityChartOption()
    }
    return buildPriceChartOption()
  }

  function buildPriceChartOption(): echarts.EChartsOption {
    const rows = ohlcHistoryRows.value
    const dates = rows.map((row) => String(row.date))
    const ohlc = rows.map((row) => ohlcTuple(row))
    const volumeBars = rows.map((row) => ({
      value: numericValue(row.volume, 0),
      itemStyle: { color: candleColor(row) },
    }))

    return baseChartOption({
      legend: [t('charts.klineSeries'), 'MA5', 'MA20', t('charts.klineVolume')],
      grid: [
        { left: 64, right: 28, top: 42, height: '55%' },
        { left: 64, right: 28, top: '73%', height: '16%' },
      ],
      xAxis: [
        categoryAxis(dates),
        { ...categoryAxis(dates), gridIndex: 1, axisLabel: { show: false } },
      ],
      yAxis: [
        valueAxis(),
        valueAxis({ gridIndex: 1, splitNumber: 2, axisLabel: { show: false } }),
      ],
      dataZoom: dataZoom([0, 1]),
      series: [
        {
          name: t('charts.klineSeries'),
          type: 'candlestick',
          data: ohlc,
          itemStyle: CANDLE_ITEM_STYLE,
        },
        movingAverageSeries('MA5', ohlc, 5),
        movingAverageSeries('MA20', ohlc, 20),
        {
          name: t('charts.klineVolume'),
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumeBars,
          barMaxWidth: 12,
        },
      ],
    })
  }

  function buildReturnChartOption(): echarts.EChartsOption {
    const rows = ohlcHistoryRows.value
    const dates = rows.map((row) => String(row.date))
    const closes = rows.map((row) => numericValue(row.close, null)).filter(isFiniteNumber)
    const returns = cumulativeReturns(closes)
    const drawdowns = drawdownSeries(closes)
    const volumes = rows.map((row) => numericValue(row.volume, 0))
    const palette = chartPalette()

    return baseChartOption({
      legend: [t('dataMgmt.chartCumulativeReturn'), t('dataMgmt.chartDrawdown'), t('charts.klineVolume')],
      grid: [
        { left: 64, right: 28, top: 42, height: '55%' },
        { left: 64, right: 28, top: '73%', height: '16%' },
      ],
      xAxis: [
        categoryAxis(dates),
        { ...categoryAxis(dates), gridIndex: 1, axisLabel: { show: false } },
      ],
      yAxis: [
        valueAxis({ axisLabel: { formatter: '{value}%' } }),
        valueAxis({ gridIndex: 1, splitNumber: 2, axisLabel: { show: false } }),
      ],
      dataZoom: dataZoom([0, 1]),
      series: [
        {
          name: t('dataMgmt.chartCumulativeReturn'),
          type: 'line',
          data: returns,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, color: palette.primary },
          areaStyle: { opacity: 0.16 },
        },
        {
          name: t('dataMgmt.chartDrawdown'),
          type: 'line',
          data: drawdowns,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1.6, color: palette.danger },
        },
        {
          name: t('charts.klineVolume'),
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumes,
          itemStyle: { color: palette.secondary },
          barMaxWidth: 12,
        },
      ],
    })
  }

  function buildLiquidityChartOption(): echarts.EChartsOption {
    const rows = ohlcHistoryRows.value.length ? ohlcHistoryRows.value : historyRows.value
    const dates = rows.map((row, index) => String(row.date || row.name || index + 1))
    const volume = rows.map((row) => numericValue(row.volume, 0))
    const turnover = rows.map((row) => numericValue(row.turnover, null))
    const openInterest = rows.map((row) => numericValue(row.open_interest, null))
    const palette = chartPalette()

    return baseChartOption({
      legend: [
        t('charts.klineVolume'),
        t('dataMgmt.fieldTurnover'),
        t('dataMgmt.fieldOpenInterest'),
      ],
      grid: [{ left: 64, right: 36, top: 44, bottom: 54 }],
      xAxis: [categoryAxis(dates)],
      yAxis: [
        valueAxis(),
        valueAxis({ axisLabel: { formatter: compactAxisLabel }, splitLine: { show: false } }),
      ],
      dataZoom: dataZoom([0]),
      series: [
        {
          name: t('charts.klineVolume'),
          type: 'bar',
          data: volume,
          itemStyle: { color: palette.success },
          barMaxWidth: 14,
        },
        {
          name: t('dataMgmt.fieldTurnover'),
          type: 'line',
          yAxisIndex: 1,
          data: turnover,
          smooth: true,
          showSymbol: false,
          lineStyle: { color: palette.warning, width: 2 },
        },
        {
          name: t('dataMgmt.fieldOpenInterest'),
          type: 'line',
          yAxisIndex: 1,
          data: openInterest,
          smooth: true,
          showSymbol: false,
          lineStyle: { color: palette.info, width: 2 },
        },
      ],
    })
  }

  function buildStructureChartOption(): echarts.EChartsOption {
    const rows = historyRows.value
    const labels = rows.map((row, index) => String(row.name || row.date || index + 1))
    const palette = chartPalette()

    return baseChartOption({
      legend: [
        t('charts.klineVolume'),
        t('dataMgmt.fieldOpenInterest'),
        t('dataMgmt.colChangeValue'),
      ],
      grid: [{ left: 64, right: 36, top: 44, bottom: 58 }],
      xAxis: [categoryAxis(labels)],
      yAxis: [
        valueAxis(),
        valueAxis({ splitLine: { show: false } }),
      ],
      dataZoom: labels.length > 8 ? dataZoom([0]) : [],
      series: [
        {
          name: t('charts.klineVolume'),
          type: 'bar',
          data: rows.map((row) => numericValue(row.volume, 0)),
          itemStyle: { color: palette.primary },
          barMaxWidth: 18,
        },
        {
          name: t('dataMgmt.fieldOpenInterest'),
          type: 'bar',
          data: rows.map((row) => numericValue(row.open_interest, 0)),
          itemStyle: { color: palette.info },
          barMaxWidth: 18,
        },
        {
          name: t('dataMgmt.colChangeValue'),
          type: 'line',
          yAxisIndex: 1,
          data: rows.map((row) => numericValue(row.change, null)),
          smooth: true,
          lineStyle: { color: palette.danger, width: 2 },
        },
      ],
    })
  }

  function baseChartOption(option: MarketChartOptionDraft): echarts.EChartsOption {
    const { legend, ...restOption } = option
    const palette = chartPalette()
    return {
      animation: false,
      color: [palette.primary, palette.danger, palette.success, palette.warning, palette.info],
      backgroundColor: 'transparent',
      legend: {
        top: 8,
        left: 56,
        itemWidth: 10,
        itemHeight: 8,
        textStyle: { color: palette.mutedText, fontSize: 12 },
        data: legend as string[],
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        valueFormatter: (value: unknown) => (typeof value === 'number' ? formatNumber(value) : String(value ?? '-')),
      },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      ...restOption,
    }
  }

  function categoryAxis(data: string[]): echarts.XAXisComponentOption {
    const palette = chartPalette()
    return {
      type: 'category',
      data,
      boundaryGap: false,
      axisLine: { lineStyle: { color: palette.border }, onZero: false },
      axisTick: { show: false },
      axisLabel: { color: palette.secondary, hideOverlap: true },
      splitLine: { show: false },
    }
  }

  function valueAxis(overrides: Partial<echarts.YAXisComponentOption> = {}): echarts.YAXisComponentOption {
    const palette = chartPalette()
    return {
      type: 'value',
      scale: true,
      axisLabel: { color: palette.secondary, formatter: compactAxisLabel },
      splitLine: { lineStyle: { color: palette.grid, type: 'dashed' } },
      ...overrides,
    } as echarts.YAXisComponentOption
  }

  function themeColor(name: string, fallback: string) {
    if (typeof window === 'undefined') return fallback
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    return value || fallback
  }

  function chartPalette() {
    return {
      primary: themeColor('--primary-color', 'royalblue'),
      danger: themeColor('--danger-color', 'crimson'),
      success: themeColor('--success-color', 'seagreen'),
      warning: themeColor('--warning-color', 'goldenrod'),
      info: themeColor('--info-text-color', 'slateblue'),
      secondary: themeColor('--text-color-secondary', 'slategray'),
      mutedText: themeColor('--text-color-regular', 'dimgray'),
      border: themeColor('--border-color', 'lightgray'),
      grid: themeColor('--border-color-light', 'gainsboro'),
    }
  }

  function dataZoom(xAxisIndex: number[]): echarts.DataZoomComponentOption[] {
    return [
      { type: 'inside', xAxisIndex, start: 55, end: 100 },
      { type: 'slider', xAxisIndex, height: 18, bottom: 16, start: 55, end: 100 },
    ]
  }

  function movingAverageSeries(name: string, data: number[][], period: number): echarts.SeriesOption {
    return {
      name,
      type: 'line',
      data: movingAverage(data, period),
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 1.5, opacity: 0.75 },
    }
  }

  function movingAverage(data: number[][], period: number) {
    return data.map((_, index) => {
      if (index < period - 1) return '-'
      const slice = data.slice(index - period + 1, index + 1)
      const average = slice.reduce((sum, item) => sum + item[1], 0) / period
      return Number(average.toFixed(4))
    })
  }

  function ohlcTuple(row: MarketHistoryRow) {
    const open = numericValue(row.open, null)
    const close = numericValue(row.close, null)
    const low = numericValue(row.low, null)
    const high = numericValue(row.high, null)
    if (
      !isFiniteNumber(open)
      || !isFiniteNumber(close)
      || !isFiniteNumber(low)
      || !isFiniteNumber(high)
    ) {
      throw new Error('MARKET_DATA_OHLC_INVALID')
    }
    return [
      open,
      close,
      low,
      high,
    ]
  }

  function candleColor(row: MarketHistoryRow) {
    const open = numericValue(row.open, null)
    const close = numericValue(row.close, null)
    if (!isFiniteNumber(open) || !isFiniteNumber(close)) {
      throw new Error('MARKET_DATA_OHLC_INVALID')
    }
    return close >= open ? CANDLE_UP_COLOR : CANDLE_DOWN_COLOR
  }

  function buildAssetKpiCards(): KpiCard[] {
    if (isFundNavReferenceSeries.value) {
      return fundNavReferenceFields.value.map((field) => ({
        label: fieldLabel(field),
        value: formatReferenceSeriesField(field, snapshot.value[field]),
        tone: referenceSeriesFieldTone(field, snapshot.value[field]),
      }))
    }

    const latestPrice = snapshot.value.price ?? result.value?.indicators.latest_close
    const periodReturn = result.value?.indicators.return_pct ?? snapshot.value.change_pct
    const cardsByAsset: Record<MarketAssetType, KpiCard[]> = {
      stock: [
        metricCard('dataMgmt.fieldPrice', formatNumber(latestPrice)),
        metricCard('dataMgmt.metricReturn', formatPercent(periodReturn), toneClass(periodReturn)),
        metricCard('dataMgmt.fieldTurnover', formatNumber(snapshot.value.turnover)),
        metricCard('dataMgmt.metricPePb', formatValuation()),
      ],
      futures: [
        metricCard('dataMgmt.fieldPrice', formatNumber(latestPrice)),
        metricCard('dataMgmt.fieldOpenInterest', formatNumber(snapshot.value.open_interest)),
        metricCard('dataMgmt.fieldSettle', formatNumber(snapshot.value.settle)),
        metricCard('dataMgmt.metricBidAskSpread', formatNumber(bidAskSpread())),
      ],
      bond: [
        metricCard('dataMgmt.fieldPrice', formatNumber(latestPrice)),
        metricCard('dataMgmt.colChange', formatPercent(snapshot.value.change_pct), toneClass(snapshot.value.change_pct)),
        metricCard('dataMgmt.fieldTurnover', formatNumber(snapshot.value.turnover)),
        metricCard('dataMgmt.fieldBidAsk', formatPair(snapshot.value.bid, snapshot.value.ask)),
      ],
      fund: [
        metricCard('dataMgmt.fieldPrice', formatNumber(latestPrice)),
        metricCard('dataMgmt.colChange', formatPercent(periodReturn), toneClass(periodReturn)),
        metricCard('dataMgmt.fieldTurnover', formatNumber(snapshot.value.turnover)),
        metricCard('dataMgmt.metricAvgVolume', formatNumber(result.value?.indicators.avg_volume)),
      ],
      option: [
        metricCard('dataMgmt.metricPremium', formatNumber(latestPrice)),
        metricCard('dataMgmt.colChangeValue', formatNumber(snapshot.value.change), toneClass(snapshot.value.change)),
        metricCard('dataMgmt.colChange', formatPercent(periodReturn), toneClass(periodReturn)),
        metricCard('dataMgmt.metricSampleCount', formatNumber(result.value?.indicators.observation_count)),
      ],
      fx: [
        metricCard('dataMgmt.fieldPrice', formatNumber(latestPrice)),
        metricCard('dataMgmt.colChange', formatPercent(periodReturn), toneClass(periodReturn)),
        metricCard('dataMgmt.fieldHighLow', formatPair(snapshot.value.high, snapshot.value.low)),
        metricCard('dataMgmt.fieldPreviousClose', formatNumber(snapshot.value.previous_close)),
      ],
      crypto: [
        metricCard('dataMgmt.fieldPrice', formatNumber(latestPrice)),
        metricCard('dataMgmt.colChange', formatPercent(snapshot.value.change_pct), toneClass(snapshot.value.change_pct)),
        metricCard('dataMgmt.metric24hVolume', formatNumber(snapshot.value.volume)),
        metricCard('dataMgmt.metricCmeOpenInterest', formatNumber(totalHistoryField('open_interest'))),
      ],
    }
    return cardsByAsset[form.asset_type]
  }

  function metricCard(labelKey: string, value: string, tone = ''): KpiCard {
    return {
      label: t(labelKey),
      value,
      tone,
    }
  }

  function formatDetailValue(field: DetailFieldSpec) {
    const [firstField, secondField] = field.fields
    if (field.format === 'percent') {
      return formatPercent(snapshot.value[firstField])
    }
    if (field.format === 'text') {
      return formatText(snapshot.value[firstField])
    }
    if (field.format === 'pair') {
      return formatPair(snapshot.value[firstField], snapshot.value[secondField])
    }
    if (field.format === 'bidAsk') {
      return formatPair(snapshot.value.bid, snapshot.value.ask)
    }
    if (field.format === 'valuation') {
      return formatValuation()
    }
    return formatNumber(snapshot.value[firstField])
  }

  function formatReferenceSeriesField(field: string, value: unknown): string {
    return field === 'daily_growth_rate' ? formatPercent(value) : formatNumber(value)
  }

  function referenceSeriesFieldTone(field: string, value: unknown): string {
    return field === 'daily_growth_rate' ? toneClass(value) : ''
  }

  function formatHistoryCell(row: MarketHistoryRow, column: HistoryTableColumn) {
    const value = row[column.key]
    if (column.format === 'percent') {
      return formatPercent(value)
    }
    if (column.format === 'text') {
      return formatText(value)
    }
    return formatNumber(value)
  }

  function shouldShowHistoryColumn(field: string) {
    if (!historyRows.value.length) return true
    return hasHistoryValue(field)
  }

  function formatPair(firstValue: unknown, secondValue: unknown) {
    if (!hasValue(firstValue) && !hasValue(secondValue)) return '-'
    return `${formatNumber(firstValue)} / ${formatNumber(secondValue)}`
  }

  function formatValuation() {
    if (!hasValue(snapshot.value.pe) && !hasValue(snapshot.value.pb)) return '-'
    return `PE ${formatNumber(snapshot.value.pe)} / PB ${formatNumber(snapshot.value.pb)}`
  }

  function formatText(value: unknown) {
    if (!hasValue(value)) return '-'
    return String(value)
  }

  function formatGenericObservationCell(
    observation: MarketDataQueryObservation,
    column: GenericObservationColumn,
  ): string {
    if (column.source === 'field') {
      return formatGenericObservationValue(observation.fields[column.key])
    }
    const metadata: Record<string, unknown> = {
      event_at: observation.event_at,
      quality: observation.quality,
      source_snapshot_id: observation.source_snapshot_id,
      revision_id: observation.revision_id,
      available_at: observation.available_at,
      committed_at: observation.committed_at,
      revision_number: observation.revision_number,
    }
    return formatGenericObservationValue(metadata[column.key])
  }

  function formatGenericObservationValue(value: unknown): string {
    if (!hasValue(value)) return '-'
    if (typeof value === 'number') return Number.isFinite(value) ? formatNumber(value) : '-'
    if (typeof value === 'boolean') return value ? 'true' : 'false'
    if (typeof value === 'string') return publicMarketDataProvenanceValue(value) || '-'
    try {
      const serialized = JSON.stringify(value)
      return typeof serialized === 'string' ? publicMarketDataProvenanceValue(serialized) || '-' : '-'
    } catch {
      return '-'
    }
  }

  function bidAskSpread() {
    const bid = Number(snapshot.value.bid)
    const ask = Number(snapshot.value.ask)
    if (!Number.isFinite(bid) || !Number.isFinite(ask)) return null
    return ask - bid
  }

  function totalHistoryField(field: string) {
    const total = historyRows.value.reduce((sum, row) => {
      const value = Number(row[field])
      return Number.isFinite(value) ? sum + value : sum
    }, 0)
    return total || null
  }

  function numericSeries(rows: MarketHistoryRow[], field: string) {
    return rows.map((row) => numericValue(row[field], null)).filter(isFiniteNumber)
  }

  function numericValue<T extends number | null>(value: unknown, fallback: T): number | T {
    if (!hasValue(value)) return fallback
    const numeric = Number(value)
    return Number.isFinite(numeric) ? numeric : fallback
  }

  function isFiniteNumber(value: number | null): value is number {
    return typeof value === 'number' && Number.isFinite(value)
  }

  function sumNumbers(values: number[]) {
    return values.reduce((sum, value) => sum + value, 0)
  }

  function averageNumbers(values: number[]) {
    if (!values.length) return null
    return sumNumbers(values) / values.length
  }

  function periodReturnPct(values: number[]) {
    if (values.length < 2 || !values[0]) return null
    return ((values[values.length - 1] / values[0]) - 1) * 100
  }

  function closeVolatilityPct(values: number[]) {
    if (values.length < 3) return null
    const returns = values.slice(1)
      .map((value, index) => values[index] ? ((value / values[index]) - 1) * 100 : null)
      .filter(isFiniteNumber)
    if (!returns.length) return null
    const mean = averageNumbers(returns) || 0
    const variance = returns.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / returns.length
    return Math.sqrt(variance)
  }

  function cumulativeReturns(values: number[]) {
    if (!values.length || !values[0]) return []
    const first = values[0]
    return values.map((value) => Number((((value / first) - 1) * 100).toFixed(2)))
  }

  function drawdownSeries(values: number[]) {
    let peak = values[0] || 0
    return values.map((value) => {
      peak = Math.max(peak, value)
      if (!peak) return 0
      return Number((((value / peak) - 1) * 100).toFixed(2))
    })
  }

  function compactAxisLabel(value: unknown) {
    const numericValue = Number(value)
    if (!Number.isFinite(numericValue)) return String(value ?? '')
    const absValue = Math.abs(numericValue)
    if (absValue >= 1e8) return t('dataMgmt.compactHundredMillion', { value: (numericValue / 1e8).toFixed(1) })
    if (absValue >= 1e4) return t('dataMgmt.compactTenThousand', { value: (numericValue / 1e4).toFixed(1) })
    return String(numericValue)
  }

  function formatNumber(value: unknown) {
    if (!hasValue(value)) return '-'
    const numericValue = Number(value)
    if (!Number.isFinite(numericValue)) return '-'
    return new Intl.NumberFormat(undefined, {
      maximumFractionDigits: Math.abs(numericValue) >= 1000 ? 0 : 4,
    }).format(numericValue)
  }

  function formatPercent(value: unknown) {
    if (!hasValue(value)) return '-'
    const numericValue = Number(value)
    if (!Number.isFinite(numericValue)) return '-'
    return `${numericValue >= 0 ? '+' : ''}${numericValue.toFixed(2)}%`
  }

  function coverageStatusTagType(status: string) {
    if (status === 'pass') return 'success'
    if (status === 'failed') return 'danger'
    if (status === 'warning') return 'warning'
    return 'info'
  }

  function coverageStatusLabel(status: string) {
    const labels: Record<string, string> = {
      pass: t('dataMgmt.coveragePassed'),
      warning: t('dataMgmt.coverageWarning'),
      failed: t('dataMgmt.coverageFailed'),
      unknown: t('dataMgmt.coverageUnknown'),
    }
    return labels[status] || status
  }

  function coverageDateRange(row: MarketDataCoverageResponse) {
    const start = row.start_date || '-'
    const end = row.end_date || '-'
    return t('dataMgmt.coverageDateRange', { start, end })
  }

  function formatCoverageRatio(value: unknown) {
    const numeric = Number(value)
    if (!Number.isFinite(numeric)) return '-'
    return `${(numeric * 100).toFixed(2)}%`
  }

  function toneClass(value: unknown) {
    const numericValue = Number(value)
    if (!Number.isFinite(numericValue) || numericValue === 0) return ''
    return numericValue > 0 ? 'is-positive' : 'is-negative'
  }

  function hasHistoryValue(field: string) {
    return historyRows.value.some((row) => hasValue(row[field]))
  }

  function hasValue(value: unknown) {
    return value !== null && value !== undefined && value !== ''
  }

  return {
    t,
    route,
    router,
    today,
    ninetyDaysAgo,
    assetTabs,
    assetDisplayConfigs,
    assetDataFamilySpecs,
    assetTableSearchKeywords,
    fieldLabelKeys,
    selectedFamilyId,
    selectableDataFamilies,
    periods,
    routeTabMap,
    form,
    dateRange,
    loading,
    result,
    chartMode,
    marketChartRef,
    instrumentOptions,
    instrumentOptionsLoading,
    relatedTablesLoading,
    relatedTables,
    relatedTablesError,
    coverageRows,
    coverageLoading,
    coverageRefreshing,
    coverageError,
    coverageTimeframe,
    coverageProvider,
    marketDataPlatformStatus,
    snapshotDescriptionColumns,
    marketChart,
    instrumentOptionsRequestId,
    relatedTableRequestId,
    coverageRequestId,
    snapshot,
    historyRows,
    selectedMarketPageFamily,
    isReferenceSeriesSelected,
    isGenericObservationSelected,
    isFundNavReferenceSeries,
    fundNavReferenceFields,
    referenceSeriesResult,
    referenceSeriesRows,
    referenceSeriesTableColumns,
    referenceSeriesEmptyText,
    genericObservationResult,
    genericObservationRows,
    genericObservationColumns,
    genericObservationEmptyText,
    displayHistoryRows,
    ohlcHistoryRows,
    hasOhlcChart,
    hasStructureChart,
    chartCanRender,
    activeAssetConfig,
    activeAssetIcon,
    symbolPlaceholder,
    emptyHistoryText,
    chartEmptyText,
    chartSubtitle,
    chartAriaLabel,
    hasSnapshotChange,
    marketOverviewPrimaryLabel,
    marketOverviewPrimaryValue,
    marketOverviewTone,
    marketOverviewSecondaryText,
    assetOverviewDescription,
    assetDetailTitle,
    assetDetailNote,
    hasSnapshotTurnover,
    hasSnapshotBidAsk,
    hasSnapshotOpenInterest,
    hasSnapshotSettle,
    hasSnapshotValuation,
    hasSnapshotDataSource,
    snapshotMetrics,
    assetKpiCards,
    chartModeOptions,
    rangeStats,
    dataCoverageRows,
    coverageScore,
    heroStats,
    marketDataPlatformSourceText,
    marketDataPlatformCacheText,
    marketDataPlatformCoverageText,
    marketDataPlatformTagType,
    marketDataPlatformProvenance,
    coverageMatrixSubtitle,
    coverageSummaryCards,
    assetDataFamilies,
    relatedTablesBadge,
    relatedTableSummary,
    assetDetailRows,
    historyTableColumns,
    currentAssetTab,
    assetLabel,
    setAssetType,
    applyRouteTab,
    applyAssetType,
    restoreAssetSelection,
    selectDataFamily,
    lookupInstrument,
    loadCoverageMatrix,
    refreshCoverageMatrix,
    searchInstrumentOptions,
    handleInstrumentDropdownVisible,
    loadInstrumentOptions,
    ensureCurrentInstrumentOption,
    formSymbolText,
    formMarketText,
    v2FrequencyForLegacyPeriod,
    queryWindowFromDateRange,
    queryContractForCurrentLookup,
    queryContractForCurrentPeriod,
    selectedMarketPageFamilyFromQueryBundle,
    isMarketPageSelectableFamily,
    referenceSeriesRowsFromV2Response,
    genericObservationResultFromV2Response,
    v2HistoryRows,
    v2EventTimeLabel,
    lookupFromV2Response,
    lookupFromReferenceSeriesResponse,
    lookupFromGenericObservationResponse,
    setLegacyMarketDataPlatformStatus,
    setV2MarketDataPlatformStatus,
    queryV2FromLookupContract,
    instrumentOptionLabel,
    formatInstrumentHistoryStatus,
    toDateInput,
    loadRelatedTables,
    buildRelatedTableKeywords,
    relatedTableScore,
    goTableDetail,
    buildRangeStats,
    statRow,
    buildCoverageRows,
    coverageRow,
    countSnapshotFields,
    countHistoryFields,
    countAvailableAssetFields,
    buildAssetDataFamilies,
    countMatchingTables,
    fieldLabel,
    capitalize,
    renderMarketChart,
    resizeMarketChart,
    handleViewportResize,
    disposeMarketChart,
    buildMarketChartOption,
    buildPriceChartOption,
    buildReturnChartOption,
    buildLiquidityChartOption,
    buildStructureChartOption,
    baseChartOption,
    categoryAxis,
    valueAxis,
    themeColor,
    chartPalette,
    dataZoom,
    movingAverageSeries,
    movingAverage,
    ohlcTuple,
    candleColor,
    buildAssetKpiCards,
    metricCard,
    formatDetailValue,
    formatReferenceSeriesField,
    referenceSeriesFieldTone,
    formatHistoryCell,
    formatGenericObservationCell,
    formatGenericObservationValue,
    shouldShowHistoryColumn,
    formatPair,
    formatValuation,
    formatText,
    bidAskSpread,
    totalHistoryField,
    numericSeries,
    numericValue,
    isFiniteNumber,
    sumNumbers,
    averageNumbers,
    periodReturnPct,
    closeVolatilityPct,
    cumulativeReturns,
    drawdownSeries,
    compactAxisLabel,
    formatNumber,
    formatPercent,
    coverageStatusTagType,
    coverageStatusLabel,
    coverageDateRange,
    formatCoverageRatio,
    toneClass,
    hasHistoryValue,
    hasValue,
  }
}
