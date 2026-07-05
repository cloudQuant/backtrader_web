<template>
  <div
    class="executions-page"
    data-test="executions-page"
  >
    <section
      class="executions-hero"
      data-test="executions-hero"
    >
      <div class="executions-hero-copy">
        <div class="executions-kicker">
          {{ t('dataPages.execHeroKicker') }}
        </div>
        <h1>{{ t('dataPages.execPageTitle') }}</h1>
        <p>{{ t('dataPages.execPageDesc') }}</p>
      </div>

      <div class="executions-hero-actions">
        <el-button
          :icon="Refresh"
          :loading="loading"
          @click="loadExecutions"
        >
          {{ t('dataPages.execRefresh') }}
        </el-button>
      </div>

      <div
        class="executions-metrics"
        data-test="executions-metrics"
      >
        <article class="executions-metric">
          <el-icon aria-hidden="true">
            <Operation />
          </el-icon>
          <span>{{ t('dataPages.execStatTotal') }}</span>
          <strong>{{ stats.total_count }}</strong>
        </article>
        <article class="executions-metric">
          <el-icon aria-hidden="true">
            <CircleCheck />
          </el-icon>
          <span>{{ t('dataPages.execStatSuccess') }}</span>
          <strong class="is-success">{{ stats.success_count }}</strong>
        </article>
        <article class="executions-metric">
          <el-icon aria-hidden="true">
            <Warning />
          </el-icon>
          <span>{{ t('dataPages.execStatFailed') }}</span>
          <strong class="is-danger">{{ stats.failed_count }}</strong>
        </article>
        <article class="executions-metric">
          <el-icon aria-hidden="true">
            <Clock />
          </el-icon>
          <span>{{ t('dataPages.execStatRunning') }}</span>
          <strong>{{ stats.running_count }}</strong>
        </article>
      </div>
    </section>

    <el-card
      class="executions-workbench"
      data-test="executions-workbench"
    >
      <template #header>
        <div class="executions-panel-heading">
          <div>
            <div class="executions-kicker">
              {{ t('dataPages.execWorkbenchKicker') }}
            </div>
            <div class="executions-panel-title">
              {{ t('dataPages.execWorkbenchTitle') }}
            </div>
            <p>{{ t('dataPages.execWorkbenchDesc') }}</p>
          </div>
          <div class="executions-count">
            {{ t('dataPages.execVisibleCount', { count: executions.length }) }}
            <span>{{ t('dataPages.execTotalCount', { count: total }) }}</span>
          </div>
        </div>
      </template>

      <div class="executions-toolbar">
        <el-input
          v-model="filters.script_id"
          clearable
          :placeholder="t('dataPages.execScriptIdPh')"
          class="toolbar-item"
        />
        <el-input-number
          v-model="taskIdInput"
          :min="1"
          :controls="false"
          class="toolbar-item"
          :placeholder="t('dataPages.execTaskIdPh')"
        />
        <el-select
          v-model="filters.status"
          clearable
          class="toolbar-item"
          :placeholder="t('dataPages.execStatusPh')"
        >
          <el-option
            v-for="status in statuses"
            :key="status"
            :label="status"
            :value="status"
          />
        </el-select>
        <el-button
          type="primary"
          :icon="Search"
          @click="reloadFirstPage"
        >
          {{ t('dataPages.execQuery') }}
        </el-button>
      </div>

      <div
        v-if="!loading && executions.length === 0"
        class="executions-empty"
      >
        <strong>{{ t('dataPages.execEmptyTitle') }}</strong>
        <span>{{ t('dataPages.execEmptyDesc') }}</span>
      </div>

      <template v-else>
        <el-table
          v-loading="loading"
          :data="executions"
          stripe
          class="executions-table"
          data-test="executions-table"
        >
          <el-table-column
            prop="execution_id"
            :label="t('dataPages.execColExecId')"
            min-width="190"
          >
            <template #default="{ row }">
              <div class="execution-id-cell">
                <strong>{{ row.execution_id }}</strong>
                <span>{{ row.created_at ? formatDateTime(row.created_at) : '-' }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            prop="script_id"
            :label="t('dataPages.execColScript')"
            min-width="150"
          />
          <el-table-column
            prop="task_id"
            :label="t('dataPages.execColTask')"
            width="90"
          />
          <el-table-column
            :label="t('dataPages.execColStatus')"
            width="120"
          >
            <template #default="{ row }">
              <el-tag :type="statusMap[row.status]?.type || 'info'">
                {{ statusMap[row.status]?.label || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="triggered_by"
            :label="t('dataPages.execColTriggeredBy')"
            width="120"
          />
          <el-table-column
            prop="start_time"
            :label="t('dataPages.execColStartTime')"
            width="180"
          >
            <template #default="{ row }">
              {{ formatDateTime(row.start_time) }}
            </template>
          </el-table-column>
          <el-table-column
            prop="duration"
            :label="t('dataPages.execColDuration')"
            width="110"
          >
            <template #default="{ row }">
              {{ formatDuration(row.duration) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.execColRowsDelta')"
            width="140"
          >
            <template #default="{ row }">
              {{ formatRowsDelta(row) }}
            </template>
          </el-table-column>
          <el-table-column
            prop="error_message"
            :label="t('dataPages.execColErrorMessage')"
            min-width="220"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <span class="error-message">{{ row.error_message || t('dataPages.execNoErrorMessage') }}</span>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.execColActions')"
            fixed="right"
            min-width="180"
          >
            <template #default="{ row }">
              <div class="execution-table-actions">
                <el-button
                  link
                  type="primary"
                  @click="openDetail(row.execution_id)"
                >
                  {{ t('dataPages.execActionDetail') }}
                </el-button>
                <el-button
                  v-if="isAdmin && row.status === 'failed'"
                  link
                  type="danger"
                  @click="retryExecution(row.execution_id)"
                >
                  {{ t('dataPages.execActionRetry') }}
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div
          class="executions-mobile-list"
          data-test="executions-mobile-list"
        >
          <article
            v-for="execution in executions"
            :key="execution.execution_id"
            class="execution-mobile-card"
          >
            <div class="execution-mobile-head">
              <div>
                <strong>{{ execution.execution_id }}</strong>
                <span>{{ execution.script_id }}</span>
              </div>
              <span :class="`is-${execution.status}`">
                {{ statusMap[execution.status]?.label || execution.status }}
              </span>
            </div>
            <div class="execution-mobile-grid">
              <span>{{ t('dataPages.execColTask') }}</span>
              <strong>{{ execution.task_id ?? '-' }}</strong>
              <span>{{ t('dataPages.execColTriggeredBy') }}</span>
              <strong>{{ execution.triggered_by }}</strong>
              <span>{{ t('dataPages.execColStartTime') }}</span>
              <strong>{{ formatDateTime(execution.start_time) }}</strong>
              <span>{{ t('dataPages.execColDuration') }}</span>
              <strong>{{ formatDuration(execution.duration) }}</strong>
              <span>{{ t('dataPages.execColRowsDelta') }}</span>
              <strong>{{ formatRowsDelta(execution) }}</strong>
            </div>
            <p>{{ execution.error_message || t('dataPages.execNoErrorMessage') }}</p>
            <div class="execution-mobile-actions">
              <el-button
                size="small"
                @click="openDetail(execution.execution_id)"
              >
                {{ t('dataPages.execActionDetail') }}
              </el-button>
              <el-button
                v-if="isAdmin && execution.status === 'failed'"
                size="small"
                type="danger"
                @click="retryExecution(execution.execution_id)"
              >
                {{ t('dataPages.execActionRetry') }}
              </el-button>
            </div>
          </article>
        </div>
      </template>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadExecutions"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <el-drawer
      v-model="detailVisible"
      :title="t('dataPages.execDetailTitle')"
      size="55%"
      class="execution-detail-drawer"
    >
      <div v-if="currentExecution">
        <el-descriptions
          :column="2"
          border
        >
          <el-descriptions-item :label="t('dataPages.execDetailExecId')">
            {{ currentExecution.execution_id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPages.execDetailScriptId')">
            {{ currentExecution.script_id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPages.execDetailTaskId')">
            {{ currentExecution.task_id ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPages.execDetailStatus')">
            {{ currentExecution.status }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPages.execDetailStartTime')">
            {{ formatDateTime(currentExecution.start_time) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPages.execDetailEndTime')">
            {{ formatDateTime(currentExecution.end_time) }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="drawer-section">
          <div class="section-title">
            {{ t('dataPages.execDetailParams') }}
          </div>
          <pre>{{ toJsonText(currentExecution.params || {}) }}</pre>
        </div>

        <div class="drawer-section">
          <div class="section-title">
            {{ t('dataPages.execDetailResult') }}
          </div>
          <pre>{{ toJsonText(currentExecution.result || {}) }}</pre>
        </div>

        <div class="drawer-section">
          <div class="section-title">
            {{ t('dataPages.execDetailErrorTrace') }}
          </div>
          <pre>{{ currentExecution.error_trace || currentExecution.error_message || t('dataPages.execDetailNoError') }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  CircleCheck,
  Clock,
  Operation,
  Refresh,
  Search,
  Warning,
} from '@element-plus/icons-vue'
import { akshareExecutionsApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type { ExecutionStatsResponse, TaskExecution } from '@/types'
import { formatDateTime, toJsonText } from '@/views/data/utils'

const { t } = useI18n()
const route = useRoute()
const authStore = useAuthStore()

const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const executions = ref<TaskExecution[]>([])
const detailVisible = ref(false)
const currentExecution = ref<TaskExecution | null>(null)
const taskIdInput = ref<number | undefined>(undefined)
const stats = reactive<ExecutionStatsResponse>({
  total_count: 0,
  success_count: 0,
  failed_count: 0,
  running_count: 0,
  success_rate: 0,
  avg_duration: 0,
})
const filters = reactive({
  script_id: '',
  status: '',
})

const isAdmin = computed(() => authStore.user?.is_admin ?? false)
const statuses = ['pending', 'running', 'completed', 'failed', 'timeout', 'cancelled'] as const
const statusMap = computed<Record<string, { label: string; type: 'info' | 'primary' | 'success' | 'warning' | 'danger' }>>(() => ({
  pending: { label: t('dataPages.execStatusPending'), type: 'info' },
  running: { label: t('dataPages.execStatusRunning'), type: 'primary' },
  completed: { label: t('dataPages.execStatusCompleted'), type: 'success' },
  failed: { label: t('dataPages.execStatusFailed'), type: 'danger' },
  timeout: { label: t('dataPages.execStatusTimeout'), type: 'warning' },
  cancelled: { label: t('dataPages.execStatusCancelled'), type: 'info' },
}))

function formatDuration(value: number | null | undefined): string {
  return typeof value === 'number' ? `${value.toFixed(2)}s` : '-'
}

function formatRowsDelta(row: Pick<TaskExecution, 'rows_before' | 'rows_after'>): string {
  return `${row.rows_before ?? '-'} -> ${row.rows_after ?? '-'}`
}

async function loadStats() {
  Object.assign(stats, await akshareExecutionsApi.getStats())
}

async function loadExecutions() {
  loading.value = true
  try {
    const response = await akshareExecutionsApi.list({
      page: page.value,
      page_size: pageSize.value,
      task_id: taskIdInput.value,
      script_id: filters.script_id || undefined,
      status: filters.status || undefined,
    })
    executions.value = response.items
    total.value = response.total
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.execLoadFailed')))
  } finally {
    loading.value = false
  }
}

function reloadFirstPage() {
  page.value = 1
  void loadExecutions()
}

function handleSizeChange() {
  page.value = 1
  void loadExecutions()
}

async function openDetail(executionId: string) {
  try {
    currentExecution.value = await akshareExecutionsApi.getDetail(executionId)
    detailVisible.value = true
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.execLoadDetailFailed')))
  }
}

async function retryExecution(executionId: string) {
  try {
    const result = await akshareExecutionsApi.retry(executionId)
    ElMessage.success(t('dataPages.execRetried', { id: result.execution_id }))
    await Promise.all([loadStats(), loadExecutions()])
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.execRetryFailed')))
  }
}

onMounted(() => {
  const taskId = Number(route.query.task_id)
  if (Number.isFinite(taskId) && taskId > 0) {
    taskIdInput.value = taskId
  }
  if (typeof route.query.script_id === 'string') {
    filters.script_id = route.query.script_id
  }
  void Promise.all([loadStats(), loadExecutions()])
})
</script>

<style scoped>
.executions-page {
  display: grid;
  gap: 24px;
}

.executions-hero,
.executions-workbench {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 1px 2px var(--shadow-color);
}

.executions-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  padding: 24px;
}

.executions-hero-copy {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.executions-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.executions-hero h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 30px;
  line-height: 1.12;
}

.executions-hero p,
.executions-panel-heading p {
  max-width: 780px;
  margin: 0;
  color: var(--text-color-regular);
  line-height: 1.65;
}

.executions-hero-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.executions-metrics {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.executions-metric {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.executions-metric .el-icon {
  color: var(--primary-color);
  font-size: 18px;
}

.executions-metric span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.executions-metric strong {
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.executions-metric .is-success {
  color: var(--success-text-color);
}

.executions-metric .is-danger {
  color: var(--danger-text-color);
}

.executions-workbench {
  box-shadow: none;
}

.executions-workbench :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.executions-workbench :deep(.el-card__body) {
  padding: 18px;
}

.executions-panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.executions-panel-title {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 780;
  line-height: 1.25;
}

.executions-count {
  display: grid;
  gap: 4px;
  min-width: 140px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 760;
  line-height: 1.2;
  text-align: right;
}

.executions-count span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.executions-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.toolbar-item {
  width: 180px;
  max-width: 100%;
}

.executions-table {
  width: 100%;
}

.executions-table :deep(.el-table__header-wrapper th) {
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-weight: 760;
}

.execution-id-cell {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.execution-id-cell strong {
  color: var(--text-color-primary);
  font-weight: 720;
  overflow-wrap: anywhere;
}

.execution-id-cell span,
.error-message {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.execution-table-actions {
  display: flex;
  align-items: center;
  gap: 2px 8px;
  flex-wrap: wrap;
}

.executions-mobile-list {
  display: none;
  gap: 12px;
}

.execution-mobile-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.execution-mobile-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.execution-mobile-head > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.execution-mobile-head strong {
  color: var(--text-color-primary);
  font-size: 14px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.execution-mobile-head span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.execution-mobile-head [class^='is-'] {
  flex: none;
  padding: 5px 8px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 720;
}

.execution-mobile-head .is-completed {
  border-color: var(--success-border-color);
  background: var(--success-surface);
  color: var(--success-text-color);
}

.execution-mobile-head .is-failed,
.execution-mobile-head .is-timeout {
  border-color: var(--danger-border-color);
  background: var(--danger-surface);
  color: var(--danger-text-color);
}

.execution-mobile-head .is-running {
  border-color: var(--info-border-color);
  background: var(--info-surface);
  color: var(--info-text-color);
}

.execution-mobile-grid {
  display: grid;
  grid-template-columns: minmax(95px, 0.45fr) minmax(0, 1fr);
  gap: 8px 10px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.execution-mobile-grid span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.execution-mobile-grid strong {
  color: var(--text-color-primary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.execution-mobile-card p {
  margin: 0;
  color: var(--text-color-regular);
  font-size: 13px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.execution-mobile-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.executions-empty {
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

.executions-empty strong {
  color: var(--text-color-primary);
  font-size: 18px;
}

.executions-empty span {
  max-width: 520px;
  color: var(--text-color-secondary);
  line-height: 1.5;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.drawer-section {
  margin-top: 20px;
}

.section-title {
  margin-bottom: 8px;
  color: var(--text-color-primary);
  font-weight: 760;
}

pre {
  margin: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  background: var(--code-bg-color);
  color: var(--code-text-color);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.55;
  overflow: auto;
}

.execution-detail-drawer :deep(.el-drawer) {
  background: var(--bg-color);
  color: var(--text-color-primary);
}

.execution-detail-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color-light);
  color: var(--text-color-primary);
}

.execution-detail-drawer :deep(.el-drawer__body) {
  background: var(--bg-color);
  color: var(--text-color-primary);
}

.execution-detail-drawer :deep(.el-descriptions__body),
.execution-detail-drawer :deep(.el-descriptions__cell) {
  background: var(--bg-color);
  color: var(--text-color-primary);
}

@media (max-width: 960px) {
  .executions-hero {
    grid-template-columns: 1fr;
  }

  .executions-hero-actions {
    justify-content: flex-start;
  }

  .executions-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .executions-table {
    display: none;
  }

  .executions-mobile-list {
    display: grid;
  }

  .executions-panel-heading {
    display: grid;
  }

  .executions-count {
    text-align: left;
  }
}

@media (max-width: 640px) {
  .executions-hero {
    padding: 18px;
  }

  .executions-hero h1 {
    font-size: 24px;
  }

  .executions-metrics {
    grid-template-columns: 1fr;
  }

  .executions-hero-actions,
  .execution-mobile-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .executions-hero-actions :deep(.el-button),
  .execution-mobile-actions :deep(.el-button) {
    width: 100%;
  }

  .toolbar-item {
    width: 100%;
  }
}
</style>
