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

export interface GatewayHealthInfo {
  gateway_key: string
  state: string
  is_healthy: boolean
  market_connection: string
  trade_connection: string
  uptime_sec: number
  last_heartbeat: number | null
  heartbeat_age_sec: number | null
  last_tick_time: number | null
  last_order_time: number | null
  strategy_count: number
  symbol_count: number
  tick_count: number
  order_count: number
  recent_errors: { timestamp: number; source: string; message: string }[]
  ref_count: number
  instances: string[]
  exchange?: string
  asset_type?: string
  account_id?: string
  strategy_name?: string
}

export interface GatewayHealthListResponse {
  total: number
  gateways: GatewayHealthInfo[]
}

export interface GatewayConnectRequest {
  exchange_type: string
  credentials: Record<string, unknown>
}

export interface GatewayConnectResponse {
  gateway_key: string
  status: string
  message: string
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

  listGatewayHealth(): Promise<GatewayHealthListResponse> {
    return request.get('/live-trading/gateways/health')
  },

  connectGateway(data: GatewayConnectRequest): Promise<GatewayConnectResponse> {
    return request.post('/live-trading/gateways/connect', data)
  },

  disconnectGateway(gatewayKey: string): Promise<GatewayConnectResponse> {
    return request.post('/live-trading/gateways/disconnect', null, { params: { gateway_key: gatewayKey } })
  },

  listConnectedGateways(): Promise<{ total: number; gateways: { gateway_key: string; exchange_type: string; account_id: string; has_runtime: boolean }[] }> {
    return request.get('/live-trading/gateways/connected')
  },

  queryGatewayAccount(gatewayKey: string): Promise<Record<string, unknown>> {
    return request.get(`/live-trading/gateways/${encodeURIComponent(gatewayKey)}/account`)
  },

  queryGatewayPositions(gatewayKey: string): Promise<{ total: number; positions: Record<string, unknown>[] }> {
    return request.get(`/live-trading/gateways/${encodeURIComponent(gatewayKey)}/positions`)
  },
}
