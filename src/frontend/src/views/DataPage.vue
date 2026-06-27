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
          <el-icon aria-hidden="true">
            <component :is="asset.icon" />
          </el-icon>
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
          <el-icon aria-hidden="true">
            <Search />
          </el-icon>
          <span>{{ t('dataMgmt.btnQuery') }}</span>
        </el-button>
      </div>
    </el-card>

    <section class="asset-overview">
      <div class="asset-overview-main">
        <span class="asset-overview-icon">
          <el-icon aria-hidden="true">
            <component :is="currentAssetTab().icon" />
          </el-icon>
        </span>
        <div>
          <span class="asset-overview-label">{{ assetLabel(form.asset_type) }}</span>
          <h3>{{ t(activeAssetConfig.titleKey) }}</h3>
          <p>{{ t(activeAssetConfig.descKey) }}</p>
        </div>
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
        <div class="history-metric-head">
          <span>{{ item.label }}</span>
          <i :class="item.tone || 'is-neutral'" />
        </div>
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

    <section class="market-workbench-grid">
      <el-card class="market-chart-card">
        <template #header>
          <div class="section-header market-chart-header">
            <div>
              <span>{{ t('dataMgmt.chartOverviewTitle') }}</span>
              <small>{{ chartSubtitle }}</small>
            </div>
            <div class="chart-mode-tabs">
              <button
                v-for="mode in chartModeOptions"
                :key="mode.value"
                class="chart-mode-tab"
                :class="{ 'is-active': chartMode === mode.value }"
                type="button"
                @click="chartMode = mode.value"
              >
                {{ mode.label }}
              </button>
            </div>
          </div>
        </template>
        <el-empty
          v-if="!chartCanRender"
          :description="chartEmptyText"
        />
        <div
          v-show="chartCanRender"
          ref="marketChartRef"
          class="market-main-chart"
          data-test="market-main-chart"
          role="img"
          :aria-label="chartAriaLabel"
        />
      </el-card>

      <div class="market-side-panels">
        <section class="market-panel">
          <div class="market-panel-header">
            <span>{{ t('dataMgmt.rangeStatsTitle') }}</span>
            <strong>{{ formatNumber(result?.indicators.observation_count) }}</strong>
          </div>
          <div class="market-stat-list">
            <div
              v-for="item in rangeStats"
              :key="item.label"
              class="market-stat-row"
            >
              <span>{{ item.label }}</span>
              <strong :class="item.tone">{{ item.value }}</strong>
            </div>
          </div>
        </section>

        <section class="market-panel">
          <div class="market-panel-header">
            <span>{{ t('dataMgmt.coverageTitle') }}</span>
            <strong>{{ coverageScore }}%</strong>
          </div>
          <div class="coverage-list">
            <div
              v-for="item in dataCoverageRows"
              :key="item.label"
              class="coverage-row"
            >
              <div>
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
              <i :style="{ width: `${item.coverage}%` }" />
            </div>
          </div>
        </section>
      </div>
    </section>

    <section class="data-catalog-section">
      <div class="data-catalog-header">
        <div>
          <span>{{ t('dataMgmt.dataCatalogTitle') }}</span>
          <p>{{ t('dataMgmt.dataCatalogDesc') }}</p>
        </div>
        <el-tag :type="relatedTablesError ? 'warning' : 'info'">
          {{ relatedTablesBadge }}
        </el-tag>
      </div>

      <div class="data-catalog-grid">
        <div class="data-family-grid">
          <article
            v-for="family in assetDataFamilies"
            :key="family.label"
            class="data-family-card"
          >
            <div class="data-family-card-head">
              <span>{{ family.label }}</span>
              <el-tag
                size="small"
                :type="family.tagType"
              >
                {{ family.statusLabel }}
              </el-tag>
            </div>
            <p>{{ family.description }}</p>
            <div class="field-chip-row">
              <span
                v-for="field in family.fields"
                :key="field.name"
                class="field-chip"
                :class="{ 'is-present': field.present }"
              >
                {{ field.label }}
              </span>
            </div>
          </article>
        </div>

        <aside
          v-loading="relatedTablesLoading"
          class="related-table-panel"
        >
          <div class="related-table-header">
            <div>
              <span>{{ t('dataMgmt.relatedTablesTitle') }}</span>
              <small>{{ relatedTableSummary }}</small>
            </div>
            <el-button
              size="small"
              @click="loadRelatedTables()"
            >
              <el-icon aria-hidden="true">
                <Refresh />
              </el-icon>
              <span>{{ t('dataMgmt.btnRefresh') }}</span>
            </el-button>
          </div>
          <el-empty
            v-if="!relatedTables.length && !relatedTablesLoading"
            :description="relatedTablesError || t('dataMgmt.relatedTablesEmpty')"
          />
          <div
            v-else
            class="related-table-list"
          >
            <button
              v-for="table in relatedTables.slice(0, 6)"
              :key="table.id"
              type="button"
              class="related-table-row"
              @click="goTableDetail(table.id)"
            >
              <span>
                <strong>{{ table.table_name }}</strong>
                <small>{{ table.table_comment || table.script_id || '-' }}</small>
              </span>
              <em>{{ formatNumber(table.row_count) }}</em>
            </button>
          </div>
        </aside>
      </div>
    </section>

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
          <el-descriptions-item
            v-if="hasSnapshotDataSource"
            :label="t('dataMgmt.fieldDataSourceTable')"
          >
            {{ snapshot.data_source_table }}
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
  Refresh,
  Search,
  Tickets,
  TrendCharts,
} from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { akshareTablesApi } from '@/api/akshare'
import {
  marketDataApi,
  type MarketAssetType,
  type MarketHistoryRow,
  type MarketInstrumentLookupResponse,
} from '@/api/marketData'
import { CANDLE_DOWN_COLOR, CANDLE_ITEM_STYLE, CANDLE_UP_COLOR } from '@/constants/chartColors'
import type { DataTable } from '@/types'

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
    defaultSymbol: '151.ni2609C184000',
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
const relatedTablesLoading = ref(false)
const relatedTables = ref<DataTable[]>([])
const relatedTablesError = ref('')
let marketChart: echarts.ECharts | null = null
let relatedTableRequestId = 0

const snapshot = computed<Record<string, unknown>>(() => result.value?.snapshot || {})
const historyRows = computed(() => result.value?.history.rows || [])
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
  applyRouteTab(route.query.tab, false)
  void lookupInstrument()
  window.addEventListener('resize', resizeMarketChart)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeMarketChart)
  disposeMarketChart()
})

watch(
  () => route.query.tab,
  (tab) => {
    if (applyRouteTab(tab, true)) {
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
        lineStyle: { width: 2, color: '#2563eb' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(37, 99, 235, 0.22)' },
            { offset: 1, color: 'rgba(37, 99, 235, 0.02)' },
          ]),
        },
      },
      {
        name: t('dataMgmt.chartDrawdown'),
        type: 'line',
        data: drawdowns,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.6, color: '#dc2626' },
      },
      {
        name: t('charts.klineVolume'),
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes,
        itemStyle: { color: '#64748b' },
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
        itemStyle: { color: '#0f766e' },
        barMaxWidth: 14,
      },
      {
        name: t('dataMgmt.fieldTurnover'),
        type: 'line',
        yAxisIndex: 1,
        data: turnover,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: '#f59e0b', width: 2 },
      },
      {
        name: t('dataMgmt.fieldOpenInterest'),
        type: 'line',
        yAxisIndex: 1,
        data: openInterest,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: '#7c3aed', width: 2 },
      },
    ],
  })
}

function buildStructureChartOption(): echarts.EChartsOption {
  const rows = historyRows.value
  const labels = rows.map((row, index) => String(row.name || row.date || index + 1))
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
        itemStyle: { color: '#0891b2' },
        barMaxWidth: 18,
      },
      {
        name: t('dataMgmt.fieldOpenInterest'),
        type: 'bar',
        data: rows.map((row) => numericValue(row.open_interest, 0)),
        itemStyle: { color: '#6366f1' },
        barMaxWidth: 18,
      },
      {
        name: t('dataMgmt.colChangeValue'),
        type: 'line',
        yAxisIndex: 1,
        data: rows.map((row) => numericValue(row.change, null)),
        smooth: true,
        lineStyle: { color: '#dc2626', width: 2 },
      },
    ],
  })
}

function baseChartOption(option: MarketChartOptionDraft): echarts.EChartsOption {
  const { legend, ...restOption } = option
  return {
    animation: false,
    color: ['#2563eb', '#dc2626', '#0f766e', '#f59e0b', '#7c3aed'],
    backgroundColor: 'transparent',
    legend: {
      top: 8,
      left: 56,
      itemWidth: 10,
      itemHeight: 8,
      textStyle: { color: '#475569', fontSize: 12 },
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
  return {
    type: 'category',
    data,
    boundaryGap: false,
    axisLine: { lineStyle: { color: '#cbd5e1' }, onZero: false },
    axisTick: { show: false },
    axisLabel: { color: '#64748b', hideOverlap: true },
    splitLine: { show: false },
  }
}

function valueAxis(overrides: Partial<echarts.YAXisComponentOption> = {}): echarts.YAXisComponentOption {
  return {
    type: 'value',
    scale: true,
    axisLabel: { color: '#64748b', formatter: compactAxisLabel },
    splitLine: { lineStyle: { color: '#e2e8f0', type: 'dashed' } },
    ...overrides,
  } as echarts.YAXisComponentOption
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
  if (absValue >= 1e8) return `${(numericValue / 1e8).toFixed(1)}亿`
  if (absValue >= 1e4) return `${(numericValue / 1e4).toFixed(1)}万`
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
  gap: 18px;
  color: var(--text-color-primary);
}

.history-query-card,
.market-chart-card,
.snapshot-card,
.asset-detail-card,
.history-table-card {
  border: 1px solid rgba(148, 163, 184, 0.22);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
}

.history-query-card :deep(.el-card__header),
.market-chart-card :deep(.el-card__header),
.snapshot-card :deep(.el-card__header),
.asset-detail-card :deep(.el-card__header),
.history-table-card :deep(.el-card__header) {
  padding: 14px 18px;
  border-bottom-color: rgba(148, 163, 184, 0.18);
  background: var(--bg-color-overlay);
}

.history-query-card :deep(.el-card__body),
.market-chart-card :deep(.el-card__body),
.snapshot-card :deep(.el-card__body),
.asset-detail-card :deep(.el-card__body),
.history-table-card :deep(.el-card__body) {
  padding: 16px 18px;
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
  font-size: 21px;
  line-height: 1.25;
  letter-spacing: 0;
}

.history-query-header p {
  margin: 6px 0 0;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.history-query-header :deep(.el-tag) {
  height: 26px;
  border-color: transparent;
  background: var(--bg-color-page);
  color: var(--text-color-secondary);
  font-weight: 600;
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
  gap: 8px;
  min-width: 0;
  min-height: 44px;
  padding: 9px 11px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 8px;
  background: var(--bg-color-page);
  color: var(--text-color-primary);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.asset-tab:hover {
  border-color: rgba(37, 99, 235, 0.28);
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.05);
  transform: translateY(-1px);
}

.asset-tab .el-icon {
  flex: 0 0 auto;
  color: var(--text-color-secondary);
  font-size: 16px;
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
  box-shadow: inset 0 -2px 0 var(--el-color-primary);
}

.asset-tab.is-active .el-icon {
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

.history-query-toolbar :deep(.el-input__wrapper),
.history-query-toolbar :deep(.el-select__wrapper) {
  min-height: 36px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.24) inset;
}

.history-query-toolbar :deep(.el-button) {
  min-height: 36px;
  padding-inline: 16px;
  font-weight: 700;
}

.asset-overview {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 18px 20px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  background: var(--bg-color-overlay);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
}

.asset-overview-main {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  min-width: 0;
}

.asset-overview-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  border: 1px solid rgba(37, 99, 235, 0.22);
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 18px;
}

.asset-overview-label {
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
}

.asset-overview h3 {
  margin: 4px 0 5px;
  color: var(--text-color-primary);
  font-size: 20px;
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
  padding-left: 18px;
  border-left: 1px solid rgba(148, 163, 184, 0.22);
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
  gap: 12px;
}

.history-metric-card {
  display: grid;
  gap: 10px;
  min-height: 82px;
  padding: 14px 15px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  background: var(--bg-color-overlay);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.045);
}

.history-metric-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.history-metric-head span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 600;
}

.history-metric-head i {
  display: block;
  width: 28px;
  height: 3px;
  border-radius: 999px;
  background: var(--border-color-light);
}

.history-metric-head i.is-positive {
  background: var(--el-color-danger);
}

.history-metric-head i.is-negative {
  background: var(--el-color-success);
}

.history-metric-card strong {
  min-width: 0;
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1.15;
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

.market-workbench-grid {
  display: grid;
  grid-template-columns: minmax(620px, 1fr) minmax(280px, 0.31fr);
  gap: 16px;
  align-items: stretch;
}

.market-chart-card,
.market-side-panels,
.data-catalog-section {
  min-width: 0;
}

.market-chart-header > div:first-child {
  display: grid;
  gap: 4px;
}

.market-chart-header span,
.data-catalog-header span,
.market-panel-header span,
.related-table-header span,
.data-family-card-head span {
  color: var(--text-color-primary);
  font-size: 15px;
  font-weight: 700;
  line-height: 1.3;
}

.market-chart-header small,
.related-table-header small {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.chart-mode-tabs {
  display: inline-grid;
  grid-auto-flow: column;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-page);
}

.chart-mode-tab {
  min-height: 28px;
  padding: 5px 10px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-color-secondary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.chart-mode-tab.is-active {
  background: var(--el-color-primary);
  color: #fff;
}

.market-main-chart {
  width: 100%;
  height: 410px;
}

.market-side-panels {
  display: grid;
  gap: 16px;
}

.market-panel,
.data-catalog-section,
.related-table-panel {
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  background: var(--bg-color-overlay);
}

.market-panel {
  display: grid;
  gap: 12px;
  padding: 15px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.045);
}

.market-panel-header,
.data-catalog-header,
.related-table-header,
.data-family-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.related-table-header > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.market-panel-header strong {
  color: var(--el-color-primary);
  font-size: 18px;
  line-height: 1.2;
}

.market-stat-list,
.coverage-list,
.related-table-list {
  display: grid;
  gap: 8px;
}

.market-stat-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 30px;
}

.market-stat-row span,
.coverage-row span,
.field-chip,
.related-table-row small {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.market-stat-row strong {
  min-width: 0;
  color: var(--text-color-primary);
  font-size: 13px;
  text-align: right;
  overflow-wrap: anywhere;
}

.coverage-row {
  display: grid;
  gap: 6px;
}

.coverage-row div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.coverage-row strong {
  color: var(--text-color-primary);
  font-size: 12px;
}

.coverage-row i {
  display: block;
  height: 5px;
  min-width: 4px;
  border-radius: 999px;
  background: var(--el-color-primary);
}

.data-catalog-section {
  display: grid;
  gap: 14px;
  padding: 16px 18px;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
}

.data-catalog-header p {
  margin: 4px 0 0;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.data-catalog-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 0.36fr);
  gap: 14px;
  align-items: start;
}

.data-family-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  align-items: start;
}

.data-family-card {
  display: grid;
  align-content: start;
  gap: 10px;
  min-width: 0;
  min-height: 132px;
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  background: var(--bg-color-page);
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.data-family-card:hover {
  border-color: rgba(37, 99, 235, 0.24);
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.045);
  transform: translateY(-1px);
}

.data-family-card p {
  margin: 0;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.field-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.field-chip {
  max-width: 100%;
  padding: 3px 7px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 999px;
  background: var(--bg-color-overlay);
  overflow-wrap: anywhere;
}

.field-chip.is-present {
  border-color: rgba(15, 118, 110, 0.26);
  background: rgba(15, 118, 110, 0.08);
  color: #0f766e;
}

.related-table-panel {
  display: grid;
  align-content: start;
  gap: 12px;
  min-width: 0;
  padding: 12px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.045);
}

.related-table-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-height: 48px;
  padding: 8px 10px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  background: var(--bg-color-page);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.16s ease, background-color 0.16s ease;
}

.related-table-row:hover {
  border-color: rgba(37, 99, 235, 0.24);
  background: var(--el-color-primary-light-9);
}

.related-table-row span {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.related-table-row strong,
.related-table-row small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.related-table-row strong {
  color: var(--text-color-primary);
  font-size: 13px;
}

.related-table-row em {
  flex: 0 0 auto;
  color: var(--el-color-primary);
  font-size: 12px;
  font-style: normal;
  font-weight: 700;
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
  border: 1px solid rgba(148, 163, 184, 0.16);
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

.snapshot-card :deep(.el-descriptions__label) {
  width: 108px;
  background: var(--bg-color-page);
  color: var(--text-color-secondary);
  font-weight: 700;
}

.snapshot-card :deep(.el-descriptions__content) {
  color: var(--text-color-primary);
  font-weight: 600;
}

.history-table-card :deep(.el-table) {
  --el-table-header-bg-color: var(--bg-color-page);
  --el-table-row-hover-bg-color: var(--el-color-primary-light-9);
}

.history-table-card :deep(.el-table th.el-table__cell) {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 700;
}

.history-table-card :deep(.el-table .cell) {
  line-height: 1.45;
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

  .market-workbench-grid,
  .data-catalog-grid {
    grid-template-columns: 1fr;
  }

  .data-family-grid {
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
  .history-metrics-grid,
  .data-family-grid {
    grid-template-columns: 1fr;
  }

  .market-chart-header,
  .data-catalog-header,
  .related-table-header {
    flex-direction: column;
  }

  .chart-mode-tabs {
    grid-auto-flow: row;
    width: 100%;
  }

  .chart-mode-tab {
    width: 100%;
  }

  .market-main-chart {
    height: 320px;
  }

  .asset-overview {
    flex-direction: column;
  }

  .asset-overview-meta {
    justify-items: start;
  }
}
</style>
