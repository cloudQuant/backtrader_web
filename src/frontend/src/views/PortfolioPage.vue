<template>
  <div class="space-y-6">
    <!-- Loading state -->
    <div
      v-if="loading"
      class="flex justify-center py-16"
    >
      <el-icon class="is-loading text-4xl text-blue-500">
        <Loading />
      </el-icon>
    </div>

    <template v-else>
      <!-- Overview cards -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
        <el-card shadow="hover">
          <div class="text-center">
            <div class="text-gray-500 text-sm mb-1">
              {{ t('portfolio.cardTotalAssets') }}
            </div>
            <div class="text-3xl font-bold">
              {{ formatMoney(overview.total_assets) }}
            </div>
          </div>
        </el-card>
        <el-card shadow="hover">
          <div class="text-center">
            <div class="text-gray-500 text-sm mb-1">
              {{ t('portfolio.cardTotalPnl') }}
            </div>
            <div
              class="text-3xl font-bold"
              :class="overview.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'"
            >
              {{ overview.total_pnl >= 0 ? '+' : '' }}{{ formatMoney(overview.total_pnl) }}
              <span class="text-sm ml-1">({{ overview.total_pnl_pct >= 0 ? '+' : '' }}{{ overview.total_pnl_pct.toFixed(2) }}%)</span>
            </div>
          </div>
        </el-card>
        <el-card shadow="hover">
          <div class="text-center">
            <div class="text-gray-500 text-sm mb-1">
              {{ t('portfolio.cardPositionValue') }}
            </div>
            <div class="text-2xl font-bold text-blue-600">
              {{ formatMoney(selectedPositionValue || overview.total_position_value) }}
            </div>
          </div>
        </el-card>
        <el-card shadow="hover">
          <div class="text-center">
            <div class="text-gray-500 text-sm mb-1">
              {{ t('portfolio.cardWorkspaceRunning') }}
            </div>
            <div class="text-3xl font-bold">
              <span class="text-gray-700">{{ selectedWorkspaceIds.length }}</span>
              <span class="text-gray-400 mx-1">/</span>
              <span class="text-green-600">{{ runningWorkspaces.length }}</span>
            </div>
          </div>
        </el-card>
      </div>

      <el-card>
        <div class="flex items-start justify-between gap-4 mb-4">
          <div>
            <h3 class="text-base font-semibold text-gray-900">
              {{ t('portfolio.workspaceSelectorTitle') }}
            </h3>
            <p class="text-sm text-gray-500 mt-1">
              {{ t('portfolio.workspaceSelectorDesc') }}
            </p>
          </div>
          <el-button
            size="small"
            @click="loadData"
          >
            {{ t('portfolio.btnRefresh') }}
          </el-button>
        </div>
        <div
          v-if="runningWorkspaces.length === 0"
          class="text-center text-gray-400 py-6"
        >
          {{ t('portfolio.emptyRunningWorkspaces') }}
        </div>
        <div
          v-else
          class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3"
        >
          <label
            v-for="workspace in runningWorkspaces"
            :key="workspace.id"
            class="flex items-start gap-3 rounded border border-gray-200 p-3 hover:border-blue-300"
          >
            <input
              type="checkbox"
              class="mt-1"
              :checked="selectedWorkspaceIds.includes(workspace.id)"
              @change="toggleWorkspace(workspace.id, ($event.target as HTMLInputElement).checked)"
            >
            <span>
              <span class="block font-medium text-gray-900">{{ workspace.name }}</span>
              <span class="block text-xs text-gray-500">
                {{ workspace.unit_count }} {{ t('portfolio.workspaceUnitSuffix') }} · {{ workspaceStatusLabel(workspace.status) }}
              </span>
            </span>
          </label>
        </div>
      </el-card>

      <!-- Main content -->
      <el-tabs v-model="activeTab">
        <!-- Workspaces tab -->
        <el-tab-pane
          :label="t('portfolio.tabWorkspaces')"
          name="workspaces"
        >
          <el-card>
            <el-table
              :data="runningWorkspaces"
              stripe
              size="small"
              class="w-full"
            >
              <el-table-column
                prop="name"
                :label="t('portfolio.colWorkspaceName')"
                min-width="140"
              />
              <el-table-column
                :label="t('portfolio.colStatus')"
                width="80"
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
                width="110"
                align="right"
              />
              <el-table-column
                :label="t('portfolio.colSelected')"
                width="90"
                align="center"
              >
                <template #default="{ row }">
                  <el-tag
                    :type="selectedWorkspaceIds.includes(row.id) ? 'success' : 'info'"
                    size="small"
                  >
                    {{ selectedWorkspaceIds.includes(row.id) ? t('portfolio.selected') : t('portfolio.notSelected') }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-tab-pane>

        <!-- Positions tab -->
        <el-tab-pane
          :label="t('portfolio.tabPositions')"
          name="positions"
        >
          <el-card>
            <div
              v-if="positions.length > 0"
              class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4"
            >
              <div class="rounded border border-gray-200 px-3 py-2">
                <div class="text-xs text-gray-500">
                  {{ t('portfolio.cardLongValue') }}
                </div>
                <div class="text-lg font-semibold text-red-600">
                  {{ formatMoney(positionSummary.total_long_value) }}
                </div>
              </div>
              <div class="rounded border border-gray-200 px-3 py-2">
                <div class="text-xs text-gray-500">
                  {{ t('portfolio.cardShortValue') }}
                </div>
                <div class="text-lg font-semibold text-green-600">
                  {{ formatMoney(positionSummary.total_short_value) }}
                </div>
              </div>
              <div class="rounded border border-gray-200 px-3 py-2">
                <div class="text-xs text-gray-500">
                  {{ t('portfolio.cardNetExposure') }}
                </div>
                <div
                  class="text-lg font-semibold"
                  :class="exposureValueClass(positionSummary.net_market_value)"
                >
                  {{ formatSignedMoney(positionSummary.net_market_value) }}
                </div>
              </div>
              <div class="rounded border border-gray-200 px-3 py-2">
                <div class="text-xs text-gray-500">
                  {{ t('portfolio.cardPositionPnl') }}
                </div>
                <div
                  class="text-lg font-semibold"
                  :class="signedValueClass(positionSummary.total_pnl)"
                >
                  {{ formatSignedMoney(positionSummary.total_pnl) }}
                </div>
              </div>
            </div>
            <div
              v-if="positions.length === 0"
              class="text-center text-gray-400 py-8"
            >
              {{ t('portfolio.emptyPositions') }}
            </div>
            <el-table
              v-else
              :data="positions"
              stripe
              size="small"
              class="w-full"
            >
              <el-table-column
                prop="strategy_name"
                :label="t('portfolio.colStrategy')"
                min-width="120"
              />
              <el-table-column
                prop="data_name"
                :label="t('portfolio.colSymbol')"
                width="120"
              />
              <el-table-column
                :label="t('portfolio.colDirection')"
                width="70"
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
                width="90"
                align="right"
              >
                <template #default="{ row }">
                  {{ formatPositionSize(row.long_position) }}
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colShortPosition')"
                width="90"
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
                width="100"
                align="right"
              >
                <template #default="{ row }">
                  {{ formatNumber(row.price, 4) }}
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colLatestPrice')"
                width="100"
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
                width="110"
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
                width="80"
                align="right"
              >
                <template #default="{ row }">
                  {{ formatNumber(row.leverage, 2) }}
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colCommission')"
                width="95"
                align="right"
              >
                <template #default="{ row }">
                  {{ formatNumber(row.commission, 2) }}
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colValuationStatus')"
                width="125"
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
                width="150"
              >
                <template #default="{ row }">
                  {{ formatDateTime(row.updated_at) }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-tab-pane>

        <!-- Trades tab -->
        <el-tab-pane
          :label="t('portfolio.tabTrades')"
          name="trades"
        >
          <el-card>
            <div
              v-if="trades.length === 0"
              class="text-center text-gray-400 py-8"
            >
              {{ t('portfolio.emptyTrades') }}
            </div>
            <el-table
              v-else
              :data="trades"
              stripe
              size="small"
              class="w-full"
              max-height="500"
            >
              <el-table-column
                prop="strategy_name"
                :label="t('portfolio.colStrategy')"
                min-width="100"
              />
              <el-table-column
                prop="data_name"
                :label="t('portfolio.colSymbolShort')"
                width="90"
              />
              <el-table-column
                :label="t('portfolio.colDirection')"
                width="60"
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
                width="150"
              />
              <el-table-column
                prop="dtclose"
                :label="t('portfolio.colCloseDate')"
                width="150"
              />
              <el-table-column
                :label="t('portfolio.colPrice')"
                width="90"
                align="right"
              >
                <template #default="{ row }">
                  {{ row.price.toFixed(2) }}
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colSizeShort')"
                width="70"
                align="right"
              >
                <template #default="{ row }">
                  {{ row.size }}
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colCommission')"
                width="80"
                align="right"
              >
                <template #default="{ row }">
                  {{ row.commission.toFixed(2) }}
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colNetPnl')"
                width="100"
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
                width="80"
                align="center"
              />
            </el-table>
          </el-card>
        </el-tab-pane>

        <!-- Equity curve tab -->
        <el-tab-pane
          :label="t('portfolio.tabEquity')"
          name="equity"
        >
          <el-card v-if="activeTab === 'equity'">
            <div
              ref="equityChartRef"
              style="width:100%;height:400px"
            />
            <div
              ref="drawdownChartRef"
              style="width:100%;height:180px;margin-top:8px"
            />
          </el-card>
        </el-tab-pane>

        <!-- Allocation tab -->
        <el-tab-pane
          :label="t('portfolio.tabAllocation')"
          name="allocation"
        >
          <el-card v-if="activeTab === 'allocation'">
            <div
              ref="allocationChartRef"
              style="width:100%;height:400px"
            />
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick, onBeforeUnmount, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
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
const selectedWorkspaceIds = ref<string[]>([])
const positionSummary = ref<PositionSummary>(emptyPositionSummary())
const POSITION_EPSILON = 1e-12

// Chart refs
const equityChartRef = ref<HTMLElement | null>(null)
const drawdownChartRef = ref<HTMLElement | null>(null)
const allocationChartRef = ref<HTMLElement | null>(null)
let equityChart: echarts.ECharts | null = null
let drawdownChart: echarts.ECharts | null = null
let allocationChart: echarts.ECharts | null = null

function formatMoney(v: number) {
  if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(2) + t('portfolio.unitYi')
  if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(2) + t('portfolio.unitWan')
  return v.toFixed(2)
}

function formatSignedMoney(v: number) {
  return `${v >= 0 ? '+' : ''}${formatMoney(v)}`
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
const selectedWorkspaces = computed(() => (
  runningWorkspaces.value.filter(workspace => selectedWorkspaceIds.value.includes(workspace.id))
))
const selectedPositionValue = computed(() => (
  positionSummary.value.gross_market_value
))

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
  try {
    const [dashboard, workspaceList] = await Promise.all([
      portfolioApi.getOverview(),
      workspaceApi.list(0, 100, 'trading'),
    ])
    overview.value = dashboard
    runningWorkspaces.value = workspaceList.items.filter(workspace => workspace.status === 'running')
    selectedWorkspaceIds.value = runningWorkspaces.value.map(workspace => workspace.id)
    await loadWorkspaceAggregates()
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('portfolio.msgLoadFailed')))
  } finally {
    loading.value = false
  }
}

async function loadTabData(tab: string) {
  if (loadedTabs.value.has(tab)) return
  try {
    if (tab === 'positions' || tab === 'trades') {
      await loadWorkspaceAggregates()
    } else if (tab === 'equity') {
      equityData.value = await portfolioApi.getEquity()
    } else if (tab === 'allocation') {
      allocationItems.value = (await portfolioApi.getAllocation()).items
    }
    loadedTabs.value.add(tab)
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('portfolio.msgLoadTabFailed')))
  }
}

async function loadWorkspaceAggregates() {
  const workspaces = selectedWorkspaces.value
  if (workspaces.length === 0) {
    positions.value = []
    trades.value = []
    positionSummary.value = emptyPositionSummary()
    return
  }

  const [positionResults, tradeResults] = await Promise.all([
    Promise.all(workspaces.map(workspace => workspaceApi.getTradingPositions(workspace.id))),
    Promise.all(workspaces.map(workspace => portfolioApi.getTrades(1000, [workspace.id]))),
  ])

  const nextPositions = positionResults.flatMap((result, index) => (
    result.positions.map(item => mapWorkspacePosition(workspaces[index], item))
  )).filter(item => hasOpenPosition(item))
  positions.value = nextPositions
  positionSummary.value = buildWorkspacePositionSummary(nextPositions)
  trades.value = tradeResults
    .flatMap((result, index) => (
      result.trades.filter(item => isTradeInSelectedWorkspaces(item, [workspaces[index]]))
    ))
    .sort((a, b) => tradeSortKey(b).localeCompare(tradeSortKey(a)))
}

function buildWorkspacePositionSummary(rows: PositionItem[]): PositionSummary {
  const exposure = rows.reduce((sum, item) => {
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

async function toggleWorkspace(workspaceId: string, checked: boolean) {
  if (checked) {
    selectedWorkspaceIds.value = Array.from(new Set([...selectedWorkspaceIds.value, workspaceId]))
  } else {
    selectedWorkspaceIds.value = selectedWorkspaceIds.value.filter(id => id !== workspaceId)
  }
  loadedTabs.value = new Set(['workspaces'])
  await loadWorkspaceAggregates()
}

// ---- Charts ----

function renderEquityChart() {
  if (!equityChartRef.value || !equityData.value) return
  if (!equityChart) equityChart = echarts.init(equityChartRef.value)

  const data = equityData.value
  const series: echarts.SeriesOption[] = []

  // 各策略堆叠面积
  for (const s of data.strategies) {
    series.push({
      name: s.strategy_name,
      type: 'line',
      stack: 'total',
      areaStyle: { opacity: 0.3 },
      emphasis: { focus: 'series' },
      data: s.values,
      symbol: 'none',
      lineStyle: { width: 1 },
    })
  }

  // 组合总资产
  series.push({
    name: t('portfolio.seriesTotalEquity'),
    type: 'line',
    data: data.total_equity,
    symbol: 'none',
    lineStyle: { width: 2, color: PORTFOLIO_EQUITY_COLOR },
    itemStyle: { color: PORTFOLIO_EQUITY_COLOR },
    z: 10,
  })

  equityChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0, type: 'scroll' },
    grid: { left: 80, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: data.dates, boundaryGap: false },
    yAxis: { type: 'value', axisLabel: { formatter: (v: number) => formatMoney(v) } },
    series,
  }, true)
}

function renderDrawdownChart() {
  if (!drawdownChartRef.value || !equityData.value) return
  if (!drawdownChart) drawdownChart = echarts.init(drawdownChartRef.value)

  const data = equityData.value
  drawdownChart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params: { axisValue?: string; value?: number } | { axisValue?: string; value?: number }[]) => {
        const p = Array.isArray(params) ? params[0] : params
        return `${p?.axisValue ?? ''}<br/>${t('portfolio.drawdownTooltip', { value: ((p?.value ?? 0) * 100).toFixed(2) })}`
      },
    },
    grid: { left: 80, right: 20, top: 10, bottom: 30 },
    xAxis: { type: 'category', data: data.dates, boundaryGap: false, show: false },
    yAxis: { type: 'value', axisLabel: { formatter: (v: number) => (v * 100).toFixed(1) + '%' } },
    series: [{
      type: 'line',
      data: data.total_drawdown,
      areaStyle: { color: PORTFOLIO_DRAWDOWN_AREA_COLOR },
      lineStyle: { color: PORTFOLIO_DRAWDOWN_COLOR, width: 1 },
      itemStyle: { color: PORTFOLIO_DRAWDOWN_COLOR },
      symbol: 'none',
    }],
  }, true)
}

function renderAllocationChart() {
  if (!allocationChartRef.value || allocationItems.value.length === 0) return
  if (!allocationChart) allocationChart = echarts.init(allocationChartRef.value)

  const pieData = allocationItems.value.map(item => ({
    name: item.strategy_name,
    value: item.value,
  }))

  allocationChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', right: 20, top: 'center', type: 'scroll' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['40%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: { show: true, formatter: '{b}\n{d}%' },
      data: pieData,
    }],
  }, true)
}

function handleResize() {
  equityChart?.resize()
  drawdownChart?.resize()
  allocationChart?.resize()
}

watch(activeTab, async (tab) => {
  await loadTabData(tab)
  if (tab === 'equity') {
    nextTick(() => { renderEquityChart(); renderDrawdownChart() })
  } else if (tab === 'allocation') {
    nextTick(() => renderAllocationChart())
  }
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
