<template>
  <div class="space-y-6">
    <section class="stats-grid">
      <el-card>
        <div class="stat-title">总执行</div>
        <div class="stat-value">{{ stats.total_count }}</div>
      </el-card>
      <el-card>
        <div class="stat-title">成功</div>
        <div class="stat-value success">{{ stats.success_count }}</div>
      </el-card>
      <el-card>
        <div class="stat-title">失败</div>
        <div class="stat-value danger">{{ stats.failed_count }}</div>
      </el-card>
      <el-card>
        <div class="stat-title">运行中</div>
        <div class="stat-value primary">{{ stats.running_count }}</div>
      </el-card>
    </section>

    <el-card>
      <template #header>
        <div class="header-row">
          <div>
            <div class="page-title">执行记录</div>
            <div class="page-subtitle">按任务、脚本和状态排查 akshare 采集执行情况。</div>
          </div>
          <el-button @click="loadExecutions">刷新</el-button>
        </div>
      </template>

      <div class="toolbar">
        <el-input
          v-model="filters.script_id"
          clearable
          placeholder="脚本 ID"
          class="toolbar-item"
        />
        <el-input-number
          v-model="taskIdInput"
          :min="1"
          :controls="false"
          class="toolbar-item"
          placeholder="任务 ID"
        />
        <el-select
          v-model="filters.status"
          clearable
          class="toolbar-item"
          placeholder="执行状态"
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
          @click="reloadFirstPage"
        >
          查询
        </el-button>
      </div>

      <el-table
        v-loading="loading"
        :data="executions"
        stripe
      >
        <el-table-column
          prop="execution_id"
          label="执行 ID"
          min-width="180"
        />
        <el-table-column
          prop="script_id"
          label="脚本"
          min-width="140"
        />
        <el-table-column
          prop="task_id"
          label="任务"
          width="90"
        />
        <el-table-column
          label="状态"
          width="110"
        >
          <template #default="{ row }">
            <el-tag :type="statusMap[row.status]?.type || 'info'">
              {{ statusMap[row.status]?.label || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="triggered_by"
          label="触发方式"
          width="110"
        />
        <el-table-column
          prop="start_time"
          label="开始时间"
          width="180"
        >
          <template #default="{ row }">
            {{ formatDateTime(row.start_time) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="duration"
          label="耗时"
          width="100"
        >
          <template #default="{ row }">
            {{ row.duration ? `${row.duration.toFixed(2)}s` : '-' }}
          </template>
        </el-table-column>
        <el-table-column
          label="数据量"
          width="140"
        >
          <template #default="{ row }">
            {{ row.rows_before ?? '-' }} -> {{ row.rows_after ?? '-' }}
          </template>
        </el-table-column>
        <el-table-column
          prop="error_message"
          label="错误信息"
          min-width="220"
          show-overflow-tooltip
        />
        <el-table-column
          label="操作"
          fixed="right"
          min-width="180"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="openDetail(row.execution_id)"
            >
              详情
            </el-button>
            <el-button
              v-if="isAdmin && row.status === 'failed'"
              link
              type="danger"
              @click="retryExecution(row.execution_id)"
            >
              重试
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
          @current-change="loadExecutions"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <el-drawer
      v-model="detailVisible"
      title="执行详情"
      size="55%"
    >
      <div v-if="currentExecution">
        <el-descriptions
          :column="2"
          border
        >
          <el-descriptions-item label="执行 ID">
            {{ currentExecution.execution_id }}
          </el-descriptions-item>
          <el-descriptions-item label="脚本 ID">
            {{ currentExecution.script_id }}
          </el-descriptions-item>
          <el-descriptions-item label="任务 ID">
            {{ currentExecution.task_id ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            {{ currentExecution.status }}
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">
            {{ formatDateTime(currentExecution.start_time) }}
          </el-descriptions-item>
          <el-descriptions-item label="结束时间">
            {{ formatDateTime(currentExecution.end_time) }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="drawer-section">
          <div class="section-title">执行参数</div>
          <pre>{{ toJsonText(currentExecution.params || {}) }}</pre>
        </div>

        <div class="drawer-section">
          <div class="section-title">执行结果</div>
          <pre>{{ toJsonText(currentExecution.result || {}) }}</pre>
        </div>

        <div class="drawer-section">
          <div class="section-title">错误堆栈</div>
          <pre>{{ currentExecution.error_trace || currentExecution.error_message || '无' }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { akshareExecutionsApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type { ExecutionStatsResponse, TaskExecution } from '@/types'
import { formatDateTime, toJsonText } from '@/views/data/utils'

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
const statusMap: Record<string, { label: string; type: 'info' | 'primary' | 'success' | 'warning' | 'danger' }> = {
  pending: { label: '等待中', type: 'info' },
  running: { label: '执行中', type: 'primary' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
  timeout: { label: '超时', type: 'warning' },
  cancelled: { label: '已取消', type: 'info' },
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
    ElMessage.error(getErrorMessage(error, '加载执行记录失败'))
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
    ElMessage.error(getErrorMessage(error, '加载执行详情失败'))
  }
}

async function retryExecution(executionId: string) {
  try {
    const result = await akshareExecutionsApi.retry(executionId)
    ElMessage.success(`已重试：${result.execution_id}`)
    await Promise.all([loadStats(), loadExecutions()])
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '重试执行失败'))
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
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.stat-title {
  color: #64748b;
  font-size: 13px;
}

.stat-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
}

.stat-value.success { color: #15803d; }
.stat-value.danger { color: #b91c1c; }
.stat-value.primary { color: #1d4ed8; }

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

.page-subtitle {
  margin-top: 4px;
  color: #64748b;
}

.toolbar {
  margin-bottom: 16px;
  justify-content: flex-start;
}

.toolbar-item {
  width: 180px;
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
  font-weight: 700;
}

pre {
  margin: 0;
  padding: 14px;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 12px;
  overflow: auto;
}

@media (max-width: 960px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
