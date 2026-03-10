/**
 * 模拟交易 API
 */
import request from './index'

export interface SimulationInstanceInfo {
  id: string
  strategy_id: string
  strategy_name: string
  status: 'running' | 'stopped' | 'error'
  pid: number | null
  error: string | null
  params: Record<string, any>
  created_at: string
  started_at: string | null
  stopped_at: string | null
  log_dir: string | null
}

export interface SimulationInstanceListResponse {
  total: number
  instances: SimulationInstanceInfo[]
}

export interface SimulationBatchResponse {
  success: number
  failed: number
  details: { id: string; strategy_id: string; result: string }[]
}

export const simulationApi = {
  list(): Promise<SimulationInstanceListResponse> {
    return request.get('/simulation/')
  },

  add(strategy_id: string, params?: Record<string, any>): Promise<SimulationInstanceInfo> {
    return request.post('/simulation/', { strategy_id, params })
  },

  remove(instanceId: string): Promise<{ message: string }> {
    return request.delete(`/simulation/${instanceId}`)
  },

  get(instanceId: string): Promise<SimulationInstanceInfo> {
    return request.get(`/simulation/${instanceId}`)
  },

  start(instanceId: string): Promise<SimulationInstanceInfo> {
    return request.post(`/simulation/${instanceId}/start`)
  },

  stop(instanceId: string): Promise<SimulationInstanceInfo> {
    return request.post(`/simulation/${instanceId}/stop`)
  },

  startAll(): Promise<SimulationBatchResponse> {
    return request.post('/simulation/start-all')
  },

  stopAll(): Promise<SimulationBatchResponse> {
    return request.post('/simulation/stop-all')
  },

  getTemplateConfig(id: string): Promise<any> {
    return request.get(`/strategy/templates/${id}/config`)
  },

  listLogs(instanceId: string): Promise<{ files: { name: string; size: number }[] }> {
    return request.get(`/simulation/${instanceId}/logs`)
  },

  getLog(instanceId: string, filename: string, tail?: number): Promise<string> {
    const params = tail != null ? { tail } : {}
    return request.get(
      `/simulation/${instanceId}/logs/${encodeURIComponent(filename)}`,
      { params, responseType: 'text' }
    )
  },

  async downloadLog(instanceId: string, filename: string): Promise<void> {
    const resp = await request.get(
      `/simulation/${instanceId}/logs/${encodeURIComponent(filename)}/download`,
      { responseType: 'blob' }
    )
    const blob = resp as unknown as Blob
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },
}
