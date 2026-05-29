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
        {{ t('dataPages.airflowBackend', { backend: orchestrationStatus.type === 'apscheduler' ? t('dataPages.airflowBackendApSched') : t('dataPages.airflowBackendUninit') }) }}
      </template>
      {{ t('dataPages.airflowNotConnected') }}
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
            {{ t('dataPages.airflowRefresh') }}
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
          :label="t('dataPages.airflowColDagId')"
          min-width="200"
        />
        <el-table-column
          prop="schedule_interval"
          :label="t('dataPages.airflowColSchedule')"
          width="150"
        />
        <el-table-column
          :label="t('dataPages.airflowColStatus')"
          width="100"
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
          width="200"
        >
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              data-testid="dag-trigger-btn"
              @click="triggerDag(row.dag_id)"
            >
              {{ t('dataPages.airflowExecute') }}
            </el-button>
            <el-button
              size="small"
              data-testid="dag-runs-btn"
              @click="viewRuns(row.dag_id)"
            >
              {{ t('dataPages.airflowHistory') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Fallback: APScheduler mode info -->
    <el-card v-else>
      <el-empty :description="t('dataPages.airflowEmptyDesc')" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { airflowApi } from '@/api/airflow'
import type { AirflowDAG, OrchestrationStatus } from '@/api/airflow'

const { t } = useI18n()
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
    ElMessage.error(t('dataPages.airflowListFailed'))
  } finally {
    loading.value = false
  }
}

async function togglePause(dagId: string, isPaused: boolean) {
  try {
    await airflowApi.togglePause(dagId, isPaused)
    ElMessage.success(isPaused ? t('dataPages.airflowDagPaused') : t('dataPages.airflowDagResumed'))
    await refreshDags()
  } catch {
    ElMessage.error(t('dataPages.airflowOpFailed'))
  }
}

async function triggerDag(dagId: string) {
  try {
    await airflowApi.triggerDag(dagId)
    ElMessage.success(t('dataPages.airflowDagTriggered'))
  } catch {
    ElMessage.error(t('dataPages.airflowTriggerFailed'))
  }
}

function viewRuns(dagId: string) {
  // TODO: Navigate to DAG runs detail page
  ElMessage.info(t('dataPages.airflowViewHistory', { dag: dagId }))
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
