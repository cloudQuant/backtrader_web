<template>
  <div
    class="table-detail-page"
    data-test="data-table-detail-page"
  >
    <section
      v-loading="loading"
      class="table-detail-hero"
    >
      <div class="table-detail-hero-copy">
        <button
          type="button"
          class="detail-back-button"
          @click="goBack"
        >
          <el-icon aria-hidden="true">
            <Back />
          </el-icon>
          <span>{{ t('dataPages.detailGoBack') }}</span>
        </button>
        <span class="detail-eyebrow">{{ t('dataPages.detailHeroKicker') }}</span>
        <h1>{{ tableTitle }}</h1>
        <p>{{ tableDescription }}</p>
      </div>

      <div class="detail-stat-grid">
        <article
          v-for="stat in detailStats"
          :key="stat.key"
          class="detail-stat-card"
        >
          <span>{{ stat.label }}</span>
          <strong>{{ stat.value }}</strong>
          <small>{{ stat.helper }}</small>
        </article>
      </div>
    </section>

    <section
      v-if="table"
      class="detail-meta-panel"
    >
      <div class="detail-section-heading">
        <div>
          <span class="detail-section-kicker">{{ t('dataPages.detailMetaKicker') }}</span>
          <h2>{{ t('dataPages.detailMetaTitle') }}</h2>
          <p>{{ t('dataPages.detailMetaDesc') }}</p>
        </div>
        <span
          class="detail-status-pill"
          :class="statusClass(table.last_update_status)"
        >
          {{ table.last_update_status || '-' }}
        </span>
      </div>

      <div class="detail-meta-grid">
        <div
          v-for="item in metadataItems"
          :key="item.label"
          class="detail-meta-card"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </section>

    <section class="detail-workbench">
      <el-tabs
        v-model="activeTab"
        class="detail-tabs"
        @tab-change="handleTabChange"
      >
        <el-tab-pane
          :label="t('dataPages.detailTabSchema')"
          name="schema"
        >
          <div class="detail-tab-panel">
            <div class="detail-section-heading">
              <div>
                <span class="detail-section-kicker">{{ t('dataPages.detailSchemaKicker') }}</span>
                <h2>{{ t('dataPages.detailSchemaTitle') }}</h2>
                <p>{{ t('dataPages.detailSchemaDesc') }}</p>
              </div>
              <span class="detail-total-pill">
                {{ t('dataPages.detailColumnCount', { count: schemaColumnCount }) }}
              </span>
            </div>

            <el-alert
              v-if="schema?.data_available === false"
              class="detail-alert"
              type="warning"
              show-icon
              :closable="false"
              :title="t('dataPages.detailWarehouseUnavailable')"
              :description="schema?.error || t('dataPages.detailWarehouseUnavailableDesc')"
            />

            <el-table
              class="detail-schema-table"
              :data="schema?.columns || []"
            >
              <el-table-column
                :label="t('dataPages.detailColColumnName')"
                min-width="220"
              >
                <template #default="{ row }">
                  <code class="detail-code-text">{{ row.name }}</code>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('dataPages.detailColColumnType')"
                min-width="180"
              >
                <template #default="{ row }">
                  <span class="detail-type-pill">{{ row.type }}</span>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('dataPages.detailColNullable')"
                width="120"
              >
                <template #default="{ row }">
                  <span
                    class="detail-nullable-pill"
                    :class="row.nullable ? 'is-nullable' : 'is-required'"
                  >
                    {{ row.nullable ? t('dataPages.detailColNullYes') : t('dataPages.detailColNullNo') }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('dataPages.detailColDefault')"
                min-width="160"
              >
                <template #default="{ row }">
                  {{ formatDefaultValue(row.default) }}
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <el-tab-pane
          :label="t('dataPages.detailTabRows')"
          name="rows"
        >
          <div class="detail-tab-panel">
            <div class="detail-section-heading">
              <div>
                <span class="detail-section-kicker">{{ t('dataPages.detailRowsKicker') }}</span>
                <h2>{{ t('dataPages.detailRowsTitle') }}</h2>
                <p>{{ t('dataPages.detailRowsDesc') }}</p>
              </div>
              <span class="detail-total-pill">
                {{ t('dataPages.detailRowsCount', { count: rows.total }) }}
              </span>
            </div>

            <el-alert
              v-if="rows.data_available === false"
              class="detail-alert"
              type="warning"
              show-icon
              :closable="false"
              :title="t('dataPages.detailWarehouseUnavailable')"
              :description="rows.error || t('dataPages.detailWarehouseUnavailableDesc')"
            />

            <el-table
              class="detail-rows-table"
              :data="rows.rows"
              max-height="520"
            >
              <el-table-column
                v-for="column in rows.columns"
                :key="column"
                :prop="column"
                :label="column"
                min-width="160"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  {{ displayCellValue(row[column]) }}
                </template>
              </el-table-column>
            </el-table>

            <div class="pagination-wrap">
              <el-pagination
                v-model:current-page="rowsPage"
                v-model:page-size="rowsPageSize"
                :page-sizes="[20, 50, 100, 200]"
                :total="rows.total"
                layout="total, sizes, prev, pager, next, jumper"
                @current-change="loadRows"
                @size-change="handleRowsSizeChange"
              />
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Back } from '@element-plus/icons-vue'
import { akshareTablesApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import type { DataTable, DataTableRowsResponse, DataTableSchemaResponse } from '@/types'
import { compactCount, formatDateTime, formatShortDate } from '@/views/data/utils'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const loading = ref(false)
const activeTab = ref('schema')
const rowsPage = ref(1)
const rowsPageSize = ref(50)
const table = ref<DataTable | null>(null)
const schema = ref<DataTableSchemaResponse | null>(null)
const rows = reactive<DataTableRowsResponse>({
  table_name: '',
  columns: [],
  rows: [],
  page: 1,
  page_size: 50,
  total: 0,
  data_available: true,
  error: null,
})

const tableId = Number(route.params.id)

const tableTitle = computed(() => table.value?.table_name || t('dataPages.detailFallbackTitle'))
const tableDescription = computed(() => {
  if (!table.value) return t('dataPages.detailHeroDesc')
  return table.value.table_comment || t('dataPages.detailNoComment')
})
const schemaColumnCount = computed(() => schema.value?.columns.length || 0)
const coverageLabel = computed(() => {
  if (!table.value) return '-'
  return `${formatShortDate(table.value.data_start_date)} / ${formatShortDate(table.value.data_end_date)}`
})
const detailStats = computed(() => [
  {
    key: 'rows',
    label: t('dataPages.detailStatRows'),
    value: compactCount(table.value?.row_count),
    helper: t('dataPages.detailStatRowsHelper'),
  },
  {
    key: 'columns',
    label: t('dataPages.detailStatColumns'),
    value: compactCount(schemaColumnCount.value),
    helper: t('dataPages.detailStatColumnsHelper'),
  },
  {
    key: 'status',
    label: t('dataPages.detailStatStatus'),
    value: table.value?.last_update_status || '-',
    helper: t('dataPages.detailStatStatusHelper'),
  },
  {
    key: 'coverage',
    label: t('dataPages.detailStatCoverage'),
    value: coverageLabel.value,
    helper: t('dataPages.detailStatCoverageHelper'),
  },
])
const metadataItems = computed(() => {
  if (!table.value) return []
  return [
    { label: t('dataPages.detailLabelTableName'), value: table.value.table_name },
    { label: t('dataPages.detailLabelScriptId'), value: table.value.script_id || '-' },
    { label: t('dataPages.detailMetaCategory'), value: table.value.category || '-' },
    { label: t('dataPages.detailMetaAssetType'), value: table.value.asset_type || '-' },
    { label: t('dataPages.detailMetaMarket'), value: table.value.market || '-' },
    { label: t('dataPages.detailMetaSymbol'), value: table.value.symbol_normalized || table.value.symbol_raw || '-' },
    { label: t('dataPages.detailLabelDataStart'), value: formatShortDate(table.value.data_start_date) },
    { label: t('dataPages.detailLabelDataEnd'), value: formatShortDate(table.value.data_end_date) },
    { label: t('dataPages.detailMetaUpdatedAt'), value: formatDateTime(table.value.updated_at) },
  ]
})

function goBack() {
  void router.back()
}

async function loadBase() {
  loading.value = true
  try {
    const [tableDetail, schemaDetail] = await Promise.all([
      akshareTablesApi.getDetail(tableId),
      akshareTablesApi.getSchema(tableId),
    ])
    table.value = tableDetail
    schema.value = schemaDetail
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.detailLoadFailed')))
  } finally {
    loading.value = false
  }
}

async function loadRows() {
  try {
    const response = await akshareTablesApi.getRows(tableId, {
      page: rowsPage.value,
      page_size: rowsPageSize.value,
    })
    Object.assign(rows, response)
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.detailLoadRowsFailed')))
  }
}

function handleTabChange(tabName: string | number) {
  if (String(tabName) === 'rows' && rows.columns.length === 0) {
    void loadRows()
  }
}

function handleRowsSizeChange() {
  rowsPage.value = 1
  void loadRows()
}

function statusClass(status: string | null) {
  if (status === 'success') return 'is-success'
  if (status === 'failed' || status === 'error') return 'is-danger'
  if (status === 'running') return 'is-warning'
  return 'is-muted'
}

function formatDefaultValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

function displayCellValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

onMounted(() => {
  void loadBase()
})
</script>

<style scoped>
.table-detail-page {
  --detail-surface: color-mix(in srgb, var(--bg-color) 92%, transparent);
  --detail-surface-strong: color-mix(in srgb, var(--bg-color) 82%, var(--el-color-primary) 18%);
  --detail-text: var(--text-color-primary);
  --detail-muted: var(--text-color-secondary);
  --detail-border: color-mix(in srgb, var(--border-color) 78%, transparent);
  --detail-border-strong: color-mix(in srgb, var(--border-color) 64%, var(--el-color-primary) 36%);
  --detail-shadow: 0 18px 48px color-mix(in srgb, #000 16%, transparent);
  --detail-good: var(--success-color, #16a34a);
  --detail-warn: var(--warning-color, #d97706);
  --detail-bad: var(--danger-color, #dc2626);
  display: grid;
  gap: 18px;
  color: var(--detail-text);
}

.table-detail-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(360px, 0.92fr);
  gap: 18px;
  padding: clamp(22px, 3.2vw, 34px);
  border: 1px solid var(--detail-border);
  border-radius: 8px;
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--bg-color) 94%, var(--el-color-primary) 6%), transparent),
    var(--detail-surface);
  background-color: var(--detail-surface);
  box-shadow: var(--detail-shadow);
}

.table-detail-hero-copy {
  display: grid;
  align-content: center;
  gap: 10px;
  min-width: 0;
}

.detail-back-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  width: fit-content;
  min-height: 34px;
  padding: 0 11px;
  border: 1px solid var(--detail-border);
  border-radius: 8px;
  color: var(--detail-text);
  background: var(--detail-surface-strong);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.detail-eyebrow,
.detail-section-kicker {
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.table-detail-hero h1,
.detail-section-heading h2 {
  margin: 0;
  color: var(--detail-text);
  letter-spacing: 0;
}

.table-detail-hero h1 {
  font-size: clamp(28px, 3.6vw, 42px);
  line-height: 1.08;
  overflow-wrap: anywhere;
}

.table-detail-hero p,
.detail-section-heading p {
  max-width: 760px;
  margin: 0;
  color: var(--detail-muted);
  line-height: 1.68;
}

.detail-stat-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.detail-stat-card,
.detail-meta-panel,
.detail-workbench {
  border: 1px solid var(--detail-border);
  border-radius: 8px;
  background: var(--detail-surface);
  background-color: var(--detail-surface);
}

.detail-stat-card {
  display: grid;
  align-content: center;
  gap: 8px;
  min-height: 118px;
  padding: 16px;
}

.detail-stat-card span,
.detail-stat-card small,
.detail-meta-card span {
  color: var(--detail-muted);
  font-size: 12px;
  line-height: 1.5;
}

.detail-stat-card strong {
  color: var(--detail-text);
  font-size: 24px;
  line-height: 1.15;
  overflow-wrap: anywhere;
}

.detail-meta-panel,
.detail-workbench {
  box-shadow: 0 12px 30px color-mix(in srgb, #000 10%, transparent);
}

.detail-meta-panel {
  display: grid;
  gap: 16px;
  padding: 18px;
}

.detail-section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.detail-section-heading > div {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.detail-status-pill,
.detail-total-pill,
.detail-nullable-pill,
.detail-type-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 26px;
  padding: 0 9px;
  border: 1px solid var(--detail-border);
  border-radius: 999px;
  color: var(--detail-muted);
  background: var(--detail-surface-strong);
  font-size: 12px;
  font-weight: 700;
}

.detail-status-pill.is-success,
.detail-nullable-pill.is-nullable {
  border-color: color-mix(in srgb, var(--detail-good) 55%, transparent);
  color: var(--detail-good);
  background: color-mix(in srgb, var(--detail-good) 12%, var(--bg-color));
}

.detail-status-pill.is-danger,
.detail-nullable-pill.is-required {
  border-color: color-mix(in srgb, var(--detail-bad) 55%, transparent);
  color: var(--detail-bad);
  background: color-mix(in srgb, var(--detail-bad) 12%, var(--bg-color));
}

.detail-status-pill.is-warning {
  border-color: color-mix(in srgb, var(--detail-warn) 55%, transparent);
  color: var(--detail-warn);
  background: color-mix(in srgb, var(--detail-warn) 12%, var(--bg-color));
}

.detail-meta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.detail-meta-card {
  display: grid;
  gap: 6px;
  min-height: 76px;
  padding: 12px;
  border: 1px solid var(--detail-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-color-page) 58%, var(--bg-color) 42%);
}

.detail-meta-card strong {
  color: var(--detail-text);
  font-size: 13px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.detail-workbench {
  overflow: hidden;
}

.detail-tabs {
  --el-tabs-header-height: 48px;
}

.detail-tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 18px;
  border-bottom: 1px solid var(--detail-border);
}

.detail-tabs :deep(.el-tabs__item) {
  color: var(--detail-muted);
}

.detail-tabs :deep(.el-tabs__item.is-active) {
  color: var(--el-color-primary);
}

.detail-tabs :deep(.el-tabs__content) {
  padding: 0;
}

.detail-tab-panel {
  display: grid;
  gap: 16px;
  padding: 18px;
}

.detail-alert {
  margin: 0;
}

.detail-schema-table,
.detail-rows-table {
  --el-table-bg-color: var(--detail-surface);
  --el-table-tr-bg-color: var(--detail-surface);
  --el-table-header-bg-color: color-mix(in srgb, var(--bg-color-page) 62%, var(--bg-color) 38%);
  --el-table-text-color: var(--detail-text);
  --el-table-header-text-color: var(--detail-text);
  --el-table-border-color: var(--detail-border);
}

.detail-code-text {
  color: var(--detail-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
}

.detail-type-pill {
  border-radius: 6px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
}

.pagination-wrap :deep(.el-pagination) {
  --el-pagination-bg-color: transparent;
  --el-pagination-button-bg-color: var(--detail-surface);
  --el-pagination-text-color: var(--detail-muted);
  --el-pagination-hover-color: var(--el-color-primary);
  color: var(--detail-muted);
}

.pagination-wrap :deep(.btn-prev),
.pagination-wrap :deep(.btn-next),
.pagination-wrap :deep(.el-pager li),
.pagination-wrap :deep(.el-input__wrapper) {
  border: 1px solid var(--detail-border);
  border-radius: 6px;
  color: var(--detail-muted);
  background: var(--detail-surface);
  box-shadow: none;
}

.pagination-wrap :deep(.el-pager li.is-active) {
  border-color: color-mix(in srgb, var(--el-color-primary) 64%, transparent);
  color: var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary) 12%, var(--bg-color));
}

@media (max-width: 1120px) {
  .table-detail-hero {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .table-detail-hero,
  .detail-meta-panel,
  .detail-tab-panel {
    padding: 16px;
  }

  .detail-stat-grid,
  .detail-meta-grid {
    grid-template-columns: 1fr;
  }

  .pagination-wrap {
    justify-content: flex-start;
    overflow-x: auto;
  }
}
</style>
