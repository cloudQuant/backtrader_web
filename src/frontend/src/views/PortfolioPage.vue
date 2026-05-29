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
              {{ formatMoney(overview.total_position_value) }}
            </div>
          </div>
        </el-card>
        <el-card shadow="hover">
          <div class="text-center">
            <div class="text-gray-500 text-sm mb-1">
              {{ t('portfolio.cardStrategyRunning') }}
            </div>
            <div class="text-3xl font-bold">
              <span class="text-gray-700">{{ overview.strategy_count }}</span>
              <span class="text-gray-400 mx-1">/</span>
              <span class="text-green-600">{{ overview.running_count }}</span>
            </div>
          </div>
        </el-card>
      </div>

      <!-- Main content -->
      <el-tabs v-model="activeTab">
        <!-- Strategies tab -->
        <el-tab-pane
          :label="t('portfolio.tabStrategies')"
          name="strategies"
        >
          <el-card>
            <el-table
              :data="overview.strategies"
              stripe
              size="small"
              class="w-full"
            >
              <el-table-column
                prop="strategy_name"
                :label="t('portfolio.colStrategyName')"
                min-width="140"
              >
                <template #default="{ row }">
                  <router-link
                    :to="`/${tradingType}/${row.id}`"
                    class="text-blue-600 hover:underline"
                  >
                    {{ row.strategy_name }}
                  </router-link>
                </template>
              </el-table-column>
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
                    {{ row.status === 'running' ? t('portfolio.statusRunning') : row.status === 'error' ? t('portfolio.statusError') : t('portfolio.statusStopped') }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colCurrentAssets')"
                width="130"
                align="right"
              >
                <template #default="{ row }">
                  {{ formatMoney(row.total_assets) }}
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colInitialCapital')"
                width="130"
                align="right"
              >
                <template #default="{ row }">
                  {{ formatMoney(row.initial_capital) }}
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colPnl')"
                width="130"
                align="right"
              >
                <template #default="{ row }">
                  <span :class="row.pnl >= 0 ? 'text-green-600' : 'text-red-600'">
                    {{ row.pnl >= 0 ? '+' : '' }}{{ formatMoney(row.pnl) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colPnlPct')"
                width="90"
                align="right"
              >
                <template #default="{ row }">
                  <span :class="row.pnl_pct >= 0 ? 'text-green-600' : 'text-red-600'">
                    {{ row.pnl_pct >= 0 ? '+' : '' }}{{ row.pnl_pct.toFixed(2) }}%
                  </span>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colTradeCount')"
                prop="total_trades"
                width="80"
                align="center"
              />
              <el-table-column
                :label="t('portfolio.colWinRate')"
                width="70"
                align="center"
              >
                <template #default="{ row }">
                  {{ row.win_rate.toFixed(1) }}%
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
                    :type="row.size > 0 ? 'danger' : row.size < 0 ? 'success' : 'info'"
                    size="small"
                  >
                    {{ row.direction }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colSize')"
                width="100"
                align="right"
              >
                <template #default="{ row }">
                  {{ row.size }}
                </template>
              </el-table-column>
              <el-table-column
                :label="t('portfolio.colCostPrice')"
                width="100"
                align="right"
              >
                <template #default="{ row }">
                  {{ row.price.toFixed(4) }}
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
                  <span :class="row.direction === 'long' ? 'text-red-600' : 'text-green-600'">
                    {{ row.direction === 'long' ? t('portfolio.directionLong') : t('portfolio.directionShort') }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column
                prop="dtopen"
                :label="t('portfolio.colOpenDate')"
                width="100"
              />
              <el-table-column
                prop="dtclose"
                :label="t('portfolio.colCloseDate')"
                width="100"
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
import type {
  PortfolioOverview,
  PositionItem,
  TradeItem,
  PortfolioEquity,
  AllocationItem,
} from '@/api/portfolio'
import { usePortfolioUiStore } from '@/stores/portfolioUi'
import { PORTFOLIO_DRAWDOWN_AREA_COLOR, PORTFOLIO_DRAWDOWN_COLOR, PORTFOLIO_EQUITY_COLOR } from '@/constants/chartColors'

const { t } = useI18n()
const portfolioUiStore = usePortfolioUiStore()

const loading = ref(true)
const tradingType = computed(() => portfolioUiStore.tradingType)
const activeTab = ref('strategies')

const overview = ref<PortfolioOverview>({
  total_assets: 0, total_cash: 0, total_position_value: 0,
  total_initial_capital: 0, total_pnl: 0, total_pnl_pct: 0,
  strategy_count: 0, running_count: 0, strategies: [],
})
const positions = ref<PositionItem[]>([])
const trades = ref<TradeItem[]>([])
const equityData = ref<PortfolioEquity | null>(null)
const allocationItems = ref<AllocationItem[]>([])

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

const loadedTabs = ref<Set<string>>(new Set(['strategies']))

async function loadData() {
  loading.value = true
  loadedTabs.value = new Set(['strategies'])
  try {
    if (tradingType.value === 'live') {
      overview.value = await portfolioApi.getOverview()
    } else {
      overview.value = await portfolioApi.getSimulationOverview()
    }
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('portfolio.msgLoadFailed')))
  } finally {
    loading.value = false
  }
}

async function loadTabData(tab: string) {
  if (loadedTabs.value.has(tab)) return
  try {
    if (tradingType.value === 'live') {
      if (tab === 'positions') {
        const pos = await portfolioApi.getPositions()
        positions.value = pos.positions
      } else if (tab === 'trades') {
        const trd = await portfolioApi.getTrades()
        trades.value = trd.trades
      } else if (tab === 'equity') {
        equityData.value = await portfolioApi.getEquity()
      } else if (tab === 'allocation') {
        allocationItems.value = (await portfolioApi.getAllocation()).items
      }
    } else {
      if (tab === 'positions') {
        const pos = await portfolioApi.getSimulationPositions()
        positions.value = pos.positions
      } else if (tab === 'trades') {
        const trd = await portfolioApi.getSimulationTrades()
        trades.value = trd.trades
      } else if (tab === 'equity') {
        equityData.value = await portfolioApi.getSimulationEquity()
      } else if (tab === 'allocation') {
        allocationItems.value = (await portfolioApi.getSimulationAllocation()).items
      }
    }
    loadedTabs.value.add(tab)
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('portfolio.msgLoadTabFailed')))
  }
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

// 当头部的交易类型切换时，自动重新加载数据
watch(tradingType, async () => {
  activeTab.value = 'strategies'
  await loadData()
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
