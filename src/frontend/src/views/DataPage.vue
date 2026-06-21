<template>
  <div class="history-data-page">
    <el-card class="history-query-card">
      <template #header>
        <div class="history-query-header">
          <div>
            <h2>{{ t('dataMgmt.headerTitle') }}</h2>
            <p>{{ t('dataMgmt.headerDesc') }}</p>
          </div>
          <el-tag type="info">
            {{ t('dataMgmt.providerTag', { provider: result?.provider || '-' }) }}
          </el-tag>
        </div>
      </template>

      <div
        class="asset-tabbar"
        role="tablist"
      >
        <button
          v-for="asset in assetTabs"
          :key="asset.key"
          class="asset-tab"
          :class="{ 'is-active': form.asset_type === asset.key }"
          type="button"
          role="tab"
          :aria-selected="form.asset_type === asset.key"
          @click="setAssetType(asset.key)"
        >
          <span>{{ t(asset.labelKey) }}</span>
        </button>
      </div>

      <div
        class="history-query-toolbar"
        :class="{ 'has-market': form.asset_type === 'futures' }"
      >
        <el-input
          v-model="form.symbol"
          clearable
          :placeholder="symbolPlaceholder"
          @keyup.enter="lookupInstrument"
        />
        <el-select
          v-model="form.period"
          :placeholder="t('dataMgmt.periodPlaceholder')"
        >
          <el-option
            v-for="period in periods"
            :key="period.value"
            :label="t(period.labelKey)"
            :value="period.value"
          />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          :start-placeholder="t('dataMgmt.formStartDate')"
          :end-placeholder="t('dataMgmt.formEndDate')"
          value-format="YYYY-MM-DD"
        />
        <el-input
          v-if="form.asset_type === 'futures'"
          v-model="form.market"
          :placeholder="t('dataMgmt.futuresMarketPlaceholder')"
        />
        <el-button
          type="primary"
          :loading="loading"
          @click="lookupInstrument"
        >
          {{ t('dataMgmt.btnQuery') }}
        </el-button>
      </div>
    </el-card>

    <section class="asset-overview">
      <div>
        <span class="asset-overview-label">{{ assetLabel(form.asset_type) }}</span>
        <h3>{{ t(activeAssetConfig.titleKey) }}</h3>
        <p>{{ t(activeAssetConfig.descKey) }}</p>
      </div>
      <div class="asset-overview-meta">
        <span>{{ result?.market || '-' }}</span>
        <strong>{{ result?.symbol || form.symbol || '-' }}</strong>
      </div>
    </section>

    <div class="history-metrics-grid">
      <div
        v-for="item in assetKpiCards"
        :key="item.label"
        class="history-metric-card"
      >
        <span>{{ item.label }}</span>
        <strong :class="item.tone">{{ item.value }}</strong>
      </div>
    </div>

    <el-alert
      v-if="result?.warnings?.length"
      class="history-alert"
      type="warning"
      show-icon
      :closable="false"
      :title="t('dataMgmt.warningTitle')"
      :description="result.warnings.join('；')"
    />

    <div class="asset-insight-grid">
      <el-card class="snapshot-card">
        <template #header>
          <div class="section-header">
            <span>{{ t('dataMgmt.snapshotTitle') }}</span>
            <el-tag size="small">
              {{ assetLabel(result?.asset_type || form.asset_type) }}
            </el-tag>
          </div>
        </template>
        <el-empty
          v-if="!result"
          :description="t('dataMgmt.emptyQueryFirst')"
        />
        <el-descriptions
          v-else
          :column="1"
          border
        >
          <el-descriptions-item :label="t('dataMgmt.fieldSymbol')">
            {{ result.symbol }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataMgmt.fieldName')">
            {{ result.name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataMgmt.fieldMarket')">
            {{ result.market || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataMgmt.fieldPrice')">
            {{ formatNumber(snapshot.price) }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="hasSnapshotChange"
            :label="t('dataMgmt.colChange')"
          >
            <span :class="toneClass(snapshot.change_pct ?? snapshot.change)">
              {{ formatNumber(snapshot.change) }} / {{ formatPercent(snapshot.change_pct) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataMgmt.fieldOpen')">
            {{ formatNumber(snapshot.open) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataMgmt.fieldHighLow')">
            {{ formatNumber(snapshot.high) }} / {{ formatNumber(snapshot.low) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataMgmt.fieldVolume')">
            {{ formatNumber(snapshot.volume) }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="hasSnapshotTurnover"
            :label="t('dataMgmt.fieldTurnover')"
          >
            {{ formatNumber(snapshot.turnover) }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="hasSnapshotBidAsk"
            :label="t('dataMgmt.fieldBidAsk')"
          >
            {{ formatNumber(snapshot.bid) }} / {{ formatNumber(snapshot.ask) }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="hasSnapshotOpenInterest"
            :label="t('dataMgmt.fieldOpenInterest')"
          >
            {{ formatNumber(snapshot.open_interest) }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="hasSnapshotSettle"
            :label="t('dataMgmt.fieldSettle')"
          >
            {{ formatNumber(snapshot.settle) }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="hasSnapshotValuation"
            :label="t('dataMgmt.fieldValuation')"
          >
            PE {{ formatNumber(snapshot.pe) }} / PB {{ formatNumber(snapshot.pb) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataMgmt.fieldUpdated')">
            {{ snapshot.update_time || '-' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card class="asset-detail-card">
        <template #header>
          <div class="section-header">
            <span>{{ t(activeAssetConfig.detailTitleKey) }}</span>
            <el-tag
              v-if="result?.provider"
              size="small"
              type="info"
            >
              {{ result.provider }}
            </el-tag>
          </div>
        </template>
        <el-empty
          v-if="!result"
          :description="t('dataMgmt.emptyQueryFirst')"
        />
        <div
          v-else
          class="asset-detail-list"
        >
          <div
            v-for="row in assetDetailRows"
            :key="row.label"
            class="asset-detail-row"
          >
            <span>{{ row.label }}</span>
            <strong :class="row.tone">{{ row.value }}</strong>
          </div>
          <p>{{ t(activeAssetConfig.detailNoteKey) }}</p>
        </div>
      </el-card>
    </div>

    <el-card class="history-table-card">
      <template #header>
        <div class="section-header">
          <span>{{ t('dataMgmt.cardHistory') }}</span>
          <el-tag
            v-if="result"
            size="small"
            type="success"
          >
            {{ t('dataMgmt.historyRows', { count: result.history.total }) }}
          </el-tag>
        </div>
      </template>
      <el-table
        v-if="historyRows.length"
        v-loading="loading"
        :data="historyRows"
        stripe
        max-height="520"
      >
        <el-table-column
          v-for="column in historyTableColumns"
          :key="column.key"
          :prop="column.key"
          :label="column.label"
          :width="column.width"
          :min-width="column.minWidth"
          :align="column.align"
          :fixed="column.fixed"
        >
          <template #default="{ row }">
            <span :class="column.tone ? toneClass(row[column.key]) : ''">
              {{ formatHistoryCell(row, column) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-else
        :description="emptyHistoryText"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  marketDataApi,
  type MarketAssetType,
  type MarketHistoryRow,
  type MarketInstrumentLookupResponse,
} from '@/api/marketData'

const { t } = useI18n()
const route = useRoute()

const today = new Date()
const ninetyDaysAgo = new Date(today)
ninetyDaysAgo.setDate(today.getDate() - 90)

type AssetTab = {
  key: MarketAssetType
  labelKey: string
  placeholderKey: string
  defaultSymbol: string
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

type HistoryTableColumn = Omit<HistoryColumnSpec, 'labelKey'> & {
  label: string
}

const assetTabs: AssetTab[] = [
  {
    key: 'stock',
    labelKey: 'dataMgmt.tabStock',
    placeholderKey: 'dataMgmt.stockSymbolPlaceholder',
    defaultSymbol: '000001',
  },
  {
    key: 'futures',
    labelKey: 'dataMgmt.tabFutures',
    placeholderKey: 'dataMgmt.futuresSymbolPlaceholder',
    defaultSymbol: 'RB2510',
  },
  {
    key: 'bond',
    labelKey: 'dataMgmt.tabBond',
    placeholderKey: 'dataMgmt.bondSymbolPlaceholder',
    defaultSymbol: 'sh113527',
  },
  {
    key: 'fund',
    labelKey: 'dataMgmt.tabFund',
    placeholderKey: 'dataMgmt.fundSymbolPlaceholder',
    defaultSymbol: '159915',
  },
  {
    key: 'option',
    labelKey: 'dataMgmt.tabOptions',
    placeholderKey: 'dataMgmt.optionSymbolPlaceholder',
    defaultSymbol: '10003889',
  },
  {
    key: 'fx',
    labelKey: 'dataMgmt.tabFx',
    placeholderKey: 'dataMgmt.fxSymbolPlaceholder',
    defaultSymbol: 'USDCNH',
  },
  {
    key: 'crypto',
    labelKey: 'dataMgmt.tabCrypto',
    placeholderKey: 'dataMgmt.cryptoSymbolPlaceholder',
    defaultSymbol: 'BTCJPY',
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
    ],
    historyColumns: [
      { key: 'open', labelKey: 'dataMgmt.colOpen', width: 110, align: 'right' },
      { key: 'high', labelKey: 'dataMgmt.colHigh', width: 110, align: 'right' },
      { key: 'low', labelKey: 'dataMgmt.colLow', width: 110, align: 'right' },
      { key: 'close', labelKey: 'dataMgmt.colClose', width: 110, align: 'right' },
      { key: 'volume', labelKey: 'dataMgmt.colVolume', width: 130, align: 'right' },
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

const snapshot = computed<Record<string, unknown>>(() => result.value?.snapshot || {})
const historyRows = computed(() => result.value?.history.rows || [])
const activeAssetConfig = computed(() => assetDisplayConfigs[form.asset_type])
const symbolPlaceholder = computed(() => t(currentAssetTab().placeholderKey))
const emptyHistoryText = computed(() => (
  result.value ? t('dataMgmt.emptyNoRows') : t('dataMgmt.emptyQueryFirst')
))
const hasSnapshotChange = computed(() => hasValue(snapshot.value.change) || hasValue(snapshot.value.change_pct))
const hasSnapshotTurnover = computed(() => hasValue(snapshot.value.turnover))
const hasSnapshotBidAsk = computed(() => hasValue(snapshot.value.bid) || hasValue(snapshot.value.ask))
const hasSnapshotOpenInterest = computed(() => hasValue(snapshot.value.open_interest))
const hasSnapshotSettle = computed(() => hasValue(snapshot.value.settle))
const hasSnapshotValuation = computed(() => hasValue(snapshot.value.pe) || hasValue(snapshot.value.pb))
const assetKpiCards = computed<KpiCard[]>(() => buildAssetKpiCards())
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
  applyRouteTab(route.query.tab, false)
  void lookupInstrument()
})

watch(
  () => route.query.tab,
  (tab) => {
    if (applyRouteTab(tab, true)) {
      void lookupInstrument()
    }
  },
)

function currentAssetTab() {
  return assetTabs.find((asset) => asset.key === form.asset_type) || {
    key: 'stock',
    labelKey: 'dataMgmt.tabStock',
    placeholderKey: 'dataMgmt.stockSymbolPlaceholder',
    defaultSymbol: '000001',
  }
}

function assetLabel(assetType: MarketAssetType) {
  return t(assetTabs.find((asset) => asset.key === assetType)?.labelKey || 'dataMgmt.assetStock')
}

function setAssetType(assetType: MarketAssetType) {
  if (applyAssetType(assetType)) {
    void lookupInstrument()
  }
}

function applyRouteTab(tabValue: unknown, resetResult: boolean) {
  const assetType = routeTabMap[String(tabValue || '').toLowerCase()]
  if (!assetType) return false
  return applyAssetType(assetType, resetResult)
}

function applyAssetType(assetType: MarketAssetType, resetResult = true) {
  if (form.asset_type === assetType) return false

  const previousTab = currentAssetTab()
  form.asset_type = assetType
  const nextTab = currentAssetTab()
  if (!form.symbol.trim() || form.symbol === previousTab.defaultSymbol) {
    form.symbol = nextTab.defaultSymbol
  }
  if (form.asset_type !== 'futures') {
    form.market = 'CF'
  }
  if (resetResult) {
    result.value = null
  }
  return true
}

async function lookupInstrument() {
  if (!form.symbol.trim()) {
    ElMessage.error(t('dataMgmt.msgSymbolRequired'))
    return
  }
  loading.value = true
  try {
    const response = await marketDataApi.lookupInstrument({
      asset_type: form.asset_type,
      symbol: form.symbol.trim(),
      period: form.period,
      start_date: dateRange.value?.[0],
      end_date: dateRange.value?.[1],
      market: form.asset_type === 'futures' ? form.market.trim() || undefined : undefined,
    })
    result.value = response
    ElMessage.success(t('dataMgmt.msgQueriedCount', { count: response.history.total }))
  } catch {
    result.value = null
    ElMessage.error(t('dataMgmt.msgQueryFail'))
  } finally {
    loading.value = false
  }
}

function toDateInput(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
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
</script>

<style scoped>
.history-data-page {
  display: grid;
  gap: 16px;
}

.history-query-header,
.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.history-query-header h2 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 22px;
  line-height: 1.25;
}

.history-query-header p {
  margin: 6px 0 0;
  color: var(--text-color-secondary);
  font-size: 13px;
}

.asset-tabbar {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.asset-tab {
  display: flex;
  align-items: center;
  min-width: 0;
  min-height: 44px;
  padding: 9px 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-page);
  color: var(--text-color-primary);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease;
}

.asset-tab span {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.2;
}

.asset-tab.is-active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.history-query-toolbar {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 140px minmax(260px, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.history-query-toolbar.has-market {
  grid-template-columns: minmax(180px, 1fr) 140px minmax(260px, 1fr) minmax(120px, 0.5fr) auto;
}

.asset-overview {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 18px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-overlay);
}

.asset-overview-label {
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
}

.asset-overview h3 {
  margin: 6px 0 4px;
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.3;
}

.asset-overview p {
  margin: 0;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.asset-overview-meta {
  display: grid;
  justify-items: end;
  gap: 4px;
  min-width: 140px;
}

.asset-overview-meta span {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.asset-overview-meta strong {
  color: var(--text-color-primary);
  font-size: 18px;
  overflow-wrap: anywhere;
}

.history-metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.history-metric-card {
  display: grid;
  gap: 6px;
  min-height: 76px;
  padding: 12px 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-overlay);
}

.history-metric-card span {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.history-metric-card strong {
  min-width: 0;
  color: var(--text-color-primary);
  font-size: 18px;
  overflow-wrap: anywhere;
}

.is-positive {
  color: var(--el-color-danger) !important;
}

.is-negative {
  color: var(--el-color-success) !important;
}

.history-alert {
  margin: 0;
}

.asset-insight-grid {
  display: grid;
  grid-template-columns: minmax(300px, 0.42fr) minmax(360px, 1fr);
  gap: 16px;
}

.snapshot-card,
.asset-detail-card,
.history-table-card {
  min-width: 0;
}

.asset-detail-list {
  display: grid;
  gap: 10px;
}

.asset-detail-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  min-height: 42px;
  padding: 10px 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-page);
}

.asset-detail-row span {
  color: var(--text-color-secondary);
  font-size: 13px;
}

.asset-detail-row strong {
  min-width: 0;
  color: var(--text-color-primary);
  font-size: 15px;
  text-align: right;
  overflow-wrap: anywhere;
}

.asset-detail-list p {
  margin: 2px 0 0;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 1180px) {
  .asset-tabbar {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .history-query-toolbar,
  .history-query-toolbar.has-market {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .history-metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .asset-insight-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .history-query-header,
  .section-header {
    flex-direction: column;
  }

  .asset-tabbar,
  .history-query-toolbar,
  .history-query-toolbar.has-market,
  .history-metrics-grid {
    grid-template-columns: 1fr;
  }

  .asset-overview {
    flex-direction: column;
  }

  .asset-overview-meta {
    justify-items: start;
  }
}
</style>
