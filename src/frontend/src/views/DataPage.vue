<template>
  <div class="history-data-page">
    <el-card
      class="history-query-card"
      data-test="data-market-page"
    >
      <template #header>
        <div class="history-query-header">
          <div>
            <span class="history-query-kicker">{{ t('dataMgmt.heroKicker') }}</span>
            <h2>{{ t('dataMgmt.headerTitle') }}</h2>
            <p>{{ t('dataMgmt.headerDesc') }}</p>
          </div>
          <div class="history-query-status">
            <el-tag type="info">
              {{ t('dataMgmt.providerTag', { provider: result?.provider || '-' }) }}
            </el-tag>
            <div class="history-query-stats">
              <article
                v-for="item in heroStats"
                :key="item.label"
              >
                <span>{{ item.label }}</span>
                <strong :class="item.tone">{{ item.value }}</strong>
              </article>
            </div>
          </div>
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
          :class="{
            'is-active': form.asset_type === asset.key,
            'is-core-asset': asset.key === 'stock' || asset.key === 'futures',
          }"
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
        <el-select
          v-model="form.symbol"
          class="instrument-select"
          data-test="market-instrument-select"
          filterable
          remote
          clearable
          allow-create
          default-first-option
          reserve-keyword
          :loading="instrumentOptionsLoading"
          :placeholder="symbolPlaceholder"
          :remote-method="searchInstrumentOptions"
          @visible-change="handleInstrumentDropdownVisible"
        >
          <el-option
            v-for="option in instrumentOptions"
            :key="`${option.asset_type}:${option.symbol}:${option.market || ''}`"
            :label="instrumentOptionLabel(option)"
            :value="option.symbol"
          >
            <div class="instrument-option">
              <span>
                <strong>{{ option.symbol }}</strong>
                <small>{{ option.name || '-' }}</small>
              </span>
              <em>{{ option.market || '-' }}</em>
              <el-tag
                size="small"
                :type="option.has_history ? 'success' : 'warning'"
              >
                {{ formatInstrumentHistoryStatus(option) }}
              </el-tag>
            </div>
          </el-option>
        </el-select>
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

    <section
      class="asset-overview"
      :class="`asset-overview--${form.asset_type}`"
      data-test="market-instrument-overview"
    >
      <div class="asset-overview-main">
        <span class="asset-overview-icon">
          <el-icon aria-hidden="true">
            <component :is="activeAssetIcon" />
          </el-icon>
        </span>
        <div>
          <span class="asset-overview-label">{{ assetLabel(form.asset_type) }}</span>
          <h3>{{ result?.name || result?.symbol || form.symbol || '-' }}</h3>
          <p>{{ t(activeAssetConfig.descKey) }}</p>
        </div>
      </div>
      <div class="asset-overview-meta">
        <span>{{ t('dataMgmt.fieldPrice') }}</span>
        <strong :class="toneClass(snapshot.change_pct ?? snapshot.change)">
          {{ formatNumber(snapshot.price) }}
        </strong>
        <small
          v-if="hasSnapshotChange"
          :class="toneClass(snapshot.change_pct ?? snapshot.change)"
        >
          {{ formatNumber(snapshot.change) }} / {{ formatPercent(snapshot.change_pct) }}
        </small>
        <small v-else>{{ chartSubtitle }}</small>
        <div class="asset-overview-context">
          <el-tag size="small" type="info">{{ result?.provider || '-' }}</el-tag>
          <span>{{ result?.market || (form.asset_type === 'futures' ? form.market : '-') }}</span>
        </div>
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

    <section
      v-loading="coverageLoading"
      class="market-data-details"
      data-test="market-coverage-matrix"
    >
      <el-collapse>
        <el-collapse-item
          :title="t('dataMgmt.dataSourceDetailsCoverageMatrix')"
          name="coverage-matrix"
        >
    <section class="market-coverage-section">
      <div class="market-coverage-header">
        <div>
          <span>{{ t('dataMgmt.coverageMatrixTitle') }}</span>
          <p>{{ coverageMatrixSubtitle }}</p>
        </div>
        <div class="market-coverage-actions">
          <el-select
            v-model="coverageTimeframe"
            size="small"
            class="coverage-timeframe-select"
            @change="loadCoverageMatrix()"
          >
            <el-option
              label="1d"
              value="1d"
            />
            <el-option
              label="1h"
              value="1h"
            />
            <el-option
              label="30m"
              value="30m"
            />
            <el-option
              label="5m"
              value="5m"
            />
          </el-select>
          <el-input
            v-model="coverageProvider"
            size="small"
            clearable
            class="coverage-provider-input"
            placeholder="provider"
            @change="loadCoverageMatrix()"
          />
          <el-button
            size="small"
            :loading="coverageRefreshing"
            data-test="market-coverage-refresh"
            @click="refreshCoverageMatrix"
          >
            <el-icon aria-hidden="true">
              <Refresh />
            </el-icon>
            <span>{{ t('dataMgmt.coverageRefresh') }}</span>
          </el-button>
        </div>
      </div>

      <div class="market-coverage-summary">
        <article
          v-for="item in coverageSummaryCards"
          :key="item.label"
        >
          <span>{{ item.label }}</span>
          <strong :class="item.tone">{{ item.value }}</strong>
        </article>
      </div>

      <el-alert
        v-if="coverageError"
        class="history-alert"
        type="warning"
        show-icon
        :closable="false"
        :title="coverageError"
      />

      <el-table
        v-if="coverageRows.length"
        :data="coverageRows"
        stripe
        max-height="360"
      >
        <el-table-column
          :label="t('dataMgmt.coverageStatus')"
          width="96"
        >
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="coverageStatusTagType(row.quality_status)"
            >
              {{ coverageStatusLabel(row.quality_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="symbol"
          :label="t('dataMgmt.coverageSymbol')"
          min-width="120"
        />
        <el-table-column
          prop="asset_type"
          :label="t('dataMgmt.coverageAsset')"
          width="100"
        />
        <el-table-column
          prop="timeframe"
          :label="t('dataMgmt.coveragePeriod')"
          width="88"
        />
        <el-table-column
          prop="provider"
          :label="t('dataMgmt.coverageProvider')"
          min-width="120"
        />
        <el-table-column
          :label="t('dataMgmt.coverageRange')"
          min-width="180"
        >
          <template #default="{ row }">
            {{ coverageDateRange(row) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataMgmt.coverageRows')"
          width="110"
          align="right"
        >
          <template #default="{ row }">
            {{ formatNumber(row.row_count) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataMgmt.coverageGap')"
          width="110"
          align="right"
        >
          <template #default="{ row }">
            {{ formatCoverageRatio(row.missing_ratio) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="latest_bar_time"
          :label="t('dataMgmt.coverageLatestBar')"
          min-width="150"
        />
      </el-table>
      <el-empty
        v-else-if="!coverageLoading"
        :description="t('dataMgmt.coverageEmpty')"
      />
    </section>
        </el-collapse-item>
      </el-collapse>
    </section>

    <section class="market-workbench-grid">
      <el-card class="market-chart-card">
        <template #header>
          <div class="section-header market-chart-header">
            <div>
              <span>
                {{ t('dataMgmt.marketWorkbenchTitle') }} · {{ t(activeAssetConfig.titleKey) }}
              </span>
              <small>{{ t(activeAssetConfig.descKey) }}</small>
              <div class="market-workbench-context">
                <el-tag size="small">{{ assetLabel(form.asset_type) }}</el-tag>
                <span>{{ result?.market || '-' }}</span>
                <strong>{{ result?.symbol || form.symbol || '-' }}</strong>
                <span>{{ chartSubtitle }}</span>
              </div>
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

      </div>
    </section>

    <section class="market-data-details">
      <el-collapse>
        <el-collapse-item
          :title="t('dataMgmt.dataSourceDetailsCatalog')"
          name="data-catalog"
        >
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
        </el-collapse-item>
      </el-collapse>
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

    <section class="market-data-details">
      <el-collapse>
        <el-collapse-item
          :title="t('dataMgmt.dataSourceDetailsCoverage')"
          name="data-coverage"
        >
          <section class="market-panel market-panel--coverage">
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
        </el-collapse-item>
      </el-collapse>
    </section>
  </div>
</template>

<script setup lang="ts">
import { Refresh, Search } from '@element-plus/icons-vue'
import { useDataPage } from './data/useDataPage'

const dataPage = useDataPage()

const {
  t,
  assetTabs,
  periods,
  form,
  dateRange,
  loading,
  result,
  chartMode,
  marketChartRef,
  instrumentOptions,
  instrumentOptionsLoading,
  relatedTablesLoading,
  relatedTables,
  relatedTablesError,
  coverageRows,
  coverageLoading,
  coverageRefreshing,
  coverageError,
  coverageTimeframe,
  coverageProvider,
  snapshot,
  historyRows,
  chartCanRender,
  activeAssetConfig,
  activeAssetIcon,
  symbolPlaceholder,
  emptyHistoryText,
  chartEmptyText,
  chartSubtitle,
  chartAriaLabel,
  hasSnapshotChange,
  hasSnapshotTurnover,
  hasSnapshotBidAsk,
  hasSnapshotOpenInterest,
  hasSnapshotSettle,
  hasSnapshotValuation,
  hasSnapshotDataSource,
  assetKpiCards,
  chartModeOptions,
  rangeStats,
  dataCoverageRows,
  coverageScore,
  heroStats,
  coverageMatrixSubtitle,
  coverageSummaryCards,
  assetDataFamilies,
  relatedTablesBadge,
  relatedTableSummary,
  assetDetailRows,
  historyTableColumns,
  assetLabel,
  setAssetType,
  lookupInstrument,
  loadCoverageMatrix,
  refreshCoverageMatrix,
  searchInstrumentOptions,
  handleInstrumentDropdownVisible,
  instrumentOptionLabel,
  formatInstrumentHistoryStatus,
  loadRelatedTables,
  goTableDetail,
  formatHistoryCell,
  formatNumber,
  formatPercent,
  coverageStatusTagType,
  coverageStatusLabel,
  coverageDateRange,
  formatCoverageRatio,
  toneClass,
} = dataPage

defineExpose(dataPage)
</script>

<style scoped src="./DataPage.css" />
