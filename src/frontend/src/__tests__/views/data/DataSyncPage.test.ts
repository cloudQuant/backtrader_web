import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import type { DatabaseSyncInfo, SyncConfig, SyncConnectionStatus, SyncTaskStatus } from '@/types'
import { elStubs } from '@/test/stubs'

const configFixture: SyncConfig = {
  connection_mode: 'direct_mysql',
  local_mysql_host: '127.0.0.1',
  local_mysql_port: 3306,
  local_mysql_user: 'root',
  local_mysql_password: 'local-secret',
  sync_parallel_workers: 4,
  remote_host: '',
  remote_user: 'root',
  remote_ssh_key: '~/.ssh/id_rsa',
  remote_container: 'backtrader_mysql',
  remote_install_dir: '/opt/ai-for-investor',
  remote_mysql_host: '10.0.0.2',
  remote_mysql_port: 3306,
  remote_mysql_user: 'remote',
  remote_mysql_password: 'remote-secret',
  sync_databases: ['ai_for_investor', 'akshare_data'],
}

const databaseRows: DatabaseSyncInfo[] = [
  {
    name: 'ai_for_investor',
    local: { name: 'ai_for_investor', size_bytes: 1024, size_display: '1 KB', table_count: 12, exists: true },
    remote: { name: 'ai_for_investor', size_bytes: 512, size_display: '512 B', table_count: 10, exists: true },
  },
  {
    name: 'akshare_data',
    local: { name: 'akshare_data', size_bytes: 2048, size_display: '2 KB', table_count: 8, exists: true },
    remote: { name: 'akshare_data', size_bytes: 0, size_display: '0 B', table_count: 0, exists: false },
  },
]

const historyItem: SyncTaskStatus = {
  task_id: 'sync-1',
  status: 'completed',
  direction: 'upload',
  databases: ['ai_for_investor'],
  current_database: null,
  completed_databases: ['ai_for_investor'],
  stage: 'done',
  progress_pct: 100,
  message: 'synced',
  started_at: '2026-07-01T08:00:00Z',
  finished_at: '2026-07-01T08:00:12Z',
  duration_seconds: 12,
  error: null,
  sync_mode: 'full',
}

const connectionStatus: SyncConnectionStatus = {
  success: true,
  checks: {
    local_mysql: true,
    remote_mysql: true,
  },
  details: {
    local_mysql: 'local ok',
    remote_mysql: 'remote ok',
  },
}

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) => {
      if (!params) return key
      return `${key}:${Object.values(params).join('|')}`
    },
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

vi.mock('@/api/sync', () => ({
  syncApi: {
    getConfig: vi.fn(),
    saveConfig: vi.fn(),
    testConnection: vi.fn(),
    getDatabases: vi.fn(),
    upload: vi.fn(),
    download: vi.fn(),
    getStatus: vi.fn(),
    getHistory: vi.fn(),
  },
}))

vi.mock('@/api/index', () => ({
  getErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

import { ElMessage, ElMessageBox } from 'element-plus'
import DataSyncPage from '@/views/data/DataSyncPage.vue'
import DataSyncConfigForm from '@/views/data/components/DataSyncConfigForm.vue'
import { syncApi } from '@/api/sync'

const api = syncApi as unknown as Record<string, ReturnType<typeof vi.fn>>

async function flushAll() {
  await flushPromises()
  await new Promise(resolve => setTimeout(resolve, 0))
}

function doMount() {
  return mount(DataSyncPage, { global: { stubs: elStubs } })
}

describe('DataSyncPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    api.getConfig.mockResolvedValue({ ...configFixture })
    api.saveConfig.mockImplementation(async (payload: SyncConfig) => ({ ...payload }))
    api.testConnection.mockResolvedValue({ ...connectionStatus })
    api.getDatabases.mockResolvedValue({ items: databaseRows.map(row => ({ ...row })) })
    api.getHistory.mockResolvedValue({ items: [{ ...historyItem }] })
    api.upload.mockResolvedValue({ task_id: 'sync-2', status: 'pending', message: 'queued' })
    api.download.mockResolvedValue({ task_id: 'sync-3', status: 'pending', message: 'queued' })
    api.getStatus.mockResolvedValue({
      ...historyItem,
      task_id: 'sync-2',
      databases: ['ai_for_investor'],
    })
  })

  it('loads config, database state and sync history on mount', async () => {
    const wrapper = doMount()
    await flushAll()

    expect(api.getConfig).toHaveBeenCalled()
    expect(api.getDatabases).toHaveBeenCalled()
    expect(api.getHistory).toHaveBeenCalled()
    expect(wrapper.find('[data-test="sync-hero"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="sync-metrics"]').findAll('.sync-metric')).toHaveLength(4)
    expect(wrapper.find('[data-test="sync-config-panel"]').exists()).toBe(true)
    expect(wrapper.findComponent(DataSyncConfigForm).exists()).toBe(true)
    expect(wrapper.find('[data-test="sync-database-grid"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="sync-history-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="sync-history-table"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('ai_for_investor')
    expect(wrapper.text()).toContain('dataPages.syncConfigTitle')
  })

  it('saves config before testing connection and renders check results', async () => {
    const wrapper = doMount()
    await flushAll()

    await (wrapper.vm as unknown as { handleTestConnection: () => Promise<void> }).handleTestConnection()
    await flushAll()

    expect(api.saveConfig).toHaveBeenCalledWith(expect.objectContaining({
      connection_mode: 'direct_mysql',
      sync_databases: ['ai_for_investor', 'akshare_data'],
    }))
    expect(api.testConnection).toHaveBeenCalledWith(expect.objectContaining({
      remote_mysql_host: '10.0.0.2',
    }))
    expect(wrapper.find('[data-test="sync-connection-grid"]').exists()).toBe(true)
    expect(ElMessage.success).toHaveBeenCalledWith('dataPages.syncTestPassed')
  })

  it('starts an upload task and refreshes state after completion', async () => {
    const wrapper = doMount()
    await flushAll()

    await (wrapper.vm as unknown as {
      startSync: (direction: 'upload', databases: string[]) => Promise<void>
    }).startSync('upload', ['ai_for_investor'])
    await flushAll()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(api.upload).toHaveBeenCalledWith({
      databases: ['ai_for_investor'],
      confirm: true,
      compress: true,
      sync_mode: 'full',
    })
    expect(api.getStatus).toHaveBeenCalledWith('sync-2')
    expect(api.getDatabases).toHaveBeenCalledTimes(2)
    expect(api.getHistory).toHaveBeenCalledTimes(2)
  })
})
