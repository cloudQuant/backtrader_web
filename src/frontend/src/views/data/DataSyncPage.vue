<template>
  <div class="space-y-6">
    <el-card>
      <template #header>
        <div class="header-row">
          <div>
            <div class="page-title">
              {{ t('dataPages.syncPageTitle') }}
            </div>
            <div class="page-subtitle">
              {{ t('dataPages.syncPageDesc') }}
            </div>
          </div>
          <div class="toolbar-actions">
            <el-button
              :loading="testingConnection"
              @click="handleTestConnection"
            >
              {{ t('dataPages.syncTestConnection') }}
            </el-button>
            <el-button
              type="primary"
              :loading="savingConfig"
              @click="handleSaveConfig"
            >
              {{ t('dataPages.syncSaveConfig') }}
            </el-button>
          </div>
        </div>
      </template>

      <DataSyncConfigForm
        v-model:sync-mode="syncMode"
        v-model:sync-databases-input="syncDatabasesInput"
        :config="configForm"
        @update:config="updateConfigForm"
      />

      <div class="tips-grid">
        <div class="tip-card">
          <div class="tip-title">
            {{ t('dataPages.syncTipFillTitle') }}
          </div>
          <div class="tip-text">
            {{ t('dataPages.syncTipFillText') }}
          </div>
        </div>
        <div class="tip-card">
          <div class="tip-title">
            {{ t('dataPages.syncTipIncTitle') }}
          </div>
          <div class="tip-text">
            {{ t('dataPages.syncTipIncText') }}
          </div>
        </div>
        <div class="tip-card">
          <div class="tip-title">
            {{ t('dataPages.syncTipLimitTitle') }}
          </div>
          <div class="tip-text">
            {{ t('dataPages.syncTipLimitText') }}
          </div>
        </div>
      </div>

      <div
        v-if="connectionStatus"
        class="connection-grid"
      >
        <div
          v-for="(passed, key) in connectionStatus.checks"
          :key="key"
          class="connection-item"
        >
          <el-tag :type="passed ? 'success' : 'danger'">
            {{ passed ? t('dataPages.syncCheckPassed') : t('dataPages.syncCheckFailed') }}
          </el-tag>
          <div class="connection-content">
            <div class="connection-title">
              {{ labelForCheck(key) }}
            </div>
            <div class="connection-detail">
              {{ connectionStatus.details[key] || '-' }}
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <DataSyncActiveTasks
      :tasks="activeTasks"
      :status-label="statusLabel"
    />

    <DataSyncDatabaseTables
      :database-rows="databaseRows"
      :database-names="databaseNames"
      :loading-databases="loadingDatabases"
      :submitting-bulk-upload="submittingBulkUpload"
      :submitting-bulk-download="submittingBulkDownload"
      :format-remote-state="formatRemoteState"
      :format-local-state="formatLocalState"
      @sync="startSync"
    />

    <el-card>
      <template #header>
        <div class="section-header">
          <div>
            <div class="page-title small">
              {{ t('dataPages.syncHistoryTitle') }}
            </div>
            <div class="page-subtitle">
              {{ t('dataPages.syncHistoryDesc') }}
            </div>
          </div>
          <el-button @click="loadHistory">
            {{ t('dataPages.syncRefreshHistory') }}
          </el-button>
        </div>
      </template>

      <el-table
        v-loading="loadingHistory"
        :data="history"
        stripe
      >
        <el-table-column
          :label="t('dataPages.syncHistColTime')"
          width="220"
        >
          <template #default="{ row }">
            {{ formatDateTime(row.started_at) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.syncHistColDirection')"
          width="120"
        >
          <template #default="{ row }">
            {{ row.direction === 'upload' ? t('dataPages.syncDirUploadShort') : t('dataPages.syncDirDownloadShort') }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.syncHistColDatabases')"
          min-width="180"
        >
          <template #default="{ row }">
            {{ row.databases.join(', ') }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.syncHistColStatus')"
          width="120"
        >
          <template #default="{ row }">
            <el-tag :type="row.status === 'completed' ? 'success' : 'danger'">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.syncHistColDuration')"
          width="120"
        >
          <template #default="{ row }">
            {{ formatDuration(row.duration_seconds) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.syncHistColMessage')"
          min-width="260"
        >
          <template #default="{ row }">
            {{ row.error || row.message }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getErrorMessage } from '@/api/index'
import { syncApi } from '@/api/sync'
import DataSyncConfigForm from './components/DataSyncConfigForm.vue'
import DataSyncActiveTasks from './components/DataSyncActiveTasks.vue'
import DataSyncDatabaseTables from './components/DataSyncDatabaseTables.vue'
import type {
  DatabaseSyncInfo,
  SyncConfig,
  SyncConnectionStatus,
  SyncDirection,
  SyncMode,
  SyncTaskStatus,
} from '@/types'

const { t } = useI18n()

const configForm = reactive<SyncConfig>({
  connection_mode: 'direct_mysql',
  local_mysql_host: '127.0.0.1',
  local_mysql_port: 3306,
  local_mysql_user: 'root',
  local_mysql_password: '',
  sync_parallel_workers: 2,
  remote_host: '',
  remote_user: 'root',
  remote_ssh_key: '~/.ssh/id_rsa',
  remote_container: 'backtrader_mysql',
  remote_install_dir: '/opt/ai-for-trader',
  remote_mysql_host: '',
  remote_mysql_port: 3306,
  remote_mysql_user: 'root',
  remote_mysql_password: '',
  sync_databases: ['ai_for_trader', 'akshare_data'],
})

const connectionStatus = ref<SyncConnectionStatus | null>(null)
const databaseRows = ref<DatabaseSyncInfo[]>([])
const history = ref<SyncTaskStatus[]>([])
const activeTaskMap = ref<Record<string, SyncTaskStatus>>({})
const pollers = new Map<string, number>()
const syncDatabasesInput = ref('ai_for_trader, akshare_data')

const loadingDatabases = ref(false)
const loadingHistory = ref(false)
const savingConfig = ref(false)
const testingConnection = ref(false)
const submittingBulkUpload = ref(false)
const submittingBulkDownload = ref(false)
const syncMode = ref<SyncMode>('full')

const activeTasks = computed(() => Object.values(activeTaskMap.value))
const databaseNames = computed(() => databaseRows.value.map(item => item.name))

function formatDateTime(value: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function formatDuration(value: number | null) {
  if (value === null || Number.isNaN(value)) return '-'
  if (value < 60) return `${value.toFixed(1)}s`
  const minutes = Math.floor(value / 60)
  const seconds = Math.round(value % 60)
  return `${minutes}m${seconds}s`
}

function statusLabel(status: SyncTaskStatus['status']) {
  if (status === 'pending') return t('dataPages.syncStatusPending')
  if (status === 'running') return t('dataPages.syncStatusRunning')
  if (status === 'completed') return t('dataPages.syncStatusCompleted')
  return t('dataPages.syncStatusFailed')
}

function labelForCheck(key: string) {
  if (key === 'local_tools') return t('dataPages.syncCheckLocalTools')
  if (key === 'local_mysql') return t('dataPages.syncCheckLocalMysql')
  if (key === 'remote_mysql') return t('dataPages.syncCheckRemoteMysql')
  if (key === 'ssh') return t('dataPages.syncCheckSsh')
  if (key === 'docker') return t('dataPages.syncCheckDocker')
  if (key === 'remote_env') return t('dataPages.syncCheckRemoteEnv')
  return key
}

function formatRemoteState(row: DatabaseSyncInfo) {
  if (!row.remote.exists) return t('dataPages.syncStateNotExists')
  return t('dataPages.syncStateExists', { size: row.remote.size_display, tables: row.remote.table_count })
}

function formatLocalState(row: DatabaseSyncInfo) {
  if (!row.local.exists) return t('dataPages.syncStateNotExists')
  return t('dataPages.syncStateExists', { size: row.local.size_display, tables: row.local.table_count })
}

function normalizeDatabaseNames(value: string) {
  return value
    .split(/[\n,，]+/)
    .map(item => item.trim())
    .filter(Boolean)
}

function buildConfigPayload(): SyncConfig {
  return {
    ...configForm,
    connection_mode: 'direct_mysql',
    sync_databases: normalizeDatabaseNames(syncDatabasesInput.value),
  }
}

function updateConfigForm(nextConfig: SyncConfig) {
  Object.assign(configForm, nextConfig)
}

async function loadConfig() {
  const response = await syncApi.getConfig()
  Object.assign(configForm, response)
  configForm.connection_mode = 'direct_mysql'
  syncDatabasesInput.value = response.sync_databases.join(', ')
}

async function loadDatabases() {
  loadingDatabases.value = true
  try {
    const response = await syncApi.getDatabases()
    databaseRows.value = response.items
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.syncLoadDatabasesFailed')))
  } finally {
    loadingDatabases.value = false
  }
}

async function loadHistory() {
  loadingHistory.value = true
  try {
    const response = await syncApi.getHistory()
    history.value = response.items
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.syncLoadHistoryFailed')))
  } finally {
    loadingHistory.value = false
  }
}

async function persistConfig(options: { showSuccess?: boolean; reloadDatabases?: boolean } = {}) {
  const { showSuccess = false, reloadDatabases = false } = options
  savingConfig.value = true
  try {
    const response = await syncApi.saveConfig(buildConfigPayload())
    Object.assign(configForm, response)
    configForm.connection_mode = 'direct_mysql'
    syncDatabasesInput.value = response.sync_databases.join(', ')
    if (showSuccess) {
      ElMessage.success(t('dataPages.syncSavedSuccess'))
    }
    if (reloadDatabases) {
      await loadDatabases()
    }
  } finally {
    savingConfig.value = false
  }
}

async function handleSaveConfig() {
  try {
    await persistConfig({ showSuccess: true, reloadDatabases: true })
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.syncSaveFailed')))
  }
}

async function handleTestConnection() {
  testingConnection.value = true
  try {
    await persistConfig()
    connectionStatus.value = await syncApi.testConnection(buildConfigPayload())
    ElMessage.success(connectionStatus.value.success ? t('dataPages.syncTestPassed') : t('dataPages.syncTestPartial'))
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.syncTestFailed')))
  } finally {
    testingConnection.value = false
  }
}

async function startSync(direction: SyncDirection, databases: string[]) {
  if (databases.length === 0) {
    ElMessage.warning(t('dataPages.syncNoDatabases'))
    return
  }

  const actionLabel = direction === 'upload' ? t('dataPages.syncDirUpload') : t('dataPages.syncDirDownload')
  const loadingFlag = direction === 'upload' ? submittingBulkUpload : submittingBulkDownload

  try {
    await ElMessageBox.confirm(
      t('dataPages.syncConfirmMsg', { action: actionLabel, databases: databases.join(', ') }),
      t('dataPages.syncConfirmTitle'),
      { type: 'warning' }
    )
  } catch {
    return
  }

  loadingFlag.value = true
  try {
    const payload = { databases, confirm: true, compress: true, sync_mode: syncMode.value }
    const response = direction === 'upload'
      ? await syncApi.upload(payload)
      : await syncApi.download(payload)

    activeTaskMap.value = {
      ...activeTaskMap.value,
      [response.task_id]: {
        task_id: response.task_id,
        status: response.status,
        direction,
        databases,
        current_database: databases[0] ?? null,
        completed_databases: [],
        stage: 'queued',
        progress_pct: 0,
        message: response.message,
        started_at: new Date().toISOString(),
        finished_at: null,
        duration_seconds: null,
        error: null,
        sync_mode: syncMode.value,
      },
    }
    ElMessage.success(t('dataPages.syncTaskCreated'))
    void pollTask(response.task_id)
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.syncStartFailed')))
  } finally {
    loadingFlag.value = false
  }
}

async function pollTask(taskId: string) {
  clearPoller(taskId)
  try {
    const status = await syncApi.getStatus(taskId)
    activeTaskMap.value = {
      ...activeTaskMap.value,
      [taskId]: status,
    }
    if (status.status === 'completed' || status.status === 'failed') {
      clearPoller(taskId)
      await Promise.all([loadDatabases(), loadHistory()])
      if (status.status === 'completed') {
        ElMessage.success(t('dataPages.syncCompleted', { databases: status.databases.join(', ') }))
      } else {
        ElMessage.error(status.error || status.message)
      }
      return
    }
    const timer = window.setTimeout(() => {
      void pollTask(taskId)
    }, 2000)
    pollers.set(taskId, timer)
  } catch (error) {
    clearPoller(taskId)
    ElMessage.error(getErrorMessage(error, t('dataPages.syncStatusFetchFailed')))
  }
}

function clearPoller(taskId: string) {
  const timer = pollers.get(taskId)
  if (timer !== undefined) {
    window.clearTimeout(timer)
    pollers.delete(taskId)
  }
}

onMounted(async () => {
  try {
    await loadConfig()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.syncLoadConfigFailed')))
  }
  await Promise.all([loadDatabases(), loadHistory()])
})

onBeforeUnmount(() => {
  Array.from(pollers.values()).forEach(timer => window.clearTimeout(timer))
  pollers.clear()
})
</script>

<style scoped src="./DataSyncPage.styles.css"></style>
