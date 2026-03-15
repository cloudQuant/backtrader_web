<template>
  <div class="quote-page space-y-4">
    <!-- Data Source Tabs -->
    <el-card class="!p-0" body-class="!p-3">
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-1 flex-wrap">
          <div
            v-for="src in store.sources"
            :key="src.source"
            class="source-tab"
            :class="{
              'source-tab--active': src.source === store.activeSource,
              'source-tab--available': src.status === 'available',
              'source-tab--disconnected': src.status === 'not_connected',
              'source-tab--unavailable': src.status === 'unavailable' || src.status === 'not_configured',
            }"
            @click="handleSourceClick(src)"
          >
            <span class="source-tab__label">{{ src.source_label }}</span>
            <span class="source-tab__dot" />
          </div>
        </div>
        <!-- Refresh status -->
        <div class="flex items-center gap-2 text-xs text-gray-500">
          <el-tag size="small" :type="refreshModeTag" effect="plain">
            {{ refreshModeText }}
          </el-tag>
          <span v-if="store.updateTime" :class="{ 'text-orange-500': isDataStale }">
            {{ formatTime(store.updateTime) }}
            <el-tooltip v-if="isDataStale" content="数据可能已过期，建议刷新" placement="top">
              <el-icon class="ml-1 text-orange-500"><WarningFilled /></el-icon>
            </el-tooltip>
          </span>
          <span v-if="store.quotesLoading" class="text-blue-500 flex items-center gap-1">
            <el-icon class="is-loading"><Loading /></el-icon> 刷新中
          </span>
        </div>
      </div>
    </el-card>

    <!-- Source unavailable / disconnected state -->
    <template v-if="store.activeSourceInfo && store.activeSourceInfo.status !== 'available'">
      <el-card>
        <el-empty :description="sourceStatusText">
          <el-button
            v-if="store.activeSourceInfo.status === 'not_connected'"
            type="primary"
            @click="$router.push('/gateways')"
          >
            前往连接 Gateway
          </el-button>
        </el-empty>
      </el-card>
    </template>

    <!-- Main content (only when source is available) -->
    <template v-else>
      <!-- Toolbar -->
      <el-card class="!p-0" body-class="!py-2 !px-3">
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div class="flex items-center gap-2 flex-wrap">
            <!-- Search -->
            <el-input
              v-model="store.searchKeyword"
              placeholder="搜索代码 / 名称"
              :prefix-icon="Search"
              clearable
              style="width: 200px"
              size="default"
            />
            <!-- Category filter -->
            <el-select
              v-model="store.filterCategory"
              placeholder="全部分类"
              clearable
              size="default"
              style="width: 130px"
            >
              <el-option
                v-for="cat in store.categories"
                :key="cat"
                :label="cat"
                :value="cat"
              />
            </el-select>
            <!-- Trend filter -->
            <el-select
              v-model="store.filterTrend"
              placeholder="涨跌筛选"
              clearable
              size="default"
              style="width: 120px"
            >
              <el-option label="上涨" value="up" />
              <el-option label="下跌" value="down" />
              <el-option label="平盘" value="flat" />
            </el-select>
            <!-- Custom only -->
            <el-checkbox v-model="store.filterCustomOnly" label="仅自选" />
            <!-- Advanced filter (P1) -->
            <el-popover placement="bottom" :width="320" trigger="click">
              <template #reference>
                <el-button size="default" :type="store.hasAdvancedFilters ? 'primary' : ''">
                  <el-icon><Filter /></el-icon> 高级筛选
                  <el-badge v-if="store.hasAdvancedFilters" is-dot class="ml-1" />
                </el-button>
              </template>
              <div class="space-y-3 text-sm">
                <div>
                  <span class="text-gray-600">涨跌幅区间 (%)</span>
                  <div class="flex items-center gap-2 mt-1">
                    <el-input-number
                      v-model="store.filterChangePctMin"
                      :controls="false"
                      placeholder="最小"
                      size="small"
                      style="width: 100px"
                    />
                    <span>~</span>
                    <el-input-number
                      v-model="store.filterChangePctMax"
                      :controls="false"
                      placeholder="最大"
                      size="small"
                      style="width: 100px"
                    />
                  </div>
                </div>
                <div>
                  <span class="text-gray-600">成交量区间</span>
                  <div class="flex items-center gap-2 mt-1">
                    <el-input-number
                      v-model="store.filterVolumeMin"
                      :controls="false"
                      placeholder="最小"
                      size="small"
                      style="width: 100px"
                    />
                    <span>~</span>
                    <el-input-number
                      v-model="store.filterVolumeMax"
                      :controls="false"
                      placeholder="最大"
                      size="small"
                      style="width: 100px"
                    />
                  </div>
                </div>
                <div>
                  <el-checkbox v-model="store.filterHasOpenInterest" label="仅有持仓量" />
                </div>
                <div class="flex justify-end">
                  <el-button size="small" @click="store.clearAdvancedFilters()">重置</el-button>
                </div>
              </div>
            </el-popover>
          </div>

          <div class="flex items-center gap-2">
            <!-- Auto refresh toggle -->
            <el-tooltip content="自动刷新">
              <el-switch
                v-model="autoRefreshLocal"
                active-text=""
                inactive-text=""
                size="small"
                @change="(v: boolean) => store.setAutoRefresh(v)"
              />
            </el-tooltip>
            <el-select
              v-if="store.autoRefresh"
              v-model="refreshIntervalLocal"
              size="small"
              style="width: 80px"
              @change="(v: number) => store.setRefreshInterval(v)"
            >
              <el-option :label="'1s'" :value="1" />
              <el-option :label="'3s'" :value="3" />
              <el-option :label="'5s'" :value="5" />
              <el-option :label="'10s'" :value="10" />
              <el-option :label="'30s'" :value="30" />
            </el-select>
            <!-- Manual refresh -->
            <el-button :loading="store.quotesLoading" size="default" @click="store.fetchQuotes()">
              <el-icon><Refresh /></el-icon>
            </el-button>
            <!-- Column config (P1) -->
            <el-tooltip content="列设置">
              <el-button size="default" @click="showColumnDialog = true">
                <el-icon><Setting /></el-icon>
              </el-button>
            </el-tooltip>
            <!-- Add symbol -->
            <el-button type="primary" size="default" @click="showAddDialog = true">
              <el-icon><Plus /></el-icon> 添加品种
            </el-button>
          </div>
        </div>
      </el-card>

      <!-- Loading -->
      <div v-if="store.quotesLoading && store.ticks.length === 0" class="flex justify-center py-12">
        <el-icon class="is-loading text-4xl text-blue-500"><Loading /></el-icon>
      </div>

      <!-- Error state -->
      <el-card v-else-if="store.quotesError">
        <el-empty description="行情数据加载失败">
          <template #description>
            <p class="text-red-500">{{ store.quotesError }}</p>
          </template>
          <el-button type="primary" @click="store.fetchQuotes()">重试</el-button>
        </el-empty>
      </el-card>

      <!-- Empty state -->
      <el-card v-else-if="store.filteredTicks.length === 0 && store.ticks.length === 0">
        <el-empty description="暂无行情数据">
          <el-button type="primary" @click="showAddDialog = true">添加品种</el-button>
        </el-empty>
      </el-card>

      <!-- Quote Table -->
      <el-card v-else class="!p-0" body-class="!p-0">
        <el-table
          :data="store.filteredTicks"
          stripe
          border
          size="small"
          class="quote-table"
          highlight-current-row
          max-height="calc(100vh - 320px)"
          :default-sort="tableSortProp"
          :row-class-name="rowClassName"
          @sort-change="handleSortChange"
          @row-click="handleRowClick"
        >
          <el-table-column type="index" label="#" width="50" fixed="left" />
          <!-- Dynamic columns based on columnConfig -->
          <template v-for="col in visibleColumns" :key="col.prop">
            <el-table-column
              v-if="col.prop === 'symbol'"
              prop="symbol"
              :label="col.label"
              width="110"
              fixed="left"
              sortable="custom"
            >
              <template #default="{ row }">
                <span class="font-mono font-medium">{{ row.symbol }}</span>
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="col.prop === 'name'"
              prop="name"
              :label="col.label"
              width="130"
              fixed="left"
              show-overflow-tooltip
            />
            <el-table-column
              v-else-if="col.prop === 'category'"
              prop="category"
              :label="col.label"
              width="90"
              show-overflow-tooltip
            />
            <el-table-column
              v-else-if="col.prop === 'last_price'"
              prop="last_price"
              :label="col.label"
              width="100"
              sortable="custom"
              align="right"
            >
              <template #default="{ row }">
                <span :class="priceClass(row)">{{ fmtPrice(row.last_price) }}</span>
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="col.prop === 'change'"
              prop="change"
              :label="col.label"
              width="90"
              sortable="custom"
              align="right"
            >
              <template #default="{ row }">
                <span :class="changeClass(row.change)">{{ fmtChange(row.change) }}</span>
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="col.prop === 'change_pct'"
              prop="change_pct"
              :label="col.label"
              width="90"
              sortable="custom"
              align="right"
            >
              <template #default="{ row }">
                <span :class="changeClass(row.change_pct)">{{ fmtPct(row.change_pct) }}</span>
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="col.prop === 'update_time'"
              prop="update_time"
              :label="col.label"
              width="100"
              sortable="custom"
              align="center"
            >
              <template #default="{ row }">
                <span class="text-xs text-gray-500">{{ formatTime(row.update_time) }}</span>
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="['volume', 'turnover', 'open_interest'].includes(col.prop)"
              :prop="col.prop"
              :label="col.label"
              :width="col.prop === 'volume' || col.prop === 'turnover' ? 100 : 90"
              sortable="custom"
              align="right"
            >
              <template #default="{ row }">{{ fmtVol(row[col.prop]) }}</template>
            </el-table-column>
            <el-table-column
              v-else
              :prop="col.prop"
              :label="col.label"
              width="90"
              sortable="custom"
              align="right"
            >
              <template #default="{ row }">{{ fmtPrice(row[col.prop]) }}</template>
            </el-table-column>
          </template>
          <!-- Actions column -->
          <el-table-column label="操作" width="100" fixed="right" align="center">
            <template #default="{ row }">
              <el-button type="primary" size="small" link @click.stop="store.openChart(row.symbol)">
                <el-icon><DataLine /></el-icon>
              </el-button>
              <el-popconfirm
                v-if="isCustomSymbol(row.symbol)"
                title="确定移除此品种？"
                @confirm="store.removeSymbol(row.symbol)"
              >
                <template #reference>
                  <el-button type="danger" size="small" link @click.stop>
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
        <!-- Table footer -->
        <div class="flex items-center justify-between px-3 py-2 text-xs text-gray-500 border-t">
          <span>
            共 {{ store.filteredTicks.length }} / {{ store.ticks.length }} 条
            <template v-if="store.hasAdvancedFilters">
              <el-tag size="small" type="warning" effect="plain" class="ml-2">高级筛选已启用</el-tag>
            </template>
          </span>
          <span v-if="store.quotesLoading" class="text-blue-500">刷新中...</span>
        </div>
      </el-card>
    </template>

    <!-- Add Symbol Dialog -->
    <el-dialog v-model="showAddDialog" title="添加品种" width="480px" destroy-on-close>
      <el-input
        v-model="addKeyword"
        placeholder="输入品种代码或名称搜索"
        clearable
        @input="handleAddSearch"
      />
      <div v-if="store.symbolSearchLoading" class="py-4 text-center">
        <el-icon class="is-loading"><Loading /></el-icon> 搜索中...
      </div>
      <div v-else-if="store.symbolSearchResults.length > 0" class="mt-3 max-h-64 overflow-auto">
        <div
          v-for="item in store.symbolSearchResults"
          :key="item.symbol"
          class="flex items-center justify-between px-3 py-2 hover:bg-gray-50 rounded cursor-pointer"
          @click="handleAddSymbol(item.symbol)"
        >
          <div>
            <span class="font-mono font-medium">{{ item.symbol }}</span>
            <span class="ml-2 text-sm text-gray-500">{{ item.name }}</span>
          </div>
          <el-tag size="small" type="info" effect="plain">{{ item.exchange }}</el-tag>
        </div>
      </div>
      <div v-else-if="addKeyword && !store.symbolSearchLoading" class="py-4 text-center text-gray-400">
        未找到匹配品种
      </div>
      <el-divider />
      <div class="flex items-center gap-2">
        <el-input v-model="addSymbolDirect" placeholder="精确输入品种代码" @keyup.enter="handleDirectAdd" />
        <el-button type="primary" :disabled="!addSymbolDirect" @click="handleDirectAdd">添加</el-button>
      </div>
    </el-dialog>

    <!-- Column Config Dialog (P1) -->
    <el-dialog v-model="showColumnDialog" title="列设置" width="420px" destroy-on-close>
      <div class="text-xs text-gray-400 mb-3">勾选要显示的列，拖拽调整顺序</div>
      <div class="space-y-1 max-h-80 overflow-auto">
        <div
          v-for="(col, idx) in columnConfigLocal"
          :key="col.prop"
          class="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-gray-50"
          draggable="true"
          @dragstart="onColDragStart(idx)"
          @dragover.prevent
          @drop="onColDrop(idx)"
        >
          <el-icon class="cursor-move text-gray-400"><Rank /></el-icon>
          <el-checkbox v-model="col.visible" :label="col.label" />
        </div>
      </div>
      <template #footer>
        <el-button @click="handleResetColumns">恢复默认</el-button>
        <el-button type="primary" @click="handleSaveColumns">保存</el-button>
      </template>
    </el-dialog>

    <!-- Chart Drawer (P1) -->
    <el-drawer
      v-model="store.chartDrawerVisible"
      :title="`${store.chartSymbol} 图表详情`"
      direction="btt"
      size="50%"
      :destroy-on-close="true"
      @close="store.closeChart()"
    >
      <!-- Timeframe selector -->
      <div class="flex items-center gap-2 mb-3">
        <span class="text-sm text-gray-500">周期:</span>
        <el-radio-group
          :model-value="store.chartTimeframe"
          size="small"
          @change="(v: string) => store.setChartTimeframe(v)"
        >
          <el-radio-button label="M1">1分</el-radio-button>
          <el-radio-button label="M5">5分</el-radio-button>
          <el-radio-button label="M15">15分</el-radio-button>
          <el-radio-button label="M30">30分</el-radio-button>
          <el-radio-button label="H1">1时</el-radio-button>
          <el-radio-button label="H4">4时</el-radio-button>
          <el-radio-button label="D1">日线</el-radio-button>
        </el-radio-group>
        <el-button size="small" :loading="store.chartLoading" @click="store.fetchChartData()">
          <el-icon><Refresh /></el-icon>
        </el-button>
      </div>
      <!-- Chart content -->
      <div v-if="store.chartLoading" class="flex items-center justify-center h-64">
        <el-icon class="is-loading text-3xl text-blue-500"><Loading /></el-icon>
      </div>
      <div v-else-if="store.chartError" class="flex flex-col items-center justify-center h-64 gap-3">
        <p class="text-red-500">{{ store.chartError }}</p>
        <el-button type="primary" size="small" @click="store.fetchChartData()">重试</el-button>
      </div>
      <div v-else-if="store.chartBars.length === 0" class="flex items-center justify-center h-64">
        <el-empty description="暂无图表数据" />
      </div>
      <div v-else ref="chartContainerRef" class="w-full" style="height: calc(100% - 50px)" />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import {
  Search,
  Refresh,
  Plus,
  Loading,
  Delete,
  Setting,
  Filter,
  Rank,
  DataLine,
  WarningFilled,
} from '@element-plus/icons-vue'
import { useQuoteStore } from '@/stores/quote'
import type { DataSourceInfo, QuoteTick } from '@/api/quote'

const store = useQuoteStore()

// ---- local refs synced with store ----
const autoRefreshLocal = ref(store.autoRefresh)
const refreshIntervalLocal = ref(store.refreshInterval)

// ---- add symbol dialog ----
const showAddDialog = ref(false)
const addKeyword = ref('')
const addSymbolDirect = ref('')
let searchDebounce: ReturnType<typeof setTimeout> | null = null

function handleAddSearch() {
  if (searchDebounce) clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => {
    store.searchSymbols(addKeyword.value)
  }, 300)
}

async function handleAddSymbol(symbol: string) {
  try {
    await store.addSymbol(symbol)
    ElMessage.success(`已添加 ${symbol}`)
  } catch {
    // axios interceptor handles
  }
}

async function handleDirectAdd() {
  if (!addSymbolDirect.value) return
  await handleAddSymbol(addSymbolDirect.value.trim().toUpperCase())
  addSymbolDirect.value = ''
}

// ---- source click ----
function handleSourceClick(src: DataSourceInfo) {
  if (src.status === 'unavailable' || src.status === 'not_configured') {
    ElMessage.warning(src.status_message || '该数据源暂不可用')
    return
  }
  store.switchSource(src.source)
}

// ---- source status text ----
const sourceStatusText = computed(() => {
  const info = store.activeSourceInfo
  if (!info) return ''
  switch (info.status) {
    case 'not_connected':
      return info.status_message || '网关未连接，请前往 Gateway 状态页连接'
    case 'not_configured':
      return '数据源未配置，请先完成相关配置'
    case 'unavailable':
      return info.status_message || '该数据源接入中，暂不可用'
    default:
      return ''
  }
})

// ---- refresh mode display ----
const refreshModeTag = computed(() => {
  switch (store.refreshMode) {
    case 'push': return 'success'
    case 'polling': return 'warning'
    default: return 'info'
  }
})

const refreshModeText = computed(() => {
  switch (store.refreshMode) {
    case 'push': return '实时推送'
    case 'polling': return store.autoRefresh ? `轮询 ${store.refreshInterval}s` : '手动刷新'
    default: return '手动刷新'
  }
})

// ---- data staleness detection (P1) ----
const isDataStale = computed(() => {
  if (!store.updateTime) return false
  try {
    const elapsed = Date.now() - new Date(store.updateTime).getTime()
    return elapsed > 60_000
  } catch {
    return false
  }
})

// ---- table sort ----
const tableSortProp = computed(() => {
  if (!store.sortField) return {}
  return { prop: store.sortField, order: store.sortOrder === 'asc' ? 'ascending' : 'descending' }
})

function handleSortChange({ prop, order }: { prop: string; order: string | null }) {
  if (!order) {
    store.sortField = ''
    store.sortOrder = 'asc'
  } else {
    store.sortField = prop
    store.sortOrder = order === 'ascending' ? 'asc' : 'desc'
  }
  // persist sort state using same key convention as the store
  const pfx = 'btweb_quote_'
  try {
    localStorage.setItem(pfx + `sort_field_${store.activeSource}`, JSON.stringify(store.sortField))
    localStorage.setItem(pfx + `sort_order_${store.activeSource}`, JSON.stringify(store.sortOrder))
  } catch { /* ignore */ }
}

// ---- row click -> open chart (P1) ----
function handleRowClick(row: QuoteTick) {
  store.openChart(row.symbol)
}

// ---- tick flash animation (P1) ----
const flashSymbols = ref<Set<string>>(new Set())
let prevTickMap: Map<string, number> = new Map()

watch(
  () => store.ticks,
  (newTicks) => {
    const updated = new Set<string>()
    for (const t of newTicks) {
      const prev = prevTickMap.get(t.symbol)
      if (prev !== undefined && t.last_price !== null && prev !== t.last_price) {
        updated.add(t.symbol)
      }
      if (t.last_price != null) prevTickMap.set(t.symbol, t.last_price)
    }
    if (updated.size > 0) {
      flashSymbols.value = updated
      setTimeout(() => { flashSymbols.value = new Set() }, 600)
    }
  },
  { deep: true },
)

function rowClassName({ row }: { row: QuoteTick }) {
  return flashSymbols.value.has(row.symbol) ? 'tick-flash' : ''
}

// ---- custom symbol check ----
function isCustomSymbol(symbol: string) {
  return store.customSymbols.includes(symbol)
}

// ---- column config (P1) ----
const showColumnDialog = ref(false)
const columnConfigLocal = ref<{ prop: string; label: string; visible: boolean }[]>([])
let dragFromIdx = -1

const visibleColumns = computed(() =>
  store.columnConfig.filter((c: { visible: boolean }) => c.visible),
)

function onColDragStart(idx: number) { dragFromIdx = idx }
function onColDrop(idx: number) {
  if (dragFromIdx < 0 || dragFromIdx === idx) return
  const item = columnConfigLocal.value.splice(dragFromIdx, 1)[0]
  columnConfigLocal.value.splice(idx, 0, item)
  dragFromIdx = -1
}

function handleSaveColumns() {
  store.setColumnConfig(columnConfigLocal.value.map((c) => ({ ...c })))
  showColumnDialog.value = false
}

function handleResetColumns() {
  store.resetColumnConfig()
  columnConfigLocal.value = store.columnConfig.map((c: { prop: string; label: string; visible: boolean }) => ({ ...c }))
}

watch(showColumnDialog, (v) => {
  if (v) {
    columnConfigLocal.value = store.columnConfig.map((c: { prop: string; label: string; visible: boolean }) => ({ ...c }))
  }
})

// ---- formatting helpers ----
function fmtPrice(v: number | null): string {
  if (v == null) return '--'
  return v.toFixed(2)
}

function fmtChange(v: number | null): string {
  if (v == null) return '--'
  return (v >= 0 ? '+' : '') + v.toFixed(2)
}

function fmtPct(v: number | null): string {
  if (v == null) return '--'
  return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'
}

function fmtVol(v: number | null): string {
  if (v == null) return '--'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return String(Math.round(v))
}

function formatTime(iso: string | null): string {
  if (!iso) return '--'
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return '--'
  }
}

function priceClass(row: { change_pct: number | null }): string {
  if (row.change_pct == null) return ''
  if (row.change_pct > 0) return 'text-red-600 font-medium'
  if (row.change_pct < 0) return 'text-green-600 font-medium'
  return 'text-gray-600'
}

function changeClass(v: number | null): string {
  if (v == null) return 'text-gray-400'
  if (v > 0) return 'text-red-600'
  if (v < 0) return 'text-green-600'
  return 'text-gray-500'
}

// ---- chart (P1) ----
const chartContainerRef = ref<HTMLDivElement>()
let chartInstance: echarts.ECharts | null = null

function buildChartOption() {
  const bars = store.chartBars
  const dates = bars.map((b) => b.date)
  const ohlc = bars.map((b) => [b.open, b.close, b.low, b.high])
  const volumes = bars.map((b) => b.volume)
  // volume bar color: up=red, down=green
  const volColors = bars.map((b) => (b.close >= b.open ? '#ec0000' : '#00da3c'))

  return {
    animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: '10%', right: '5%', height: '55%' },
      { left: '10%', right: '5%', top: '72%', height: '18%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLine: { onZero: false },
        splitLine: { show: false },
      },
      {
        type: 'category',
        gridIndex: 1,
        data: dates,
        boundaryGap: false,
        axisLine: { onZero: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
      },
    ],
    yAxis: [
      { scale: true, splitArea: { show: true } },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 60, end: 100 },
      { show: true, xAxisIndex: [0, 1], type: 'slider', top: '93%', start: 60, end: 100 },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: ohlc,
        itemStyle: { color: '#ec0000', color0: '#00da3c', borderColor: '#ec0000', borderColor0: '#00da3c' },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes.map((v, i) => ({ value: v, itemStyle: { color: volColors[i] } })),
      },
    ],
  } as echarts.EChartsOption
}

function renderChart() {
  if (!chartContainerRef.value || store.chartBars.length === 0) return
  if (chartInstance) chartInstance.dispose()
  chartInstance = echarts.init(chartContainerRef.value)
  chartInstance.setOption(buildChartOption())
}

function handleChartResize() {
  chartInstance?.resize()
}

watch(
  () => [store.chartBars, store.chartDrawerVisible],
  () => {
    if (store.chartDrawerVisible && store.chartBars.length > 0) {
      nextTick(() => renderChart())
    }
  },
  { deep: true },
)

// ---- lifecycle ----
onMounted(async () => {
  await store.fetchSources()
  if (store.activeSource && store.activeSourceInfo?.status === 'available') {
    await store.fetchQuotes()
    if (store.autoRefresh) store.startAutoRefresh()
  }
  window.addEventListener('resize', handleChartResize)
})

onUnmounted(() => {
  store.cleanup()
  chartInstance?.dispose()
  window.removeEventListener('resize', handleChartResize)
})
</script>

<style scoped>
.source-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
  user-select: none;
  border: 1px solid transparent;
}

.source-tab:hover {
  background-color: rgba(59, 130, 246, 0.08);
}

.source-tab--active {
  background-color: rgba(59, 130, 246, 0.15) !important;
  border-color: #3b82f6;
  color: #3b82f6;
}

.source-tab__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.source-tab--available .source-tab__dot {
  background-color: #67c23a;
}

.source-tab--disconnected .source-tab__dot {
  background-color: #e6a23c;
}

.source-tab--unavailable .source-tab__dot {
  background-color: #909399;
}

.source-tab--unavailable {
  color: #909399;
  cursor: not-allowed;
}

/* Dense table style */
.quote-table :deep(.el-table__row td) {
  padding: 4px 0;
  font-size: 13px;
}

.quote-table :deep(.el-table__header th) {
  padding: 6px 0;
  font-size: 12px;
  background-color: #f8fafc !important;
}

/* Tick flash animation (P1) */
.quote-table :deep(.tick-flash td) {
  animation: tick-flash-anim 0.6s ease-out;
}

@keyframes tick-flash-anim {
  0% { background-color: rgba(59, 130, 246, 0.15); }
  100% { background-color: transparent; }
}

/* Row click cursor */
.quote-table :deep(.el-table__row) {
  cursor: pointer;
}
</style>
