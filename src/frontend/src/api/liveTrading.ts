/**
 * 实盘交易 API
 */
import request from './index'

export interface LiveInstanceInfo {
  id: string
  strategy_id: string
  strategy_name: string
  status: 'running' | 'stopped' | 'error'
  pid: number | null
  error: string | null
  params: Record<string, unknown>
  created_at: string
  started_at: string | null
  stopped_at: string | null
  log_dir: string | null
}

export interface LiveInstanceListResponse {
  total: number
  instances: LiveInstanceInfo[]
}

export interface LiveBatchResponse {
  success: number
  failed: number
  details: { id: string; strategy_id: string; result: string }[]
}

export interface LiveGatewayPresetInfo {
  description?: string | null
  id: string
  name: string
  params: Record<string, unknown>
  editable_fields: LiveGatewayPresetFieldInfo[]
}

export interface LiveGatewayPresetFieldInfo {
  key: string
  label: string
  input_type: 'string' | 'boolean'
  placeholder?: string | null
}

export interface LiveGatewayPresetListResponse {
  total: number
  presets: LiveGatewayPresetInfo[]
}

export const liveTradingApi = {
  list(): Promise<LiveInstanceListResponse> {
    return request.get('/live-trading/')
  },

  listPresets(): Promise<LiveGatewayPresetListResponse> {
    return request.get('/live-trading/presets')
  },

  add(strategy_id: string, params?: Record<string, unknown>): Promise<LiveInstanceInfo> {
    return request.post('/live-trading/', { strategy_id, params })
  },

  remove(instanceId: string): Promise<{ message: string }> {
    return request.delete(`/live-trading/${instanceId}`)
  },

  get(instanceId: string): Promise<LiveInstanceInfo> {
    return request.get(`/live-trading/${instanceId}`)
  },

  start(instanceId: string): Promise<LiveInstanceInfo> {
    return request.post(`/live-trading/${instanceId}/start`)
  },

  stop(instanceId: string): Promise<LiveInstanceInfo> {
    return request.post(`/live-trading/${instanceId}/stop`)
  },

  startAll(): Promise<LiveBatchResponse> {
    return request.post('/live-trading/start-all')
  },

  stopAll(): Promise<LiveBatchResponse> {
    return request.post('/live-trading/stop-all')
  },
}
