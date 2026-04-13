<template>
  <div class="space-y-6">
    <el-card>
      <template #header>
        <div class="header-row">
          <div>
            <div class="page-title">数据同步</div>
            <div class="page-subtitle">在本地 MySQL 与远程 MySQL 之间按表直连同步数据库。</div>
          </div>
          <div class="toolbar-actions">
            <el-button
              :loading="testingConnection"
              @click="handleTestConnection"
            >
              测试连接
            </el-button>
            <el-button
              type="primary"
              :loading="savingConfig"
              @click="handleSaveConfig"
            >
              保存配置
            </el-button>
          </div>
        </div>
      </template>

      <el-form
        :model="configForm"
        label-width="120px"
      >
        <div class="config-section-title">同步模式</div>
        <div class="form-grid">
          <el-form-item label="同步方式">
            <el-input value="直连 MySQL（按表同步）" disabled />
          </el-form-item>
          <el-form-item label="同步模式">
            <el-select v-model="syncMode" class="full-width">
              <el-option label="完整同步" value="full" />
              <el-option label="仅结构" value="schema_only" />
              <el-option label="仅数据" value="data_only" />
            </el-select>
          </el-form-item>
        </div>

        <div class="config-section-title">本地 MySQL</div>
        <div class="form-grid">
          <el-form-item label="本地主机">
            <el-input v-model="configForm.local_mysql_host" placeholder="127.0.0.1" />
          </el-form-item>
          <el-form-item label="本地端口">
            <el-input-number v-model="configForm.local_mysql_port" class="full-width" :min="1" :max="65535" />
          </el-form-item>
          <el-form-item label="本地用户">
            <el-input v-model="configForm.local_mysql_user" placeholder="root" />
          </el-form-item>
          <el-form-item label="本地密码">
            <el-input v-model="configForm.local_mysql_password" show-password placeholder="输入本地 MySQL 密码" />
          </el-form-item>
        </div>

        <div class="config-section-title">远程 MySQL</div>
        <div class="form-grid">
          <el-form-item label="远程 MySQL 主机">
            <el-input v-model="configForm.remote_mysql_host" placeholder="43.167.221.188" />
          </el-form-item>
          <el-form-item label="远程 MySQL 端口">
            <el-input-number v-model="configForm.remote_mysql_port" class="full-width" :min="1" :max="65535" />
          </el-form-item>
          <el-form-item label="远程 MySQL 用户">
            <el-input v-model="configForm.remote_mysql_user" placeholder="root" />
          </el-form-item>
          <el-form-item label="远程 MySQL 密码">
            <el-input v-model="configForm.remote_mysql_password" show-password placeholder="直连模式必须填写远程 MySQL 密码" />
          </el-form-item>
        </div>

        <div class="config-section-title">同步范围</div>
        <div class="form-grid single-column">
          <el-form-item label="同步数据库">
            <el-input
              v-model="syncDatabasesInput"
              type="textarea"
              :rows="2"
              placeholder="例如：backtrader_web, akshare_data"
            />
          </el-form-item>
        </div>
      </el-form>

        <div class="tips-grid">
          <div class="tip-card">
            <div class="tip-title">填写提示</div>
            <div class="tip-text">
              当前页面只保留 MySQL 直连同步。只要远程 MySQL 主机、端口、用户名、密码可访问即可，不需要 SSH。
            </div>
          </div>
          <div class="tip-card">
            <div class="tip-title">增量同步规则</div>
            <div class="tip-text">
              数据同步会优先使用数据表的主键，其次使用唯一索引，先对比两端索引值，只传输目标库缺失的数据行。
            </div>
          </div>
          <div class="tip-card">
            <div class="tip-title">使用限制</div>
            <div class="tip-text">
              如果某张表没有主键或唯一索引，就无法安全判断哪些记录已存在，这类表暂时不支持“只同步缺失数据”。
            </div>
          </div>
        </div>

      <div v-if="connectionStatus" class="connection-grid">
        <div
          v-for="(passed, key) in connectionStatus.checks"
          :key="key"
          class="connection-item"
        >
          <el-tag :type="passed ? 'success' : 'danger'">
            {{ passed ? '通过' : '失败' }}
          </el-tag>
          <div class="connection-content">
            <div class="connection-title">{{ labelForCheck(key) }}</div>
            <div class="connection-detail">{{ connectionStatus.details[key] || '-' }}</div>
          </div>
        </div>
      </div>
    </el-card>

    <el-card v-if="activeTasks.length > 0">
      <template #header>
        <div class="page-title small">同步进度</div>
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
                {{ task.direction === 'upload' ? '上传到服务器' : '从服务器拉取' }}
                <span class="task-db">{{ task.current_database || task.databases.join(', ') }}</span>
              </div>
              <div class="task-subtitle">{{ task.message }}</div>
            </div>
            <el-tag :type="task.status === 'failed' ? 'danger' : task.status === 'completed' ? 'success' : 'warning'">
              {{ statusLabel(task.status) }}
            </el-tag>
          </div>
          <el-progress :percentage="task.progress_pct" :status="task.status === 'failed' ? 'exception' : undefined" />
        </div>
      </div>
    </el-card>

    <div class="dual-grid">
      <el-card>
        <template #header>
          <div class="section-header">
            <div>
              <div class="page-title small">上传到服务器</div>
              <div class="page-subtitle">把本地数据库覆盖同步到远程环境。</div>
            </div>
            <el-button type="primary" :loading="submittingBulkUpload" @click="startSync('upload', databaseNames)">
              全部上传
            </el-button>
          </div>
        </template>

        <el-table :data="databaseRows" v-loading="loadingDatabases" stripe>
          <el-table-column prop="name" label="数据库" min-width="160" />
          <el-table-column label="本地大小" width="120">
            <template #default="{ row }">
              {{ row.local.exists ? row.local.size_display : '不存在' }}
            </template>
          </el-table-column>
          <el-table-column label="远程状态" min-width="160">
            <template #default="{ row }">
              {{ formatRemoteState(row) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" @click="startSync('upload', [row.name])">上传</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card>
        <template #header>
          <div class="section-header">
            <div>
              <div class="page-title small">从服务器拉取</div>
              <div class="page-subtitle">把远程数据库覆盖同步到本地环境。</div>
            </div>
            <el-button :loading="submittingBulkDownload" @click="startSync('download', databaseNames)">
              全部拉取
            </el-button>
          </div>
        </template>

        <el-table :data="databaseRows" v-loading="loadingDatabases" stripe>
          <el-table-column prop="name" label="数据库" min-width="160" />
          <el-table-column label="远程大小" width="120">
            <template #default="{ row }">
              {{ row.remote.exists ? row.remote.size_display : '不存在' }}
            </template>
          </el-table-column>
          <el-table-column label="本地状态" min-width="160">
            <template #default="{ row }">
              {{ formatLocalState(row) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" @click="startSync('download', [row.name])">拉取</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <el-card>
      <template #header>
        <div class="section-header">
          <div>
            <div class="page-title small">同步历史</div>
            <div class="page-subtitle">展示最近一次同步结果与耗时。</div>
          </div>
          <el-button @click="loadHistory">刷新历史</el-button>
        </div>
      </template>

      <el-table :data="history" v-loading="loadingHistory" stripe>
        <el-table-column label="时间" width="220">
          <template #default="{ row }">
            {{ formatDateTime(row.started_at) }}
          </template>
        </el-table-column>
        <el-table-column label="方向" width="120">
          <template #default="{ row }">
            {{ row.direction === 'upload' ? '上传' : '拉取' }}
          </template>
        </el-table-column>
        <el-table-column label="数据库" min-width="180">
          <template #default="{ row }">
            {{ row.databases.join(', ') }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.status === 'completed' ? 'success' : 'danger'">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="120">
          <template #default="{ row }">
            {{ formatDuration(row.duration_seconds) }}
          </template>
        </el-table-column>
        <el-table-column label="消息" min-width="260">
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

const configForm = reactive<SyncConfig>({
  connection_mode: 'direct_mysql',
  local_mysql_host: '127.0.0.1',
  local_mysql_port: 3306,
  local_mysql_user: 'root',
  local_mysql_password: '',
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
  if (status === 'pending') return '等待中'
  if (status === 'running') return '执行中'
  if (status === 'completed') return '已完成'
  return '失败'
}

function labelForCheck(key: string) {
  if (key === 'local_tools') return '本地命令依赖'
  if (key === 'local_mysql') return '本地 MySQL'
  if (key === 'remote_mysql') return '远程 MySQL'
  if (key === 'ssh') return 'SSH 连通性'
  if (key === 'docker') return 'Docker 容器状态'
  if (key === 'remote_env') return '远程密码配置'
  return key
}

function formatRemoteState(row: DatabaseSyncInfo) {
  if (!row.remote.exists) return '不存在'
  return `已存在（${row.remote.size_display} / ${row.remote.table_count}表）`
}

function formatLocalState(row: DatabaseSyncInfo) {
  if (!row.local.exists) return '不存在'
  return `已存在（${row.local.size_display} / ${row.local.table_count}表）`
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
    ElMessage.error(getErrorMessage(error, '加载数据库状态失败'))
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
    ElMessage.error(getErrorMessage(error, '加载同步历史失败'))
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
      ElMessage.success('同步配置已保存')
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
    ElMessage.error(getErrorMessage(error, '保存同步配置失败'))
  }
}

async function handleTestConnection() {
  testingConnection.value = true
  try {
    await persistConfig()
    connectionStatus.value = await syncApi.testConnection(buildConfigPayload())
    ElMessage.success(connectionStatus.value.success ? '连接测试通过' : '连接测试完成，请查看结果')
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '测试连接失败'))
  } finally {
    testingConnection.value = false
  }
}

async function startSync(direction: SyncDirection, databases: string[]) {
  if (databases.length === 0) {
    ElMessage.warning('没有可同步的数据库')
    return
  }

  const actionLabel = direction === 'upload' ? '上传到服务器' : '从服务器拉取'
  const loadingFlag = direction === 'upload' ? submittingBulkUpload : submittingBulkDownload

  try {
    await ElMessageBox.confirm(
      `${actionLabel}会覆盖目标数据库，是否继续？\n\n数据库：${databases.join(', ')}`,
      '同步确认',
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
    ElMessage.success('同步任务已创建')
    void pollTask(response.task_id)
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '启动同步任务失败'))
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
        ElMessage.success(`同步完成：${status.databases.join(', ')}`)
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
    ElMessage.error(getErrorMessage(error, '查询同步任务状态失败'))
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
    ElMessage.error(getErrorMessage(error, '加载同步配置失败'))
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
  color: #64748b;
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
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px;
  background: #f8fafc;
}

.connection-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.connection-title,
.task-title {
  font-weight: 600;
  color: #0f172a;
}

.config-section-title,
.tip-title {
  font-weight: 700;
  color: #0f172a;
  margin: 4px 0 12px;
}

.tip-text {
  color: #475569;
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
