<template>
  <div
    class="quote-page"
    data-test="quote-page"
  >
    <section class="quote-hero">
      <div class="quote-hero-copy">
        <span>{{ t('quote.heroKicker') }}</span>
        <div class="quote-title-line">
          <h1>{{ t('quote.headerTitle') }}</h1>
          <div
            class="quote-source-tabs quote-source-tabs--inline"
            role="tablist"
            :aria-label="t('quote.sourcePanelTitle')"
          >
            <button
              v-for="src in store.sources"
              :key="src.source"
              class="source-tab"
              :class="{
                'source-tab--active': src.source === store.activeSource,
                'source-tab--available': src.status === 'available',
                'source-tab--disconnected': src.status === 'not_connected',
                'source-tab--unavailable': src.status === 'unavailable' || src.status === 'not_configured',
              }"
              type="button"
              role="tab"
              :aria-selected="src.source === store.activeSource"
              @click="handleSourceClick(src)"
            >
              <span class="source-tab__label">{{ src.source_label }}</span>
              <span class="source-tab__dot" />
            </button>
          </div>
          <el-popover
            placement="bottom-end"
            :width="360"
            trigger="click"
          >
            <template #reference>
              <el-button
                size="small"
                class="quote-source-status-button"
              >
                <el-icon aria-hidden="true"><Connection /></el-icon>
                {{ t('quote.sourceStatusButton') }}
              </el-button>
            </template>
            <div class="quote-source-status-popover">
              <p>{{ t('quote.sourcePanelDesc') }}</p>
              <template v-if="store.activeSourceInfo">
                <strong>{{ store.activeSourceInfo.source_label }}</strong>
                <span>{{ sourceRuntimeSummary(store.activeSourceInfo) }}</span>
              </template>
              <div
                v-if="activeRuntimeWorkspaces.length > 0"
                class="quote-runtime-monitor__runs"
              >
                <div
                  v-for="run in activeRuntimeWorkspaces"
                  :key="`${run.workspace_id}-${run.gateway_key}`"
                  class="quote-runtime-monitor__run"
                >
                  <strong>{{ run.workspace_name }}</strong>
                  <span>{{ t('quote.runtimeSymbols', { count: run.symbol_count }) }}</span>
                  <small>{{ runtimeSymbolsPreview(run.symbols) }}</small>
                </div>
              </div>
              <span v-else>{{ t('quote.runtimeNoWorkspace') }}</span>
            </div>
          </el-popover>
        </div>
        <p>{{ t('quote.headerDesc') }}</p>
      </div>

      <div class="quote-hero-status">
        <el-tag
          size="small"
          :type="refreshModeTag"
          effect="plain"
        >
          {{ refreshModeText }}
        </el-tag>
        <span
          v-if="store.updateTime"
          class="quote-update-time"
          :class="{ 'is-stale': isDataStale }"
        >
          {{ formatTime(store.updateTime) }}
          <el-tooltip
            v-if="isDataStale"
            :content="t('quote.dataStaleTip')"
            placement="top"
          >
            <el-icon aria-hidden="true">
              <WarningFilled />
            </el-icon>
          </el-tooltip>
        </span>
        <span
          v-if="store.quotesLoading"
          class="quote-refreshing"
        >
          <el-icon
            class="is-loading"
            aria-hidden="true"
          >
            <Loading />
          </el-icon>
          {{ t('quote.refreshing') }}
        </span>
      </div>

      <div class="quote-hero-stats">
        <article
          v-for="item in quoteStats"
          :key="item.label"
        >
          <span>{{ item.label }}</span>
          <strong :class="item.tone">{{ item.value }}</strong>
        </article>
      </div>

    </section>

    <!-- Initial load: do not show an empty quote state while the query is pending. -->
    <template v-if="isInitialQuoteLoading">
      <div class="quote-loading-state">
        <div
          class="quote-querying"
          data-test="quote-initial-querying"
          role="status"
          aria-live="polite"
        >
          <el-icon
            class="is-loading"
            aria-hidden="true"
          >
            <Loading />
          </el-icon>
          <span>{{ t('quote.querying') }}</span>
          <span
            class="quote-querying__dots"
            aria-hidden="true"
          ><i /><i /><i /></span>
        </div>
        <DataTableSkeleton :label="t('quote.querying')" />
      </div>
    </template>

    <!-- Source unavailable / disconnected state -->
    <template v-else-if="store.activeSourceInfo && store.activeSourceInfo.status !== 'available'">
      <el-card class="quote-state-card">
        <el-empty :description="sourceStatusText">
          <el-button
            v-if="store.activeSourceInfo.status === 'not_connected'"
            type="primary"
            @click="$router.push('/gateways')"
          >
            {{ t('quote.btnGoConnectGateway') }}
          </el-button>
        </el-empty>
      </el-card>
    </template>

    <!-- Main content (only when source is available) -->
    <template v-else>
      <!-- Toolbar -->
      <section class="quote-control-panel">
        <div class="quote-section-heading">
          <div>
            <span>{{ t('quote.controlsTitle') }}</span>
            <p>{{ t('quote.controlsDesc') }}</p>
          </div>
        </div>
        <div class="quote-toolbar">
          <div class="quote-filter-grid">
            <!-- Search -->
            <el-input
              v-model="store.searchKeyword"
              :placeholder="t('quote.searchPh')"
              :prefix-icon="Search"
              clearable
              size="default"
            />
            <!-- Category filter -->
            <el-select
              v-model="store.filterCategory"
              :placeholder="t('quote.filterAllCategory')"
              clearable
              size="default"
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
              :placeholder="t('quote.filterTrendPh')"
              clearable
              size="default"
            >
              <el-option
                :label="t('quote.filterTrendUp')"
                value="up"
              />
              <el-option
                :label="t('quote.filterTrendDown')"
                value="down"
              />
              <el-option
                :label="t('quote.filterTrendFlat')"
                value="flat"
              />
            </el-select>
            <!-- Custom only -->
            <el-checkbox
              v-model="store.filterCustomOnly"
              :label="t('quote.filterCustomOnly')"
              class="quote-checkbox"
            />
            <!-- Advanced filter (P1) -->
            <el-popover
              placement="bottom"
              :width="320"
              trigger="click"
            >
              <template #reference>
                <el-button
                  size="default"
                  :type="store.hasAdvancedFilters ? 'primary' : ''"
                >
                  <el-icon aria-hidden="true"><Filter /></el-icon> {{ t('quote.advancedFilter') }}
                  <el-badge
                    v-if="store.hasAdvancedFilters"
                    is-dot
                    class="ml-1"
                  />
                </el-button>
              </template>
              <div class="quote-advanced-popover">
                <div>
                  <span>{{ t('quote.rangeChangePct') }}</span>
                  <div class="quote-range-row">
                    <el-input-number
                      v-model="store.filterChangePctMin"
                      :controls="false"
                      :placeholder="t('quote.rangeMin')"
                      size="small"
                    />
                    <span>~</span>
                    <el-input-number
                      v-model="store.filterChangePctMax"
                      :controls="false"
                      :placeholder="t('quote.rangeMax')"
                      size="small"
                    />
                  </div>
                </div>
                <div>
                  <span>{{ t('quote.rangeVolume') }}</span>
                  <div class="quote-range-row">
                    <el-input-number
                      v-model="store.filterVolumeMin"
                      :controls="false"
                      :placeholder="t('quote.rangeMin')"
                      size="small"
                    />
                    <span>~</span>
                    <el-input-number
                      v-model="store.filterVolumeMax"
                      :controls="false"
                      :placeholder="t('quote.rangeMax')"
                      size="small"
                    />
                  </div>
                </div>
                <div>
                  <el-checkbox
                    v-model="store.filterHasOpenInterest"
                    :label="t('quote.filterHasOI')"
                  />
                </div>
                <div class="flex justify-end">
                  <el-button
                    size="small"
                    @click="store.clearAdvancedFilters()"
                  >
                    {{ t('quote.btnReset') }}
                  </el-button>
                </div>
              </div>
            </el-popover>
          </div>

          <div class="quote-action-row">
            <!-- Auto refresh toggle -->
            <span class="quote-auto-refresh">
              <el-tooltip :content="t('quote.autoRefreshTooltip')">
                <el-switch
                  v-model="autoRefreshLocal"
                  active-text=""
                  inactive-text=""
                  size="small"
                  :aria-label="t('quote.autoRefreshTooltip')"
                  @change="(v: boolean | string | number) => store.setAutoRefresh(Boolean(v))"
                />
              </el-tooltip>
            </span>
            <el-select
              v-if="store.autoRefresh"
              v-model="refreshIntervalLocal"
              size="small"
              class="quote-interval-select"
              :aria-label="t('quote.autoRefreshInterval')"
              @change="(v: number) => store.setRefreshInterval(v)"
            >
              <el-option
                :label="'1s'"
                :value="1"
              />
              <el-option
                :label="'3s'"
                :value="3"
              />
              <el-option
                :label="'5s'"
                :value="5"
              />
              <el-option
                :label="'10s'"
                :value="10"
              />
              <el-option
                :label="'30s'"
                :value="30"
              />
              <el-option
                :label="'60s'"
                :value="60"
              />
            </el-select>
            <!-- Manual refresh -->
            <el-button
              :loading="store.quotesLoading"
              size="default"
              :aria-label="t('common.refresh')"
              @click="refreshMonitoring()"
            >
              <el-icon aria-hidden="true">
                <Refresh />
              </el-icon>
            </el-button>
            <!-- Column config (P1) -->
            <el-tooltip :content="t('quote.columnSettingsTooltip')">
              <el-button
                size="default"
                @click="showColumnDialog = true"
              >
                <el-icon aria-hidden="true">
                  <Setting />
                </el-icon>
              </el-button>
            </el-tooltip>
            <!-- Add symbol -->
            <el-button
              type="primary"
              size="default"
              @click="showAddDialog = true"
            >
              <el-icon aria-hidden="true">
                <Plus />
              </el-icon>
              {{ t('quote.btnAddSymbol') }}
            </el-button>
          </div>
        </div>
      </section>

      <!-- Error state -->
      <el-card
        v-if="store.quotesError"
        class="quote-state-card"
      >
        <el-empty :description="t('quote.errorEmptyDesc')">
          <template #description>
            <p class="quote-error-text">
              {{ store.quotesError }}
            </p>
          </template>
          <el-button
            type="primary"
            @click="store.fetchQuotes()"
          >
            {{ t('quote.btnRetry') }}
          </el-button>
        </el-empty>
      </el-card>

      <!-- Empty state -->
      <el-card
        v-else-if="store.filteredTicks.length === 0 && store.ticks.length === 0"
        class="quote-state-card"
      >
        <el-empty :description="t('quote.emptyQuotes')">
          <el-button
            type="primary"
            @click="showAddDialog = true"
          >
            {{ t('quote.btnAddSymbol') }}
          </el-button>
        </el-empty>
      </el-card>

      <!-- Quote Table -->
      <section
        v-else
        class="quote-table-panel"
      >
        <div class="quote-section-heading quote-table-heading">
          <div>
            <span>{{ t('quote.tableTitle') }}</span>
            <p>{{ t('quote.tableDesc') }}</p>
          </div>
          <el-tag
            size="small"
            effect="plain"
          >
            {{ t('quote.countDisplay', { filtered: store.filteredTicks.length, total: store.ticks.length }) }}
          </el-tag>
        </div>
        <ResponsiveDataGrid :mobile-label="t('quote.tableTitle')">
          <template #desktop>
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
              <el-table-column
                type="index"
                label="#"
                width="50"
                fixed="left"
              />
              <!-- Dynamic columns based on columnConfig -->
              <template
                v-for="col in visibleColumns"
                :key="col.prop"
              >
                <el-table-column
                  v-if="col.prop === 'symbol'"
                  prop="symbol"
                  :label="col.label"
                  width="160"
                  fixed="left"
                  sortable="custom"
                  show-overflow-tooltip
                >
                  <template #default="{ row }">
                    <span class="quote-symbol-cell">
                      <strong>{{ row.symbol }}</strong>
                      <small v-if="quoteOriginText(row)">{{ quoteOriginText(row) }}</small>
                    </span>
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
                    <span :class="priceClass(row)">{{ fmtPrice(row.last_price, row) }}</span>
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
                    <span :class="changeClass(row.change)">{{ fmtChange(row.change, row) }}</span>
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
                    <span class="quote-time-cell">{{ formatTime(row.update_time) }}</span>
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
                  <template #default="{ row }">
                    {{ fmtVol(row[col.prop]) }}
                  </template>
                </el-table-column>
                <el-table-column
                  v-else
                  :prop="col.prop"
                  :label="col.label"
                  width="90"
                  sortable="custom"
                  align="right"
                >
                  <template #default="{ row }">
                    {{ fmtPrice(row[col.prop], row) }}
                  </template>
                </el-table-column>
              </template>
              <el-table-column
                :label="t('quote.colOpenChart')"
                width="64"
                fixed="right"
                align="center"
              >
                <template #default="{ row }">
                  <el-tooltip :content="t('quote.btnOpenChart')">
                    <el-button
                      type="primary"
                      size="small"
                      link
                      :aria-label="t('quote.btnOpenChart')"
                      @click.stop="store.openChart(row.symbol)"
                    >
                      <el-icon aria-hidden="true"><DataLine /></el-icon>
                    </el-button>
                  </el-tooltip>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('quote.colRemoveSubscription')"
                width="64"
                fixed="right"
                align="center"
              >
                <template #default="{ row }">
                  <el-popconfirm
                    :title="removeSubscriptionPrompt(row)"
                    @confirm="removeQuoteSubscription(row)"
                  >
                    <template #reference>
                      <el-button
                        type="danger"
                        size="small"
                        link
                        :aria-label="t('quote.btnRemoveSubscription')"
                        @click.stop
                      >
                        <el-icon aria-hidden="true"><Delete /></el-icon>
                      </el-button>
                    </template>
                  </el-popconfirm>
                </template>
              </el-table-column>
            </el-table>
          </template>

          <template #mobile>
            <ol class="quote-mobile-list">
              <li
                v-for="row in store.filteredTicks"
                :key="row.quote_key || row.symbol"
              >
                <article
                  class="quote-mobile-card"
                  :aria-label="`${row.symbol} ${row.name || ''}`"
                >
                  <button
                    type="button"
                    class="quote-mobile-card__overview"
                    :aria-label="t('quote.chartDrawerTitleTpl', { symbol: row.symbol })"
                    @click="handleRowClick(row)"
                  >
                    <span class="quote-mobile-card__identity">
                      <strong>{{ row.symbol }}</strong>
                      <span>{{ quoteOriginText(row) || row.name || row.category || '--' }}</span>
                    </span>
                    <span :class="priceClass(row)">{{ fmtPrice(row.last_price, row) }}</span>
                  </button>

                  <dl class="quote-mobile-card__metrics">
                    <div>
                      <dt>{{ t('quote.colChangePct') }}</dt>
                      <dd :class="changeClass(row.change_pct)">
                        {{ fmtPct(row.change_pct) }}
                      </dd>
                    </div>
                    <div>
                      <dt>{{ t('quote.colChange') }}</dt>
                      <dd :class="changeClass(row.change)">
                        {{ fmtChange(row.change, row) }}
                      </dd>
                    </div>
                    <div>
                      <dt>{{ t('quote.colCategory') }}</dt>
                      <dd>{{ row.category || '--' }}</dd>
                    </div>
                    <div>
                      <dt>{{ t('quote.colUpdateTime') }}</dt>
                      <dd>{{ formatTime(row.update_time) }}</dd>
                    </div>
                  </dl>

                  <div class="quote-mobile-card__actions">
                    <el-button
                      type="primary"
                      size="small"
                      :aria-label="t('quote.chartDrawerTitleTpl', { symbol: row.symbol })"
                      @click="store.openChart(row.symbol)"
                    >
                      <el-icon aria-hidden="true">
                        <DataLine />
                      </el-icon>
                    </el-button>
                    <el-popconfirm
                      :title="removeSubscriptionPrompt(row)"
                      @confirm="removeQuoteSubscription(row)"
                    >
                      <template #reference>
                        <el-button
                          type="danger"
                          size="small"
                          :aria-label="t('quote.btnRemoveSubscription')"
                        >
                          <el-icon aria-hidden="true">
                            <Delete />
                          </el-icon>
                        </el-button>
                      </template>
                    </el-popconfirm>
                  </div>
                </article>
              </li>
            </ol>
          </template>
        </ResponsiveDataGrid>
        <!-- Table footer -->
        <div class="quote-table-footer">
          <span>
            {{ t('quote.countDisplay', { filtered: store.filteredTicks.length, total: store.ticks.length }) }}
            <template v-if="store.hasAdvancedFilters">
              <el-tag
                size="small"
                type="warning"
                effect="plain"
                class="ml-2"
              >{{ t('quote.advancedFilterEnabled') }}</el-tag>
            </template>
          </span>
          <span
            v-if="store.quotesLoading"
            class="quote-refreshing"
          >{{ t('quote.refreshingDot') }}</span>
        </div>
      </section>
    </template>

    <!-- Add Symbol Dialog -->
    <el-dialog
      v-model="showAddDialog"
      :title="t('quote.addDialogTitle')"
      width="480px"
      destroy-on-close
    >
      <el-input
        v-model="addKeyword"
        :placeholder="t('quote.addInputPh')"
        clearable
        @input="handleAddSearch"
      />
      <div
        v-if="store.symbolSearchLoading"
        class="quote-dialog-loading"
      >
        <el-icon
          class="is-loading"
          aria-hidden="true"
        >
          <Loading />
        </el-icon> {{ t('quote.searching') }}
      </div>
      <div
        v-else-if="store.symbolSearchResults.length > 0"
        class="quote-symbol-results"
      >
        <div
          v-for="item in store.symbolSearchResults"
          :key="item.symbol"
          class="quote-symbol-result"
          @click="handleAddSymbol(item.symbol)"
        >
          <div>
            <span>{{ item.symbol }}</span>
            <small>{{ item.name }}</small>
          </div>
          <el-tag
            size="small"
            type="info"
            effect="plain"
          >
            {{ item.exchange }}
          </el-tag>
        </div>
      </div>
      <div
        v-else-if="addKeyword && !store.symbolSearchLoading"
        class="quote-dialog-empty"
      >
        {{ t('quote.notFound') }}
      </div>
      <el-divider />
      <div class="quote-direct-add">
        <el-input
          v-model="addSymbolDirect"
          :placeholder="t('quote.addDirectPh')"
          @keyup.enter="handleDirectAdd"
        />
        <el-button
          type="primary"
          :disabled="!addSymbolDirect"
          @click="handleDirectAdd"
        >
          {{ t('quote.btnAdd') }}
        </el-button>
      </div>
    </el-dialog>

    <!-- Column Config Dialog (P1) -->
    <el-dialog
      v-model="showColumnDialog"
      :title="t('quote.columnDialogTitle')"
      width="420px"
      destroy-on-close
    >
      <div class="quote-column-hint">
        {{ t('quote.columnDialogHint') }}
      </div>
      <div class="quote-column-list">
        <div
          v-for="(col, idx) in columnConfigLocal"
          :key="col.prop"
          class="quote-column-row"
          draggable="true"
          @dragstart="onColDragStart(idx)"
          @dragover.prevent
          @drop="onColDrop(idx)"
        >
          <el-icon class="quote-column-drag" aria-hidden="true">
            <Rank />
          </el-icon>
          <el-checkbox
            v-model="col.visible"
            :label="col.label"
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="handleResetColumns">
          {{ t('quote.btnRestoreDefault') }}
        </el-button>
        <el-button
          type="primary"
          @click="handleSaveColumns"
        >
          {{ t('quote.btnSave') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Chart Drawer (P1) -->
    <el-drawer
      v-model="store.chartDrawerVisible"
      :title="t('quote.chartDrawerTitleTpl', { symbol: store.chartSymbol })"
      class="quote-chart-drawer"
      direction="btt"
      size="50%"
      :destroy-on-close="true"
      @close="store.closeChart()"
    >
      <!-- Timeframe selector -->
      <div class="quote-chart-toolbar">
        <span>{{ t('quote.timeframeLabel') }}</span>
        <el-radio-group
          :model-value="store.chartTimeframe"
          size="small"
          @change="(v: boolean | string | number | undefined) => store.setChartTimeframe(String(v))"
        >
          <el-radio-button label="M1">
            {{ t('quote.tf1m') }}
          </el-radio-button>
          <el-radio-button label="M5">
            {{ t('quote.tf5m') }}
          </el-radio-button>
          <el-radio-button label="M15">
            {{ t('quote.tf15m') }}
          </el-radio-button>
          <el-radio-button label="M30">
            {{ t('quote.tf30m') }}
          </el-radio-button>
          <el-radio-button label="H1">
            {{ t('quote.tf1h') }}
          </el-radio-button>
          <el-radio-button label="H4">
            {{ t('quote.tf4h') }}
          </el-radio-button>
          <el-radio-button label="D1">
            {{ t('quote.tfDay') }}
          </el-radio-button>
        </el-radio-group>
        <el-button
          size="small"
          :loading="store.chartLoading"
          @click="store.fetchChartData()"
        >
          <el-icon aria-hidden="true">
            <Refresh />
          </el-icon>
        </el-button>
      </div>
      <!-- Chart content -->
      <div
        v-if="store.chartLoading"
        class="quote-chart-state"
      >
        <el-icon
          class="is-loading"
          aria-hidden="true"
        >
          <Loading />
        </el-icon>
      </div>
      <div
        v-else-if="store.chartError"
        class="quote-chart-state"
      >
        <p class="quote-error-text">
          {{ store.chartError }}
        </p>
        <el-button
          type="primary"
          size="small"
          @click="store.fetchChartData()"
        >
          {{ t('quote.btnRetry') }}
        </el-button>
      </div>
      <div
        v-else-if="store.chartBars.length === 0"
        class="quote-chart-state"
      >
        <el-empty :description="t('quote.chartEmpty')" />
      </div>
      <div
        v-else
        ref="chartContainerRef"
        class="quote-chart-container"
        data-test="quote-chart"
      />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import type { Sort } from 'element-plus'
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
  Connection,
  WarningFilled,
} from '@element-plus/icons-vue'
import { useQuoteStore } from '@/stores/quote'
import type { DataSourceInfo, QuoteTick } from '@/api/quote'
import ResponsiveDataGrid from '@/components/common/ResponsiveDataGrid.vue'
import DataTableSkeleton from '@/components/common/DataTableSkeleton.vue'
import { formatQuoteChange, formatQuotePrice } from '@/utils/quoteFormat'
import { CANDLE_DOWN_COLOR, CANDLE_ITEM_STYLE, CANDLE_UP_COLOR } from '@/constants/chartColors'

const { t } = useI18n()
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
    ElMessage.success(t('quote.msgAdded', { symbol }))
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
    ElMessage.warning(src.status_message || t('quote.sourceUnavailableShort'))
    return
  }
  store.switchSource(src.source)
}

function sourceRuntimeSummary(src: DataSourceInfo) {
  return t('quote.runtimeSummary', {
    gateways: src.gateway_count,
    workspaces: src.workspace_count,
    symbols: src.running_symbol_count,
  })
}

const activeRuntimeWorkspaces = computed(() => store.activeSourceInfo?.workspaces ?? [])

function runtimeSymbolsPreview(symbols: string[]) {
  const visible = symbols.slice(0, 6).join(' · ')
  return symbols.length > 6 ? `${visible} +${symbols.length - 6}` : visible
}

function quoteOriginText(row: QuoteTick) {
  const origins: string[] = []
  const rowOrigins = Array.isArray(row.origins) ? row.origins : []
  const workspaceNames = Array.isArray(row.workspace_names) ? row.workspace_names : []
  if (rowOrigins.includes('subscription')) origins.push(t('quote.originSubscription'))
  if (workspaceNames.length > 0) {
    origins.push(t('quote.originWorkspace', { names: workspaceNames.join('、') }))
  }
  return origins.join(' · ')
}

async function refreshMonitoring() {
  await store.fetchSources()
  if (store.activeSourceInfo?.status === 'available') {
    await store.fetchQuotes()
  }
}

// ---- source status text ----
const sourceStatusText = computed(() => {
  const info = store.activeSourceInfo
  if (!info) return ''
  switch (info.status) {
    case 'not_connected':
      return info.status_message || t('quote.sourceNotConnected')
    case 'not_configured':
      return t('quote.sourceNotConfigured')
    case 'unavailable':
      return info.status_message || t('quote.sourceUnavailable')
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
    case 'push': return t('quote.refreshModePush')
    case 'polling': return store.autoRefresh ? t('quote.refreshModePolling', { seconds: store.refreshInterval }) : t('quote.refreshModeManual')
    default: return t('quote.refreshModeManual')
  }
})

const isInitialQuoteLoading = computed(() => (
  (store.sourcesLoading && store.sources.length === 0) ||
  (store.quotesLoading && store.ticks.length === 0)
))

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

const quoteStats = computed(() => {
  const availableSources = store.sources.filter((source) => source.status === 'available').length
  return [
    {
      label: t('quote.statSourceHealth'),
      value: `${availableSources}/${store.sources.length || 0}`,
      tone: availableSources > 0 ? 'is-positive' : '',
    },
    {
      label: t('quote.statActiveSource'),
      value: store.activeSourceInfo?.source_label || store.activeSource || '--',
      tone: '',
    },
    {
      label: t('quote.statVisibleSymbols'),
      value: String(store.filteredTicks.length),
      tone: '',
    },
    {
      label: t('quote.statCustomSymbols'),
      value: String(store.customSymbols.length),
      tone: store.customSymbols.length > 0 ? 'is-positive' : '',
    },
  ]
})

// ---- table sort ----
const tableSortProp = computed<Sort | undefined>(() => {
  if (!store.sortField) return undefined
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
const prevTickMap: Map<string, number> = new Map()
let sourceRefreshTimer: ReturnType<typeof setInterval> | null = null

watch(
  () => store.ticks,
  (newTicks) => {
    const updated = new Set<string>()
    for (const t of newTicks) {
      const key = t.quote_key || t.symbol
      const prev = prevTickMap.get(key)
      if (prev !== undefined && t.last_price !== null && prev !== t.last_price) {
        updated.add(key)
      }
      if (t.last_price != null) prevTickMap.set(key, t.last_price)
    }
    if (updated.size > 0) {
      flashSymbols.value = updated
      setTimeout(() => { flashSymbols.value = new Set() }, 600)
    }
  },
  { deep: true },
)

function rowClassName({ row }: { row: QuoteTick }) {
  return flashSymbols.value.has(row.quote_key || row.symbol) ? 'tick-flash' : ''
}

function isWorkspaceQuote(row: QuoteTick) {
  return Array.isArray(row.origins) && row.origins.includes('workspace')
}

function removeSubscriptionPrompt(row: QuoteTick) {
  return isWorkspaceQuote(row)
    ? t('quote.confirmHideWorkspaceSubscription')
    : t('quote.confirmRemoveSubscription')
}

async function removeQuoteSubscription(row: QuoteTick) {
  if (isWorkspaceQuote(row)) {
    store.dismissWorkspaceQuote(row.quote_key)
    return
  }
  await store.removeSubscription(row.symbol)
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
function fmtPrice(v: number | null, row?: QuoteTick): string {
  return formatQuotePrice(v, {
    source: row?.source,
    symbol: row?.symbol,
  })
}

function fmtChange(v: number | null, row?: QuoteTick): string {
  return formatQuoteChange(v, {
    source: row?.source,
    symbol: row?.symbol,
  })
}

function fmtPct(v: number | null): string {
  if (v == null) return '--'
  return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'
}

function fmtVol(v: number | null): string {
  if (v == null) return '--'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + t('quote.unitYi')
  if (v >= 1e4) return (v / 1e4).toFixed(2) + t('quote.unitWan')
  return String(Math.round(v))
}

function formatTime(iso: string | null): string {
  if (!iso) return '--'
  const text = iso.trim()
  if (/^\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(text)) {
    return text.slice(0, 8)
  }
  const d = new Date(text)
  if (Number.isNaN(d.getTime())) {
    return text
  }
  return d.toLocaleTimeString('zh-CN', { hour12: false })
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
  const palette = chartPalette()
  // volume bar color: up=red, down=green
  const volColors = bars.map((b) => (b.close >= b.open ? CANDLE_UP_COLOR : CANDLE_DOWN_COLOR))

  return {
    animation: false,
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
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
        axisLine: { onZero: false, lineStyle: { color: palette.border } },
        axisLabel: { color: palette.secondary, hideOverlap: true },
        splitLine: { show: false },
      },
      {
        type: 'category',
        gridIndex: 1,
        data: dates,
        boundaryGap: false,
        axisLine: { onZero: false, lineStyle: { color: palette.border } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
      },
    ],
    yAxis: [
      {
        scale: true,
        axisLabel: { color: palette.secondary },
        splitLine: { lineStyle: { color: palette.grid, type: 'dashed' } },
        splitArea: { show: false },
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: palette.grid, type: 'dashed' } },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 60, end: 100 },
      { show: true, xAxisIndex: [0, 1], type: 'slider', top: '93%', start: 60, end: 100 },
    ],
    series: [
      {
        name: t('charts.klineSeries'),
        type: 'candlestick',
        data: ohlc,
        itemStyle: CANDLE_ITEM_STYLE,
      },
      {
        name: t('charts.klineVolume'),
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes.map((v, i) => ({ value: v, itemStyle: { color: volColors[i] } })),
      },
    ],
  } as echarts.EChartsOption
}

function themeColor(name: string, fallback: string) {
  if (typeof window === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

function chartPalette() {
  return {
    secondary: themeColor('--text-color-secondary', 'slategray'),
    border: themeColor('--border-color', 'lightgray'),
    grid: themeColor('--border-color-light', 'gainsboro'),
  }
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

function stopSourceRefresh() {
  if (sourceRefreshTimer) {
    clearInterval(sourceRefreshTimer)
    sourceRefreshTimer = null
  }
}

function startSourceRefresh() {
  stopSourceRefresh()
  sourceRefreshTimer = setInterval(async () => {
    await store.fetchSources()
    if (store.activeSourceInfo?.status === 'available' && !store.quotesLoading) {
      await store.fetchQuotes()
    }
  }, 60_000)
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

watch(
  () => store.activeSourceInfo?.status,
  async (status, prevStatus) => {
    if (status === 'available') {
      if (prevStatus !== 'available' && !store.quotesLoading) {
        await store.fetchQuotes()
        if (store.autoRefresh) store.startAutoRefresh()
      }
      return
    }
    if (status) {
      startSourceRefresh()
    }
  },
)

// ---- lifecycle ----
onMounted(async () => {
  await store.fetchSources()
  startSourceRefresh()
  if (store.activeSource && store.activeSourceInfo?.status === 'available') {
    await store.fetchQuotes()
    if (store.autoRefresh) store.startAutoRefresh()
  }
  window.addEventListener('resize', handleChartResize)
})

onUnmounted(() => {
  store.cleanup()
  stopSourceRefresh()
  chartInstance?.dispose()
  window.removeEventListener('resize', handleChartResize)
})
</script>

<style scoped>
.quote-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  --quote-card-bg: var(--bg-color);
  --quote-soft-bg: var(--fill-color-lighter);
  --quote-hover-bg: var(--fill-color-light);
  --quote-border: var(--border-color-light);
  --quote-border-strong: var(--border-color);
  color: var(--text-color-primary);
}

.quote-hero,
.quote-control-panel,
.quote-table-panel,
.quote-state-card {
  border: 1px solid var(--quote-border);
  border-radius: 8px;
  background: var(--quote-card-bg);
  box-shadow: 0 10px 28px var(--shadow-color);
}

.quote-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  padding: 20px;
}

.quote-hero-copy {
  min-width: 0;
}

.quote-title-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 12px;
}

.quote-hero-copy > span,
.quote-section-heading span {
  display: inline-flex;
  margin-bottom: 7px;
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 760;
  line-height: 1.2;
}

.quote-hero-copy h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 26px;
  font-weight: 760;
  line-height: 1.2;
}

.quote-hero-copy p,
.quote-section-heading p {
  margin: 8px 0 0;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.quote-querying {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  color: var(--primary-color);
  font-size: 13px;
  font-weight: 650;
}

.quote-querying__dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  min-width: 18px;
}

.quote-querying__dots i {
  width: 4px;
  height: 4px;
  border-radius: 999px;
  background: currentColor;
  animation: quote-querying-pulse 1.1s ease-in-out infinite;
}

.quote-querying__dots i:nth-child(2) {
  animation-delay: 0.15s;
}

.quote-querying__dots i:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes quote-querying-pulse {
  0%, 60%, 100% { opacity: 0.28; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-2px); }
}

.quote-hero-status {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.quote-update-time,
.quote-refreshing {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 24px;
}

.quote-update-time.is-stale {
  color: var(--warning-color);
}

.quote-refreshing {
  color: var(--primary-color);
}

.quote-hero-stats {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.quote-hero-stats article {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--quote-border);
  border-radius: 8px;
  background: var(--quote-soft-bg);
}

.quote-hero-stats span {
  display: block;
  margin-bottom: 6px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.3;
}

.quote-hero-stats strong {
  display: block;
  overflow: hidden;
  color: var(--text-color-primary);
  font-size: 17px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-section-heading {
  min-width: 0;
}

.quote-source-tabs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-width: 0;
}

.quote-source-tabs--inline {
  justify-content: flex-start;
}

.quote-source-status-button {
  margin-left: auto;
}

.quote-source-status-popover {
  display: grid;
  gap: 8px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.quote-source-status-popover p {
  margin: 0;
}

.quote-source-status-popover > strong {
  color: var(--text-color-primary);
  font-size: 13px;
}

.source-tab {
  display: inline-flex;
  position: relative;
  align-items: center;
  gap: 6px;
  min-width: 0;
  min-height: 34px;
  padding: 7px 12px;
  border: 1px solid var(--quote-border);
  border-radius: 8px;
  background: var(--quote-card-bg);
  color: var(--text-color-regular);
  cursor: pointer;
  font-size: 13px;
  font-weight: 650;
  transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease;
  user-select: none;
}

.source-tab:hover {
  border-color: color-mix(in srgb, var(--primary-color) 32%, var(--quote-border));
  background: color-mix(in srgb, var(--primary-color) 8%, var(--quote-card-bg));
}

.source-tab--active {
  border-color: color-mix(in srgb, var(--primary-color) 48%, var(--quote-border));
  background: color-mix(in srgb, var(--primary-color) 12%, var(--quote-card-bg));
  color: var(--primary-color);
}

.source-tab__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.source-tab--available .source-tab__dot {
  background-color: var(--success-color);
}

.source-tab--disconnected .source-tab__dot {
  background-color: var(--warning-color);
}

.source-tab--unavailable .source-tab__dot {
  background-color: var(--text-color-placeholder);
}

.source-tab--unavailable {
  color: var(--text-color-placeholder);
  cursor: not-allowed;
}

.source-tab__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-tab__runtime {
  color: var(--text-color-secondary);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.quote-runtime-monitor__runs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quote-runtime-monitor__run {
  display: grid;
  gap: 2px;
  min-width: min(100%, 230px);
  padding: 8px 10px;
  border: 1px solid var(--quote-border);
  border-radius: 6px;
  background: var(--quote-card-bg);
}

.quote-runtime-monitor__run strong {
  overflow: hidden;
  color: var(--text-color-primary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-runtime-monitor__run span,
.quote-runtime-monitor__run small {
  overflow: hidden;
  color: var(--text-color-secondary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-control-panel {
  display: grid;
  gap: 14px;
  padding: 18px;
}

.quote-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: start;
}

.quote-filter-grid {
  display: grid;
  grid-template-columns: minmax(190px, 1.2fr) minmax(130px, 0.7fr) minmax(130px, 0.7fr) auto auto;
  gap: 10px;
  align-items: center;
}

.quote-checkbox {
  min-height: 32px;
}

.quote-action-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.quote-interval-select {
  width: 88px;
}

.quote-advanced-popover {
  display: grid;
  gap: 12px;
  color: var(--text-color-primary);
  font-size: 13px;
}

.quote-advanced-popover > div > span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.quote-range-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  margin-top: 6px;
}

.quote-loading-state,
.quote-chart-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 260px;
  color: var(--primary-color);
  font-size: 28px;
}

.quote-loading-state {
  position: relative;
  display: block;
}

.quote-loading-state :deep(.data-table-skeleton) {
  width: 100%;
}

.quote-loading-state .quote-querying {
  position: absolute;
  z-index: 1;
  top: 50%;
  left: 50%;
  margin: 0;
  padding: 8px 12px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 28%, var(--quote-border));
  border-radius: 999px;
  background: color-mix(in srgb, var(--quote-card-bg) 92%, var(--primary-color));
  box-shadow: 0 8px 18px var(--shadow-color);
  transform: translate(-50%, -50%);
}

.quote-chart-state {
  flex-direction: column;
  gap: 10px;
}

.quote-error-text {
  margin: 0;
  color: var(--danger-color);
}

.quote-state-card :deep(.el-card__body) {
  padding: 32px 18px;
}

.quote-table-panel {
  overflow: hidden;
}

.quote-table-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--quote-border);
}

.quote-table {
  --el-table-bg-color: var(--quote-card-bg);
  --el-table-tr-bg-color: var(--quote-card-bg);
  --el-table-header-bg-color: var(--quote-soft-bg);
  --el-table-row-hover-bg-color: var(--quote-hover-bg);
  --el-table-border-color: var(--quote-border);
  --el-table-text-color: var(--text-color-primary);
  --el-table-header-text-color: var(--text-color-secondary);
}

.quote-table :deep(.el-table__row td) {
  padding: 4px 0;
  font-size: 13px;
}

.quote-table :deep(.el-table__header th) {
  padding: 6px 0;
  font-size: 12px;
  background-color: var(--quote-soft-bg) !important;
}

.quote-table :deep(.el-table__fixed),
.quote-table :deep(.el-table__fixed-right) {
  background: var(--quote-card-bg);
}

.quote-symbol-cell {
  display: grid;
  gap: 2px;
  color: var(--text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
}

.quote-symbol-cell strong,
.quote-symbol-cell small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-symbol-cell strong {
  font-weight: 720;
}

.quote-symbol-cell small {
  color: var(--text-color-secondary);
  font-family: var(--font-family);
  font-size: 11px;
  font-weight: 500;
}

.quote-time-cell {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.quote-table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-top: 1px solid var(--quote-border);
  background: var(--quote-soft-bg);
  color: var(--text-color-secondary);
  font-size: 12px;
}

.quote-mobile-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0 14px 14px;
  list-style: none;
}

.quote-mobile-card {
  display: grid;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--quote-border);
  border-radius: 8px;
  background: var(--quote-soft-bg);
}

.quote-mobile-card__overview {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-color-primary);
  cursor: pointer;
  text-align: left;
}

.quote-mobile-card__overview:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 3px;
}

.quote-mobile-card__identity {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.quote-mobile-card__identity strong {
  overflow: hidden;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-mobile-card__identity span {
  overflow: hidden;
  color: var(--text-color-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-mobile-card__overview > :last-child {
  flex: none;
  font-size: 16px;
  font-weight: 760;
}

.quote-mobile-card__metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.quote-mobile-card__metrics > div {
  min-width: 0;
}

.quote-mobile-card__metrics dt {
  margin-bottom: 3px;
  color: var(--text-color-secondary);
  font-size: 11px;
}

.quote-mobile-card__metrics dd {
  margin: 0;
  overflow: hidden;
  color: var(--text-color-primary);
  font-size: 13px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-mobile-card__actions {
  display: flex;
  gap: 8px;
}

.quote-mobile-card__actions :deep(.el-button:first-child) {
  flex: 1;
}

/* Tick flash animation (P1) */
.quote-table :deep(.tick-flash td) {
  animation: tick-flash-anim 0.6s ease-out;
}

@keyframes tick-flash-anim {
  0% { background-color: color-mix(in srgb, var(--primary-color) 16%, var(--quote-card-bg)); }
  100% { background-color: transparent; }
}

/* Row click cursor */
.quote-table :deep(.el-table__row) {
  cursor: pointer;
}

.quote-page :deep(.el-tag) {
  border-color: var(--quote-border);
  background: var(--quote-soft-bg);
  color: var(--text-color-regular);
}

.quote-page :deep(.el-tag.el-tag--success) {
  border-color: color-mix(in srgb, var(--success-color) 36%, var(--quote-border));
  background: color-mix(in srgb, var(--success-color) 12%, var(--quote-card-bg));
  color: var(--success-color);
}

.quote-page :deep(.el-tag.el-tag--warning) {
  border-color: color-mix(in srgb, var(--warning-color) 38%, var(--quote-border));
  background: color-mix(in srgb, var(--warning-color) 12%, var(--quote-card-bg));
  color: var(--warning-color);
}

.quote-page :deep(.el-button:not(.el-button--primary):not(.el-button--danger):not(.is-link)) {
  border-color: var(--quote-border);
  background: var(--quote-soft-bg);
  color: var(--text-color-regular);
}

.quote-page :deep(.el-button:not(.el-button--primary):not(.el-button--danger):not(.is-link):hover),
.quote-page :deep(.el-button:not(.el-button--primary):not(.el-button--danger):not(.is-link):focus) {
  border-color: color-mix(in srgb, var(--primary-color) 36%, var(--quote-border));
  background: color-mix(in srgb, var(--primary-color) 10%, var(--quote-card-bg));
  color: var(--primary-color);
}

.quote-page :deep(.el-input__wrapper),
.quote-page :deep(.el-select__wrapper),
.quote-page :deep(.el-input-number .el-input__wrapper) {
  background: var(--quote-soft-bg);
  box-shadow: 0 0 0 1px var(--quote-border) inset;
}

.quote-page :deep(.el-checkbox__label),
.quote-page :deep(.el-switch__label) {
  color: var(--text-color-regular);
}

.quote-dialog-loading,
.quote-dialog-empty {
  padding: 18px 0;
  color: var(--text-color-secondary);
  text-align: center;
}

.quote-symbol-results,
.quote-column-list {
  display: grid;
  gap: 6px;
  max-height: 320px;
  margin-top: 12px;
  overflow: auto;
}

.quote-symbol-result,
.quote-column-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid var(--quote-border);
  border-radius: 8px;
  background: var(--quote-soft-bg);
  cursor: pointer;
}

.quote-symbol-result:hover,
.quote-column-row:hover {
  border-color: color-mix(in srgb, var(--primary-color) 32%, var(--quote-border));
  background: color-mix(in srgb, var(--primary-color) 8%, var(--quote-card-bg));
}

.quote-symbol-result > div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.quote-symbol-result span {
  color: var(--text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-weight: 720;
}

.quote-symbol-result small {
  overflow: hidden;
  color: var(--text-color-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-direct-add {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
}

.quote-column-hint {
  margin-bottom: 12px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.quote-column-row {
  justify-content: flex-start;
}

.quote-column-drag {
  color: var(--text-color-secondary);
  cursor: move;
}

.quote-chart-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}

.quote-chart-toolbar > span {
  color: var(--text-color-secondary);
  font-size: 13px;
  font-weight: 650;
}

.quote-chart-container {
  width: 100%;
  height: calc(100% - 52px);
  min-height: 300px;
}

:global(.quote-chart-drawer) {
  background: var(--bg-color) !important;
  color: var(--text-color-primary);
}

:global(.quote-chart-drawer .el-drawer__header) {
  margin-bottom: 0;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--border-color-light);
  color: var(--text-color-primary);
}

:global(.quote-chart-drawer .el-drawer__body) {
  padding: 16px 20px 20px;
  background: var(--bg-color);
  color: var(--text-color-primary);
}

:global(.quote-chart-drawer .el-drawer__close-btn) {
  color: var(--text-color-secondary);
}

:global(.quote-chart-drawer .el-radio-button__inner) {
  border-color: var(--border-color-light);
  background: var(--fill-color-lighter);
  color: var(--text-color-regular);
}

:global(.quote-chart-drawer .el-radio-button__original-radio:checked + .el-radio-button__inner) {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: var(--el-color-white);
  box-shadow: none;
}

.text-red-600 {
  color: var(--danger-color) !important;
  font-weight: 700;
}

.text-green-600 {
  color: var(--success-color) !important;
  font-weight: 700;
}

.text-gray-400,
.text-gray-500,
.text-gray-600 {
  color: var(--text-color-secondary) !important;
}

.is-positive {
  color: var(--success-color) !important;
}

@media (max-width: 1180px) {
  .quote-hero,
  .quote-toolbar {
    grid-template-columns: 1fr;
  }

  .quote-hero-status,
  .quote-source-tabs,
  .quote-action-row {
    justify-content: flex-start;
  }

  .quote-source-status-button {
    margin-left: 0;
  }

  .quote-filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .quote-page {
    gap: 14px;
  }

  .quote-hero,
  .quote-control-panel {
    padding: 14px;
  }

  .quote-hero-copy h1 {
    font-size: 22px;
  }

  .quote-hero-stats,
  .quote-filter-grid {
    grid-template-columns: 1fr;
  }

  .quote-source-tabs {
    display: grid;
    grid-template-columns: 1fr;
  }

  .quote-action-row :deep(.el-button),
  .quote-action-row :deep(.el-select),
  .quote-action-row :deep(.el-select__wrapper) {
    width: 100%;
  }

  .quote-table-heading,
  .quote-table-footer,
  .quote-direct-add,
  .quote-range-row {
    grid-template-columns: 1fr;
  }

  .quote-table-heading,
  .quote-table-footer {
    display: grid;
  }

  .quote-chart-container {
    min-height: 260px;
  }
}
</style>
