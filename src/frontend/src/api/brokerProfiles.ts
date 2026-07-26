import request from './index'

export interface BrokerProfileRuntimeBinding {
  gateway_key: string
  exchange_type: string
  account_id: string
  has_runtime: boolean
}

export interface BrokerProfile {
  id: string
  broker_id: string
  account_alias: string
  capabilities: string[]
  credentials_ref: Record<string, string>
  runtime_gateway_key?: string | null
  runtime_account_id?: string | null
  enabled: boolean
  last_health: Record<string, unknown> | null
  created_by: string
  is_destructive_enabled: boolean
  credentials_rotated_at: string | null
  rotation_warning: string | null
  runtime_binding?: BrokerProfileRuntimeBinding | null
  created_at: string | null
  updated_at: string | null
}

export interface BrokerProfileCreatePayload {
  broker_id: string
  account_alias: string
  capabilities: string[]
  credentials_ref: Record<string, string>
  credentials_rotated_at?: string
  runtime_gateway_key?: string
  runtime_account_id?: string
}

export interface BrokerProfileEnableWritePayload {
  confirmation_text: string
  idempotency_key: string
}

export interface BrokerAccountItem {
  account_id: string
  cash?: number
  equity?: number
  available_cash?: number
}

export const brokerProfilesApi = {
  listProfiles() {
    return request.get<{ items: BrokerProfile[]; total: number }>('/brokers/profiles')
  },
  createProfile(payload: BrokerProfileCreatePayload) {
    return request.post<BrokerProfile>('/brokers/profiles', payload)
  },
  getHealth(profileId: string) {
    return request.get<Record<string, unknown>>(`/brokers/profiles/${profileId}/health`)
  },
  getAccounts(profileId: string) {
    return request.get<{ items: BrokerAccountItem[]; total: number }>(`/brokers/profiles/${profileId}/accounts`)
  },
  getPositions(profileId: string) {
    return request.get<{ items: Array<Record<string, unknown>>; total: number }>(`/brokers/profiles/${profileId}/positions`)
  },
  getOrders(profileId: string) {
    return request.get<{ items: Array<Record<string, unknown>>; total: number }>(`/brokers/profiles/${profileId}/orders`)
  },
  getQuote(profileId: string, symbol: string) {
    return request.get<Record<string, unknown>>(`/brokers/profiles/${profileId}/quotes`, {
      params: { symbol },
    })
  },
  enableWrite(profileId: string, payload: BrokerProfileEnableWritePayload) {
    return request.post<BrokerProfile>(`/brokers/profiles/${profileId}/enable-write`, payload)
  },
}
