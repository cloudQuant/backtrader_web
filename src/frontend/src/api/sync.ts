import api from './index'
import type {
  DatabaseSyncInfo,
  SyncConfig,
  SyncConnectionStatus,
  SyncRequest,
  SyncTaskCreateResponse,
  SyncTaskStatus,
} from '@/types'

export const syncApi = {
  getConfig() {
    return api.get<SyncConfig>('/data/sync/config')
  },
  saveConfig(payload: SyncConfig) {
    return api.put<SyncConfig, SyncConfig>('/data/sync/config', payload)
  },
  testConnection(payload: SyncConfig) {
    return api.post<SyncConnectionStatus, SyncConfig>('/data/sync/test-connection', payload)
  },
  getDatabases() {
    return api.get<{ items: DatabaseSyncInfo[] }>('/data/sync/databases')
  },
  upload(payload: SyncRequest) {
    return api.post<SyncTaskCreateResponse, SyncRequest>('/data/sync/upload', payload)
  },
  download(payload: SyncRequest) {
    return api.post<SyncTaskCreateResponse, SyncRequest>('/data/sync/download', payload)
  },
  getStatus(taskId: string) {
    return api.get<SyncTaskStatus>(`/data/sync/status/${taskId}`)
  },
  getHistory(limit: number = 50) {
    return api.get<{ items: SyncTaskStatus[] }>('/data/sync/history', { params: { limit } })
  },
}
