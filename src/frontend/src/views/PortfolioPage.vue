<template>
  <div
    class="portfolio-page"
    data-test="portfolio-page"
  >
    <div
      v-if="loading"
      class="portfolio-loading"
    >
      <el-icon class="is-loading portfolio-loading__icon" aria-hidden="true">
        <Loading />
      </el-icon>
      <span>{{ t('common.loading') }}</span>
    </div>

    <template v-else>
      <section
        class="portfolio-hero"
        data-test="portfolio-hero"
      >
        <div class="portfolio-hero__copy">
          <span class="portfolio-kicker">{{ t('portfolio.heroKicker') }}</span>
          <h1>{{ t('portfolio.heroTitle') }}</h1>
          <p>
            {{ t('portfolio.heroSubtitle', { running: runningWorkspaces.length }) }}
          </p>
          <div class="portfolio-hero__badges">
            <span
              v-for="badge in heroBadges"
              :key="badge.label"
              class="portfolio-badge"
            >
              <span>{{ badge.label }}</span>
              <strong>{{ badge.value }}</strong>
            </span>
          </div>
        </div>

        <div class="portfolio-hero__status">
          <span class="portfolio-status-chip">
            <span class="portfolio-status-dot" />
            {{ portfolioHealthLabel }}
          </span>
          <div class="portfolio-hero__asset">
            <span>{{ t('portfolio.cardTotalAssets') }}</span>
            <strong>{{ formatMoney(overview.total_assets) }}</strong>
          </div>
          <div
            class="portfolio-hero__pnl"
            :class="signedValueClass(overview.total_pnl)"
          >
            {{ formatSignedMoney(overview.total_pnl) }}
            <span>{{ formatSignedPercent(overview.total_pnl_pct) }}</span>
          </div>
          <el-button
            class="portfolio-refresh"
            :icon="Refresh"
            @click="loadData"
          >
            {{ t('portfolio.btnRefresh') }}
          </el-button>
        </div>
      </section>

      <section
        class="portfolio-overview"
        data-test="portfolio-overview"
        :aria-label="t('portfolio.overviewTitle')"
      >
        <article
          v-for="card in summaryCards"
          :key="card.label"
          class="portfolio-metric"
          :class="'portfolio-metric--' + card.tone"
        >
          <span class="portfolio-metric__icon">
            <el-icon aria-hidden="true">
              <component :is="card.icon" />
            </el-icon>
          </span>
          <span class="portfolio-metric__label">{{ card.label }}</span>
          <strong :class="card.valueClass">{{ card.value }}</strong>
          <small>{{ card.helper }}</small>
        </article>
      </section>

      <section class="portfolio-layout">
        <section
          class="portfolio-workbench"
          data-test="portfolio-workbench"
        >
          <div class="portfolio-panel-heading portfolio-panel-heading--inline">
            <div>
              <span class="portfolio-kicker">{{ t('portfolio.workbenchKicker') }}</span>
              <h2>{{ t('portfolio.workbenchTitle') }}</h2>
              <p>{{ t('portfolio.workbenchDesc') }}</p>
            </div>
          </div>

          <el-tabs
            v-model="activeTab"
            class="portfolio-tabs"
          >
            <el-tab-pane
              :label="t('portfolio.tabWorkspaces')"
              name="workspaces"
            >
              <div class="portfolio-tab-panel">
                <div class="portfolio-section-heading">
                  <h3>{{ t('portfolio.tabWorkspaces') }}</h3>
                  <span>{{ t('portfolio.workspacesDesc') }}</span>
                </div>
                <el-table
                  :data="runningWorkspaces"
                  stripe
                  size="small"
                  class="portfolio-table"
                >
                  <el-table-column
                    prop="name"
                    :label="t('portfolio.colWorkspaceName')"
                    min-width="180"
                  />
                  <el-table-column
                    :label="t('portfolio.colStatus')"
                    width="110"
                    align="center"
                  >
                    <template #default="{ row }">
                      <el-tag
                        :type="row.status === 'running' ? 'success' : row.status === 'error' ? 'danger' : 'info'"
                        size="small"
                      >
                        {{ workspaceStatusLabel(row.status) }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column
                    prop="unit_count"
                    :label="t('portfolio.colWorkspaceUnits')"
                    width="130"
                    align="right"
                  />
                </el-table>
              </div>
            </el-tab-pane>

            <el-tab-pane
              :label="t('portfolio.tabPositions')"
              name="positions"
            >
              <div class="portfolio-tab-panel">
                <div class="portfolio-section-heading">
                  <h3>{{ t('portfolio.tabPositions') }}</h3>
                  <span>{{ t('portfolio.positionsDesc') }}</span>
                </div>

                <div
                  v-if="isTabLoading('positions')"
                  class="portfolio-querying"
                >
                  <el-icon class="is-loading" aria-hidden="true">
                    <Loading />
                  </el-icon>
                  <span>{{ t('portfolio.querying') }}</span>
                </div>
                <template v-else>
                  <div
                    v-if="positions.length > 0"
                    class="portfolio-exposure-grid"
                  >
                    <article
                      v-for="card in positionMetricCards"
                      :key="card.label"
                      class="portfolio-exposure-card"
                    >
                      <span>{{ card.label }}</span>
                      <strong :class="card.valueClass">{{ card.value }}</strong>
                    </article>
                  </div>
                  <div
                    v-if="positions.length === 0"
                    class="portfolio-empty"
                  >
                    <el-icon aria-hidden="true">
                      <Operation />
                    </el-icon>
                    <span>{{ t('portfolio.emptyPositions') }}</span>
                  </div>
                  <el-table
                    v-else
                    :data="positions"
                    stripe
                    size="small"
                    class="portfolio-table"
                  >
                  <el-table-column
                    prop="strategy_name"
                    :label="t('portfolio.colStrategy')"
                    min-width="180"
                  />
                  <el-table-column
                    prop="data_name"
                    :label="t('portfolio.colSymbol')"
                    width="120"
                  />
                  <el-table-column
                    :label="t('portfolio.colDirection')"
                    width="90"
                    align="center"
                  >
                    <template #default="{ row }">
                      <el-tag
                        :type="positionDirectionTag(row)"
                        size="small"
                      >
                        {{ directionLabel(row.direction) }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colLongPosition')"
                    width="100"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ formatPositionSize(row.long_position) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colShortPosition')"
                    width="100"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ formatPositionSize(row.short_position) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colSize')"
                    width="100"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ formatPositionSize(row.size) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colCostPrice')"
                    width="110"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ formatNumber(row.price, 4) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colLatestPrice')"
                    width="110"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ formatNumber(row.latest_price ?? row.price, 4) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colMarketValue')"
                    width="130"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ formatMoney(row.market_value) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colPositionPnl')"
                    width="120"
                    align="right"
                  >
                    <template #default="{ row }">
                      <span :class="signedValueClass(row.position_pnl || 0)">
                        {{ formatSignedMoney(row.position_pnl || 0) }}
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colMarginValue')"
                    width="110"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ formatOptionalMoney(row.margin_value) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('workspaceDialogs.leverage')"
                    width="90"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ formatNumber(row.leverage, 2) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colCommission')"
                    width="100"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ formatNumber(row.commission, 2) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colValuationStatus')"
                    width="130"
                    align="center"
                  >
                    <template #default="{ row }">
                      <el-tooltip
                        :content="valuationTooltip(row)"
                        placement="top"
                      >
                        <el-tag
                          :type="valuationStatusTag(row)"
                          size="small"
                        >
                          {{ valuationStatusLabel(row) }}
                        </el-tag>
                      </el-tooltip>
                    </template>
                  </el-table-column>
                  <el-table-column
                    prop="updated_at"
                    :label="t('portfolio.colUpdatedAt')"
                    width="160"
                  >
                    <template #default="{ row }">
                      {{ formatDateTime(row.updated_at) }}
                    </template>
                  </el-table-column>
                  </el-table>
                </template>
              </div>
            </el-tab-pane>

            <el-tab-pane
              :label="t('portfolio.tabTrades')"
              name="trades"
            >
              <div class="portfolio-tab-panel">
                <div class="portfolio-section-heading">
                  <h3>{{ t('portfolio.tabTrades') }}</h3>
                  <span>{{ t('portfolio.tradesDesc') }}</span>
                </div>
                <div
                  v-if="isTabLoading('trades')"
                  class="portfolio-querying"
                >
                  <el-icon class="is-loading" aria-hidden="true">
                    <Loading />
                  </el-icon>
                  <span>{{ t('portfolio.querying') }}</span>
                </div>
                <template v-else>
                  <div
                    v-if="trades.length === 0"
                    class="portfolio-empty"
                  >
                    <el-icon aria-hidden="true">
                      <DataLine />
                    </el-icon>
                    <span>{{ t('portfolio.emptyTrades') }}</span>
                  </div>
                  <el-table
                    v-else
                    :data="trades"
                    stripe
                    size="small"
                    class="portfolio-table"
                    max-height="500"
                  >
                  <el-table-column
                    prop="strategy_name"
                    :label="t('portfolio.colStrategy')"
                    min-width="180"
                  />
                  <el-table-column
                    prop="data_name"
                    :label="t('portfolio.colSymbolShort')"
                    width="100"
                  />
                  <el-table-column
                    :label="t('portfolio.colDirection')"
                    width="80"
                    align="center"
                  >
                    <template #default="{ row }">
                      <span :class="tradeDirectionClass(row.direction)">
                        {{ tradeDirectionLabel(row.direction) }}
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column
                    prop="dtopen"
                    :label="t('portfolio.colOpenDate')"
                    width="160"
                  />
                  <el-table-column
                    prop="dtclose"
                    :label="t('portfolio.colCloseDate')"
                    width="160"
                  />
                  <el-table-column
                    :label="t('portfolio.colPrice')"
                    width="100"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ row.price.toFixed(2) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colSizeShort')"
                    width="80"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ row.size }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colCommission')"
                    width="100"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ row.commission.toFixed(2) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colNetPnl')"
                    width="120"
                    align="right"
                    sortable
                  >
                    <template #default="{ row }">
                      <span :class="row.pnlcomm >= 0 ? 'text-green-600' : 'text-red-600'">
                        {{ row.pnlcomm >= 0 ? '+' : '' }}{{ row.pnlcomm.toFixed(2) }}
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('portfolio.colHoldingDays')"
                    prop="barlen"
                    width="100"
                    align="center"
                  />
                  </el-table>
                </template>
              </div>
            </el-tab-pane>

            <el-tab-pane
              :label="t('portfolio.tabEquity')"
              name="equity"
            >
              <div
                v-if="activeTab === 'equity'"
                class="portfolio-tab-panel"
              >
                <div class="portfolio-section-heading portfolio-section-heading--chart">
                  <div>
                    <h3>{{ t('portfolio.tabEquity') }}</h3>
                    <span>{{ t('portfolio.equityDesc') }}</span>
                  </div>
                  <el-select
                    v-if="equityData?.strategies.length"
                    v-model="selectedEquitySeries"
                    class="portfolio-equity-selector"
                    size="small"
                    :placeholder="t('portfolio.equitySelectorPlaceholder')"
                  >
                    <el-option
                      value="portfolio"
                      :label="t('portfolio.seriesTotalEquity')"
                    />
                    <el-option
                      v-for="strategy in equityData.strategies"
                      :key="strategy.instance_id"
                      :value="strategy.instance_id"
                      :label="strategy.strategy_name"
                    />
                  </el-select>
                </div>
                <div
                  v-if="isTabLoading('equity')"
                  class="portfolio-querying"
                >
                  <el-icon class="is-loading" aria-hidden="true">
                    <Loading />
                  </el-icon>
                  <span>{{ t('portfolio.querying') }}</span>
                </div>
                <div
                  v-else-if="selectedEquityCurve.values.length === 0"
                  class="portfolio-empty"
                >
                  <el-icon aria-hidden="true">
                    <DataLine />
                  </el-icon>
                  <span>{{ t('portfolio.emptyEquity') }}</span>
                </div>
                <div
                  v-else
                  class="portfolio-chart-stack"
                >
                  <div
                    ref="equityChartRef"
                    class="portfolio-chart portfolio-chart--equity"
                  />
                  <div
                    ref="drawdownChartRef"
                    class="portfolio-chart portfolio-chart--drawdown"
                  />
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane
              :label="t('portfolio.tabAllocation')"
              name="allocation"
            >
              <div
                v-if="activeTab === 'allocation'"
                class="portfolio-tab-panel"
              >
                <div class="portfolio-section-heading">
                  <h3>{{ t('portfolio.tabAllocation') }}</h3>
                  <span>{{ t('portfolio.allocationDesc') }}</span>
                </div>
                <div
                  v-if="isTabLoading('allocation')"
                  class="portfolio-querying"
                >
                  <el-icon class="is-loading" aria-hidden="true">
                    <Loading />
                  </el-icon>
                  <span>{{ t('portfolio.querying') }}</span>
                </div>
                <div
                  v-else-if="allocationItems.length === 0"
                  class="portfolio-empty"
                >
                  <el-icon aria-hidden="true">
                    <DataLine />
                  </el-icon>
                  <span>{{ t('portfolio.emptyAllocation') }}</span>
                </div>
                <div
                  v-else
                  ref="allocationChartRef"
                  class="portfolio-chart portfolio-chart--allocation"
                />
              </div>
            </el-tab-pane>
          </el-tabs>
        </section>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick, onBeforeUnmount, computed, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Connection,
  DataLine,
  Histogram,
  Loading,
  Operation,
  Refresh,
  TrendCharts,
  Wallet,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type * as echarts from 'echarts'
import { getErrorMessage } from '@/api'
import { portfolioApi } from '@/api/portfolio'
import { workspaceApi } from '@/api/workspace'
import type {
  PortfolioOverview,
  PositionItem,
  PositionSummary,
  TradeItem,
  PortfolioEquity,
  AllocationItem,
} from '@/api/portfolio'
import type {
  TradingPositionManagerItem,
  Workspace,
} from '@/types/workspace'
import { PORTFOLIO_DRAWDOWN_AREA_COLOR, PORTFOLIO_DRAWDOWN_COLOR, PORTFOLIO_EQUITY_COLOR } from '@/constants/chartColors'

const { t } = useI18n()

const loading = ref(true)
const activeTab = ref('workspaces')

const overview = ref<PortfolioOverview>({
  total_assets: 0, total_cash: 0, total_position_value: 0, net_position_value: 0,
  total_initial_capital: 0, total_pnl: 0, total_pnl_pct: 0,
  strategy_count: 0, running_count: 0, strategies: [],
})
const positions = ref<PositionItem[]>([])
const trades = ref<TradeItem[]>([])
const equityData = ref<PortfolioEquity | null>(null)
const allocationItems = ref<AllocationItem[]>([])
const runningWorkspaces = ref<Workspace[]>([])
const positionSummary = ref<PositionSummary>(emptyPositionSummary())
const selectedEquitySeries = ref('portfolio')
const loadingTabs = ref<Set<string>>(new Set())
const POSITION_EPSILON = 1e-12

interface EquityCurveSelection {
  name: string
  dates: string[]
  values: number[]
  drawdown: number[]
}

const selectedEquityCurve = computed<EquityCurveSelection>(() => {
  const data = equityData.value
  if (!data) return { name: '', dates: [], values: [], drawdown: [] }

  let name = t('portfolio.seriesTotalEquity')
  let sourceValues = data.total_equity
  if (selectedEquitySeries.value !== 'portfolio') {
    const strategy = data.strategies.find(item => item.instance_id === selectedEquitySeries.value)
    if (!strategy) return { name: '', dates: [], values: [], drawdown: [] }
    name = strategy.strategy_name
    sourceValues = strategy.values
  }

  const pointCount = Math.min(data.dates.length, sourceValues.length)
  const normalizedValues = sourceValues
    .slice(0, pointCount)
    .map(value => Number(value))
  const firstValueIndex = normalizedValues.findIndex(value => (
    Number.isFinite(value) && Math.abs(value) > POSITION_EPSILON
  ))
  if (firstValueIndex === -1) return { name, dates: [], values: [], drawdown: [] }

  const values = normalizedValues.slice(firstValueIndex)
  const dates = data.dates.slice(firstValueIndex, pointCount)
  let peak = values[0]
  const drawdown = values.map(value => {
    peak = Math.max(peak, value)
    return peak > 0 && value < peak ? -((peak - value) / peak) : 0
  })
  return { name, dates, values, drawdown }
})

// Chart refs
const equityChartRef = ref<HTMLElement | null>(null)
const drawdownChartRef = ref<HTMLElement | null>(null)
const allocationChartRef = ref<HTMLElement | null>(null)
let equityChart: echarts.ECharts | null = null
let drawdownChart: echarts.ECharts | null = null
let allocationChart: echarts.ECharts | null = null
let echartsLoader: Promise<typeof import('echarts')> | null = null

function loadEcharts() {
  echartsLoader ??= import('echarts')
  return echartsLoader
}

function formatMoney(v: number) {
  if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(2) + t('portfolio.unitYi')
  if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(2) + t('portfolio.unitWan')
  return v.toFixed(2)
}

function formatSignedMoney(v: number) {
  return `${v >= 0 ? '+' : ''}${formatMoney(v)}`
}

function formatSignedPercent(v: number) {
  const n = Number(v || 0)
  return `(${n >= 0 ? '+' : ''}${n.toFixed(2)}%)`
}

function formatNumber(v: number | null | undefined, digits = 2) {
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(digits) : '--'
}

function formatOptionalMoney(v: number | null | undefined) {
  const n = Number(v)
  return Number.isFinite(n) ? formatMoney(n) : '--'
}

function formatPositionSize(v: number | null | undefined) {
  const n = Number(v || 0)
  if (!Number.isFinite(n) || n === 0) return '--'
  if (Math.abs(n) < 0.0001) return n.toFixed(8).replace(/\.?0+$/, '')
  return formatNumber(n, 4)
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '--'
  return String(value).replace('T', ' ').replace('Z', '').slice(0, 19)
}

function signedValueClass(v: number | null | undefined) {
  const n = Number(v || 0)
  if (n > 0) return 'text-green-600'
  if (n < 0) return 'text-red-600'
  return 'text-gray-700'
}

function exposureValueClass(v: number | null | undefined) {
  const n = Number(v || 0)
  if (n > 0) return 'text-red-600'
  if (n < 0) return 'text-green-600'
  return 'text-gray-700'
}

function directionLabel(direction: string) {
  if (direction === 'long') return t('portfolio.directionLong')
  if (direction === 'short') return t('portfolio.directionShort')
  if (direction === 'hedged') return t('portfolio.directionHedged')
  return t('portfolio.directionFlat')
}

function positionDirectionTag(row: PositionItem) {
  if (row.direction === 'hedged') return 'warning'
  if (Number(row.size || 0) > 0) return 'danger'
  if (Number(row.size || 0) < 0) return 'success'
  return 'info'
}

function isLongTradeDirection(direction: string | null | undefined) {
  const normalized = String(direction || '').toLowerCase()
  return normalized === 'long' || normalized === 'buy'
}

function isShortTradeDirection(direction: string | null | undefined) {
  const normalized = String(direction || '').toLowerCase()
  return normalized === 'short' || normalized === 'sell'
}

function tradeDirectionLabel(direction: string | null | undefined) {
  if (isLongTradeDirection(direction)) return t('portfolio.directionLong')
  if (isShortTradeDirection(direction)) return t('portfolio.directionShort')
  return String(direction || '--')
}

function tradeDirectionClass(direction: string | null | undefined) {
  if (isLongTradeDirection(direction)) return 'text-red-600'
  if (isShortTradeDirection(direction)) return 'text-green-600'
  return 'text-gray-700'
}

function emptyPositionSummary(): PositionSummary {
  return {
    total_long_value: 0,
    total_short_value: 0,
    gross_market_value: 0,
    net_market_value: 0,
    total_pnl: 0,
    long_count: 0,
    short_count: 0,
    flat_count: 0,
  }
}

const loadedTabs = ref<Set<string>>(new Set(['workspaces']))
const runningWorkspaceIds = computed(() => runningWorkspaces.value.map(workspace => workspace.id))
const selectedPositionValue = computed(() => (
  positionSummary.value.gross_market_value
))
type MetricTone = 'primary' | 'success' | 'warning' | 'danger' | 'neutral'

interface PortfolioMetricCard {
  label: string
  value: string
  helper: string
  icon: Component
  tone: MetricTone
  valueClass?: string
}

const portfolioHealthLabel = computed(() => {
  if (overview.value.total_pnl > 0) return t('portfolio.riskPosturePositive')
  if (overview.value.total_pnl < 0) return t('portfolio.riskPostureNegative')
  return t('portfolio.riskPostureNeutral')
})

const heroBadges = computed(() => [
  { label: t('portfolio.heroCash'), value: formatMoney(overview.value.total_cash) },
  { label: t('portfolio.heroStrategies'), value: String(overview.value.strategy_count) },
  { label: t('portfolio.heroWorkspaces'), value: String(runningWorkspaces.value.length) },
])

const summaryCards = computed<PortfolioMetricCard[]>(() => [
  {
    label: t('portfolio.cardTotalAssets'),
    value: formatMoney(overview.value.total_assets),
    helper: t('portfolio.cardTotalAssetsHelper'),
    icon: Wallet,
    tone: 'primary',
  },
  {
    label: t('portfolio.cardTotalPnl'),
    value: `${formatSignedMoney(overview.value.total_pnl)} ${formatSignedPercent(overview.value.total_pnl_pct)}`,
    helper: t('portfolio.cardTotalPnlHelper'),
    icon: TrendCharts,
    tone: overview.value.total_pnl >= 0 ? 'success' : 'danger',
    valueClass: signedValueClass(overview.value.total_pnl),
  },
  {
    label: t('portfolio.cardPositionValue'),
    value: formatMoney(selectedPositionValue.value || overview.value.total_position_value),
    helper: t('portfolio.cardPositionValueHelper'),
    icon: Histogram,
    tone: 'warning',
  },
  {
    label: t('portfolio.cardWorkspaceRunning'),
    value: String(runningWorkspaces.value.length),
    helper: t('portfolio.cardWorkspaceRunningHelper'),
    icon: Connection,
    tone: 'neutral',
  },
])

const positionMetricCards = computed(() => [
  {
    label: t('portfolio.cardLongValue'),
    value: formatMoney(positionSummary.value.total_long_value),
    valueClass: 'text-red-600',
  },
  {
    label: t('portfolio.cardShortValue'),
    value: formatMoney(positionSummary.value.total_short_value),
    valueClass: 'text-green-600',
  },
  {
    label: t('portfolio.cardNetExposure'),
    value: formatSignedMoney(positionSummary.value.net_market_value),
    valueClass: exposureValueClass(positionSummary.value.net_market_value),
  },
  {
    label: t('portfolio.cardPositionPnl'),
    value: formatSignedMoney(positionSummary.value.total_pnl),
    valueClass: signedValueClass(positionSummary.value.total_pnl),
  },
])

function workspaceStatusLabel(status: string) {
  const map: Record<string, string> = {
    running: t('portfolio.statusRunning'),
    error: t('portfolio.statusError'),
    idle: t('portfolio.statusStopped'),
    completed: t('portfolio.statusStopped'),
  }
  return map[status] || status
}

function valuationStatusTag(row: PositionItem) {
  const status = String(row.valuation_status || '').toLowerCase()
  if (row.position_source === 'gateway' && status === 'confirmed') return 'success'
  if (status === 'stale_fallback') return 'danger'
  if (status === 'estimated' || (row.valuation_warnings?.length ?? 0) > 0) return 'warning'
  return 'info'
}

function valuationStatusLabel(row: PositionItem) {
  const status = String(row.valuation_status || '').toLowerCase()
  if (row.position_source === 'gateway' && status === 'confirmed') return t('portfolio.valuationGatewayConfirmed')
  if (status === 'stale_fallback') return t('portfolio.valuationStale')
  if (status === 'estimated' || (row.valuation_warnings?.length ?? 0) > 0) return t('portfolio.valuationEstimated')
  return t('portfolio.valuationUnknown')
}

function positionSourceLabel(value: string | null | undefined) {
  const source = String(value || '').toLowerCase()
  if (source === 'gateway') return t('portfolio.sourceGateway')
  if (source === 'log') return t('portfolio.sourceLog')
  if (source === 'snapshot') return t('portfolio.sourceSnapshot')
  if (source === 'mixed') return t('portfolio.sourceMixed')
  return t('portfolio.sourceUnknown')
}

function valuationTooltip(row: PositionItem) {
  const warnings = row.valuation_warnings?.filter(Boolean) ?? []
  if (warnings.length > 0) return warnings.join('；')
  const assetSource = row.asset_spec_source || '--'
  return `${t('portfolio.positionSource')}: ${positionSourceLabel(row.position_source)}；${t('portfolio.assetSpecSource')}: ${assetSource}`
}

async function loadData() {
  loading.value = true
  loadedTabs.value = new Set(['workspaces'])
  loadingTabs.value = new Set()
  try {
    const [dashboard, workspaceList] = await Promise.all([
      portfolioApi.getOverview(true),
      workspaceApi.list(0, 100, 'trading'),
    ])
    overview.value = dashboard
    runningWorkspaces.value = workspaceList.items.filter(workspace => workspace.status === 'running')
    if (activeTab.value !== 'workspaces') {
      await loadTabData(activeTab.value)
    }
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('portfolio.msgLoadFailed')))
  } finally {
    loading.value = false
  }
}

function isTabLoading(tab: string) {
  return loadingTabs.value.has(tab)
}

function setTabLoading(tab: string, isLoading: boolean) {
  const next = new Set(loadingTabs.value)
  if (isLoading) next.add(tab)
  else next.delete(tab)
  loadingTabs.value = next
}

async function loadTabData(tab: string) {
  if (loadedTabs.value.has(tab) || isTabLoading(tab)) return
  setTabLoading(tab, true)
  try {
    if (tab === 'positions') {
      await loadWorkspacePositions()
    } else if (tab === 'trades') {
      await loadWorkspaceTrades()
    } else if (tab === 'equity') {
      equityData.value = await portfolioApi.getEquity()
      selectedEquitySeries.value = 'portfolio'
    } else if (tab === 'allocation') {
      allocationItems.value = (await portfolioApi.getAllocation(runningWorkspaceIds.value)).items
    }
    loadedTabs.value = new Set([...loadedTabs.value, tab])
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('portfolio.msgLoadTabFailed')))
  } finally {
    setTabLoading(tab, false)
  }
}

async function loadWorkspacePositions() {
  const workspaces = runningWorkspaces.value
  if (workspaces.length === 0) {
    positions.value = []
    positionSummary.value = emptyPositionSummary()
    return
  }

  const positionResults = await Promise.all(
    workspaces.map(workspace => workspaceApi.getTradingPositions(workspace.id)),
  )

  const nextPositions = positionResults.flatMap((result, index) => (
    result.positions.map(item => mapWorkspacePosition(workspaces[index], item))
  )).filter(item => hasOpenPosition(item))
  positions.value = nextPositions
  positionSummary.value = buildWorkspacePositionSummary(nextPositions)
}

async function loadWorkspaceTrades() {
  const workspaces = runningWorkspaces.value
  if (workspaces.length === 0) {
    trades.value = []
    return
  }

  const result = await portfolioApi.getTrades(1000, runningWorkspaceIds.value)
  trades.value = result.trades
    .filter(item => isTradeInSelectedWorkspaces(item, workspaces))
    .sort((a, b) => tradeSortKey(b).localeCompare(tradeSortKey(a)))
}

function buildWorkspacePositionSummary(rows: PositionItem[]): PositionSummary {
  const exposure = rows.reduce((sum, item) => {
    const longMarketValue = Number(item.long_market_value)
    const shortMarketValue = Number(item.short_market_value)
    if (Number.isFinite(longMarketValue) || Number.isFinite(shortMarketValue)) {
      sum.long += Number.isFinite(longMarketValue) ? Math.max(longMarketValue, 0) : 0
      sum.short += Number.isFinite(shortMarketValue) ? Math.max(shortMarketValue, 0) : 0
      sum.pnl += Number(item.position_pnl || 0)
      return sum
    }
    const longPosition = Math.max(Number(item.long_position || 0), 0)
    const shortPosition = Math.max(Number(item.short_position || 0), 0)
    const marketValue = Math.abs(Number(item.market_value || 0))
    const totalPosition = longPosition + shortPosition
    if (totalPosition > 0) {
      sum.long += marketValue * (longPosition / totalPosition)
      sum.short += marketValue * (shortPosition / totalPosition)
    } else if (Number(item.size || 0) > 0) {
      sum.long += marketValue
    } else if (Number(item.size || 0) < 0) {
      sum.short += marketValue
    }
    sum.pnl += Number(item.position_pnl || 0)
    return sum
  }, { long: 0, short: 0, pnl: 0 })
  const totalLong = exposure.long
  const totalShort = exposure.short
  const totalPnl = exposure.pnl
  return {
    total_long_value: roundMoney(totalLong),
    total_short_value: roundMoney(totalShort),
    gross_market_value: roundMoney(totalLong + totalShort),
    net_market_value: roundMoney(totalLong - totalShort),
    total_pnl: roundMoney(totalPnl),
    long_count: rows.filter(item => Number(item.long_position || 0) > POSITION_EPSILON || Number(item.size || 0) > POSITION_EPSILON).length,
    short_count: rows.filter(item => Number(item.short_position || 0) > POSITION_EPSILON || Number(item.size || 0) < -POSITION_EPSILON).length,
    flat_count: rows.filter(item => !hasOpenPosition(item)).length,
  }
}

function roundMoney(v: number) {
  return Math.round((Number(v) || 0) * 100) / 100
}

function mapWorkspacePosition(
  workspace: Workspace,
  item: TradingPositionManagerItem,
): PositionItem {
  const longPosition = Number(item.long_position || 0)
  const shortPosition = Number(item.short_position || 0)
  const netSize = longPosition - shortPosition
  const latestPrice = Number(item.latest_price ?? item.avg_price ?? 0)
  const avgPrice = Number(item.avg_price ?? latestPrice)
  const direction = longPosition > 0 && shortPosition > 0
    ? 'hedged'
    : netSize > 0 ? 'long' : netSize < 0 ? 'short' : 'flat'
  return {
    strategy_id: item.unit_id,
    strategy_name: `${workspace.name} / ${item.unit_name}`,
    instance_id: item.unit_id,
    data_name: item.symbol,
    size: netSize,
    price: avgPrice,
    latest_price: latestPrice,
    market_value: Number(item.market_value ?? 0),
    margin_value: item.margin_value == null ? undefined : Number(item.margin_value),
    long_market_value: item.long_market_value == null ? undefined : Number(item.long_market_value),
    short_market_value: item.short_market_value == null ? undefined : Number(item.short_market_value),
    position_pnl: Number(item.position_pnl || 0),
    gross_pnl: item.gross_pnl == null ? undefined : Number(item.gross_pnl),
    commission: item.commission == null ? undefined : Number(item.commission),
    commission_source: item.commission_source,
    multiplier: item.multiplier == null ? undefined : Number(item.multiplier),
    margin_rate: item.margin_rate == null ? undefined : Number(item.margin_rate),
    leverage: item.leverage == null ? undefined : Number(item.leverage),
    direction,
    long_position: longPosition,
    short_position: shortPosition,
    trading_mode: item.trading_mode,
    updated_at: item.updated_at ?? workspace.updated_at,
    data_time: item.data_time,
    position_source: item.position_source,
    asset_spec_source: item.asset_spec_source,
    valuation_status: item.valuation_status,
    valuation_warnings: item.valuation_warnings ?? [],
  }
}

function hasOpenPosition(item: PositionItem) {
  return (
    Math.abs(Number(item.size || 0)) > POSITION_EPSILON
    || Number(item.long_position || 0) > POSITION_EPSILON
    || Number(item.short_position || 0) > POSITION_EPSILON
  )
}

function isTradeInSelectedWorkspaces(item: TradeItem, workspaces: Workspace[]) {
  const strategyName = String(item.strategy_name || '')
  return workspaces.some(workspace => (
    strategyName === workspace.name || strategyName.startsWith(`${workspace.name} /`)
  ))
}

function tradeSortKey(item: TradeItem) {
  return String(item.dtclose || item.datetime || item.dtopen || '')
}

function readThemeColor(name: string, fallback = 'currentColor') {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

function chartThemeColors() {
  return {
    text: readThemeColor('--text-color-secondary'),
    primaryText: readThemeColor('--text-color-primary'),
    border: readThemeColor('--border-color-light'),
    surface: readThemeColor('--bg-color'),
  }
}

// ---- Charts ----

async function renderEquityChart() {
  const curve = selectedEquityCurve.value
  if (!equityChartRef.value || curve.values.length === 0) return
  const echarts = await loadEcharts()
  if (equityChart && equityChart.getDom() !== equityChartRef.value) {
    equityChart.dispose()
    equityChart = null
  }
  if (!equityChart) equityChart = echarts.init(equityChartRef.value)

  const colors = chartThemeColors()

  equityChart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: colors.surface,
      borderColor: colors.border,
      textStyle: { color: colors.primaryText },
    },
    grid: { left: 80, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: curve.dates,
      boundaryGap: false,
      axisLabel: { color: colors.text },
      axisLine: { lineStyle: { color: colors.border } },
      axisTick: { lineStyle: { color: colors.border } },
    },
    yAxis: {
      type: 'value',
      // The curve is trimmed to its first valid balance. Keep the visual scale
      // aligned with those values instead of forcing the axis to include zero.
      scale: true,
      axisLabel: { color: colors.text, formatter: (v: number) => formatMoney(v) },
      axisLine: { lineStyle: { color: colors.border } },
      splitLine: { lineStyle: { color: colors.border } },
    },
    series: [{
      name: curve.name,
      type: 'line',
      data: curve.values,
      symbol: 'none',
      lineStyle: { width: 2, color: PORTFOLIO_EQUITY_COLOR },
      itemStyle: { color: PORTFOLIO_EQUITY_COLOR },
    }],
  }, true)
  equityChart.resize()
}

async function renderDrawdownChart() {
  const curve = selectedEquityCurve.value
  if (!drawdownChartRef.value || curve.values.length === 0) return
  const echarts = await loadEcharts()
  if (drawdownChart && drawdownChart.getDom() !== drawdownChartRef.value) {
    drawdownChart.dispose()
    drawdownChart = null
  }
  if (!drawdownChart) drawdownChart = echarts.init(drawdownChartRef.value)

  const colors = chartThemeColors()
  drawdownChart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: colors.surface,
      borderColor: colors.border,
      textStyle: { color: colors.primaryText },
      formatter: (params: { axisValue?: string; value?: number } | { axisValue?: string; value?: number }[]) => {
        const p = Array.isArray(params) ? params[0] : params
        return `${p?.axisValue ?? ''}<br/>${t('portfolio.drawdownTooltip', { value: ((p?.value ?? 0) * 100).toFixed(2) })}`
      },
    },
    grid: { left: 80, right: 20, top: 10, bottom: 30 },
    xAxis: {
      type: 'category',
      data: curve.dates,
      boundaryGap: false,
      show: false,
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: colors.text, formatter: (v: number) => (v * 100).toFixed(1) + '%' },
      axisLine: { lineStyle: { color: colors.border } },
      splitLine: { lineStyle: { color: colors.border } },
    },
    series: [{
      type: 'line',
      data: curve.drawdown,
      areaStyle: { color: PORTFOLIO_DRAWDOWN_AREA_COLOR },
      lineStyle: { color: PORTFOLIO_DRAWDOWN_COLOR, width: 1 },
      itemStyle: { color: PORTFOLIO_DRAWDOWN_COLOR },
      symbol: 'none',
    }],
  }, true)
  drawdownChart.resize()
}

async function renderAllocationChart() {
  if (!allocationChartRef.value || allocationItems.value.length === 0) return
  const echarts = await loadEcharts()
  if (allocationChart && allocationChart.getDom() !== allocationChartRef.value) {
    allocationChart.dispose()
    allocationChart = null
  }
  if (!allocationChart) allocationChart = echarts.init(allocationChartRef.value)
  const colors = chartThemeColors()

  const pieData = allocationItems.value.map(item => ({
    name: item.asset,
    value: item.value,
  }))

  allocationChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)',
      backgroundColor: colors.surface,
      borderColor: colors.border,
      textStyle: { color: colors.primaryText },
    },
    legend: {
      orient: 'vertical',
      right: 20,
      top: 'center',
      type: 'scroll',
      textStyle: { color: colors.text },
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['40%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: colors.surface, borderWidth: 2 },
      label: { show: true, color: colors.text, formatter: '{b}\n{d}%' },
      data: pieData,
    }],
  }, true)
  allocationChart.resize()
}

function handleResize() {
  equityChart?.resize()
  drawdownChart?.resize()
  allocationChart?.resize()
}

watch(activeTab, async (tab) => {
  await loadTabData(tab)
  if (tab === 'equity') {
    nextTick(() => {
      void renderEquityChart()
      void renderDrawdownChart()
    })
  } else if (tab === 'allocation') {
    nextTick(() => { void renderAllocationChart() })
  }
})

watch(selectedEquitySeries, () => {
  if (activeTab.value !== 'equity') return
  nextTick(() => {
    void renderEquityChart()
    void renderDrawdownChart()
  })
})

onMounted(() => {
  loadData()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  equityChart?.dispose()
  drawdownChart?.dispose()
  allocationChart?.dispose()
})
</script>

<style scoped>
.portfolio-page {
  display: grid;
  gap: 20px;
  color: var(--text-color-primary);
}

.portfolio-loading {
  display: grid;
  justify-items: center;
  gap: 12px;
  padding: 72px 16px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-secondary);
}

.portfolio-loading__icon {
  color: var(--primary-color);
  font-size: 34px;
}

.portfolio-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
  gap: 18px;
  align-items: stretch;
  padding: 22px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--bg-color) 90%, var(--primary-color) 10%), transparent),
    var(--bg-color);
}

.portfolio-hero__copy {
  display: grid;
  align-content: center;
  gap: 12px;
  min-width: 0;
}

.portfolio-kicker {
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  text-transform: uppercase;
}

.portfolio-hero h1,
.portfolio-panel-heading h2,
.portfolio-section-heading h3 {
  margin: 0;
  color: var(--text-color-primary);
  line-height: 1.2;
}

.portfolio-hero h1 {
  max-width: 780px;
  font-size: 40px;
  font-weight: 800;
}

.portfolio-hero p,
.portfolio-panel-heading p,
.portfolio-section-heading span {
  margin: 0;
  color: var(--text-color-secondary);
  line-height: 1.6;
}

.portfolio-hero p {
  max-width: 760px;
  font-size: 14px;
}

.portfolio-hero__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.portfolio-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 7px 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-color) 82%, var(--fill-color-light) 18%);
  color: var(--text-color-secondary);
  font-size: 12px;
}

.portfolio-badge strong {
  color: var(--text-color-primary);
  font-weight: 760;
}

.portfolio-hero__status {
  display: grid;
  align-content: space-between;
  gap: 14px;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-color) 84%, var(--fill-color-light) 16%);
}

.portfolio-status-chip {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  gap: 8px;
  min-height: 30px;
  padding: 6px 10px;
  border: 1px solid var(--success-border-color);
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg-color) 82%, var(--success-color) 18%);
  color: var(--success-color);
  font-size: 12px;
  font-weight: 700;
}

.portfolio-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: currentcolor;
}

.portfolio-hero__asset,
.portfolio-hero__pnl {
  display: grid;
  gap: 4px;
}

.portfolio-hero__asset span,
.portfolio-hero__pnl span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.portfolio-hero__asset strong,
.portfolio-hero__pnl {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 34px;
  font-weight: 820;
  line-height: 1.1;
}

.portfolio-refresh {
  justify-self: start;
  --el-button-bg-color: var(--fill-color-lighter);
  --el-button-border-color: var(--border-color);
  --el-button-text-color: var(--text-color-primary);
  --el-button-hover-bg-color: var(--fill-color-light);
  --el-button-hover-border-color: var(--info-border-color);
  --el-button-hover-text-color: var(--primary-color);
}

.portfolio-overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.portfolio-metric,
.portfolio-workbench,
.portfolio-tab-panel {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.portfolio-metric {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px 10px;
  align-items: start;
  min-width: 0;
  padding: 16px;
  overflow: hidden;
}

.portfolio-metric::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--primary-color);
  content: "";
}

.portfolio-metric--success::before {
  background: var(--success-color);
}

.portfolio-metric--danger::before {
  background: var(--danger-color);
}

.portfolio-metric--warning::before {
  background: var(--warning-color);
}

.portfolio-metric--neutral::before {
  background: var(--text-color-placeholder);
}

.portfolio-metric__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--primary-color);
  grid-row: span 3;
}

.portfolio-metric__label {
  min-width: 0;
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 700;
}

.portfolio-metric strong {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-color-primary);
  font-size: 22px;
  font-weight: 820;
  line-height: 1.15;
}

.portfolio-metric small {
  min-width: 0;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
}

.portfolio-layout {
  min-width: 0;
}

.portfolio-workbench {
  min-width: 0;
  padding: 16px;
}

.portfolio-panel-heading {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.portfolio-panel-heading--inline {
  margin-bottom: 14px;
}

.portfolio-panel-heading h2 {
  font-size: 18px;
  font-weight: 780;
}

.portfolio-panel-heading p {
  font-size: 13px;
}

.portfolio-workbench {
  overflow: hidden;
}

.portfolio-tabs {
  min-width: 0;
}

.portfolio-tabs :deep(.el-tabs__header) {
  margin: 0 0 12px;
}

.portfolio-tabs :deep(.el-tabs__nav-wrap::after) {
  background: var(--border-color-light);
}

.portfolio-tabs :deep(.el-tabs__item) {
  color: var(--text-color-secondary);
  font-weight: 700;
}

.portfolio-tabs :deep(.el-tabs__item.is-active),
.portfolio-tabs :deep(.el-tabs__active-bar) {
  color: var(--primary-color);
}

.portfolio-tab-panel {
  display: grid;
  gap: 14px;
  padding: 14px;
}

.portfolio-section-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  flex-wrap: wrap;
}

.portfolio-section-heading h3 {
  font-size: 16px;
  font-weight: 780;
}

.portfolio-section-heading span {
  max-width: 560px;
  font-size: 12px;
}

.portfolio-section-heading--chart > div {
  display: grid;
  gap: 4px;
}

.portfolio-equity-selector {
  width: min(100%, 260px);
}

.portfolio-exposure-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.portfolio-exposure-card {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.portfolio-exposure-card span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 680;
}

.portfolio-exposure-card strong {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 18px;
  font-weight: 800;
  line-height: 1.15;
}

.portfolio-empty {
  display: grid;
  justify-items: center;
  gap: 10px;
  min-height: 180px;
  padding: 28px 16px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  text-align: center;
}

.portfolio-empty--compact {
  min-height: 120px;
}

.portfolio-querying {
  display: grid;
  justify-items: center;
  gap: 10px;
  min-height: 180px;
  padding: 28px 16px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  text-align: center;
}

.portfolio-querying .el-icon {
  color: var(--primary-color);
  font-size: 28px;
}

.portfolio-empty .el-icon {
  color: var(--primary-color);
  font-size: 28px;
}

.portfolio-table {
  width: 100%;
  overflow: hidden;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  --el-table-bg-color: var(--bg-color);
  --el-table-tr-bg-color: var(--bg-color);
  --el-table-header-bg-color: var(--fill-color-lighter);
  --el-table-row-hover-bg-color: var(--fill-color-light);
  --el-table-border-color: var(--border-color-light);
  --el-table-text-color: var(--text-color-regular);
  --el-table-header-text-color: var(--text-color-secondary);
}

.portfolio-table :deep(.el-table__empty-block) {
  background: var(--bg-color);
}

.portfolio-chart-stack {
  display: grid;
  gap: 10px;
}

.portfolio-chart {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.portfolio-chart--equity {
  height: 400px;
}

.portfolio-chart--drawdown {
  height: 180px;
}

.portfolio-chart--allocation {
  height: 430px;
}

.text-green-600 {
  color: var(--success-color);
  font-weight: 760;
}

.text-red-600 {
  color: var(--danger-color);
  font-weight: 760;
}

.text-gray-700 {
  color: var(--text-color-primary);
  font-weight: 760;
}

@media (max-width: 1180px) {
  .portfolio-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .portfolio-hero {
    grid-template-columns: 1fr;
  }

  .portfolio-hero h1 {
    font-size: 34px;
  }
}

@media (max-width: 760px) {
  .portfolio-page {
    gap: 14px;
  }

  .portfolio-hero {
    grid-template-columns: 1fr;
    padding: 16px;
  }

  .portfolio-hero h1 {
    font-size: 28px;
  }

  .portfolio-hero__asset strong,
  .portfolio-hero__pnl {
    font-size: 28px;
  }

  .portfolio-overview,
  .portfolio-exposure-grid {
    grid-template-columns: 1fr;
  }

  .portfolio-workbench,
  .portfolio-tab-panel {
    padding: 12px;
  }

  .portfolio-section-heading {
    align-items: flex-start;
  }

  .portfolio-chart--equity {
    height: 320px;
  }

  .portfolio-chart--drawdown {
    height: 160px;
  }

  .portfolio-chart--allocation {
    height: 340px;
  }
}
</style>
