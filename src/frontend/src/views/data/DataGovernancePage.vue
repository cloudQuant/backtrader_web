<template>
  <div
    class="governance-page"
    data-test="governance-page"
  >
    <section
      class="governance-hero"
      data-test="governance-hero"
    >
      <div class="governance-hero-copy">
        <div class="governance-kicker">
          {{ t('dataPages.governanceHeroKicker') }}
        </div>
        <h1>{{ t('dataPages.governanceTitle') }}</h1>
        <p>{{ t('dataPages.governanceDesc') }}</p>
      </div>

      <div class="governance-hero-actions">
        <el-button
          type="primary"
          :icon="Refresh"
          :loading="loading"
          @click="bootstrapAndLoad"
        >
          {{ t('dataPages.governanceRefresh') }}
        </el-button>
      </div>

      <div
        class="governance-metrics"
        data-test="governance-metrics"
      >
        <article class="governance-metric">
          <el-icon aria-hidden="true">
            <Connection />
          </el-icon>
          <span>{{ t('dataPages.governanceStatProviders') }}</span>
          <strong>{{ providers.length }}</strong>
        </article>
        <article class="governance-metric">
          <el-icon aria-hidden="true">
            <Document />
          </el-icon>
          <span>{{ t('dataPages.governanceStatEndpoints') }}</span>
          <strong>{{ endpoints.length }}</strong>
        </article>
        <article class="governance-metric">
          <el-icon aria-hidden="true">
            <CircleCheck />
          </el-icon>
          <span>{{ t('dataPages.governanceStatActive') }}</span>
          <strong>{{ activeEndpointCount }}</strong>
        </article>
        <article class="governance-metric">
          <el-icon aria-hidden="true">
            <DataAnalysis />
          </el-icon>
          <span>{{ t('dataPages.governanceStatRateLimit') }}</span>
          <strong>{{ totalRateLimit }}</strong>
        </article>
      </div>
    </section>

    <div class="governance-grid">
      <el-card
        class="governance-panel governance-provider-panel"
        data-test="governance-providers-panel"
      >
        <template #header>
          <div class="governance-panel-heading">
            <div>
              <div class="governance-kicker">
                {{ t('dataPages.governanceProviderKicker') }}
              </div>
              <div class="governance-panel-title">
                {{ t('dataPages.governanceProviderTitle') }}
              </div>
              <p>{{ t('dataPages.governanceProviderDesc') }}</p>
            </div>
          </div>
        </template>

        <div
          v-if="!loading && providers.length === 0"
          class="governance-empty"
        >
          <strong>{{ t('dataPages.governanceNoProvidersTitle') }}</strong>
          <span>{{ t('dataPages.governanceNoProvidersDesc') }}</span>
        </div>

        <div
          v-else
          class="provider-list"
          data-test="governance-provider-list"
        >
          <article
            v-for="provider in providers"
            :key="provider.id"
            class="provider-card"
            :class="{ 'is-selected': selectedProviderId === provider.provider_id }"
            @click="selectProvider(provider.provider_id)"
          >
            <div class="provider-card-head">
              <div>
                <strong>{{ provider.name || provider.provider_id }}</strong>
                <span>{{ provider.provider_id }}</span>
              </div>
              <el-tag :type="provider.is_active ? 'success' : 'warning'">
                {{ provider.is_active ? t('dataPages.governanceActive') : t('dataPages.governanceInactive') }}
              </el-tag>
            </div>
            <div class="provider-card-grid">
              <span>{{ t('dataPages.governanceCategory') }}</span>
              <strong>{{ provider.category }}</strong>
              <span>{{ t('dataPages.governanceAuth') }}</span>
              <strong>{{ provider.auth_type }}</strong>
              <span>{{ t('dataPages.governanceRateLimit') }}</span>
              <strong>{{ provider.rate_limit }}</strong>
            </div>
          </article>
        </div>
      </el-card>

      <el-card
        class="governance-panel governance-endpoint-panel"
        data-test="governance-endpoints-panel"
      >
        <template #header>
          <div class="governance-panel-heading">
            <div>
              <div class="governance-kicker">
                {{ t('dataPages.governanceEndpointKicker') }}
              </div>
              <div class="governance-panel-title">
                {{ t('dataPages.governanceEndpoints') }}
              </div>
              <p>{{ t('dataPages.governanceEndpointDesc') }}</p>
            </div>
            <div class="governance-count">
              {{ t('dataPages.governanceVisibleCount', { count: filteredEndpoints.length }) }}
              <span>{{ t('dataPages.governanceTotalCount', { count: endpoints.length }) }}</span>
            </div>
          </div>
        </template>

        <div class="governance-toolbar">
          <el-select
            v-model="selectedProviderId"
            clearable
            class="toolbar-item"
            :placeholder="t('dataPages.governanceProviderFilter')"
            @change="handleProviderChange"
          >
            <el-option
              v-for="provider in providers"
              :key="provider.provider_id"
              :label="provider.name || provider.provider_id"
              :value="provider.provider_id"
            />
          </el-select>
          <el-input
            v-model="endpointSearch"
            clearable
            class="toolbar-search"
            :prefix-icon="Search"
            :placeholder="t('dataPages.governanceEndpointSearch')"
          />
        </div>

        <div
          v-if="!loading && filteredEndpoints.length === 0"
          class="governance-empty"
        >
          <strong>{{ t('dataPages.governanceNoEndpointsTitle') }}</strong>
          <span>{{ t('dataPages.governanceNoEndpointsDesc') }}</span>
        </div>

        <template v-else>
          <el-table
            v-loading="loading"
            :data="filteredEndpoints"
            stripe
            class="governance-endpoints-table"
            data-test="governance-endpoints-table"
          >
            <el-table-column
              :label="t('dataPages.governanceEndpointName')"
              min-width="240"
            >
              <template #default="{ row }">
                <div class="endpoint-name-cell">
                  <strong>{{ row.display_name || row.endpoint_name }}</strong>
                  <span>{{ row.endpoint_name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('dataPages.governanceProvider')"
              min-width="150"
            >
              <template #default="{ row }">
                {{ providerLabel(row.provider_id) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="category"
              :label="t('dataPages.governanceCategory')"
              width="130"
            />
            <el-table-column
              :label="t('dataPages.governanceTarget')"
              min-width="200"
            >
              <template #default="{ row }">
                <div class="table-main">
                  {{ row.target_database }}
                </div>
                <div class="table-subtext">
                  {{ row.target_table || t('dataPages.governanceNoTargetTable') }}
                </div>
              </template>
            </el-table-column>
            <el-table-column
              prop="incremental_sync_key"
              :label="t('dataPages.governanceIncrementalKey')"
              min-width="150"
            />
            <el-table-column
              :label="t('dataPages.governanceCacheTtl')"
              width="130"
            >
              <template #default="{ row }">
                {{ formatCacheTtl(row.cache_ttl_sec) }}
              </template>
            </el-table-column>
            <el-table-column
              :label="t('dataPages.governanceStatus')"
              width="110"
            >
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'warning'">
                  {{ row.is_active ? t('dataPages.governanceActive') : t('dataPages.governanceInactive') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('dataPages.governanceActions')"
              fixed="right"
              width="120"
            >
              <template #default="{ row }">
                <el-button
                  link
                  type="primary"
                  @click="openEndpoint(row)"
                >
                  {{ t('dataPages.governanceActionInspect') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div
            class="governance-mobile-list"
            data-test="governance-mobile-list"
          >
            <article
              v-for="endpoint in filteredEndpoints"
              :key="endpoint.id"
              class="endpoint-card"
            >
              <div class="endpoint-card-head">
                <div>
                  <strong>{{ endpoint.display_name || endpoint.endpoint_name }}</strong>
                  <span>{{ endpoint.endpoint_name }}</span>
                </div>
                <el-tag :type="endpoint.is_active ? 'success' : 'warning'">
                  {{ endpoint.is_active ? t('dataPages.governanceActive') : t('dataPages.governanceInactive') }}
                </el-tag>
              </div>
              <div class="endpoint-card-grid">
                <span>{{ t('dataPages.governanceProvider') }}</span>
                <strong>{{ providerLabel(endpoint.provider_id) }}</strong>
                <span>{{ t('dataPages.governanceCategory') }}</span>
                <strong>{{ endpoint.category }}</strong>
                <span>{{ t('dataPages.governanceTarget') }}</span>
                <strong>{{ endpoint.target_database }} / {{ endpoint.target_table || '-' }}</strong>
                <span>{{ t('dataPages.governanceIncrementalKey') }}</span>
                <strong>{{ endpoint.incremental_sync_key || '-' }}</strong>
              </div>
              <el-button
                size="small"
                type="primary"
                @click="openEndpoint(endpoint)"
              >
                {{ t('dataPages.governanceActionInspect') }}
              </el-button>
            </article>
          </div>
        </template>
      </el-card>
    </div>

    <el-drawer
      v-model="detailVisible"
      :title="t('dataPages.governanceDetailTitle')"
      size="58%"
      class="governance-detail-drawer"
    >
      <div
        v-if="currentEndpoint"
        class="governance-detail"
        data-test="governance-detail"
      >
        <section class="detail-summary">
          <div>
            <div class="governance-kicker">
              {{ t('dataPages.governanceDetailKicker') }}
            </div>
            <h3>{{ currentEndpoint.display_name || currentEndpoint.endpoint_name }}</h3>
            <p>{{ currentEndpoint.function_path || currentEndpoint.endpoint_name }}</p>
          </div>
          <el-tag :type="currentEndpoint.is_active ? 'success' : 'warning'">
            {{ currentEndpoint.is_active ? t('dataPages.governanceActive') : t('dataPages.governanceInactive') }}
          </el-tag>
        </section>

        <div class="detail-meta-grid">
          <div>
            <span>{{ t('dataPages.governanceProvider') }}</span>
            <strong>{{ providerLabel(currentEndpoint.provider_id) }}</strong>
          </div>
          <div>
            <span>{{ t('dataPages.governanceCategory') }}</span>
            <strong>{{ currentEndpoint.category }}</strong>
          </div>
          <div>
            <span>{{ t('dataPages.governanceTarget') }}</span>
            <strong>{{ currentEndpoint.target_database }} / {{ currentEndpoint.target_table || '-' }}</strong>
          </div>
          <div>
            <span>{{ t('dataPages.governanceRateLimit') }}</span>
            <strong>{{ currentEndpoint.rate_limit }}</strong>
          </div>
          <div>
            <span>{{ t('dataPages.governanceCacheTtl') }}</span>
            <strong>{{ formatCacheTtl(currentEndpoint.cache_ttl_sec) }}</strong>
          </div>
          <div>
            <span>{{ t('dataPages.governanceIncrementalKey') }}</span>
            <strong>{{ currentEndpoint.incremental_sync_key || '-' }}</strong>
          </div>
        </div>

        <div class="detail-section">
          <div class="section-title">
            {{ t('dataPages.governancePreviewParams') }}
          </div>
          <el-input
            v-model="previewParamsText"
            type="textarea"
            :rows="5"
          />
          <div class="detail-actions">
            <el-button
              type="primary"
              :loading="previewLoading"
              @click="previewEndpoint"
            >
              {{ t('dataPages.governancePreview') }}
            </el-button>
            <el-button
              :loading="jobLoading"
              @click="createIngestionJob"
            >
              {{ t('dataPages.governanceCreateJob') }}
            </el-button>
          </div>
        </div>

        <div class="detail-section">
          <div class="section-title">
            {{ t('dataPages.governanceParamsSchema') }}
          </div>
          <pre>{{ toJsonText(currentEndpoint.params_schema || {}) }}</pre>
        </div>

        <div class="detail-section">
          <div class="section-title">
            {{ t('dataPages.governanceQualityProfile') }}
          </div>
          <pre>{{ toJsonText(currentEndpoint.quality_profile || {}) }}</pre>
        </div>

        <div
          v-if="previewResult"
          class="detail-section"
          data-test="governance-preview-result"
        >
          <div class="section-title">
            {{ t('dataPages.governancePreviewResult') }}
          </div>
          <div class="preview-metadata">
            <div>
              <span>{{ t('dataPages.governancePreviewRows') }}</span>
              <strong>{{ previewResult.rows.length }}</strong>
            </div>
            <div>
              <span>{{ t('dataPages.governancePreviewLatency') }}</span>
              <strong>{{ previewResult.provider_latency_ms }}ms</strong>
            </div>
            <div>
              <span>{{ t('dataPages.governancePreviewTimestamp') }}</span>
              <strong>{{ formatDateTime(previewResult.source_timestamp) }}</strong>
            </div>
          </div>
          <el-table
            :data="previewResult.rows.slice(0, 5)"
            stripe
            class="preview-table"
          >
            <el-table-column
              v-for="column in previewResult.columns"
              :key="column"
              :prop="column"
              :label="column"
              min-width="120"
            />
          </el-table>
          <p
            v-if="previewResult.quality_warnings.length > 0"
            class="preview-warning"
          >
            {{ previewResult.quality_warnings.join(' / ') }}
          </p>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  CircleCheck,
  Connection,
  DataAnalysis,
  Document,
  Refresh,
  Search,
} from '@element-plus/icons-vue'
import { getErrorMessage } from '@/api/index'
import {
  dataGovernanceApi,
  type DataGovernanceEndpoint,
  type DataGovernanceProvider,
  type DataPreviewResponse,
} from '@/api/dataGovernance'
import { parseJsonText, toJsonText } from '@/views/data/utils'

const { t } = useI18n()

const loading = ref(false)
const previewLoading = ref(false)
const jobLoading = ref(false)
const providers = ref<DataGovernanceProvider[]>([])
const endpoints = ref<DataGovernanceEndpoint[]>([])
const selectedProviderId = ref<string | undefined>(undefined)
const endpointSearch = ref('')
const detailVisible = ref(false)
const currentEndpoint = ref<DataGovernanceEndpoint | null>(null)
const previewParamsText = ref('{}')
const previewResult = ref<DataPreviewResponse | null>(null)

const providerNameMap = computed(() =>
  Object.fromEntries(providers.value.map((item) => [item.provider_id, item.name || item.provider_id]))
)
const activeEndpointCount = computed(() => endpoints.value.filter((item) => item.is_active).length)
const totalRateLimit = computed(() =>
  endpoints.value.reduce((sum, item) => sum + (Number.isFinite(item.rate_limit) ? item.rate_limit : 0), 0)
)
const filteredEndpoints = computed(() => {
  const keyword = endpointSearch.value.trim().toLowerCase()
  if (!keyword) return endpoints.value
  return endpoints.value.filter((item) => {
    return [
      item.endpoint_name,
      item.display_name,
      item.provider_id,
      item.category,
      item.target_database,
      item.target_table,
      item.function_path,
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword))
  })
})

function providerLabel(providerId: string) {
  return providerNameMap.value[providerId] || providerId
}

function formatCacheTtl(value: number) {
  if (!value) return t('dataPages.governanceNoCache')
  if (value < 60) return `${value}s`
  const minutes = Math.round(value / 60)
  if (minutes < 60) return `${minutes}m`
  return `${Math.round(minutes / 60)}h`
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

async function loadProviders() {
  const response = await dataGovernanceApi.listProviders()
  providers.value = response.items
}

async function loadEndpoints() {
  const response = await dataGovernanceApi.listEndpoints(selectedProviderId.value)
  endpoints.value = response.items
}

async function bootstrapAndLoad() {
  loading.value = true
  try {
    await dataGovernanceApi.bootstrap()
    await Promise.all([loadProviders(), loadEndpoints()])
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.governanceLoadFailed')))
  } finally {
    loading.value = false
  }
}

async function handleProviderChange() {
  loading.value = true
  try {
    await loadEndpoints()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.governanceLoadEndpointsFailed')))
  } finally {
    loading.value = false
  }
}

function selectProvider(providerId: string) {
  selectedProviderId.value = selectedProviderId.value === providerId ? undefined : providerId
  void handleProviderChange()
}

function openEndpoint(endpoint: DataGovernanceEndpoint) {
  currentEndpoint.value = endpoint
  previewParamsText.value = '{}'
  previewResult.value = null
  detailVisible.value = true
}

async function previewEndpoint() {
  if (!currentEndpoint.value) return
  previewLoading.value = true
  try {
    previewResult.value = await dataGovernanceApi.previewEndpoint(
      currentEndpoint.value.id,
      parseJsonText(previewParamsText.value)
    )
    ElMessage.success(t('dataPages.governancePreviewLoaded'))
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.governancePreviewFailed')))
  } finally {
    previewLoading.value = false
  }
}

async function createIngestionJob() {
  if (!currentEndpoint.value) return
  jobLoading.value = true
  try {
    const result = await dataGovernanceApi.createJob(
      currentEndpoint.value.id,
      parseJsonText(previewParamsText.value)
    )
    ElMessage.success(t('dataPages.governanceJobCreated', { id: result.id }))
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.governanceJobFailed')))
  } finally {
    jobLoading.value = false
  }
}

onMounted(() => {
  void bootstrapAndLoad()
})
</script>

<style scoped>
.governance-page {
  display: grid;
  gap: 24px;
}

.governance-hero,
.governance-panel {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 1px 2px var(--shadow-color);
}

.governance-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  padding: 24px;
}

.governance-hero-copy {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.governance-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.governance-hero h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 30px;
  line-height: 1.12;
}

.governance-hero p,
.governance-panel-heading p,
.detail-summary p {
  max-width: 820px;
  margin: 0;
  color: var(--text-color-regular);
  line-height: 1.65;
}

.governance-hero-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.governance-metrics {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.governance-metric {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.governance-metric .el-icon {
  color: var(--primary-color);
  font-size: 18px;
}

.governance-metric span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.governance-metric strong {
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.governance-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.36fr) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.governance-panel {
  min-width: 0;
  box-shadow: none;
}

.governance-panel :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.governance-panel :deep(.el-card__body) {
  padding: 18px;
}

.governance-panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.governance-panel-title {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 780;
  line-height: 1.25;
}

.governance-count {
  display: grid;
  flex: none;
  gap: 4px;
  min-width: 120px;
  padding: 10px 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-primary);
  font-size: 13px;
  font-weight: 720;
  line-height: 1.35;
  text-align: right;
}

.governance-count span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.provider-list {
  display: grid;
  gap: 12px;
}

.provider-card,
.endpoint-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.provider-card {
  cursor: pointer;
}

.provider-card.is-selected {
  border-color: var(--primary-color);
  background: var(--primary-color-light);
}

.provider-card-head,
.endpoint-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.provider-card-head > div,
.endpoint-card-head > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.provider-card-head strong,
.endpoint-card-head strong {
  color: var(--text-color-primary);
  line-height: 1.3;
}

.provider-card-head span,
.endpoint-card-head span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.provider-card-grid,
.endpoint-card-grid {
  display: grid;
  grid-template-columns: minmax(80px, 0.36fr) minmax(0, 1fr);
  gap: 8px 10px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.provider-card-grid span,
.endpoint-card-grid span,
.preview-metadata span,
.detail-meta-grid span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.provider-card-grid strong,
.endpoint-card-grid strong,
.preview-metadata strong,
.detail-meta-grid strong {
  color: var(--text-color-primary);
  overflow-wrap: break-word;
}

.governance-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.toolbar-item {
  width: 220px;
}

.toolbar-search {
  width: min(380px, 100%);
}

.governance-empty {
  display: grid;
  gap: 8px;
  min-height: 180px;
  place-items: center;
  padding: 28px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  text-align: center;
}

.governance-empty strong {
  color: var(--text-color-primary);
  font-size: 18px;
}

.governance-empty span {
  max-width: 520px;
  color: var(--text-color-secondary);
  line-height: 1.5;
}

.governance-endpoints-table {
  width: 100%;
}

.governance-endpoints-table :deep(.el-table__header-wrapper th),
.preview-table :deep(.el-table__header-wrapper th) {
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-weight: 760;
}

.endpoint-name-cell {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.endpoint-name-cell strong,
.table-main {
  color: var(--text-color-primary);
  font-weight: 760;
  line-height: 1.35;
}

.endpoint-name-cell span,
.table-subtext {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.governance-mobile-list {
  display: none;
  gap: 12px;
}

.governance-detail {
  display: grid;
  gap: 18px;
}

.detail-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.detail-summary h3 {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1.25;
}

.detail-meta-grid,
.preview-metadata {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.detail-meta-grid div,
.preview-metadata div {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.detail-section {
  display: grid;
  gap: 10px;
}

.section-title {
  color: var(--text-color-primary);
  font-weight: 760;
}

.detail-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.governance-detail :deep(.el-textarea__inner) {
  border-radius: 8px;
  background: var(--bg-color-overlay);
  color: var(--text-color-primary);
}

pre {
  max-height: 280px;
  margin: 0;
  padding: 14px;
  overflow: auto;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--code-bg-color);
  color: var(--code-text-color);
  line-height: 1.5;
}

.preview-table {
  width: 100%;
}

.preview-warning {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--warning-border-color);
  border-radius: 8px;
  background: var(--warning-surface);
  color: var(--warning-text-color);
  line-height: 1.45;
}

@media (max-width: 1180px) {
  .governance-grid {
    grid-template-columns: 1fr;
  }

  .provider-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 1100px) {
  .governance-hero,
  .governance-panel-heading {
    display: grid;
    grid-template-columns: 1fr;
  }

  .governance-hero-actions {
    justify-content: flex-start;
  }

  .governance-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .governance-count {
    width: fit-content;
    text-align: left;
  }
}

@media (max-width: 900px) {
  .governance-endpoints-table {
    display: none;
  }

  .governance-mobile-list {
    display: grid;
  }
}

@media (max-width: 700px) {
  .provider-list,
  .detail-meta-grid,
  .preview-metadata {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .governance-hero {
    padding: 18px;
  }

  .governance-hero h1 {
    font-size: 24px;
  }

  .governance-metrics {
    grid-template-columns: 1fr;
  }

  .governance-hero-actions,
  .governance-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .governance-hero-actions :deep(.el-button),
  .governance-toolbar :deep(.el-button),
  .toolbar-item,
  .toolbar-search {
    width: 100%;
  }
}
</style>
