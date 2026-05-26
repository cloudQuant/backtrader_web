<template>
  <div class="airflow-dags-page">
    <!-- Orchestration Status Banner -->
    <el-alert
      v-if="orchestrationStatus && orchestrationStatus.type !== 'airflow'"
      type="info"
      :closable="false"
      class="mb-4"
    >
      <template #title>
        当前编排后端: {{ orchestrationStatus.type === 'apscheduler' ? 'APScheduler (本地)' : '未初始化' }}
      </template>
      Airflow 服务未连接，DAG 管理功能不可用。定时任务通过 APScheduler 执行。
    </el-alert>

    <!-- DAG List -->
    <el-card v-if="orchestrationStatus?.type === 'airflow'">
      <template #header>
        <div class="flex items-center justify-between">
          <span class="text-lg font-medium">Airflow DAGs</span>
          <el-button
            size="small"
            @click="refreshDags"
          >
            刷新
          </el-button>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="dags"
        stripe
      >
        <el-table-column
          prop="dag_id"
          label="DAG ID"
          min-width="200"
        />
        <el-table-column
          prop="schedule_interval"
          label="调度表达式"
          width="150"
        />
        <el-table-column
          label="状态"
          width="100"
        >
          <template #default="{ row }">
            <el-switch
              :model-value="!row.is_paused"
              active-text="运行"
              inactive-text="暂停"
              data-testid="dag-pause-switch"
              @change="(val: string | number | boolean) => togglePause(row.dag_id, !(val as boolean))"
            />
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="200"
        >
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              data-testid="dag-trigger-btn"
              @click="triggerDag(row.dag_id)"
            >
              执行
            </el-button>
            <el-button
              size="small"
              data-testid="dag-runs-btn"
              @click="viewRuns(row.dag_id)"
            >
              历史
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Fallback: APScheduler mode info -->
    <el-card v-else>
      <el-empty description="Airflow 未连接，请使用数据管理中的定时任务功能" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { airflowApi } from '@/api/airflow'
import type { AirflowDAG, OrchestrationStatus } from '@/api/airflow'

const loading = ref(false)
const dags = ref<AirflowDAG[]>([])
const orchestrationStatus = ref<OrchestrationStatus | null>(null)

async function loadStatus() {
  try {
    orchestrationStatus.value = await airflowApi.getStatus()
  } catch {
    orchestrationStatus.value = { type: 'unknown' }
  }
}

async function refreshDags() {
  loading.value = true
  try {
    const result = await airflowApi.listDags()
    dags.value = result.dags || []
  } catch {
    ElMessage.error('获取 DAG 列表失败')
  } finally {
    loading.value = false
  }
}

async function togglePause(dagId: string, isPaused: boolean) {
  try {
    await airflowApi.togglePause(dagId, isPaused)
    ElMessage.success(isPaused ? 'DAG 已暂停' : 'DAG 已恢复')
    await refreshDags()
  } catch {
    ElMessage.error('操作失败')
  }
}

async function triggerDag(dagId: string) {
  try {
    await airflowApi.triggerDag(dagId)
    ElMessage.success('DAG 已触发执行')
  } catch {
    ElMessage.error('触发执行失败')
  }
}

function viewRuns(dagId: string) {
  // TODO: Navigate to DAG runs detail page
  ElMessage.info(`查看 ${dagId} 执行历史`)
}

onMounted(async () => {
  await loadStatus()
  if (orchestrationStatus.value?.type === 'airflow') {
    await refreshDags()
  }
})
</script>

<style scoped>
.airflow-dags-page {
  padding: 0;
}
</style>
