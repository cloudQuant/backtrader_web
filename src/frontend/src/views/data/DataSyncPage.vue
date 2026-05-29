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

      <el-form
        :model="configForm"
        label-width="120px"
      >
        <div class="config-section-title">
          {{ t('dataPages.syncSecMode') }}
        </div>
        <div class="form-grid">
          <el-form-item :label="t('dataPages.syncFormMethod')">
            <el-input
              :value="t('dataPages.syncMethodValue')"
              disabled
            />
          </el-form-item>
          <el-form-item :label="t('dataPages.syncFormMode')">
            <el-select
              v-model="syncMode"
              class="full-width"
            >
              <el-option
                :label="t('dataPages.syncModeFull')"
                value="full"
              />
              <el-option
                :label="t('dataPages.syncModeSchemaOnly')"
                value="schema_only"
              />
              <el-option
                :label="t('dataPages.syncModeDataOnly')"
                value="data_only"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('dataPages.syncFormParallel')">
            <el-input-number
              v-model="configForm.sync_parallel_workers"
              class="full-width"
              :min="1"
              :max="16"
            />
          </el-form-item>
        </div>

        <div class="config-section-title">
          {{ t('dataPages.syncSecLocal') }}
        </div>
        <div class="form-grid">
          <el-form-item :label="t('dataPages.syncFormLocalHost')">
            <el-input
              v-model="configForm.local_mysql_host"
              placeholder="127.0.0.1"
            />
          </el-form-item>
          <el-form-item :label="t('dataPages.syncFormLocalPort')">
            <el-input-number
              v-model="configForm.local_mysql_port"
              class="full-width"
              :min="1"
              :max="65535"
            />
          </el-form-item>
          <el-form-item :label="t('dataPages.syncFormLocalUser')">
            <el-input
              v-model="configForm.local_mysql_user"
              placeholder="root"
            />
          </el-form-item>
          <el-form-item :label="t('dataPages.syncFormLocalPwd')">
            <el-input
              v-model="configForm.local_mysql_password"
              show-password
              :placeholder="t('dataPages.syncLocalPwdPh')"
            />
          </el-form-item>
        </div>

        <div class="config-section-title">
          {{ t('dataPages.syncSecRemote') }}
        </div>
        <div class="form-grid">
          <el-form-item :label="t('dataPages.syncFormRemoteHost')">
            <el-input
              v-model="configForm.remote_mysql_host"
              placeholder="43.167.221.188"
            />
          </el-form-item>
          <el-form-item :label="t('dataPages.syncFormRemotePort')">
            <el-input-number
              v-model="configForm.remote_mysql_port"
              class="full-width"
              :min="1"
              :max="65535"
            />
          </el-form-item>
          <el-form-item :label="t('dataPages.syncFormRemoteUser')">
            <el-input
              v-model="configForm.remote_mysql_user"
              placeholder="root"
            />
          </el-form-item>
          <el-form-item :label="t('dataPages.syncFormRemotePwd')">
            <el-input
              v-model="configForm.remote_mysql_password"
              show-password
              :placeholder="t('dataPages.syncRemotePwdPh')"
            />
          </el-form-item>
        </div>

        <div class="config-section-title">
          {{ t('dataPages.syncSecScope') }}
        </div>
        <div class="form-grid single-column">
          <el-form-item :label="t('dataPages.syncFormDatabases')">
            <el-input
              v-model="syncDatabasesInput"
              type="textarea"
              :rows="2"
              :placeholder="t('dataPages.syncDatabasesPh')"
            />
          </el-form-item>
        </div>
      </el-form>

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

    <el-card v-if="activeTasks.length > 0">
      <template #header>
        <div class="page-title small">
          {{ t('dataPages.syncProgressTitle') }}
        </div>
      </template>

      <div class="task-list">
        <div
          v-for="task in activeTasks"
          :key="task.task_id"
          class="task-item"
        >
          <div class="task-top">
            <div>
              <div class="task-title">
                {{ task.direction === 'upload' ? t('dataPages.syncDirUpload') : t('dataPages.syncDirDownload') }}
                <span class="task-db">{{ task.current_database || task.databases.join(', ') }}</span>
              </div>
              <div class="task-subtitle">
                {{ task.message }}
              </div>
            </div>
            <el-tag :type="task.status === 'failed' ? 'danger' : task.status === 'completed' ? 'success' : 'warning'">
              {{ statusLabel(task.status) }}
            </el-tag>
          </div>
          <el-progress
            :percentage="task.progress_pct"
            :status="task.status === 'failed' ? 'exception' : undefined"
          />
        </div>
      </div>
    </el-card>

    <div class="dual-grid">
      <el-card>
        <template #header>
          <div class="section-header">
            <div>
              <div class="page-title small">
                {{ t('dataPages.syncUploadTitle') }}
              </div>
              <div class="page-subtitle">
                {{ t('dataPages.syncUploadDesc') }}
              </div>
            </div>
            <el-button
              type="primary"
              :loading="submittingBulkUpload"
              @click="startSync('upload', databaseNames)"
            >
              {{ t('dataPages.syncUploadAll') }}
            </el-button>
          </div>
        </template>

        <el-table
          v-loading="loadingDatabases"
          :data="databaseRows"
          stripe
        >
          <el-table-column
            prop="name"
            :label="t('dataPages.syncColDatabase')"
            min-width="160"
          />
          <el-table-column
            :label="t('dataPages.syncColLocalSize')"
            width="120"
          >
            <template #default="{ row }">
              {{ row.local.exists ? row.local.size_display : t('dataPages.syncStateNotExists') }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.syncColRemoteState')"
            min-width="160"
          >
            <template #default="{ row }">
              {{ formatRemoteState(row) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.syncColActions')"
            width="120"
          >
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                @click="startSync('upload', [row.name])"
              >
                {{ t('dataPages.syncActionUpload') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card>
        <template #header>
          <div class="section-header">
            <div>
              <div class="page-title small">
                {{ t('dataPages.syncDownloadTitle') }}
              </div>
              <div class="page-subtitle">
                {{ t('dataPages.syncDownloadDesc') }}
              </div>
            </div>
            <el-button
              :loading="submittingBulkDownload"
              @click="startSync('download', databaseNames)"
            >
              {{ t('dataPages.syncDownloadAll') }}
            </el-button>
          </div>
        </template>

        <el-table
          v-loading="loadingDatabases"
          :data="databaseRows"
          stripe
        >
          <el-table-column
            prop="name"
            :label="t('dataPages.syncColDatabase')"
            min-width="160"
          />
          <el-table-column
            :label="t('dataPages.syncColRemoteSize')"
            width="120"
          >
            <template #default="{ row }">
              {{ row.remote.exists ? row.remote.size_display : t('dataPages.syncStateNotExists') }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.syncColLocalState')"
            min-width="160"
          >
            <template #default="{ row }">
              {{ formatLocalState(row) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.syncColActions')"
            width="120"
          >
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                @click="startSync('download', [row.name])"
              >
                {{ t('dataPages.syncActionDownload') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

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
  remote_install_dir: '/opt/backtrader_web',
  remote_mysql_host: '',
  remote_mysql_port: 3306,
  remote_mysql_user: 'root',
  remote_mysql_password: '',
  sync_databases: ['backtrader_web', 'akshare_data'],
})

const connectionStatus = ref<SyncConnectionStatus | null>(null)
const databaseRows = ref<DatabaseSyncInfo[]>([])
const history = ref<SyncTaskStatus[]>([])
const activeTaskMap = ref<Record<string, SyncTaskStatus>>({})
const pollers = new Map<string, number>()
const syncDatabasesInput = ref('backtrader_web, akshare_data')

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

<style scoped>
.header-row,
.section-header,
.toolbar-actions {
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

.page-title.small {
  font-size: 16px;
}

.page-subtitle,
.task-subtitle,
.connection-detail,
.task-db {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.form-grid,
.dual-grid,
.connection-grid,
.tips-grid {
  display: grid;
  gap: 16px;
}

.form-grid {
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}

.form-grid.single-column {
  grid-template-columns: 1fr;
}

.dual-grid {
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
}

.tips-grid {
  margin-top: 12px;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}

.connection-grid {
  margin-top: 16px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.connection-item,
.task-item,
.tip-card {
  border: 1px solid var(--border-color-light);
  border-radius: 12px;
  padding: 14px;
  background: var(--bg-color-page);
}

.connection-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.connection-title,
.task-title {
  font-weight: 600;
  color: var(--text-color-primary);
}

.config-section-title,
.tip-title {
  font-weight: 700;
  color: var(--text-color-primary);
  margin: 4px 0 12px;
}

.tip-text {
  color: var(--text-color-regular);
  font-size: 13px;
  line-height: 1.6;
}

.task-list,
.database-tags {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.database-tags {
  flex-direction: row;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 4px;
}

.db-tag {
  margin-right: 8px;
}

.full-width {
  width: 100%;
}
</style>
