/**
 * 实时数据 Pinia Store
 *
 * Manages data-source selection, quote data, custom symbols,
 * search/filter/sort state, and auto-refresh lifecycle.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import i18n from '@/i18n'
import { quoteApi } from '@/api/quote'
import type {
  DataSourceInfo,
  KlineBar,
  QuoteField,
  QuoteTick,
  SymbolItem,
} from '@/api/quote'

function tt(key: string): string {
  return i18n.global.t(key)
}

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

type ColumnDef = QuoteField

// Default columns. Labels are computed lazily via tt() so locale switches
// reflect immediately when the store rebuilds columnConfig from defaults.
function buildDefaultColumns(): ColumnDef[] {
  return [
    { prop: 'symbol', label: tt('quote.colSymbol'), visible: true, always_show: true },
    { prop: 'name', label: tt('quote.colName'), visible: true },
    { prop: 'category', label: tt('quote.colCategory'), visible: true },
    { prop: 'last_price', label: tt('quote.colLastPrice'), visible: true },
    { prop: 'bid_price', label: tt('quote.colBidPrice'), visible: true },
    { prop: 'ask_price', label: tt('quote.colAskPrice'), visible: true },
    { prop: 'update_time', label: tt('quote.colUpdateTime'), visible: true },
  ]
}

function cloneColumns(columns: ColumnDef[]): ColumnDef[] {
  return columns.map((column) => ({ ...column }))
}

function getColumnStorageKey(source: string): string {
  return `columnConfig_${source}`
}

function mergeColumnConfig(baseColumns: ColumnDef[], savedColumns: ColumnDef[]): ColumnDef[] {
  if (!savedColumns.length) {
    return cloneColumns(baseColumns)
  }

  const baseMap = new Map(baseColumns.map((column) => [column.prop, column]))
  const merged: ColumnDef[] = []

  for (const saved of savedColumns) {
    const base = baseMap.get(saved.prop)
    if (!base) {
      continue
    }
    merged.push({ ...base, visible: saved.visible })
    baseMap.delete(saved.prop)
  }

  for (const column of baseColumns) {
    if (baseMap.has(column.prop)) {
      merged.push({ ...column })
    }
  }

  return merged
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
  const availableCategories = ref<string[]>([])
  const sortField = ref<string>(lsGet(`sort_field_${activeSource.value}`, ''))
  const sortOrder = ref<'asc' | 'desc'>(lsGet(`sort_order_${activeSource.value}`, 'asc'))

  // ---- custom symbols ----
  const customSymbols = ref<string[]>([])
  const dismissedWorkspaceQuoteKeys = ref<Set<string>>(new Set())

  // ---- auto refresh ----
  const autoRefresh = ref<boolean>(lsGet('autoRefresh', false))
  const refreshInterval = ref<number>(lsGet('refreshInterval', 60))
  let refreshTimer: ReturnType<typeof setInterval> | null = null
  const pendingQuoteSources = new Set<string>()
  let latestQuoteRequest = 0
  let displayedSource = ''

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
  const quoteFields = ref<ColumnDef[]>(cloneColumns(buildDefaultColumns()))
  const columnConfig = ref<ColumnDef[]>(cloneColumns(buildDefaultColumns()))

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
    let list = ticks.value.filter((tick) => !dismissedWorkspaceQuoteKeys.value.has(tick.quote_key))

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
    const set = new Set<string>(availableCategories.value)
    for (const t of ticks.value) {
      if (t.category) set.add(t.category)
    }
    return Array.from(set).sort((left, right) => left.localeCompare(right, 'zh-Hans-CN'))
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

    // Clear the previous source immediately. The symbol metadata request below
    // repopulates code/name rows before the slower gateway quote snapshot arrives.
    ticks.value = []
    availableCategories.value = []
    updateTime.value = null
    displayedSource = ''
    await fetchQuotes()
  }

  async function fetchQuotes() {
    const source = activeSource.value
    if (!source || pendingQuoteSources.has(source)) return

    const requestId = ++latestQuoteRequest
    pendingQuoteSources.add(source)
    quotesLoading.value = true
    quotesError.value = null

    // Do not wait for the slower quote gateway before showing the locally
    // available subscription/workspace symbol metadata.
    void fetchSymbolsMeta(source, true)

    try {
      let res = await quoteApi.getQuotes(source)
      const shouldRetry =
        res.ticks.length > 0 &&
        res.ticks.every(
          (t) => t.last_price == null && t.bid_price == null && t.ask_price == null,
        )
      if (shouldRetry) {
        await new Promise((resolve) => window.setTimeout(resolve, 1200))
        res = await quoteApi.getQuotes(source)
      }

      // A response for an old source must never overwrite the source the user
      // has just selected. This is especially important for CTP/IB/MT5 where
      // a gateway snapshot can take several seconds.
      if (requestId !== latestQuoteRequest || source !== activeSource.value) return

      // The quote endpoint can legitimately return a source-side timestamp
      // that is stale (or unchanged across a polling cycle). The monitor's
      // "更新时间" represents the last successful client refresh, so every
      // visible row and the page-level status use the time this response was
      // received.
      const refreshedAt = new Date().toISOString()
      quoteFields.value = cloneColumns(buildDefaultColumns())
      columnConfig.value = mergeColumnConfig(
        quoteFields.value,
        lsGet(getColumnStorageKey(source), [] as ColumnDef[]),
      )
      ticks.value = res.ticks.map((tick) => ({ ...tick, update_time: refreshedAt }))
      displayedSource = source
      dismissedWorkspaceQuoteKeys.value = new Set()
      updateTime.value = refreshedAt
      refreshMode.value = res.refresh_mode
    } catch (e: unknown) {
      if (requestId === latestQuoteRequest && source === activeSource.value) {
        quotesError.value = e instanceof Error ? e.message : tt('quote.errorQuotesFailed')
      }
    } finally {
      pendingQuoteSources.delete(source)
      quotesLoading.value = pendingQuoteSources.has(activeSource.value)
    }
  }

  function buildPlaceholderTicks(source: string, symbols: SymbolItem[]): QuoteTick[] {
    const runtime = activeSourceInfo.value?.workspaces ?? []
    const sourceLabel = activeSourceInfo.value?.source_label || source
    const customSet = new Set(customSymbols.value)
    const merged = new Map<string, SymbolItem>()
    for (const item of symbols) {
      if (item.symbol) merged.set(item.symbol, item)
    }

    return Array.from(merged.values()).map((item) => {
      const workspaceRuns = runtime.filter((run) => run.symbols.includes(item.symbol))
      const origins: string[] = []
      if (customSet.has(item.symbol) || workspaceRuns.length === 0) origins.push('subscription')
      if (workspaceRuns.length > 0) origins.push('workspace')
      const gatewayKey = workspaceRuns[0]?.gateway_key || ''
      const workspaceIds = workspaceRuns.map((run) => run.workspace_id)
      const workspaceNames = workspaceRuns.map((run) => run.workspace_name)
      return {
        source,
        source_label: sourceLabel,
        symbol: item.symbol,
        name: item.name || item.symbol,
        exchange: item.exchange || '',
        category: item.category || '',
        last_price: null,
        change: null,
        change_pct: null,
        bid_price: null,
        ask_price: null,
        high_price: null,
        low_price: null,
        open_price: null,
        prev_close: null,
        volume: null,
        turnover: null,
        open_interest: null,
        update_time: null,
        status: 'loading',
        error_message: null,
        quote_key: `${source}:${gatewayKey || 'subscription'}:${item.symbol}`,
        gateway_key: gatewayKey,
        origins,
        workspace_ids: workspaceIds,
        workspace_names: workspaceNames,
      }
    })
  }

  async function fetchSymbolsMeta(source = activeSource.value, seedRows = false) {
    if (!source) return
    try {
      const res = await quoteApi.getSymbols(source)
      if (source !== activeSource.value) return
      customSymbols.value = res.custom_symbols
      availableCategories.value = Array.from(new Set(
        (Array.isArray(res.categories) ? res.categories : [])
          .map((category) => String(category || '').trim())
          .filter(Boolean),
      )).sort((left, right) => left.localeCompare(right, 'zh-Hans-CN'))
      if (seedRows && (displayedSource !== source || ticks.value.length === 0)) {
        const customItems = res.custom_symbols.map((symbol) => ({
          symbol,
          name: symbol,
          exchange: '',
          category: '',
        }))
        ticks.value = buildPlaceholderTicks(source, [
          ...res.default_symbols,
          ...customItems,
          ...res.running_symbols,
        ])
        displayedSource = source
      }
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

  async function removeSubscription(symbol: string) {
    if (!activeSource.value) return
    const res = await quoteApi.removeSubscriptions(activeSource.value, [symbol])
    customSymbols.value = res.symbols
    await fetchQuotes()
  }

  function dismissWorkspaceQuote(quoteKey: string) {
    if (!quoteKey) return
    dismissedWorkspaceQuoteKeys.value = new Set([
      ...dismissedWorkspaceQuoteKeys.value,
      quoteKey,
    ])
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
      chartError.value = e instanceof Error ? e.message : tt('quote.errorChartFailed')
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
    columnConfig.value = mergeColumnConfig(quoteFields.value, config)
    lsSet(getColumnStorageKey(activeSource.value), columnConfig.value)
  }

  function resetColumnConfig() {
    columnConfig.value = cloneColumns(quoteFields.value)
    lsSet(getColumnStorageKey(activeSource.value), columnConfig.value)
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
    availableCategories,
    sortField,
    sortOrder,
    customSymbols,
    dismissedWorkspaceQuoteKeys,
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
    removeSubscription,
    dismissWorkspaceQuote,
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
}, {
  persist: {
    storage: localStorage,
    paths: ['activeSource', 'autoRefresh', 'refreshInterval', 'chartTimeframe'],
  },
})
