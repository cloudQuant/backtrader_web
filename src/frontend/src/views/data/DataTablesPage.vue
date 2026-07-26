<template>
  <div
    class="data-tables-page"
    data-test="data-tables-page"
  >
    <section class="tables-hero">
      <div class="tables-hero-copy">
        <span class="tables-eyebrow">{{ t('dataPages.tablesHeroKicker') }}</span>
        <h1>{{ t('dataPages.tablesPageTitle') }}</h1>
        <p>{{ t('dataPages.tablesPageDesc') }}</p>
      </div>

      <div class="tables-hero-stats">
        <article
          v-for="stat in tableStats"
          :key="stat.key"
          class="tables-stat-card"
        >
          <span>{{ stat.label }}</span>
          <strong>{{ stat.value }}</strong>
          <small>{{ stat.helper }}</small>
        </article>
      </div>
    </section>

    <section class="tables-control-panel">
      <div class="tables-section-heading">
        <div>
          <span class="tables-section-kicker">{{ t('dataPages.tablesControlKicker') }}</span>
          <h2>{{ t('dataPages.tablesControlTitle') }}</h2>
          <p>{{ t('dataPages.tablesControlDesc') }}</p>
        </div>
        <span class="tables-total-pill">
          {{ t('dataPages.tablesTotalSuffix', { n: total }) }}
        </span>
      </div>

      <div class="toolbar">
        <el-input
          v-model="search"
          clearable
          :placeholder="t('dataPages.tablesSearchPh')"
          class="toolbar-search"
          @keyup.enter="reloadFirstPage"
          @clear="reloadFirstPage"
        />
        <el-button
          type="primary"
          @click="reloadFirstPage"
        >
          <el-icon aria-hidden="true">
            <Search />
          </el-icon>
          {{ t('dataPages.tablesQuery') }}
        </el-button>
      </div>
    </section>

    <section class="tables-list-panel">
      <div class="tables-section-heading">
        <div>
          <span class="tables-section-kicker">{{ t('dataPages.tablesTableKicker') }}</span>
          <h2>{{ t('dataPages.tablesTableTitle') }}</h2>
          <p>{{ t('dataPages.tablesTableDesc') }}</p>
        </div>
      </div>

      <div
        v-if="!loading && tables.length === 0"
        class="tables-empty-state"
      >
        <span class="tables-empty-icon">
          <el-icon aria-hidden="true">
            <Grid />
          </el-icon>
        </span>
        <strong>{{ t('dataPages.tablesEmptyTitle') }}</strong>
        <p>{{ t('dataPages.tablesEmptyDesc') }}</p>
      </div>

      <el-table
        v-else
        v-loading="loading"
        class="tables-data-grid"
        :data="tables"
        :empty-text="t('dataPages.tablesEmptyTitle')"
      >
        <el-table-column
          :label="t('dataPages.tablesColName')"
          min-width="250"
        >
          <template #default="{ row }">
            <div class="table-name-cell">
              <strong>{{ row.table_name }}</strong>
              <span>{{ tableMeta(row) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.tablesColComment')"
          min-width="220"
        >
          <template #default="{ row }">
            <span class="table-comment">
              {{ row.table_comment || t('dataPages.tablesNoComment') }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          prop="row_count"
          :label="t('dataPages.tablesColRowCount')"
          width="120"
        >
          <template #default="{ row }">
            <span class="table-count-pill">{{ compactCount(row.row_count) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="last_update_status"
          :label="t('dataPages.tablesColLastStatus')"
          width="130"
        >
          <template #default="{ row }">
            <span
              class="table-status-pill"
              :class="statusClass(row.last_update_status)"
            >
              {{ row.last_update_status || '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          prop="data_start_date"
          :label="t('dataPages.tablesColDataStart')"
          width="120"
        >
          <template #default="{ row }">
            {{ formatShortDate(row.data_start_date) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="data_end_date"
          :label="t('dataPages.tablesColDataEnd')"
          width="120"
        >
          <template #default="{ row }">
            {{ formatShortDate(row.data_end_date) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="updated_at"
          :label="t('dataPages.tablesColUpdatedAt')"
          width="180"
        >
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.tablesColActions')"
          width="110"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="goDetail(row.id)"
            >
              <el-icon aria-hidden="true">
                <View />
              </el-icon>
              {{ t('dataPages.tablesActionDetail') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadTables"
          @size-change="handleSizeChange"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Grid, Search, View } from '@element-plus/icons-vue'
import { akshareTablesApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import type { DataTable } from '@/types'
import { compactCount, formatDateTime, formatShortDate } from '@/views/data/utils'

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const tables = ref<DataTable[]>([])
const search = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const loadedRowTotal = computed(() => {
  return tables.value.reduce((sum, table) => sum + Number(table.row_count || 0), 0)
})

const successfulTables = computed(() => {
  return tables.value.filter((table) => table.last_update_status === 'success').length
})

const dateCoverage = computed(() => {
  const starts = tables.value
    .map((table) => parseDate(table.data_start_date))
    .filter((date): date is Date => Boolean(date))
  const ends = tables.value
    .map((table) => parseDate(table.data_end_date))
    .filter((date): date is Date => Boolean(date))
  if (!starts.length && !ends.length) return '-'
  const start = starts.length ? new Date(Math.min(...starts.map((date) => date.getTime()))) : null
  const end = ends.length ? new Date(Math.max(...ends.map((date) => date.getTime()))) : null
  return `${start ? formatShortDate(start.toISOString()) : '-'} / ${end ? formatShortDate(end.toISOString()) : '-'}`
})

const tableStats = computed(() => [
  {
    key: 'total',
    label: t('dataPages.tablesStatTotal'),
    value: compactCount(total.value),
    helper: t('dataPages.tablesStatTotalHelper'),
  },
  {
    key: 'rows',
    label: t('dataPages.tablesStatRows'),
    value: compactCount(loadedRowTotal.value),
    helper: t('dataPages.tablesStatRowsHelper'),
  },
  {
    key: 'success',
    label: t('dataPages.tablesStatSuccess'),
    value: `${successfulTables.value}/${tables.value.length}`,
    helper: t('dataPages.tablesStatSuccessHelper'),
  },
  {
    key: 'coverage',
    label: t('dataPages.tablesStatCoverage'),
    value: dateCoverage.value,
    helper: t('dataPages.tablesStatCoverageHelper'),
  },
])

async function loadTables() {
  loading.value = true
  try {
    const response = await akshareTablesApi.list({
      search: search.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    tables.value = response.items
    total.value = response.total
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.tablesLoadFailed')))
  } finally {
    loading.value = false
  }
}

function reloadFirstPage() {
  page.value = 1
  void loadTables()
}

function handleSizeChange() {
  page.value = 1
  void loadTables()
}

function goDetail(tableId: number) {
  void router.push({ name: 'DataTableDetail', params: { id: tableId } })
}

function parseDate(value: string | null | undefined) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function statusClass(status: string | null) {
  if (status === 'success') return 'is-success'
  if (status === 'failed' || status === 'error') return 'is-danger'
  if (status === 'running') return 'is-warning'
  return 'is-muted'
}

function tableMeta(row: DataTable) {
  return [row.category, row.asset_type, row.market, row.symbol_normalized]
    .filter(Boolean)
    .join(' · ') || row.script_id || '-'
}

onMounted(() => {
  void loadTables()
})
</script>

<style scoped>
.data-tables-page {
  --tables-surface: color-mix(in srgb, var(--bg-color) 92%, transparent);
  --tables-surface-strong: color-mix(in srgb, var(--bg-color) 82%, var(--el-color-primary) 18%);
  --tables-text: var(--text-color-primary);
  --tables-muted: var(--text-color-secondary);
  --tables-border: color-mix(in srgb, var(--border-color) 78%, transparent);
  --tables-border-strong: color-mix(in srgb, var(--border-color) 64%, var(--el-color-primary) 36%);
  --tables-shadow: 0 18px 48px color-mix(in srgb, #000 16%, transparent);
  --tables-good: var(--success-color, #16a34a);
  --tables-warn: var(--warning-color, #d97706);
  --tables-bad: var(--danger-color, #dc2626);
  display: grid;
  gap: 18px;
  color: var(--tables-text);
}

.tables-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(360px, 0.92fr);
  gap: 18px;
  padding: clamp(22px, 3.2vw, 34px);
  border: 1px solid var(--tables-border);
  border-radius: 8px;
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--bg-color) 94%, var(--el-color-primary) 6%), transparent),
    var(--tables-surface);
  background-color: var(--tables-surface);
  box-shadow: var(--tables-shadow);
}

.tables-hero-copy {
  display: grid;
  align-content: center;
  gap: 10px;
  min-width: 0;
}

.tables-eyebrow,
.tables-section-kicker {
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.tables-hero h1,
.tables-section-heading h2 {
  margin: 0;
  color: var(--tables-text);
  letter-spacing: 0;
}

.tables-hero h1 {
  font-size: clamp(30px, 4vw, 46px);
  line-height: 1.06;
}

.tables-hero p,
.tables-section-heading p {
  max-width: 760px;
  margin: 0;
  color: var(--tables-muted);
  line-height: 1.68;
}

.tables-hero-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.tables-stat-card,
.tables-control-panel,
.tables-list-panel {
  border: 1px solid var(--tables-border);
  border-radius: 8px;
  background: var(--tables-surface);
  background-color: var(--tables-surface);
}

.tables-stat-card {
  display: grid;
  align-content: center;
  gap: 8px;
  min-height: 118px;
  padding: 16px;
}

.tables-stat-card span,
.tables-stat-card small {
  color: var(--tables-muted);
  font-size: 12px;
  line-height: 1.5;
}

.tables-stat-card strong {
  color: var(--tables-text);
  font-size: 24px;
  line-height: 1.15;
}

.tables-control-panel,
.tables-list-panel {
  box-shadow: 0 12px 30px color-mix(in srgb, #000 10%, transparent);
}

.tables-control-panel {
  display: grid;
  gap: 16px;
  padding: 18px;
}

.tables-list-panel {
  overflow: hidden;
}

.tables-list-panel > .tables-section-heading {
  padding: 18px 18px 14px;
  border-bottom: 1px solid var(--tables-border);
}

.tables-section-heading,
.toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.tables-section-heading > div {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.toolbar {
  align-items: center;
  justify-content: flex-start;
}

.toolbar-search {
  width: min(520px, 100%);
}

.tables-total-pill {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--tables-border);
  border-radius: 999px;
  color: var(--tables-muted);
  background: var(--tables-surface-strong);
  font-size: 12px;
}

.tables-data-grid {
  --el-table-bg-color: var(--tables-surface);
  --el-table-tr-bg-color: var(--tables-surface);
  --el-table-header-bg-color: color-mix(in srgb, var(--bg-color-page) 62%, var(--bg-color) 38%);
  --el-table-text-color: var(--tables-text);
  --el-table-header-text-color: var(--tables-text);
  --el-table-border-color: var(--tables-border);
}

.table-name-cell {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.table-name-cell strong {
  color: var(--tables-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.table-name-cell span,
.table-comment {
  color: var(--tables-muted);
  font-size: 12px;
  line-height: 1.45;
}

.table-count-pill,
.table-status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 26px;
  padding: 0 9px;
  border: 1px solid var(--tables-border);
  border-radius: 999px;
  color: var(--tables-muted);
  background: var(--tables-surface-strong);
  font-size: 12px;
  font-weight: 700;
}

.table-status-pill.is-success {
  border-color: color-mix(in srgb, var(--tables-good) 55%, transparent);
  color: var(--tables-good);
  background: color-mix(in srgb, var(--tables-good) 12%, var(--bg-color));
}

.table-status-pill.is-danger {
  border-color: color-mix(in srgb, var(--tables-bad) 55%, transparent);
  color: var(--tables-bad);
  background: color-mix(in srgb, var(--tables-bad) 12%, var(--bg-color));
}

.table-status-pill.is-warning {
  border-color: color-mix(in srgb, var(--tables-warn) 55%, transparent);
  color: var(--tables-warn);
  background: color-mix(in srgb, var(--tables-warn) 12%, var(--bg-color));
}

.tables-empty-state {
  display: grid;
  justify-items: center;
  gap: 8px;
  margin: 18px;
  padding: 36px 18px;
  border: 1px dashed var(--tables-border-strong);
  border-radius: 8px;
  color: var(--tables-muted);
  text-align: center;
  background: color-mix(in srgb, var(--bg-color-page) 68%, var(--bg-color) 32%);
}

.tables-empty-state strong {
  color: var(--tables-text);
}

.tables-empty-state p {
  max-width: 520px;
  margin: 0;
  line-height: 1.6;
}

.tables-empty-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border: 1px solid var(--tables-border);
  border-radius: 8px;
  color: var(--el-color-primary);
  background: var(--tables-surface);
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding: 14px 18px 18px;
}

.pagination-wrap :deep(.el-pagination) {
  --el-pagination-bg-color: transparent;
  --el-pagination-button-bg-color: var(--tables-surface);
  --el-pagination-text-color: var(--tables-muted);
  --el-pagination-hover-color: var(--el-color-primary);
  color: var(--tables-muted);
}

.pagination-wrap :deep(.btn-prev),
.pagination-wrap :deep(.btn-next),
.pagination-wrap :deep(.el-pager li),
.pagination-wrap :deep(.el-input__wrapper) {
  border: 1px solid var(--tables-border);
  border-radius: 6px;
  color: var(--tables-muted);
  background: var(--tables-surface);
  box-shadow: none;
}

.pagination-wrap :deep(.el-pager li.is-active) {
  border-color: color-mix(in srgb, var(--el-color-primary) 64%, transparent);
  color: var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary) 12%, var(--bg-color));
}

@media (max-width: 1120px) {
  .tables-hero {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .tables-hero,
  .tables-control-panel {
    padding: 16px;
  }

  .tables-hero-stats {
    grid-template-columns: 1fr;
  }

  .toolbar,
  .toolbar :deep(.el-button) {
    width: 100%;
  }

  .pagination-wrap {
    justify-content: flex-start;
    overflow-x: auto;
  }
}
</style>
