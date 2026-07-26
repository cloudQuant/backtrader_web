<template>
  <div
    class="airflow-page"
    data-test="airflow-page"
  >
    <section
      class="airflow-hero"
      data-test="airflow-hero"
    >
      <div class="airflow-hero-copy">
        <div class="airflow-kicker">
          {{ t('dataPages.airflowHeroKicker') }}
        </div>
        <h1>{{ t('dataPages.airflowTitle') }}</h1>
        <p>{{ t('dataPages.airflowDesc') }}</p>
      </div>

      <div class="airflow-hero-actions">
        <el-button
          type="primary"
          :icon="Refresh"
          :loading="loading"
          @click="refreshAll"
        >
          {{ t('dataPages.airflowRefresh') }}
        </el-button>
      </div>

      <div
        class="airflow-metrics"
        data-test="airflow-metrics"
      >
        <article class="airflow-metric">
          <el-icon aria-hidden="true">
            <Connection />
          </el-icon>
          <span>{{ t('dataPages.airflowStatBackend') }}</span>
          <strong>{{ backendLabel }}</strong>
        </article>
        <article class="airflow-metric">
          <el-icon aria-hidden="true">
            <Operation />
          </el-icon>
          <span>{{ t('dataPages.airflowStatDags') }}</span>
          <strong>{{ totalDagCount }}</strong>
        </article>
        <article class="airflow-metric">
          <el-icon aria-hidden="true">
            <CircleCheck />
          </el-icon>
          <span>{{ t('dataPages.airflowStatRunning') }}</span>
          <strong>{{ runningDagCount }}</strong>
        </article>
        <article class="airflow-metric">
          <el-icon aria-hidden="true">
            <VideoPause />
          </el-icon>
          <span>{{ t('dataPages.airflowStatPaused') }}</span>
          <strong>{{ pausedDagCount }}</strong>
        </article>
      </div>
    </section>

    <el-alert
      v-if="orchestrationStatus && !isAirflowBackend"
      type="info"
      :closable="false"
      class="airflow-notice"
    >
      <template #title>
        {{ t('dataPages.airflowBackend', { backend: backendLabel }) }}
      </template>
      {{ t('dataPages.airflowNotConnected') }}
    </el-alert>

    <el-card
      class="airflow-workbench"
      data-test="airflow-workbench"
    >
      <template #header>
        <div class="airflow-panel-heading">
          <div>
            <div class="airflow-kicker">
              {{ t('dataPages.airflowWorkbenchKicker') }}
            </div>
            <div class="airflow-panel-title">
              {{ t('dataPages.airflowWorkbenchTitle') }}
            </div>
            <p>{{ t('dataPages.airflowWorkbenchDesc') }}</p>
          </div>
          <div class="airflow-count">
            {{ t('dataPages.airflowVisibleCount', { count: filteredDags.length }) }}
            <span>{{ t('dataPages.airflowTotalCount', { count: totalDagCount }) }}</span>
          </div>
        </div>
      </template>

      <div
        v-if="isAirflowBackend"
        class="airflow-toolbar"
      >
        <el-input
          v-model="dagSearch"
          clearable
          class="toolbar-search"
          :prefix-icon="Search"
          :placeholder="t('dataPages.airflowSearchPh')"
        />
        <el-select
          v-model="statusFilter"
          class="toolbar-item"
        >
          <el-option
            :label="t('dataPages.airflowFilterAll')"
            value="all"
          />
          <el-option
            :label="t('dataPages.airflowFilterRunning')"
            value="running"
          />
          <el-option
            :label="t('dataPages.airflowFilterPaused')"
            value="paused"
          />
        </el-select>
      </div>

      <div
        v-if="!loading && !isAirflowBackend"
        class="airflow-empty"
        data-test="airflow-empty"
      >
        <el-icon aria-hidden="true">
          <Connection />
        </el-icon>
        <strong>{{ t('dataPages.airflowEmptyTitle') }}</strong>
        <span>{{ t('dataPages.airflowEmptyDesc') }}</span>
      </div>

      <div
        v-else-if="!loading && filteredDags.length === 0"
        class="airflow-empty"
        data-test="airflow-empty"
      >
        <el-icon aria-hidden="true">
          <Clock />
        </el-icon>
        <strong>{{ t('dataPages.airflowNoDagsTitle') }}</strong>
        <span>{{ t('dataPages.airflowNoDagsDesc') }}</span>
      </div>

      <template v-else>
        <el-table
          v-loading="loading"
          :data="filteredDags"
          stripe
          class="airflow-table"
          data-test="airflow-table"
        >
          <el-table-column
            :label="t('dataPages.airflowColDagId')"
            min-width="260"
          >
            <template #default="{ row }">
              <div class="dag-name-cell">
                <strong>{{ row.dag_id }}</strong>
                <span>{{ row.description || t('dataPages.airflowNoDescription') }}</span>
                <div
                  v-if="row.tags?.length"
                  class="dag-tags"
                >
                  <el-tag
                    v-for="tag in row.tags"
                    :key="tag.name"
                    size="small"
                  >
                    {{ tag.name }}
                  </el-tag>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.airflowColSchedule')"
            min-width="150"
          >
            <template #default="{ row }">
              <div class="table-main">
                {{ formatSchedule(row.schedule_interval) }}
              </div>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.airflowColStatus')"
            width="150"
          >
            <template #default="{ row }">
              <el-tag :type="dagStatusType(row)">
                {{ dagStatusLabel(row) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.airflowColPause')"
            width="130"
          >
            <template #default="{ row }">
              <el-switch
                :model-value="!row.is_paused"
                :active-text="t('dataPages.airflowSwitchOn')"
                :inactive-text="t('dataPages.airflowSwitchOff')"
                data-testid="dag-pause-switch"
                @change="(val: string | number | boolean) => togglePause(row.dag_id, !(val as boolean))"
              />
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.airflowColActions')"
            fixed="right"
            min-width="190"
          >
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                data-testid="dag-trigger-btn"
                @click="triggerDag(row.dag_id)"
              >
                {{ t('dataPages.airflowExecute') }}
              </el-button>
              <el-button
                link
                data-testid="dag-runs-btn"
                @click="viewRuns(row)"
              >
                {{ t('dataPages.airflowHistory') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div
          class="airflow-mobile-list"
          data-test="airflow-mobile-list"
        >
          <article
            v-for="dag in filteredDags"
            :key="dag.dag_id"
            class="dag-card"
          >
            <div class="dag-card-head">
              <div>
                <strong>{{ dag.dag_id }}</strong>
                <span>{{ dag.description || t('dataPages.airflowNoDescription') }}</span>
              </div>
              <el-tag :type="dagStatusType(dag)">
                {{ dagStatusLabel(dag) }}
              </el-tag>
            </div>
            <div
              v-if="dag.tags?.length"
              class="dag-tags"
            >
              <el-tag
                v-for="tag in dag.tags"
                :key="tag.name"
                size="small"
              >
                {{ tag.name }}
              </el-tag>
            </div>
            <div class="dag-card-grid">
              <span>{{ t('dataPages.airflowColSchedule') }}</span>
              <strong>{{ formatSchedule(dag.schedule_interval) }}</strong>
              <span>{{ t('dataPages.airflowDagActive') }}</span>
              <strong>{{ dag.is_active ? t('common.yes') : t('common.no') }}</strong>
              <span>{{ t('dataPages.airflowDagPaused') }}</span>
              <strong>{{ dag.is_paused ? t('common.yes') : t('common.no') }}</strong>
            </div>
            <div class="dag-card-actions">
              <el-button
                size="small"
                type="primary"
                @click="triggerDag(dag.dag_id)"
              >
                {{ t('dataPages.airflowExecute') }}
              </el-button>
              <el-button
                size="small"
                @click="viewRuns(dag)"
              >
                {{ t('dataPages.airflowHistory') }}
              </el-button>
            </div>
          </article>
        </div>
      </template>
    </el-card>

    <el-drawer
      v-model="runsVisible"
      :title="t('dataPages.airflowRunsTitle')"
      size="52%"
      class="airflow-runs-drawer"
    >
      <div
        v-if="currentDag"
        class="airflow-runs"
        data-test="airflow-runs-drawer"
      >
        <section class="runs-summary">
          <div>
            <div class="airflow-kicker">
              {{ t('dataPages.airflowRunsKicker') }}
            </div>
            <h3>{{ currentDag.dag_id }}</h3>
            <p>{{ currentDag.description || t('dataPages.airflowNoDescription') }}</p>
          </div>
          <el-tag :type="dagStatusType(currentDag)">
            {{ dagStatusLabel(currentDag) }}
          </el-tag>
        </section>

        <div
          v-if="!runsLoading && dagRuns.length === 0"
          class="airflow-empty compact"
        >
          <strong>{{ t('dataPages.airflowNoRunsTitle') }}</strong>
          <span>{{ t('dataPages.airflowNoRunsDesc') }}</span>
        </div>

        <div
          v-else
          v-loading="runsLoading"
          class="run-list"
        >
          <article
            v-for="run in dagRuns"
            :key="run.dag_run_id"
            class="run-card"
          >
            <div class="run-card-head">
              <div>
                <strong>{{ run.dag_run_id }}</strong>
                <span>{{ run.dag_id }}</span>
              </div>
              <el-tag :type="runStateType(run.state)">
                {{ run.state || t('dataPages.airflowRunUnknown') }}
              </el-tag>
            </div>
            <div class="run-card-grid">
              <span>{{ t('dataPages.airflowRunStart') }}</span>
              <strong>{{ formatDateTime(run.start_date) }}</strong>
              <span>{{ t('dataPages.airflowRunEnd') }}</span>
              <strong>{{ formatDateTime(run.end_date) }}</strong>
            </div>
            <pre v-if="run.conf && Object.keys(run.conf).length > 0">{{ formatConf(run.conf) }}</pre>
          </article>
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
  Clock,
  Connection,
  Operation,
  Refresh,
  Search,
  VideoPause,
} from '@element-plus/icons-vue'
import { airflowApi } from '@/api/airflow'
import type { AirflowDAG, AirflowDAGRun, OrchestrationStatus } from '@/api/airflow'
import { getErrorMessage } from '@/api/index'

const { t } = useI18n()

const loading = ref(false)
const runsLoading = ref(false)
const dags = ref<AirflowDAG[]>([])
const totalEntries = ref(0)
const orchestrationStatus = ref<OrchestrationStatus | null>(null)
const dagSearch = ref('')
const statusFilter = ref<'all' | 'running' | 'paused'>('all')
const runsVisible = ref(false)
const currentDag = ref<AirflowDAG | null>(null)
const dagRuns = ref<AirflowDAGRun[]>([])

const isAirflowBackend = computed(() => orchestrationStatus.value?.type === 'airflow')
const totalDagCount = computed(() => totalEntries.value || dags.value.length)
const runningDagCount = computed(() => dags.value.filter((dag) => dag.is_active && !dag.is_paused).length)
const pausedDagCount = computed(() => dags.value.filter((dag) => dag.is_paused).length)
const backendLabel = computed(() => {
  const type = orchestrationStatus.value?.type
  if (type === 'airflow') {
    return orchestrationStatus.value?.connected === false
      ? t('dataPages.airflowBackendAirflowDisconnected')
      : t('dataPages.airflowBackendAirflow')
  }
  if (type === 'apscheduler') return t('dataPages.airflowBackendApSched')
  if (type) return type
  return t('dataPages.airflowBackendUninit')
})
const filteredDags = computed(() => {
  const keyword = dagSearch.value.trim().toLowerCase()
  return dags.value.filter((dag) => {
    if (statusFilter.value === 'running' && dag.is_paused) return false
    if (statusFilter.value === 'paused' && !dag.is_paused) return false
    if (!keyword) return true
    return [
      dag.dag_id,
      dag.description,
      dag.schedule_interval,
      ...(dag.tags?.map((tag) => tag.name) || []),
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword))
  })
})

async function loadStatus() {
  try {
    orchestrationStatus.value = await airflowApi.getStatus()
  } catch {
    orchestrationStatus.value = { type: 'unknown' }
  }
}

async function refreshDags() {
  try {
    const result = await airflowApi.listDags()
    dags.value = result.dags || []
    totalEntries.value = result.total_entries ?? dags.value.length
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.airflowListFailed')))
  }
}

async function refreshAll() {
  loading.value = true
  try {
    await loadStatus()
    if (isAirflowBackend.value) {
      await refreshDags()
    } else {
      dags.value = []
      totalEntries.value = 0
    }
  } finally {
    loading.value = false
  }
}

async function togglePause(dagId: string, isPaused: boolean) {
  try {
    await airflowApi.togglePause(dagId, isPaused)
    ElMessage.success(isPaused ? t('dataPages.airflowPauseSucceeded') : t('dataPages.airflowResumeSucceeded'))
    await refreshDags()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.airflowOpFailed')))
  }
}

async function triggerDag(dagId: string) {
  try {
    await airflowApi.triggerDag(dagId)
    ElMessage.success(t('dataPages.airflowDagTriggered'))
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.airflowTriggerFailed')))
  }
}

async function viewRuns(dag: AirflowDAG) {
  currentDag.value = dag
  runsVisible.value = true
  runsLoading.value = true
  try {
    const result = await airflowApi.listDagRuns(dag.dag_id)
    dagRuns.value = result.dag_runs || []
  } catch (error) {
    dagRuns.value = []
    ElMessage.error(getErrorMessage(error, t('dataPages.airflowRunsFailed')))
  } finally {
    runsLoading.value = false
  }
}

function formatSchedule(value: string | null | undefined) {
  return value || '-'
}

function dagStatusType(dag: AirflowDAG) {
  if (!dag.is_active) return 'info'
  return dag.is_paused ? 'warning' : 'success'
}

function dagStatusLabel(dag: AirflowDAG) {
  if (!dag.is_active) return t('dataPages.airflowDagInactive')
  return dag.is_paused ? t('dataPages.airflowSwitchOff') : t('dataPages.airflowSwitchOn')
}

function runStateType(state: string) {
  if (state === 'success') return 'success'
  if (state === 'failed') return 'danger'
  if (['queued', 'scheduled', 'running'].includes(state)) return 'warning'
  return 'info'
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function formatConf(conf: Record<string, unknown>) {
  return JSON.stringify(conf, null, 2)
}

onMounted(() => {
  void refreshAll()
})
</script>

<style scoped>
.airflow-page {
  display: grid;
  gap: 24px;
}

.airflow-hero,
.airflow-workbench {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 1px 2px var(--shadow-color);
}

.airflow-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  padding: 24px;
}

.airflow-hero-copy {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.airflow-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.airflow-hero h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 30px;
  line-height: 1.12;
}

.airflow-hero p,
.airflow-panel-heading p,
.runs-summary p {
  max-width: 840px;
  margin: 0;
  color: var(--text-color-regular);
  line-height: 1.65;
}

.airflow-hero-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.airflow-metrics {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.airflow-metric {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.airflow-metric .el-icon {
  color: var(--primary-color);
  font-size: 18px;
}

.airflow-metric span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.airflow-metric strong {
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.airflow-notice {
  border-radius: 8px;
}

.airflow-workbench {
  min-width: 0;
  box-shadow: none;
}

.airflow-workbench :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.airflow-workbench :deep(.el-card__body) {
  padding: 18px;
}

.airflow-panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.airflow-panel-title {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 780;
  line-height: 1.25;
}

.airflow-count {
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

.airflow-count span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.airflow-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.toolbar-search {
  width: min(380px, 100%);
}

.toolbar-item {
  width: 180px;
}

.airflow-empty {
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

.airflow-empty.compact {
  min-height: 120px;
}

.airflow-empty .el-icon {
  color: var(--primary-color);
  font-size: 24px;
}

.airflow-empty strong {
  color: var(--text-color-primary);
  font-size: 18px;
}

.airflow-empty span {
  max-width: 560px;
  color: var(--text-color-secondary);
  line-height: 1.5;
}

.airflow-table {
  width: 100%;
}

.airflow-table :deep(.el-table__header-wrapper th) {
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-weight: 760;
}

.dag-name-cell {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.dag-name-cell strong,
.table-main {
  color: var(--text-color-primary);
  font-weight: 760;
  line-height: 1.35;
}

.dag-name-cell span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.dag-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.airflow-mobile-list {
  display: none;
  gap: 12px;
}

.dag-card,
.run-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.dag-card-head,
.run-card-head,
.runs-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.dag-card-head > div,
.run-card-head > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.dag-card-head strong,
.run-card-head strong {
  color: var(--text-color-primary);
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.dag-card-head span,
.run-card-head span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.dag-card-grid,
.run-card-grid {
  display: grid;
  grid-template-columns: minmax(90px, 0.36fr) minmax(0, 1fr);
  gap: 8px 10px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.dag-card-grid span,
.run-card-grid span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.dag-card-grid strong,
.run-card-grid strong {
  color: var(--text-color-primary);
  overflow-wrap: break-word;
}

.dag-card-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.airflow-runs {
  display: grid;
  gap: 18px;
}

.runs-summary {
  padding: 16px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.runs-summary h3 {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.run-list {
  display: grid;
  gap: 12px;
  min-height: 120px;
}

.run-card pre {
  max-height: 180px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-overlay);
  color: var(--text-color-primary);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
}

@media (max-width: 1100px) {
  .airflow-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .airflow-table {
    display: none;
  }

  .airflow-mobile-list {
    display: grid;
  }
}

@media (max-width: 900px) {
  .airflow-hero {
    grid-template-columns: 1fr;
  }

  .airflow-hero-actions {
    justify-content: flex-start;
  }

  .airflow-panel-heading {
    display: grid;
  }

  .airflow-count {
    width: 100%;
    text-align: left;
  }

  .toolbar-search,
  .toolbar-item {
    width: 100%;
  }

  .airflow-runs-drawer :deep(.el-drawer) {
    width: 92% !important;
  }
}

@media (max-width: 620px) {
  .airflow-page {
    gap: 16px;
  }

  .airflow-hero {
    padding: 18px;
  }

  .airflow-hero h1 {
    font-size: 24px;
  }

  .airflow-metrics {
    grid-template-columns: 1fr;
  }

  .airflow-workbench :deep(.el-card__body) {
    padding: 14px;
  }

  .dag-card-head,
  .run-card-head,
  .runs-summary {
    display: grid;
  }
}
</style>
