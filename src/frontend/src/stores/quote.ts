/**
 * 行情报价 Pinia Store
 *
 * Manages data-source selection, quote data, custom symbols,
 * search/filter/sort state, and auto-refresh lifecycle.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { quoteApi } from '@/api/quote'
import type {
  DataSourceInfo,
  KlineBar,
  QuoteTick,
  SymbolItem,
} from '@/api/quote'

// ---------------------------------------------------------------------------
// Local-storage keys & helpers
// ---------------------------------------------------------------------------

const LS_PREFIX = 'btweb_quote_'

function lsGet<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(LS_PREFIX + key)
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

function lsSet(key: string, value: unknown): void {
  try {
    localStorage.setItem(LS_PREFIX + key, JSON.stringify(value))
  } catch { /* quota exceeded – ignore */ }
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useQuoteStore = defineStore('quote', () => {
  // ---- data sources ----
  const sources = ref<DataSourceInfo[]>([])
  const sourcesLoading = ref(false)

  const activeSource = ref<string>(lsGet('activeSource', ''))

  const activeSourceInfo = computed(() =>
    sources.value.find((s) => s.source === activeSource.value) ?? null,
  )

  // ---- quotes ----
  const ticks = ref<QuoteTick[]>([])
  const quotesLoading = ref(false)
  const quotesError = ref<string | null>(null)
  const updateTime = ref<string | null>(null)
  const refreshMode = ref<string>('polling')

  // ---- search / filter / sort ----
  const searchKeyword = ref('')
  const filterCategory = ref('')
  const filterTrend = ref<'' | 'up' | 'down' | 'flat'>('')
  const filterCustomOnly = ref(false)
  const sortField = ref<string>(lsGet(`sort_field_${activeSource.value}`, ''))
  const sortOrder = ref<'asc' | 'desc'>(lsGet(`sort_order_${activeSource.value}`, 'asc'))

  // ---- custom symbols ----
  const customSymbols = ref<string[]>([])

  // ---- auto refresh ----
  const autoRefresh = ref<boolean>(lsGet('autoRefresh', false))
  const refreshInterval = ref<number>(lsGet('refreshInterval', 5))
  let refreshTimer: ReturnType<typeof setInterval> | null = null
  let fetchInProgress = false

  // ---- symbol search dialog ----
  const symbolSearchResults = ref<SymbolItem[]>([])
  const symbolSearchLoading = ref(false)

  // ---- chart drawer (P1) ----
  const chartDrawerVisible = ref(false)
  const chartSymbol = ref('')
  const chartTimeframe = ref<string>(lsGet('chartTimeframe', 'M5'))
  const chartBars = ref<KlineBar[]>([])
  const chartLoading = ref(false)
  const chartError = ref<string | null>(null)

  // ---- column config (P1) ----
  interface ColumnDef {
    prop: string
    label: string
    visible: boolean
  }
  const ALL_COLUMNS: ColumnDef[] = [
    { prop: 'symbol', label: '代码', visible: true },
    { prop: 'name', label: '名称', visible: true },
    { prop: 'category', label: '分类', visible: true },
    { prop: 'last_price', label: '最新价', visible: true },
    { prop: 'change', label: '涨跌', visible: true },
    { prop: 'change_pct', label: '涨跌幅', visible: true },
    { prop: 'bid_price', label: '买价', visible: true },
    { prop: 'ask_price', label: '卖价', visible: true },
    { prop: 'high_price', label: '最高', visible: true },
    { prop: 'low_price', label: '最低', visible: true },
    { prop: 'open_price', label: '开盘', visible: true },
    { prop: 'prev_close', label: '昨收', visible: true },
    { prop: 'volume', label: '成交量', visible: true },
    { prop: 'turnover', label: '成交额', visible: true },
    { prop: 'open_interest', label: '持仓量', visible: true },
    { prop: 'update_time', label: '更新时间', visible: true },
  ]
  const columnConfig = ref<ColumnDef[]>(lsGet('columnConfig', ALL_COLUMNS))

  // ---- advanced filter (P1) ----
  const filterChangePctMin = ref<number | null>(null)
  const filterChangePctMax = ref<number | null>(null)
  const filterVolumeMin = ref<number | null>(null)
  const filterVolumeMax = ref<number | null>(null)
  const filterHasOpenInterest = ref(false)

  // ===========================================================================
  // Computed: filtered + sorted ticks
  // ===========================================================================

  const filteredTicks = computed(() => {
    let list = [...ticks.value]

    // search
    if (searchKeyword.value) {
      const kw = searchKeyword.value.toLowerCase()
      list = list.filter(
        (t) =>
          t.symbol.toLowerCase().includes(kw) ||
          t.name.toLowerCase().includes(kw),
      )
    }

    // filter category
    if (filterCategory.value) {
      list = list.filter((t) => t.category === filterCategory.value)
    }

    // filter trend
    if (filterTrend.value === 'up') {
      list = list.filter((t) => t.change_pct != null && t.change_pct > 0)
    } else if (filterTrend.value === 'down') {
      list = list.filter((t) => t.change_pct != null && t.change_pct < 0)
    } else if (filterTrend.value === 'flat') {
      list = list.filter((t) => t.change_pct == null || t.change_pct === 0)
    }

    // filter custom only
    if (filterCustomOnly.value) {
      const set = new Set(customSymbols.value)
      list = list.filter((t) => set.has(t.symbol))
    }

    // advanced filters (P1)
    if (filterChangePctMin.value != null) {
      list = list.filter((t) => t.change_pct != null && t.change_pct >= filterChangePctMin.value!)
    }
    if (filterChangePctMax.value != null) {
      list = list.filter((t) => t.change_pct != null && t.change_pct <= filterChangePctMax.value!)
    }
    if (filterVolumeMin.value != null) {
      list = list.filter((t) => t.volume != null && t.volume >= filterVolumeMin.value!)
    }
    if (filterVolumeMax.value != null) {
      list = list.filter((t) => t.volume != null && t.volume <= filterVolumeMax.value!)
    }
    if (filterHasOpenInterest.value) {
      list = list.filter((t) => t.open_interest != null && t.open_interest > 0)
    }

    // sort
    if (sortField.value) {
      const field = sortField.value as keyof QuoteTick
      const dir = sortOrder.value === 'asc' ? 1 : -1
      list.sort((a, b) => {
        const va = a[field]
        const vb = b[field]
        if (va == null && vb == null) return 0
        if (va == null) return 1
        if (vb == null) return -1
        if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir
        return String(va).localeCompare(String(vb)) * dir
      })
    }

    return list
  })

  // unique categories for filter dropdown
  const categories = computed(() => {
    const set = new Set<string>()
    for (const t of ticks.value) {
      if (t.category) set.add(t.category)
    }
    return Array.from(set).sort()
  })

  // ===========================================================================
  // Actions
  // ===========================================================================

  async function fetchSources() {
    sourcesLoading.value = true
    try {
      const res = await quoteApi.listSources()
      sources.value = res.sources

      const current = res.sources.find((s) => s.source === activeSource.value)
      const available = res.sources.find((s) => s.status === 'available')
      if (
        !activeSource.value ||
        !current ||
        (current.status !== 'available' && available)
      ) {
        activeSource.value = available?.source ?? current?.source ?? res.sources[0]?.source ?? ''
        lsSet('activeSource', activeSource.value)
      }
    } catch {
      // handled by axios interceptor
    } finally {
      sourcesLoading.value = false
    }
  }

  async function switchSource(source: string) {
    // save previous source sort state
    if (activeSource.value) {
      lsSet(`sort_field_${activeSource.value}`, sortField.value)
      lsSet(`sort_order_${activeSource.value}`, sortOrder.value)
    }

    activeSource.value = source
    lsSet('activeSource', source)

    // restore sort state for new source
    sortField.value = lsGet(`sort_field_${source}`, '')
    sortOrder.value = lsGet(`sort_order_${source}`, 'asc')

    // reset filters
    searchKeyword.value = ''
    filterCategory.value = ''
    filterTrend.value = ''
    filterCustomOnly.value = false
    quotesError.value = null

    // reset advanced filters (P1)
    filterChangePctMin.value = null
    filterChangePctMax.value = null
    filterVolumeMin.value = null
    filterVolumeMax.value = null
    filterHasOpenInterest.value = false

    await fetchQuotes()
  }

  async function fetchQuotes() {
    if (!activeSource.value) return
    if (fetchInProgress) return // prevent request stacking
    fetchInProgress = true
    quotesLoading.value = true
    quotesError.value = null
    try {
      let res = await quoteApi.getQuotes(activeSource.value)
      const shouldRetry =
        res.ticks.length > 0 &&
        res.ticks.every(
          (t) => t.last_price == null && t.bid_price == null && t.ask_price == null,
        )
      if (shouldRetry) {
        await new Promise((resolve) => window.setTimeout(resolve, 1200))
        res = await quoteApi.getQuotes(activeSource.value)
      }
      ticks.value = res.ticks
      updateTime.value = res.update_time
      refreshMode.value = res.refresh_mode
      customSymbols.value = [] // will be set by fetchSymbols
      await fetchSymbolsMeta()
    } catch (e: unknown) {
      quotesError.value = e instanceof Error ? e.message : '行情加载失败'
    } finally {
      quotesLoading.value = false
      fetchInProgress = false
    }
  }

  async function fetchSymbolsMeta() {
    if (!activeSource.value) return
    try {
      const res = await quoteApi.getSymbols(activeSource.value)
      customSymbols.value = res.custom_symbols
    } catch { /* silent */ }
  }

  async function addSymbol(symbol: string) {
    if (!activeSource.value) return
    const res = await quoteApi.addSymbols(activeSource.value, [symbol])
    customSymbols.value = res.symbols
    await fetchQuotes()
  }

  async function removeSymbol(symbol: string) {
    if (!activeSource.value) return
    const res = await quoteApi.removeSymbols(activeSource.value, [symbol])
    customSymbols.value = res.symbols
    await fetchQuotes()
  }

  async function searchSymbols(keyword: string) {
    if (!activeSource.value || !keyword) {
      symbolSearchResults.value = []
      return
    }
    symbolSearchLoading.value = true
    try {
      const res = await quoteApi.searchSymbols(activeSource.value, keyword)
      symbolSearchResults.value = res.results
    } catch {
      symbolSearchResults.value = []
    } finally {
      symbolSearchLoading.value = false
    }
  }

  function setSort(field: string) {
    if (sortField.value === field) {
      sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortField.value = field
      sortOrder.value = 'desc'
    }
    lsSet(`sort_field_${activeSource.value}`, sortField.value)
    lsSet(`sort_order_${activeSource.value}`, sortOrder.value)
  }

  // ---- auto refresh lifecycle ----

  function startAutoRefresh() {
    stopAutoRefresh()
    if (!autoRefresh.value) return
    refreshTimer = setInterval(() => {
      fetchQuotes()
    }, refreshInterval.value * 1000)
  }

  function stopAutoRefresh() {
    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
  }

  function setAutoRefresh(enabled: boolean) {
    autoRefresh.value = enabled
    lsSet('autoRefresh', enabled)
    if (enabled) startAutoRefresh()
    else stopAutoRefresh()
  }

  function setRefreshInterval(seconds: number) {
    refreshInterval.value = seconds
    lsSet('refreshInterval', seconds)
    if (autoRefresh.value) startAutoRefresh()
  }

  function cleanup() {
    stopAutoRefresh()
  }

  // ---- chart actions (P1) ----

  async function openChart(symbol: string) {
    chartSymbol.value = symbol
    chartDrawerVisible.value = true
    chartError.value = null
    await fetchChartData()
  }

  function closeChart() {
    chartDrawerVisible.value = false
    chartBars.value = []
    chartError.value = null
  }

  async function fetchChartData() {
    if (!activeSource.value || !chartSymbol.value) return
    chartLoading.value = true
    chartError.value = null
    try {
      const res = await quoteApi.getChartData(
        activeSource.value,
        chartSymbol.value,
        chartTimeframe.value,
      )
      chartBars.value = res.bars
    } catch (e: unknown) {
      chartError.value = e instanceof Error ? e.message : '图表数据加载失败'
      chartBars.value = []
    } finally {
      chartLoading.value = false
    }
  }

  async function setChartTimeframe(tf: string) {
    chartTimeframe.value = tf
    lsSet('chartTimeframe', tf)
    await fetchChartData()
  }

  // ---- column config actions (P1) ----

  function setColumnConfig(config: ColumnDef[]) {
    columnConfig.value = config
    lsSet('columnConfig', config)
  }

  function resetColumnConfig() {
    columnConfig.value = ALL_COLUMNS.map((c) => ({ ...c }))
    lsSet('columnConfig', columnConfig.value)
  }

  // ---- advanced filter actions (P1) ----

  function clearAdvancedFilters() {
    filterChangePctMin.value = null
    filterChangePctMax.value = null
    filterVolumeMin.value = null
    filterVolumeMax.value = null
    filterHasOpenInterest.value = false
  }

  const hasAdvancedFilters = computed(() => {
    return (
      filterChangePctMin.value != null ||
      filterChangePctMax.value != null ||
      filterVolumeMin.value != null ||
      filterVolumeMax.value != null ||
      filterHasOpenInterest.value
    )
  })

  return {
    // state
    sources,
    sourcesLoading,
    activeSource,
    activeSourceInfo,
    ticks,
    filteredTicks,
    categories,
    quotesLoading,
    quotesError,
    updateTime,
    refreshMode,
    searchKeyword,
    filterCategory,
    filterTrend,
    filterCustomOnly,
    sortField,
    sortOrder,
    customSymbols,
    autoRefresh,
    refreshInterval,
    symbolSearchResults,
    symbolSearchLoading,

    // chart (P1)
    chartDrawerVisible,
    chartSymbol,
    chartTimeframe,
    chartBars,
    chartLoading,
    chartError,

    // column config (P1)
    columnConfig,

    // advanced filter (P1)
    filterChangePctMin,
    filterChangePctMax,
    filterVolumeMin,
    filterVolumeMax,
    filterHasOpenInterest,
    hasAdvancedFilters,

    // actions
    fetchSources,
    switchSource,
    fetchQuotes,
    addSymbol,
    removeSymbol,
    searchSymbols,
    setSort,
    setAutoRefresh,
    setRefreshInterval,
    startAutoRefresh,
    cleanup,
    openChart,
    closeChart,
    fetchChartData,
    setChartTimeframe,
    setColumnConfig,
    resetColumnConfig,
    clearAdvancedFilters,
  }
})
