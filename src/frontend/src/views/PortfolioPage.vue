<template>
  <div class="space-y-6">
    <!-- 加载状态 -->
    <div v-if="loading" class="flex justify-center py-16">
      <el-icon class="is-loading text-4xl text-blue-500"><Loading /></el-icon>
    </div>

    <template v-else>
      <!-- 组合概览卡片 -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <el-card shadow="hover">
          <div class="text-center">
            <div class="text-gray-500 text-sm mb-1">组合总资产</div>
            <div class="text-2xl font-bold">{{ formatMoney(overview.total_assets) }}</div>
          </div>
        </el-card>
        <el-card shadow="hover">
          <div class="text-center">
            <div class="text-gray-500 text-sm mb-1">总盈亏</div>
            <div class="text-2xl font-bold" :class="overview.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ overview.total_pnl >= 0 ? '+' : '' }}{{ formatMoney(overview.total_pnl) }}
              <span class="text-sm ml-1">({{ overview.total_pnl_pct >= 0 ? '+' : '' }}{{ overview.total_pnl_pct.toFixed(2) }}%)</span>
            </div>
          </div>
        </el-card>
        <el-card shadow="hover">
          <div class="text-center">
            <div class="text-gray-500 text-sm mb-1">持仓市值</div>
            <div class="text-2xl font-bold text-blue-600">{{ formatMoney(overview.total_position_value) }}</div>
          </div>
        </el-card>
        <el-card shadow="hover">
          <div class="text-center">
            <div class="text-gray-500 text-sm mb-1">策略 / 运行中</div>
            <div class="text-2xl font-bold">
              <span class="text-gray-700">{{ overview.strategy_count }}</span>
              <span class="text-gray-400 mx-1">/</span>
              <span class="text-green-600">{{ overview.running_count }}</span>
            </div>
          </div>
        </el-card>
      </div>

      <!-- 主内容区 -->
      <el-tabs v-model="activeTab">
        <!-- 策略概览 Tab -->
        <el-tab-pane label="策略概览" name="strategies">
          <el-card>
            <el-table :data="overview.strategies" stripe size="small" class="w-full">
              <el-table-column prop="strategy_name" label="策略名称" min-width="140">
                <template #default="{ row }">
                  <router-link :to="`/live-trading/${row.id}`" class="text-blue-600 hover:underline">
                    {{ row.strategy_name }}
                  </router-link>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="80" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'running' ? 'success' : row.status === 'error' ? 'danger' : 'info'" size="small">
                    {{ row.status === 'running' ? '运行' : row.status === 'error' ? '异常' : '停止' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="当前资产" width="130" align="right">
                <template #default="{ row }">{{ formatMoney(row.total_assets) }}</template>
              </el-table-column>
              <el-table-column label="初始资金" width="130" align="right">
                <template #default="{ row }">{{ formatMoney(row.initial_capital) }}</template>
              </el-table-column>
              <el-table-column label="盈亏" width="130" align="right">
                <template #default="{ row }">
                  <span :class="row.pnl >= 0 ? 'text-green-600' : 'text-red-600'">
                    {{ row.pnl >= 0 ? '+' : '' }}{{ formatMoney(row.pnl) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="收益率" width="90" align="right">
                <template #default="{ row }">
                  <span :class="row.pnl_pct >= 0 ? 'text-green-600' : 'text-red-600'">
                    {{ row.pnl_pct >= 0 ? '+' : '' }}{{ row.pnl_pct.toFixed(2) }}%
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="交易次数" prop="total_trades" width="80" align="center" />
              <el-table-column label="胜率" width="70" align="center">
                <template #default="{ row }">{{ row.win_rate.toFixed(1) }}%</template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-tab-pane>

        <!-- 持仓 Tab -->
        <el-tab-pane label="当前持仓" name="positions">
          <el-card>
            <div v-if="positions.length === 0" class="text-center text-gray-400 py-8">暂无持仓数据</div>
            <el-table v-else :data="positions" stripe size="small" class="w-full">
              <el-table-column prop="strategy_name" label="策略" min-width="120" />
              <el-table-column prop="data_name" label="标的代码" width="120" />
              <el-table-column label="方向" width="70" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.size > 0 ? 'danger' : row.size < 0 ? 'success' : 'info'" size="small">
                    {{ row.direction }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="持仓量" width="100" align="right">
                <template #default="{ row }">{{ row.size }}</template>
              </el-table-column>
              <el-table-column label="成本价" width="100" align="right">
                <template #default="{ row }">{{ row.price.toFixed(4) }}</template>
              </el-table-column>
              <el-table-column label="市值" width="130" align="right">
                <template #default="{ row }">{{ formatMoney(row.market_value) }}</template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-tab-pane>

        <!-- 交易记录 Tab -->
        <el-tab-pane label="交易记录" name="trades">
          <el-card>
            <div v-if="trades.length === 0" class="text-center text-gray-400 py-8">暂无交易记录</div>
            <el-table v-else :data="trades" stripe size="small" class="w-full" max-height="500">
              <el-table-column prop="strategy_name" label="策略" min-width="100" />
              <el-table-column prop="data_name" label="标的" width="90" />
              <el-table-column label="方向" width="60" align="center">
                <template #default="{ row }">
                  <span :class="row.direction === 'long' ? 'text-red-600' : 'text-green-600'">
                    {{ row.direction === 'long' ? '多' : '空' }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="dtopen" label="开仓日期" width="100" />
              <el-table-column prop="dtclose" label="平仓日期" width="100" />
              <el-table-column label="价格" width="90" align="right">
                <template #default="{ row }">{{ row.price.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column label="数量" width="70" align="right">
                <template #default="{ row }">{{ row.size }}</template>
              </el-table-column>
              <el-table-column label="手续费" width="80" align="right">
                <template #default="{ row }">{{ row.commission.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column label="净盈亏" width="100" align="right" sortable>
                <template #default="{ row }">
                  <span :class="row.pnlcomm >= 0 ? 'text-green-600' : 'text-red-600'">
                    {{ row.pnlcomm >= 0 ? '+' : '' }}{{ row.pnlcomm.toFixed(2) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="持仓天数" prop="barlen" width="80" align="center" />
            </el-table>
          </el-card>
        </el-tab-pane>

        <!-- 资金曲线 Tab -->
        <el-tab-pane label="资金曲线" name="equity">
          <el-card v-if="activeTab === 'equity'">
            <div ref="equityChartRef" style="width:100%;height:400px"></div>
            <div ref="drawdownChartRef" style="width:100%;height:180px;margin-top:8px"></div>
          </el-card>
        </el-tab-pane>

        <!-- 资产配置 Tab -->
        <el-tab-pane label="资产配置" name="allocation">
          <el-card v-if="activeTab === 'allocation'">
            <div ref="allocationChartRef" style="width:100%;height:400px"></div>
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick, onBeforeUnmount } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { portfolioApi } from '@/api/portfolio'
import type {
  PortfolioOverview,
  PositionItem,
  TradeItem,
  PortfolioEquity,
  AllocationItem,
} from '@/api/portfolio'

const loading = ref(true)
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
  if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return v.toFixed(2)
}

const loadedTabs = ref<Set<string>>(new Set(['strategies']))

async function loadData() {
  loading.value = true
  try {
    overview.value = await portfolioApi.getOverview()
  } catch (e: any) {
    ElMessage.error(e.message || '加载组合数据失败')
  } finally {
    loading.value = false
  }
}

async function loadTabData(tab: string) {
  if (loadedTabs.value.has(tab)) return
  try {
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
    loadedTabs.value.add(tab)
  } catch (e: any) {
    ElMessage.error(e.message || '加载数据失败')
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
    name: '组合总资产',
    type: 'line',
    data: data.total_equity,
    symbol: 'none',
    lineStyle: { width: 2, color: '#1a56db' },
    itemStyle: { color: '#1a56db' },
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
    tooltip: { trigger: 'axis', formatter: (params: any) => {
      const p = Array.isArray(params) ? params[0] : params
      return `${p.axisValue}<br/>回撤: ${(p.value * 100).toFixed(2)}%`
    }},
    grid: { left: 80, right: 20, top: 10, bottom: 30 },
    xAxis: { type: 'category', data: data.dates, boundaryGap: false, show: false },
    yAxis: { type: 'value', axisLabel: { formatter: (v: number) => (v * 100).toFixed(1) + '%' } },
    series: [{
      type: 'line',
      data: data.total_drawdown,
      areaStyle: { color: 'rgba(220,38,38,0.15)' },
      lineStyle: { color: '#dc2626', width: 1 },
      itemStyle: { color: '#dc2626' },
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
