<template>
  <div class="space-y-6">
    <el-card>
      <template #header>
        <div class="header-row">
          <div>
            <div class="page-title">
              定时任务
            </div>
            <div class="page-subtitle">
              把脚本绑定成可重复执行的调度任务。
            </div>
          </div>
          <el-button
            v-if="isAdmin"
            type="primary"
            @click="openCreateDialog"
          >
            新建任务
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
            label="全部状态"
            value="all"
          />
          <el-option
            label="仅启用"
            value="active"
          />
          <el-option
            label="仅停用"
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
          label="任务名"
          min-width="180"
        />
        <el-table-column
          label="脚本"
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
          label="调度类型"
          width="120"
        />
        <el-table-column
          prop="schedule_expression"
          label="调度表达式"
          min-width="180"
        />
        <el-table-column
          label="状态"
          width="100"
        >
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'warning'">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="next_execution_at"
          label="下次执行"
          width="180"
        >
          <template #default="{ row }">
            {{ formatDateTime(row.next_execution_at) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="last_execution_at"
          label="最近执行"
          width="180"
        >
          <template #default="{ row }">
            {{ formatDateTime(row.last_execution_at) }}
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          fixed="right"
          min-width="280"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="viewExecutions(row.id)"
            >
              执行记录
            </el-button>
            <el-button
              v-if="isAdmin"
              link
              type="success"
              @click="runTask(row.id)"
            >
              立即执行
            </el-button>
            <el-button
              v-if="isAdmin"
              link
              @click="toggleTask(row.id)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button
              v-if="isAdmin"
              link
              @click="openEditDialog(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="isAdmin"
              link
              type="danger"
              @click="deleteTask(row.id)"
            >
              删除
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
      :title="dialogMode === 'create' ? '新建任务' : '编辑任务'"
      width="760px"
    >
      <el-form
        :model="form"
        label-width="120px"
      >
        <el-form-item label="任务名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="绑定脚本">
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
        <el-form-item label="快捷模板">
          <el-select
            v-model="selectedTemplate"
            class="full-width"
            clearable
            placeholder="选择后自动填充 cron"
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
        <el-form-item label="调度类型">
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
        <el-form-item label="调度表达式">
          <el-input
            v-model="form.schedule_expression"
            placeholder="cron 如 0 8 * * 1-5，interval 如 10m"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
        <el-form-item label="执行参数">
          <el-input
            v-model="paramsText"
            type="textarea"
            :rows="8"
          />
        </el-form-item>
        <el-form-item label="最大重试">
          <el-input-number
            v-model="form.max_retries"
            :min="0"
            :max="10"
          />
        </el-form-item>
        <el-form-item label="超时秒数">
          <el-input-number
            v-model="form.timeout"
            :min="0"
            :step="30"
          />
        </el-form-item>
        <el-form-item label="失败重试">
          <el-switch v-model="form.retry_on_failure" />
        </el-form-item>
        <el-form-item label="启用任务">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="submitForm"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
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
    ElMessage.error(getErrorMessage(error, '加载任务失败'))
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
    form.name = `执行 ${scriptId}`
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
    ElMessage.warning('请填写任务名称并选择脚本')
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
      ElMessage.success('任务已创建')
    } else if (editingTaskId.value !== null) {
      await akshareTasksApi.update(editingTaskId.value, payload)
      ElMessage.success('任务已更新')
    }
    dialogVisible.value = false
    await loadTasks()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '保存任务失败'))
  } finally {
    saving.value = false
  }
}

async function runTask(taskId: number) {
  try {
    const result = await akshareTasksApi.run(taskId)
    ElMessage.success(`任务已触发：${result.execution_id}`)
    void router.push({ name: 'DataExecutions', query: { task_id: String(taskId) } })
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '执行任务失败'))
  }
}

async function toggleTask(taskId: number) {
  try {
    await akshareTasksApi.toggle(taskId)
    ElMessage.success('任务状态已更新')
    await loadTasks()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '更新任务状态失败'))
  }
}

async function deleteTask(taskId: number) {
  try {
    await ElMessageBox.confirm('确认删除该定时任务？', '删除确认', { type: 'warning' })
    await akshareTasksApi.delete(taskId)
    ElMessage.success('任务已删除')
    await loadTasks()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(getErrorMessage(error, '删除任务失败'))
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
  color: #64748b;
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
