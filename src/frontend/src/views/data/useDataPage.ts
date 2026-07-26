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
  marketDataApi,
  type MarketAssetType,
  type MarketHistoryRow,
  type MarketInstrumentOption,
  type MarketInstrumentLookupResponse,
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

  type DataFamilySpec = {
    labelKey: string
    descKey: string
    fields: string[]
    historyFields?: string[]
    tableKeywords: string[]
  }

  type DataFamilyView = {
    label: string
    description: string
    statusLabel: string
    tagType: 'success' | 'warning' | 'info'
    fields: Array<{
      name: string
      label: string
      present: boolean
    }>
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
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'change_pct', 'open', 'high', 'low', 'volume', 'turnover'],
        historyFields: ['open', 'high', 'low', 'close', 'volume', 'turnover', 'turnover_rate'],
        tableKeywords: ['stock_zh_a_spot', 'stock_zh_a_hist', 'stock_market'],
      },
      {
        labelKey: 'dataMgmt.familyValuation',
        descKey: 'dataMgmt.familyValuationDesc',
        fields: ['market_cap', 'float_market_cap', 'pe', 'pb'],
        tableKeywords: ['stock_market_pe', 'stock_market_pb', 'stock_individual_info'],
      },
      {
        labelKey: 'dataMgmt.familyLiquidity',
        descKey: 'dataMgmt.familyLiquidityDesc',
        fields: ['volume', 'turnover'],
        historyFields: ['volume', 'turnover', 'turnover_rate'],
        tableKeywords: ['stock_market_fund_flow', 'stock_individual_fund_flow'],
      },
    ],
    futures: [
      {
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'bid', 'ask', 'volume', 'open_interest'],
        historyFields: ['open', 'high', 'low', 'close', 'volume', 'open_interest'],
        tableKeywords: ['futures_zh_spot', 'daily_market_data', 'minute_market'],
      },
      {
        labelKey: 'dataMgmt.familySettlement',
        descKey: 'dataMgmt.familySettlementDesc',
        fields: ['settle', 'previous_settle', 'open_interest'],
        historyFields: ['settle', 'open_interest'],
        tableKeywords: ['settle', 'delivery', 'member_position'],
      },
      {
        labelKey: 'dataMgmt.familyInventory',
        descKey: 'dataMgmt.familyInventoryDesc',
        fields: ['volume', 'open_interest'],
        historyFields: ['volume', 'open_interest'],
        tableKeywords: ['inventory', 'receipt', 'warehouse'],
      },
    ],
    bond: [
      {
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'change_pct', 'bid', 'ask', 'turnover'],
        historyFields: ['open', 'high', 'low', 'close', 'volume', 'turnover'],
        tableKeywords: ['bond_zh_hs_cov_spot', 'bond_zh_hs_cov_daily'],
      },
      {
        labelKey: 'dataMgmt.familyOrderBook',
        descKey: 'dataMgmt.familyOrderBookDesc',
        fields: ['bid', 'ask', 'volume', 'turnover'],
        tableKeywords: ['bond_spot', 'bond_info', 'bond_quote'],
      },
      {
        labelKey: 'dataMgmt.familyFixedIncome',
        descKey: 'dataMgmt.familyFixedIncomeDesc',
        fields: ['price', 'previous_close'],
        historyFields: ['close', 'change_pct'],
        tableKeywords: ['bond_info_cm', 'bond_market'],
      },
    ],
    fund: [
      {
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'change_pct', 'volume', 'turnover'],
        historyFields: ['open', 'high', 'low', 'close', 'volume', 'turnover'],
        tableKeywords: ['fund_etf_spot', 'fund_etf_hist'],
      },
      {
        labelKey: 'dataMgmt.familyLiquidity',
        descKey: 'dataMgmt.familyLiquidityDesc',
        fields: ['volume', 'turnover'],
        historyFields: ['volume', 'turnover'],
        tableKeywords: ['fund_flow', 'fund_scale', 'fund_industry_allocation'],
      },
      {
        labelKey: 'dataMgmt.familyNav',
        descKey: 'dataMgmt.familyNavDesc',
        fields: ['price', 'previous_close'],
        historyFields: ['close', 'change_pct'],
        tableKeywords: ['fund_open_fund', 'fund_net_value', 'reits_hist'],
      },
    ],
    option: [
      {
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'change', 'change_pct', 'volume'],
        historyFields: ['name', 'price', 'volume', 'turnover'],
        tableKeywords: ['option_sse_daily', 'option_cffex'],
      },
      {
        labelKey: 'dataMgmt.familyDerivative',
        descKey: 'dataMgmt.familyDerivativeDesc',
        fields: ['price', 'volume', 'open_interest', 'strike', 'days_to_expiry'],
        historyFields: ['volume', 'open_interest', 'strike', 'days_to_expiry'],
        tableKeywords: ['option_base', 'option_finance_board', 'options_stock'],
      },
      {
        labelKey: 'dataMgmt.familyRiskSurface',
        descKey: 'dataMgmt.familyRiskSurfaceDesc',
        fields: ['change_pct', 'bid', 'ask'],
        historyFields: ['change_pct', 'change'],
        tableKeywords: ['option_minute', 'option_sse_minute', 'option_iv'],
      },
    ],
    fx: [
      {
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'change_pct', 'open', 'high', 'low', 'previous_close'],
        historyFields: ['open', 'high', 'low', 'close', 'change_pct'],
        tableKeywords: ['forex_spot', 'forex_hist', 'fx_quote'],
      },
      {
        labelKey: 'dataMgmt.familyMacroFx',
        descKey: 'dataMgmt.familyMacroFxDesc',
        fields: ['price', 'previous_close'],
        historyFields: ['close', 'change_pct'],
        tableKeywords: ['macro', 'fx_quote_baidu', 'currency'],
      },
      {
        labelKey: 'dataMgmt.familyRange',
        descKey: 'dataMgmt.familyRangeDesc',
        fields: ['high', 'low', 'open'],
        historyFields: ['high', 'low', 'open'],
        tableKeywords: ['forex', 'fx'],
      },
    ],
    crypto: [
      {
        labelKey: 'dataMgmt.familyRealtime',
        descKey: 'dataMgmt.familyRealtimeDesc',
        fields: ['price', 'change', 'change_pct', 'high', 'low', 'volume'],
        tableKeywords: ['crypto_js_spot', 'crypto'],
      },
      {
        labelKey: 'dataMgmt.familyCmePosition',
        descKey: 'dataMgmt.familyCmePositionDesc',
        fields: ['volume', 'open_interest', 'change'],
        historyFields: ['volume', 'open_interest', 'change'],
        tableKeywords: ['crypto_bitcoin_cme', 'bitcoin_cme'],
      },
      {
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

  const periods = [
    { value: 'daily', labelKey: 'dataMgmt.periodDaily' },
    { value: 'weekly', labelKey: 'dataMgmt.periodWeekly' },
    { value: 'monthly', labelKey: 'dataMgmt.periodMonthly' },
  ]

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
  const viewportWidth = ref(window.innerWidth)
  let marketChart: echarts.ECharts | null = null
  let instrumentOptionsRequestId = 0
  let relatedTableRequestId = 0
  let coverageRequestId = 0

  const snapshot = computed<Record<string, unknown>>(() => result.value?.snapshot || {})
  const historyRows = computed(() => result.value?.history.rows || [])
  const displayHistoryRows = computed(() => (
    [...historyRows.value].sort((left, right) => historyRowTimestamp(right) - historyRowTimestamp(left))
  ))
  const ohlcHistoryRows = computed(() => historyRows.value.filter((row) => (
    hasValue(row.date) && hasValue(row.close) && (
      hasValue(row.open) || hasValue(row.high) || hasValue(row.low)
    )
  )))
  const hasOhlcChart = computed(() => ohlcHistoryRows.value.length > 0)
  const hasStructureChart = computed(() => historyRows.value.some((row) => (
    hasValue(row.name) || hasValue(row.open_interest) || hasValue(row.volume)
  )))
  const chartCanRender = computed(() => hasOhlcChart.value || hasStructureChart.value)
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
  const heroStats = computed<KpiCard[]>(() => [
    metricCard('dataMgmt.heroStatAsset', assetLabel(form.asset_type)),
    metricCard('dataMgmt.heroStatSymbol', result.value?.symbol || form.symbol || '-'),
    metricCard('dataMgmt.heroStatRows', formatNumber(result.value?.history.total)),
    metricCard('dataMgmt.heroStatCoverage', `${coverageScore.value}%`),
  ])
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
  const assetDetailRows = computed<DetailRow[]>(() => (
    activeAssetConfig.value.detailFields.map((field) => ({
      label: t(field.labelKey),
      value: formatDetailValue(field),
      tone: field.tone ? toneClass(snapshot.value[field.fields[0]]) : '',
    }))
  ))
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
    void lookupInstrument()
    window.addEventListener('resize', handleViewportResize)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', handleViewportResize)
    disposeMarketChart()
  })

  watch(
    () => route.query.tab,
    (tab) => {
      if (applyRouteTab(tab, true)) {
        void loadInstrumentOptions(formSymbolText())
        void loadCoverageMatrix()
        void lookupInstrument()
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

  function assetLabel(assetType: MarketAssetType) {
    return t(assetTabs.find((asset) => asset.key === assetType)?.labelKey || 'dataMgmt.assetStock')
  }

  function setAssetType(assetType: MarketAssetType) {
    if (applyAssetType(assetType)) {
      void loadInstrumentOptions(formSymbolText())
      void loadCoverageMatrix()
      void lookupInstrument()
    }
  }

  function applyRouteTab(tabValue: unknown, resetResult: boolean) {
    const assetType = routeTabMap[String(tabValue || '').toLowerCase()]
    if (!assetType) return false
    return applyAssetType(assetType, resetResult)
  }

  function applyAssetType(assetType: MarketAssetType, resetResult = true) {
    const changed = form.asset_type !== assetType
    form.asset_type = assetType
    restoreAssetSelection(assetType)
    if (changed && resetResult) {
      result.value = null
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

  async function lookupInstrument(refreshOnline = false) {
    const symbol = formSymbolText()
    if (!symbol) {
      ElMessage.error(t('dataMgmt.msgSymbolRequired'))
      return
    }
    const queryAssetType = form.asset_type
    const queryMarket = queryAssetType === 'futures' ? formMarketText() : ''
    loading.value = true
    try {
      const response = await marketDataApi.lookupInstrument({
        asset_type: queryAssetType,
        symbol,
        period: form.period,
        start_date: dateRange.value?.[0],
        end_date: dateRange.value?.[1],
        market: queryMarket || undefined,
        refresh_online: refreshOnline,
      })
      result.value = response
      rememberMarketAssetSelection(queryAssetType, symbol, queryMarket)
      void loadRelatedTables(response)
      ElMessage.success(t('dataMgmt.msgQueriedCount', { count: response.history.total }))
    } catch {
      result.value = null
      relatedTables.value = []
      ElMessage.error(t('dataMgmt.msgQueryFail'))
    } finally {
      loading.value = false
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

  function buildAssetDataFamilies(): DataFamilyView[] {
    return assetDataFamilySpecs[form.asset_type].map((family) => {
      const fieldEntries = [...family.fields, ...(family.historyFields || [])]
      const uniqueFields = Array.from(new Set(fieldEntries))
      const fields = uniqueFields.map((field) => ({
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
        label: t(family.labelKey),
        description: t(family.descKey, { count: relatedTableCount }),
        statusLabel: t(`dataMgmt.familyStatus${capitalize(status)}`),
        tagType: status === 'available' ? 'success' : status === 'partial' ? 'warning' : 'info',
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
    return t(fieldLabelKeys[field] || field)
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
    const close = numericValue(row.close, 0)
    return [
      numericValue(row.open, close),
      close,
      numericValue(row.low, close),
      numericValue(row.high, close),
    ]
  }

  function candleColor(row: MarketHistoryRow) {
    const open = numericValue(row.open, 0)
    const close = numericValue(row.close, open)
    return close >= open ? CANDLE_UP_COLOR : CANDLE_DOWN_COLOR
  }

  function buildAssetKpiCards(): KpiCard[] {
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
    snapshotDescriptionColumns,
    marketChart,
    instrumentOptionsRequestId,
    relatedTableRequestId,
    coverageRequestId,
    snapshot,
    historyRows,
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
    lookupInstrument,
    loadCoverageMatrix,
    refreshCoverageMatrix,
    searchInstrumentOptions,
    handleInstrumentDropdownVisible,
    loadInstrumentOptions,
    ensureCurrentInstrumentOption,
    formSymbolText,
    formMarketText,
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
    formatHistoryCell,
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
