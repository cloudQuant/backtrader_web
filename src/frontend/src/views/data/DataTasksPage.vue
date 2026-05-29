<template>
  <div class="space-y-6">
    <el-card>
      <template #header>
        <div class="header-row">
          <div>
            <div class="page-title">
              {{ t('dataPages.tasksPageTitle') }}
            </div>
            <div class="page-subtitle">
              {{ t('dataPages.tasksPageDesc') }}
            </div>
          </div>
          <el-button
            v-if="isAdmin"
            type="primary"
            @click="openCreateDialog"
          >
            {{ t('dataPages.tasksNewTask') }}
          </el-button>
        </div>
      </template>

      <div class="toolbar">
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

      <el-table
        v-loading="loading"
        :data="tasks"
        stripe
      >
        <el-table-column
          prop="name"
          :label="t('dataPages.tasksColName')"
          min-width="180"
        />
        <el-table-column
          :label="t('dataPages.tasksColScript')"
          min-width="200"
        >
          <template #default="{ row }">
            <div>{{ scriptNameMap[row.script_id] || row.script_id }}</div>
            <div class="table-subtext">
              {{ row.script_id }}
            </div>
          </template>
        </el-table-column>
        <el-table-column
          prop="schedule_type"
          :label="t('dataPages.tasksColScheduleType')"
          width="120"
        />
        <el-table-column
          prop="schedule_expression"
          :label="t('dataPages.tasksColScheduleExpr')"
          min-width="180"
        />
        <el-table-column
          :label="t('dataPages.tasksColStatus')"
          width="100"
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
          min-width="280"
        >
          <template #default="{ row }">
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
    void router.push({ name: 'DataExecutions', query: { task_id: String(taskId) } })
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
  void router.push({ name: 'DataExecutions', query: { task_id: String(taskId) } })
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
.header-row,
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
}

.page-subtitle,
.table-subtext {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.toolbar {
  margin-bottom: 16px;
  justify-content: flex-start;
}

.toolbar-item,
.full-width {
  width: 100%;
  max-width: 220px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
