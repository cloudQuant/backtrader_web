import request from './index'

export interface DataGovernanceProvider {
  id: string
  provider_id: string
  name: string
  category: string
  auth_type: string
  api_key_env?: string | null
  rate_limit: number
  is_active: boolean
}

export interface DataGovernanceEndpoint {
  id: string
  provider_id: string
  endpoint_name: string
  display_name: string
  category: string
  function_path?: string | null
  params_schema: Record<string, unknown>
  auth_type: string
  api_key_env?: string | null
  rate_limit: number
  cache_ttl_sec: number
  target_database: string
  target_table?: string | null
  normalization_profile: Record<string, unknown>
  quality_profile: Record<string, unknown>
  incremental_sync_key: string
  is_active: boolean
}

export interface DataPreviewResponse {
  columns: string[]
  rows: Array<Record<string, unknown>>
  metadata: Record<string, unknown>
  source_timestamp: string
  provider_latency_ms: number
  quality_warnings: string[]
  provider_id: string
  endpoint_name: string
}

export const dataGovernanceApi = {
  bootstrap() {
    return request.post<{ providers: number; seed_endpoints: number; akshare_migrated_endpoints: number }>('/data-governance/bootstrap')
  },
  listProviders() {
    return request.get<{ items: DataGovernanceProvider[]; total: number }>('/data-governance/providers')
  },
  listEndpoints(provider_id?: string) {
    return request.get<{ items: DataGovernanceEndpoint[]; total: number }>('/data-governance/endpoints', {
      params: provider_id ? { provider_id } : undefined,
    })
  },
  previewEndpoint(endpointId: string, params: Record<string, unknown>) {
    return request.post<DataPreviewResponse>(`/data-governance/endpoints/${endpointId}/preview`, { params })
  },
  createJob(endpointId: string, params: Record<string, unknown>) {
    return request.post<{ id: string; endpoint_id: string; status: string; row_count: number; created_at: string }>(`/data-governance/endpoints/${endpointId}/jobs`, { params })
  },
}
