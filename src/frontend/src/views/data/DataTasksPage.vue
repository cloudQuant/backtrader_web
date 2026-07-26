<template>
  <div
    class="tasks-page"
    data-test="tasks-page"
  >
    <section
      class="tasks-hero"
      data-test="tasks-hero"
    >
      <div class="tasks-hero-copy">
        <div class="tasks-kicker">
          {{ t('dataPages.tasksHeroKicker') }}
        </div>
        <h1>{{ t('dataPages.tasksPageTitle') }}</h1>
        <p>{{ t('dataPages.tasksPageDesc') }}</p>
      </div>

      <div class="tasks-hero-actions">
        <el-button
          :icon="Refresh"
          :loading="loading"
          @click="loadTasks"
        >
          {{ t('dataPages.execRefresh') }}
        </el-button>
        <el-button
          v-if="isAdmin"
          type="primary"
          :icon="Plus"
          @click="openCreateDialog"
        >
          {{ t('dataPages.tasksNewTask') }}
        </el-button>
      </div>

      <div
        class="tasks-metrics"
        data-test="tasks-metrics"
      >
        <article class="tasks-metric">
          <el-icon aria-hidden="true">
            <Operation />
          </el-icon>
          <span>{{ t('dataPages.tasksStatTotal') }}</span>
          <strong>{{ total }}</strong>
        </article>
        <article class="tasks-metric">
          <el-icon aria-hidden="true">
            <CircleCheck />
          </el-icon>
          <span>{{ t('dataPages.tasksStatActive') }}</span>
          <strong>{{ activePageCount }}</strong>
        </article>
        <article class="tasks-metric">
          <el-icon aria-hidden="true">
            <Clock />
          </el-icon>
          <span>{{ t('dataPages.tasksStatInactive') }}</span>
          <strong>{{ inactivePageCount }}</strong>
        </article>
        <article class="tasks-metric">
          <el-icon aria-hidden="true">
            <Calendar />
          </el-icon>
          <span>{{ t('dataPages.tasksStatNextRun') }}</span>
          <strong>{{ scheduledPageCount }}</strong>
        </article>
      </div>
    </section>

    <el-card
      class="tasks-workbench"
      data-test="tasks-workbench"
    >
      <template #header>
        <div class="tasks-panel-heading">
          <div>
            <div class="tasks-kicker">
              {{ t('dataPages.tasksWorkbenchKicker') }}
            </div>
            <div class="tasks-panel-title">
              {{ t('dataPages.tasksWorkbenchTitle') }}
            </div>
            <p>{{ t('dataPages.tasksWorkbenchDesc') }}</p>
          </div>
          <div class="tasks-count">
            {{ t('dataPages.tasksVisibleCount', { count: tasks.length }) }}
            <span>{{ t('dataPages.tasksTotalCount', { count: total }) }}</span>
          </div>
        </div>
      </template>

      <div class="tasks-toolbar">
        <el-select
          v-model="activeFilter"
          class="toolbar-item"
          @change="reloadFirstPage"
        >
          <el-option
            :label="t('dataPages.tasksFilterAll')"
            value="all"
          />
          <el-option
            :label="t('dataPages.tasksFilterActive')"
            value="active"
          />
          <el-option
            :label="t('dataPages.tasksFilterInactive')"
            value="inactive"
          />
        </el-select>
      </div>

      <div
        v-if="!loading && tasks.length === 0"
        class="tasks-empty"
      >
        <strong>{{ t('dataPages.tasksEmptyTitle') }}</strong>
        <span>{{ t('dataPages.tasksEmptyDesc') }}</span>
      </div>

      <template v-else>
        <el-table
          v-loading="loading"
          :data="tasks"
          stripe
          class="tasks-table"
          data-test="tasks-table"
        >
          <el-table-column
            prop="name"
            :label="t('dataPages.tasksColName')"
            min-width="190"
          >
            <template #default="{ row }">
              <div class="task-name-cell">
                <strong>{{ row.name }}</strong>
                <span>{{ row.description || t('dataPages.tasksNoDescription') }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.tasksColScript')"
            min-width="220"
          >
            <template #default="{ row }">
              <div class="table-main">
                {{ scriptNameMap[row.script_id] || row.script_id }}
              </div>
              <div class="table-subtext">
                {{ row.script_id }}
              </div>
            </template>
          </el-table-column>
          <el-table-column
            prop="schedule_type"
            :label="t('dataPages.tasksColScheduleType')"
            width="130"
          />
          <el-table-column
            prop="schedule_expression"
            :label="t('dataPages.tasksColScheduleExpr')"
            min-width="190"
          />
          <el-table-column
            :label="t('dataPages.tasksColStatus')"
            width="110"
          >
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'warning'">
                {{ row.is_active ? t('dataPages.tasksStatusActive') : t('dataPages.tasksStatusInactive') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="next_execution_at"
            :label="t('dataPages.tasksColNextRun')"
            width="180"
          >
            <template #default="{ row }">
              {{ formatDateTime(row.next_execution_at) }}
            </template>
          </el-table-column>
          <el-table-column
            prop="last_execution_at"
            :label="t('dataPages.tasksColLastRun')"
            width="180"
          >
            <template #default="{ row }">
              {{ formatDateTime(row.last_execution_at) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.tasksColActions')"
            fixed="right"
            min-width="300"
          >
            <template #default="{ row }">
              <div class="task-table-actions">
                <el-button
                  link
                  type="primary"
                  @click="viewExecutions(row.id)"
                >
                  {{ t('dataPages.tasksActionExecutions') }}
                </el-button>
                <el-button
                  v-if="isAdmin"
                  link
                  type="success"
                  @click="runTask(row.id)"
                >
                  {{ t('dataPages.tasksActionRunNow') }}
                </el-button>
                <el-button
                  v-if="isAdmin"
                  link
                  @click="toggleTask(row.id)"
                >
                  {{ row.is_active ? t('dataPages.tasksActionDisable') : t('dataPages.tasksActionEnable') }}
                </el-button>
                <el-button
                  v-if="isAdmin"
                  link
                  @click="openEditDialog(row)"
                >
                  {{ t('dataPages.tasksActionEdit') }}
                </el-button>
                <el-button
                  v-if="isAdmin"
                  link
                  type="danger"
                  @click="deleteTask(row.id)"
                >
                  {{ t('dataPages.tasksActionDelete') }}
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div
          class="tasks-mobile-list"
          data-test="tasks-mobile-list"
        >
          <article
            v-for="task in tasks"
            :key="task.id"
            class="task-mobile-card"
          >
            <div class="task-mobile-head">
              <div>
                <strong>{{ task.name }}</strong>
                <span>{{ scriptNameMap[task.script_id] || task.script_id }}</span>
              </div>
              <span :class="task.is_active ? 'is-active' : 'is-inactive'">
                {{ task.is_active ? t('dataPages.tasksStatusActive') : t('dataPages.tasksStatusInactive') }}
              </span>
            </div>
            <p>{{ task.description || t('dataPages.tasksNoDescription') }}</p>
            <div class="task-mobile-grid">
              <span>{{ t('dataPages.tasksColScheduleType') }}</span>
              <strong>{{ task.schedule_type }}</strong>
              <span>{{ t('dataPages.tasksColScheduleExpr') }}</span>
              <strong>{{ task.schedule_expression }}</strong>
              <span>{{ t('dataPages.tasksColNextRun') }}</span>
              <strong>{{ formatDateTime(task.next_execution_at) }}</strong>
              <span>{{ t('dataPages.tasksColLastRun') }}</span>
              <strong>{{ formatDateTime(task.last_execution_at) }}</strong>
            </div>
            <div class="task-mobile-actions">
              <el-button
                size="small"
                @click="viewExecutions(task.id)"
              >
                {{ t('dataPages.tasksActionExecutions') }}
              </el-button>
              <el-button
                v-if="isAdmin"
                size="small"
                type="primary"
                @click="runTask(task.id)"
              >
                {{ t('dataPages.tasksActionRunNow') }}
              </el-button>
              <el-button
                v-if="isAdmin"
                size="small"
                @click="openEditDialog(task)"
              >
                {{ t('dataPages.tasksActionEdit') }}
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
          @current-change="loadTasks"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? t('dataPages.tasksDialogCreate') : t('dataPages.tasksDialogEdit')"
      width="760px"
    >
      <el-form
        :model="form"
        label-width="120px"
      >
        <el-form-item :label="t('dataPages.tasksFormName')">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="t('dataPages.tasksFormScript')">
          <el-select
            v-model="form.script_id"
            class="full-width"
            filterable
          >
            <el-option
              v-for="script in scriptOptions"
              :key="script.script_id"
              :label="`${script.script_name} (${script.script_id})`"
              :value="script.script_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('dataPages.tasksFormTemplate')">
          <el-select
            v-model="selectedTemplate"
            class="full-width"
            clearable
            :placeholder="t('dataPages.tasksTemplatePh')"
            @change="handleTemplateChange"
          >
            <el-option
              v-for="template in templates"
              :key="template.value"
              :label="`${template.label} (${template.cron_expression})`"
              :value="template.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('dataPages.tasksFormScheduleType')">
          <el-select
            v-model="form.schedule_type"
            class="full-width"
          >
            <el-option
              v-for="type in scheduleTypes"
              :key="type"
              :label="type"
              :value="type"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('dataPages.tasksFormScheduleExpr')">
          <el-input
            v-model="form.schedule_expression"
            :placeholder="t('dataPages.tasksScheduleExprPh')"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.tasksFormDesc')">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.tasksFormParams')">
          <el-input
            v-model="paramsText"
            type="textarea"
            :rows="8"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.tasksFormMaxRetries')">
          <el-input-number
            v-model="form.max_retries"
            :min="0"
            :max="10"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.tasksFormTimeout')">
          <el-input-number
            v-model="form.timeout"
            :min="0"
            :step="30"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.tasksFormRetryOnFailure')">
          <el-switch v-model="form.retry_on_failure" />
        </el-form-item>
        <el-form-item :label="t('dataPages.tasksFormIsActive')">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="submitForm"
        >
          {{ t('common.save') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Calendar,
  CircleCheck,
  Clock,
  Operation,
  Plus,
  Refresh,
} from '@element-plus/icons-vue'
import { akshareScriptsApi, akshareTasksApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type {
  DataScript,
  ScheduledTask,
  ScheduledTaskFormPayload,
  ScheduleTemplateResponse,
} from '@/types'
import { formatDateTime, parseJsonText, toJsonText } from '@/views/data/utils'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const selectedTemplate = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const activeFilter = ref<'all' | 'active' | 'inactive'>('all')
const tasks = ref<ScheduledTask[]>([])
const scriptOptions = ref<DataScript[]>([])
const templates = ref<ScheduleTemplateResponse[]>([])
const editingTaskId = ref<number | null>(null)
const paramsText = ref('{}')
const form = reactive<ScheduledTaskFormPayload>({
  name: '',
  description: '',
  script_id: '',
  schedule_type: 'cron',
  schedule_expression: '0 8 * * 1-5',
  parameters: {},
  is_active: true,
  retry_on_failure: true,
  max_retries: 3,
  timeout: 0,
})

const isAdmin = computed(() => authStore.user?.is_admin ?? false)
const scheduleTypes = ['cron', 'interval', 'daily', 'weekly', 'monthly', 'once'] as const
const scriptNameMap = computed(() =>
  Object.fromEntries(scriptOptions.value.map((item) => [item.script_id, item.script_name]))
)
const activePageCount = computed(() => tasks.value.filter((task) => task.is_active).length)
const inactivePageCount = computed(() => tasks.value.length - activePageCount.value)
const scheduledPageCount = computed(() => tasks.value.filter((task) => Boolean(task.next_execution_at)).length)

function resetForm() {
  form.name = ''
  form.description = ''
  form.script_id = ''
  form.schedule_type = 'cron'
  form.schedule_expression = '0 8 * * 1-5'
  form.parameters = {}
  form.is_active = true
  form.retry_on_failure = true
  form.max_retries = 3
  form.timeout = 0
  paramsText.value = '{}'
  selectedTemplate.value = ''
  editingTaskId.value = null
}

async function loadScripts() {
  const response = await akshareScriptsApi.list({ page: 1, page_size: 200, is_active: true })
  scriptOptions.value = response.items
}

async function loadTemplates() {
  const response = await akshareTasksApi.getScheduleTemplates()
  templates.value = response.templates
}

async function loadTasks() {
  loading.value = true
  try {
    const response = await akshareTasksApi.list({
      page: page.value,
      page_size: pageSize.value,
      is_active:
        activeFilter.value === 'all'
          ? undefined
          : activeFilter.value === 'active',
    })
    tasks.value = response.items
    total.value = response.total
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.tasksLoadFailed')))
  } finally {
    loading.value = false
  }
}

function reloadFirstPage() {
  page.value = 1
  void loadTasks()
}

function handleSizeChange() {
  page.value = 1
  void loadTasks()
}

function openCreateDialog() {
  dialogMode.value = 'create'
  resetForm()
  const scriptId = String(route.query.script_id ?? '')
  if (scriptId) {
    form.script_id = scriptId
    form.name = t('dataPages.tasksDefaultName', { scriptId })
  }
  dialogVisible.value = true
}

function openEditDialog(task: ScheduledTask) {
  dialogMode.value = 'edit'
  editingTaskId.value = task.id
  form.name = task.name
  form.description = task.description ?? ''
  form.script_id = task.script_id
  form.schedule_type = task.schedule_type
  form.schedule_expression = task.schedule_expression
  form.parameters = task.parameters
  form.is_active = task.is_active
  form.retry_on_failure = task.retry_on_failure
  form.max_retries = task.max_retries
  form.timeout = task.timeout
  paramsText.value = toJsonText(task.parameters)
  dialogVisible.value = true
}

function handleTemplateChange(value: string | null | undefined) {
  const template = templates.value.find((item) => item.value === value)
  if (!template) {
    return
  }
  form.schedule_type = 'cron'
  form.schedule_expression = template.cron_expression
}

async function submitForm() {
  if (!form.name.trim() || !form.script_id) {
    ElMessage.warning(t('dataPages.tasksValidationFill'))
    return
  }

  saving.value = true
  try {
    const payload: ScheduledTaskFormPayload = {
      ...form,
      name: form.name.trim(),
      description: form.description?.trim() || null,
      parameters: parseJsonText(paramsText.value),
    }
    if (dialogMode.value === 'create') {
      await akshareTasksApi.create(payload)
      ElMessage.success(t('dataPages.tasksCreated'))
    } else if (editingTaskId.value !== null) {
      await akshareTasksApi.update(editingTaskId.value, payload)
      ElMessage.success(t('dataPages.tasksUpdated'))
    }
    dialogVisible.value = false
    await loadTasks()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.tasksSaveFailed')))
  } finally {
    saving.value = false
  }
}

async function runTask(taskId: number) {
  try {
    const result = await akshareTasksApi.run(taskId)
    ElMessage.success(t('dataPages.tasksRunTriggered', { id: result.execution_id }))
    void router.push({ name: 'ConfigDataExecutions', query: { task_id: String(taskId) } })
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.tasksRunFailed')))
  }
}

async function toggleTask(taskId: number) {
  try {
    await akshareTasksApi.toggle(taskId)
    ElMessage.success(t('dataPages.tasksToggled'))
    await loadTasks()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.tasksToggleFailed')))
  }
}

async function deleteTask(taskId: number) {
  try {
    await ElMessageBox.confirm(
      t('dataPages.tasksDeleteConfirmMsg'),
      t('dataPages.tasksDeleteConfirmTitle'),
      { type: 'warning' }
    )
    await akshareTasksApi.delete(taskId)
    ElMessage.success(t('dataPages.tasksDeleted'))
    await loadTasks()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(getErrorMessage(error, t('dataPages.tasksDeleteFailed')))
    }
  }
}

function viewExecutions(taskId: number) {
  void router.push({ name: 'ConfigDataExecutions', query: { task_id: String(taskId) } })
}

watch(
  () => route.query.script_id,
  (scriptId) => {
    if (scriptId && isAdmin.value && !dialogVisible.value) {
      openCreateDialog()
    }
  },
  { immediate: true }
)

onMounted(() => {
  void Promise.all([loadScripts(), loadTemplates(), loadTasks()])
})
</script>

<style scoped>
.tasks-page {
  display: grid;
  gap: 24px;
}

.tasks-hero,
.tasks-workbench {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 1px 2px var(--shadow-color);
}

.tasks-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  padding: 24px;
}

.tasks-hero-copy {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.tasks-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.tasks-hero h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 30px;
  line-height: 1.12;
}

.tasks-hero p,
.tasks-panel-heading p {
  max-width: 760px;
  margin: 0;
  color: var(--text-color-regular);
  line-height: 1.65;
}

.tasks-hero-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.tasks-metrics {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.tasks-metric {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.tasks-metric .el-icon {
  color: var(--primary-color);
  font-size: 18px;
}

.tasks-metric span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.tasks-metric strong {
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1.2;
}

.tasks-workbench {
  box-shadow: none;
}

.tasks-workbench :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.tasks-workbench :deep(.el-card__body) {
  padding: 18px;
}

.tasks-panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.tasks-panel-title {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 780;
  line-height: 1.25;
}

.tasks-count {
  display: grid;
  gap: 4px;
  min-width: 140px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 760;
  line-height: 1.2;
  text-align: right;
}

.tasks-count span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.tasks-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.toolbar-item {
  width: 220px;
  max-width: 100%;
}

.full-width {
  width: 100%;
}

.tasks-table {
  width: 100%;
}

.tasks-table :deep(.el-table__header-wrapper th) {
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-weight: 760;
}

.task-name-cell {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.task-name-cell strong,
.table-main {
  color: var(--text-color-primary);
  font-weight: 720;
  overflow-wrap: anywhere;
}

.task-name-cell span,
.table-subtext {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.task-table-actions {
  display: flex;
  align-items: center;
  gap: 2px 8px;
  flex-wrap: wrap;
}

.tasks-mobile-list {
  display: none;
  gap: 12px;
}

.task-mobile-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.task-mobile-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.task-mobile-head > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.task-mobile-head strong {
  color: var(--text-color-primary);
  font-size: 15px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.task-mobile-head span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.task-mobile-head .is-active,
.task-mobile-head .is-inactive {
  flex: none;
  padding: 5px 8px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 720;
}

.task-mobile-head .is-active {
  border: 1px solid var(--success-border-color);
  background: var(--success-surface);
  color: var(--success-text-color);
}

.task-mobile-head .is-inactive {
  border: 1px solid var(--warning-border-color);
  background: var(--warning-surface);
  color: var(--warning-text-color);
}

.task-mobile-card p {
  margin: 0;
  color: var(--text-color-regular);
  font-size: 13px;
  line-height: 1.5;
}

.task-mobile-grid {
  display: grid;
  grid-template-columns: minmax(90px, 0.45fr) minmax(0, 1fr);
  gap: 8px 10px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.task-mobile-grid span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.task-mobile-grid strong {
  color: var(--text-color-primary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.task-mobile-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tasks-empty {
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

.tasks-empty strong {
  color: var(--text-color-primary);
  font-size: 18px;
}

.tasks-empty span {
  max-width: 520px;
  color: var(--text-color-secondary);
  line-height: 1.5;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.tasks-page :deep(.el-dialog) {
  border-radius: 8px;
  background: var(--bg-color);
}

.tasks-page :deep(.el-dialog__body) {
  color: var(--text-color-primary);
}

.tasks-page :deep(.el-textarea__inner) {
  color: var(--text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.55;
}

@media (max-width: 1100px) {
  .tasks-hero {
    grid-template-columns: 1fr;
  }

  .tasks-hero-actions {
    justify-content: flex-start;
  }

  .tasks-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .tasks-table {
    display: none;
  }

  .tasks-mobile-list {
    display: grid;
  }

  .tasks-panel-heading {
    display: grid;
  }

  .tasks-count {
    text-align: left;
  }
}

@media (max-width: 640px) {
  .tasks-hero {
    padding: 18px;
  }

  .tasks-hero h1 {
    font-size: 24px;
  }

  .tasks-metrics {
    grid-template-columns: 1fr;
  }

  .tasks-hero-actions,
  .task-mobile-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .tasks-hero-actions :deep(.el-button),
  .task-mobile-actions :deep(.el-button) {
    width: 100%;
  }

  .toolbar-item {
    width: 100%;
  }
}
</style>
