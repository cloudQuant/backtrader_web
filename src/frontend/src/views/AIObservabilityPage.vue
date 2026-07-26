<template>
  <div
    class="ai-observability-page"
    data-test="ai-observability-page"
  >
    <section
      class="ai-observability-hero"
      data-test="ai-observability-hero"
    >
      <div class="ai-observability-hero-copy">
        <div class="observability-kicker">
          {{ t('aiObs.heroKicker') }}
        </div>
        <h1>{{ t('aiObs.heroTitle') }}</h1>
        <p>{{ t('aiObs.heroDesc') }}</p>
      </div>

      <div class="ai-observability-hero-actions">
        <el-button
          type="primary"
          :icon="Refresh"
          :loading="loading"
          @click="loadDashboard"
        >
          {{ t('aiObs.btnRefresh') }}
        </el-button>
      </div>

      <div
        class="observability-metrics"
        data-test="ai-observability-metrics"
      >
        <article class="observability-metric">
          <el-icon aria-hidden="true">
            <TrendCharts />
          </el-icon>
          <span>{{ t('aiObs.sumTotalCalls') }}</span>
          <strong>{{ formatInteger(usage?.summary.total_calls) }}</strong>
        </article>
        <article class="observability-metric">
          <el-icon aria-hidden="true">
            <Cpu />
          </el-icon>
          <span>{{ t('aiObs.sumTotalTokens') }}</span>
          <strong>{{ formatInteger(usage?.summary.total_tokens) }}</strong>
        </article>
        <article class="observability-metric">
          <el-icon aria-hidden="true">
            <Money />
          </el-icon>
          <span>{{ t('aiObs.sumEstCost') }}</span>
          <strong>{{ formatUsd(usage?.summary.estimated_cost_usd) }}</strong>
        </article>
        <article class="observability-metric">
          <el-icon aria-hidden="true">
            <Warning />
          </el-icon>
          <span>{{ t('aiObs.sumFailedCalls') }}</span>
          <strong>{{ formatInteger(usage?.summary.failed_calls) }}</strong>
        </article>
      </div>
    </section>

    <el-card
      class="observability-panel filter-panel"
      data-test="ai-observability-filters"
    >
      <template #header>
        <div class="observability-panel-heading">
          <div>
            <div class="observability-kicker">
              {{ t('aiObs.filterKicker') }}
            </div>
            <div class="observability-panel-title">
              {{ t('aiObs.filterTitle') }}
            </div>
            <p>{{ t('aiObs.filterDesc') }}</p>
          </div>
        </div>
      </template>

      <div class="observability-filters">
        <el-input
          v-model="serviceFilter"
          clearable
          :prefix-icon="Search"
          :placeholder="t('aiObs.filterServicePh')"
        />
        <el-input
          v-model="modelFilter"
          clearable
          :prefix-icon="Search"
          :placeholder="t('aiObs.filterModelPh')"
        />
        <el-input
          v-model="startAt"
          clearable
          :placeholder="t('aiObs.filterStartPh')"
        />
        <el-input
          v-model="endAt"
          clearable
          :placeholder="t('aiObs.filterEndPh')"
        />
        <div class="filter-actions">
          <el-button
            type="primary"
            :loading="loading"
            @click="loadDashboard"
          >
            {{ t('aiObs.btnApply') }}
          </el-button>
          <el-button @click="resetFilters">
            {{ t('common.reset') }}
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card
      class="observability-panel observability-workbench"
      data-test="ai-observability-workbench"
    >
      <template #header>
        <div class="observability-panel-heading">
          <div>
            <div class="observability-kicker">
              {{ t('aiObs.workbenchKicker') }}
            </div>
            <div class="observability-panel-title">
              {{ t('aiObs.workbenchTitle') }}
            </div>
            <p>{{ t('aiObs.workbenchDesc') }}</p>
          </div>
          <div class="observability-count">
            {{ t('aiObs.failureRateLabel', { rate: formatPercent(failureRate) }) }}
            <span>{{ t('aiObs.latencyLabel', { ms: formatMs(slowCalls?.summary.p95_latency_ms) }) }}</span>
          </div>
        </div>
      </template>

      <el-tabs
        v-model="activeTab"
        class="observability-tabs"
      >
        <el-tab-pane
          :label="t('aiObs.tabUsage')"
          name="usage"
        >
          <div class="usage-grid">
            <section class="observability-subpanel">
              <div class="subpanel-heading">
                <div>
                  <div class="observability-kicker">
                    {{ t('aiObs.usageServiceKicker') }}
                  </div>
                  <h3>{{ t('aiObs.cardByService') }}</h3>
                </div>
              </div>

              <el-table
                :data="usage?.by_service ?? []"
                stripe
                class="observability-table"
                data-test="ai-usage-service-table"
              >
                <el-table-column
                  prop="service_name"
                  :label="t('aiObs.colService')"
                  min-width="150"
                />
                <el-table-column
                  prop="total_calls"
                  :label="t('aiObs.colCallCount')"
                  width="100"
                />
                <el-table-column
                  prop="total_tokens"
                  :label="t('aiObs.colTokens')"
                  width="120"
                >
                  <template #default="{ row }">
                    {{ formatInteger(row.total_tokens) }}
                  </template>
                </el-table-column>
                <el-table-column
                  :label="t('aiObs.colCost')"
                  width="120"
                >
                  <template #default="{ row }">
                    {{ formatUsd(row.estimated_cost_usd) }}
                  </template>
                </el-table-column>
              </el-table>

              <div
                class="observability-mobile-list"
                data-test="ai-usage-service-cards"
              >
                <article
                  v-for="item in usage?.by_service ?? []"
                  :key="item.service_name || 'unknown-service'"
                  class="observability-card"
                >
                  <div class="card-head">
                    <strong>{{ item.service_name || '-' }}</strong>
                    <el-tag>{{ formatUsd(item.estimated_cost_usd) }}</el-tag>
                  </div>
                  <div class="card-grid">
                    <span>{{ t('aiObs.colCallCount') }}</span>
                    <strong>{{ formatInteger(item.total_calls) }}</strong>
                    <span>{{ t('aiObs.colTokens') }}</span>
                    <strong>{{ formatInteger(item.total_tokens) }}</strong>
                    <span>{{ t('aiObs.statAvg') }}</span>
                    <strong>{{ formatMs(item.avg_latency_ms) }}</strong>
                  </div>
                </article>
              </div>
            </section>

            <section class="observability-subpanel">
              <div class="subpanel-heading">
                <div>
                  <div class="observability-kicker">
                    {{ t('aiObs.usageModelKicker') }}
                  </div>
                  <h3>{{ t('aiObs.cardByModel') }}</h3>
                </div>
              </div>

              <el-table
                :data="usage?.by_model ?? []"
                stripe
                class="observability-table"
                data-test="ai-usage-model-table"
              >
                <el-table-column
                  prop="model_name"
                  :label="t('aiObs.colModel')"
                  min-width="180"
                />
                <el-table-column
                  prop="total_calls"
                  :label="t('aiObs.colCallCount')"
                  width="100"
                />
                <el-table-column
                  prop="total_tokens"
                  :label="t('aiObs.colTokens')"
                  width="120"
                >
                  <template #default="{ row }">
                    {{ formatInteger(row.total_tokens) }}
                  </template>
                </el-table-column>
                <el-table-column
                  :label="t('aiObs.colCost')"
                  width="120"
                >
                  <template #default="{ row }">
                    {{ formatUsd(row.estimated_cost_usd) }}
                  </template>
                </el-table-column>
              </el-table>

              <div
                class="observability-mobile-list"
                data-test="ai-usage-model-cards"
              >
                <article
                  v-for="item in usage?.by_model ?? []"
                  :key="item.model_name || 'unknown-model'"
                  class="observability-card"
                >
                  <div class="card-head">
                    <strong>{{ item.model_name || '-' }}</strong>
                    <el-tag>{{ formatUsd(item.estimated_cost_usd) }}</el-tag>
                  </div>
                  <div class="card-grid">
                    <span>{{ t('aiObs.colCallCount') }}</span>
                    <strong>{{ formatInteger(item.total_calls) }}</strong>
                    <span>{{ t('aiObs.colTokens') }}</span>
                    <strong>{{ formatInteger(item.total_tokens) }}</strong>
                    <span>{{ t('aiObs.statAvg') }}</span>
                    <strong>{{ formatMs(item.avg_latency_ms) }}</strong>
                  </div>
                </article>
              </div>
            </section>
          </div>

          <section class="observability-subpanel day-panel">
            <div class="subpanel-heading">
              <div>
                <div class="observability-kicker">
                  {{ t('aiObs.usageTrendKicker') }}
                </div>
                <h3>{{ t('aiObs.cardByDay') }}</h3>
              </div>
            </div>
            <div class="day-strip">
              <article
                v-for="item in usage?.by_day ?? []"
                :key="item.date"
                class="day-item"
              >
                <span>{{ item.date || '-' }}</span>
                <strong>{{ formatInteger(item.total_calls) }}</strong>
                <small>{{ formatUsd(item.estimated_cost_usd) }}</small>
              </article>
            </div>
          </section>
        </el-tab-pane>

        <el-tab-pane
          :label="t('aiObs.tabFailures')"
          name="failures"
        >
          <div class="failure-grid">
            <section class="observability-subpanel">
              <div class="subpanel-heading">
                <div>
                  <div class="observability-kicker">
                    {{ t('aiObs.failureCodeKicker') }}
                  </div>
                  <h3>{{ t('aiObs.cardErrorCodes') }}</h3>
                </div>
              </div>
              <div class="error-chip-list">
                <el-tag
                  v-for="item in failures?.by_error_code ?? []"
                  :key="item.error_code || 'unknown'"
                  type="danger"
                >
                  {{ item.error_code || 'unknown' }} x {{ item.failed_calls }}
                </el-tag>
              </div>
              <el-table
                :data="failures?.by_error_code ?? []"
                stripe
                class="observability-table"
                data-test="ai-failure-code-table"
              >
                <el-table-column
                  prop="error_code"
                  :label="t('aiObs.colErrorCode')"
                  min-width="160"
                />
                <el-table-column
                  prop="failed_calls"
                  :label="t('aiObs.colFailedCount')"
                  width="130"
                />
              </el-table>
            </section>

            <section class="observability-subpanel">
              <div class="subpanel-heading">
                <div>
                  <div class="observability-kicker">
                    {{ t('aiObs.failureRecentKicker') }}
                  </div>
                  <h3>{{ t('aiObs.cardRecentFailures') }}</h3>
                </div>
              </div>
              <el-table
                :data="failures?.recent_failures ?? []"
                stripe
                class="observability-table"
                data-test="ai-recent-failure-table"
              >
                <el-table-column
                  prop="service_name"
                  :label="t('aiObs.colService')"
                  min-width="140"
                />
                <el-table-column
                  prop="error_code"
                  :label="t('aiObs.colErrorCode')"
                  min-width="140"
                />
                <el-table-column
                  prop="created_at"
                  :label="t('aiObs.colTime')"
                  min-width="170"
                >
                  <template #default="{ row }">
                    {{ formatDateTime(row.created_at) }}
                  </template>
                </el-table-column>
              </el-table>

              <div
                class="observability-mobile-list"
                data-test="ai-failure-cards"
              >
                <article
                  v-for="item in failures?.recent_failures ?? []"
                  :key="item.id"
                  class="observability-card"
                >
                  <div class="card-head">
                    <strong>{{ item.service_name }}</strong>
                    <el-tag type="danger">
                      {{ item.error_code || 'unknown' }}
                    </el-tag>
                  </div>
                  <div class="card-grid">
                    <span>{{ t('aiObs.colModel') }}</span>
                    <strong>{{ item.model_name || '-' }}</strong>
                    <span>{{ t('aiObs.colTime') }}</span>
                    <strong>{{ formatDateTime(item.created_at) }}</strong>
                    <span>{{ t('aiObs.colCost') }}</span>
                    <strong>{{ formatUsd(item.estimated_cost_usd) }}</strong>
                  </div>
                </article>
              </div>
            </section>
          </div>
        </el-tab-pane>

        <el-tab-pane
          :label="t('aiObs.tabSlow')"
          name="slow"
        >
          <div class="latency-metrics">
            <article class="latency-card">
              <span>{{ t('aiObs.statP95') }}</span>
              <strong>{{ formatMs(slowCalls?.summary.p95_latency_ms) }}</strong>
            </article>
            <article class="latency-card">
              <span>{{ t('aiObs.statP99') }}</span>
              <strong>{{ formatMs(slowCalls?.summary.p99_latency_ms) }}</strong>
            </article>
            <article class="latency-card">
              <span>{{ t('aiObs.statAvg') }}</span>
              <strong>{{ formatMs(slowCalls?.summary.avg_latency_ms) }}</strong>
            </article>
          </div>

          <section class="observability-subpanel">
            <div class="subpanel-heading">
              <div>
                <div class="observability-kicker">
                  {{ t('aiObs.slowTopKicker') }}
                </div>
                <h3>{{ t('aiObs.cardTopSlow') }}</h3>
              </div>
            </div>
            <el-table
              :data="slowCalls?.top_calls ?? []"
              stripe
              class="observability-table"
              data-test="ai-slow-call-table"
            >
              <el-table-column
                prop="service_name"
                :label="t('aiObs.colService')"
                min-width="140"
              />
              <el-table-column
                prop="model_name"
                :label="t('aiObs.colModel')"
                min-width="180"
              />
              <el-table-column
                prop="latency_ms"
                :label="t('aiObs.colLatencyMs')"
                width="130"
              >
                <template #default="{ row }">
                  {{ formatMs(row.latency_ms) }}
                </template>
              </el-table-column>
              <el-table-column
                prop="created_at"
                :label="t('aiObs.colTime')"
                min-width="170"
              >
                <template #default="{ row }">
                  {{ formatDateTime(row.created_at) }}
                </template>
              </el-table-column>
            </el-table>

            <div
              class="observability-mobile-list"
              data-test="ai-slow-call-cards"
            >
              <article
                v-for="item in slowCalls?.top_calls ?? []"
                :key="item.id"
                class="observability-card"
              >
                <div class="card-head">
                  <strong>{{ item.service_name }}</strong>
                  <el-tag type="warning">
                    {{ formatMs(item.latency_ms) }}
                  </el-tag>
                </div>
                <div class="card-grid">
                  <span>{{ t('aiObs.colModel') }}</span>
                  <strong>{{ item.model_name || '-' }}</strong>
                  <span>{{ t('aiObs.colTime') }}</span>
                  <strong>{{ formatDateTime(item.created_at) }}</strong>
                  <span>{{ t('aiObs.colTokens') }}</span>
                  <strong>{{ formatInteger(item.total_tokens) }}</strong>
                </div>
              </article>
            </div>
          </section>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  Cpu,
  Money,
  Refresh,
  Search,
  TrendCharts,
  Warning,
} from '@element-plus/icons-vue'

import { aiObservabilityApi } from '@/api/aiObservability'
import type {
  AIFailureStats,
  AIObservabilityQuery,
  AISlowCallStats,
  AIUsageStats,
} from '@/api/aiObservability'

const { t } = useI18n()

const activeTab = ref('usage')
const loading = ref(false)
const usage = ref<AIUsageStats | null>(null)
const failures = ref<AIFailureStats | null>(null)
const slowCalls = ref<AISlowCallStats | null>(null)
const serviceFilter = ref('')
const modelFilter = ref('')
const startAt = ref('')
const endAt = ref('')

const failureRate = computed(() => {
  const summary = failures.value?.summary || usage.value?.summary
  if (!summary) return 0
  if (typeof summary.failure_rate === 'number') return summary.failure_rate
  const totalCalls = summary.total_calls || 0
  return totalCalls > 0 ? (summary.failed_calls || 0) / totalCalls : 0
})

function buildFilters(): AIObservabilityQuery {
  const filters: AIObservabilityQuery = {}
  if (serviceFilter.value.trim()) filters.service_name = serviceFilter.value.trim()
  if (modelFilter.value.trim()) filters.model_name = modelFilter.value.trim()
  if (startAt.value.trim()) filters.start_at = startAt.value.trim()
  if (endAt.value.trim()) filters.end_at = endAt.value.trim()
  return filters
}

function formatUsd(value?: number): string {
  return `$${Number(value ?? 0).toFixed(6)}`
}

function formatInteger(value?: number): string {
  return Number(value ?? 0).toLocaleString()
}

function formatMs(value?: number): string {
  return `${Math.round(Number(value ?? 0)).toLocaleString()} ms`
}

function formatPercent(value?: number): string {
  return `${(Number(value ?? 0) * 100).toFixed(1)}%`
}

function formatDateTime(value?: string | null): string {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function resetFilters() {
  serviceFilter.value = ''
  modelFilter.value = ''
  startAt.value = ''
  endAt.value = ''
  void loadDashboard()
}

async function loadDashboard() {
  loading.value = true
  try {
    const filters = buildFilters()
    const [usageData, failureData, slowData] = await Promise.all([
      aiObservabilityApi.getAdminUsage(filters),
      aiObservabilityApi.getAdminFailures({ ...filters, limit: 50 }),
      aiObservabilityApi.getAdminSlowCalls({ ...filters, limit: 20 }),
    ])
    usage.value = usageData
    failures.value = failureData
    slowCalls.value = slowData
  } catch {
    ElMessage.error(t('aiObs.msgLoadFailed'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadDashboard()
})
</script>

<style scoped>
.ai-observability-page {
  display: grid;
  gap: 24px;
}

.ai-observability-hero,
.observability-panel {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 1px 2px var(--shadow-color);
}

.ai-observability-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  padding: 24px;
}

.ai-observability-hero-copy {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.observability-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.ai-observability-hero h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 30px;
  line-height: 1.12;
}

.ai-observability-hero p,
.observability-panel-heading p {
  max-width: 840px;
  margin: 0;
  color: var(--text-color-regular);
  line-height: 1.65;
}

.ai-observability-hero-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.observability-metrics {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.observability-metric {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.observability-metric .el-icon {
  color: var(--primary-color);
  font-size: 18px;
}

.observability-metric span,
.latency-card span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.observability-metric strong,
.latency-card strong {
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.observability-panel {
  min-width: 0;
  box-shadow: none;
}

.observability-panel :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.observability-panel :deep(.el-card__body) {
  padding: 18px;
}

.observability-panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.observability-panel-title {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 780;
  line-height: 1.25;
}

.observability-count {
  display: grid;
  flex: none;
  gap: 4px;
  min-width: 160px;
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

.observability-count span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.observability-filters {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr)) auto;
  gap: 12px;
  align-items: center;
}

.filter-actions,
.error-chip-list,
.row-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-actions {
  justify-content: flex-end;
}

.observability-tabs :deep(.el-tabs__nav-wrap::after) {
  background: var(--border-color-light);
}

.observability-tabs :deep(.el-tabs__item) {
  color: var(--text-color-secondary);
}

.observability-tabs :deep(.el-tabs__item.is-active) {
  color: var(--primary-color);
}

.observability-tabs :deep(.el-tabs__active-bar) {
  background: var(--primary-color);
}

.usage-grid,
.failure-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.observability-subpanel {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.day-panel {
  margin-top: 16px;
}

.subpanel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.subpanel-heading h3 {
  margin: 4px 0 0;
  color: var(--text-color-primary);
  font-size: 16px;
  line-height: 1.25;
}

.observability-table {
  width: 100%;
}

.observability-table :deep(.el-table__header-wrapper th) {
  background: var(--bg-color);
  color: var(--text-color-secondary);
  font-weight: 760;
}

.observability-mobile-list {
  display: none;
  gap: 12px;
}

.observability-card {
  display: grid;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.card-head strong {
  color: var(--text-color-primary);
  overflow-wrap: anywhere;
}

.card-grid {
  display: grid;
  grid-template-columns: minmax(100px, 0.35fr) minmax(0, 1fr);
  gap: 8px 10px;
}

.card-grid span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.card-grid strong {
  color: var(--text-color-primary);
  overflow-wrap: break-word;
}

.day-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}

.day-item {
  display: grid;
  gap: 5px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.day-item span,
.day-item small {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.day-item strong {
  color: var(--text-color-primary);
  font-size: 18px;
}

.latency-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.latency-card {
  display: grid;
  gap: 8px;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

@media (max-width: 1180px) {
  .observability-metrics,
  .latency-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .observability-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .filter-actions {
    justify-content: flex-start;
  }
}

@media (max-width: 1100px) {
  .usage-grid,
  .failure-grid {
    grid-template-columns: 1fr;
  }

  .observability-table {
    display: none;
  }

  .observability-mobile-list {
    display: grid;
  }
}

@media (max-width: 900px) {
  .ai-observability-hero {
    grid-template-columns: 1fr;
  }

  .ai-observability-hero-actions {
    justify-content: flex-start;
  }

  .observability-panel-heading {
    display: grid;
  }

  .observability-count {
    width: 100%;
    text-align: left;
  }
}

@media (max-width: 620px) {
  .ai-observability-page {
    gap: 16px;
  }

  .ai-observability-hero {
    padding: 18px;
  }

  .ai-observability-hero h1 {
    font-size: 24px;
  }

  .observability-metrics,
  .observability-filters,
  .latency-metrics,
  .card-grid {
    grid-template-columns: 1fr;
  }

  .observability-panel :deep(.el-card__body) {
    padding: 14px;
  }

  .card-head {
    display: grid;
  }
}
</style>
