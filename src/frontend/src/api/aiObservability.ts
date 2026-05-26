import request from '@/api/index'

export interface AICallSummary {
  total_calls: number
  successful_calls?: number
  failed_calls: number
  total_tokens?: number
  estimated_cost_usd?: number
  avg_latency_ms?: number
  failure_rate?: number
  p95_latency_ms?: number
  p99_latency_ms?: number
}

export interface AIUsageGroup {
  date?: string
  service_name?: string
  model_name?: string
  user_id?: string
  total_calls: number
  successful_calls?: number
  failed_calls?: number
  total_tokens?: number
  estimated_cost_usd?: number
  avg_latency_ms?: number
}

export interface AIUsageStats {
  summary: AICallSummary
  by_day: AIUsageGroup[]
  by_service: AIUsageGroup[]
  by_model: AIUsageGroup[]
  by_user?: AIUsageGroup[]
}

export interface AIFailureGroup {
  error_code?: string
  service_name?: string
  failed_calls: number
  total_tokens?: number
  estimated_cost_usd?: number
}

export interface AIFailureRecord {
  id: string
  user_id?: string | null
  service_name: string
  mode?: string
  model_name?: string
  provider?: string
  total_tokens?: number
  estimated_cost_usd?: number
  latency_ms?: number
  status?: string
  error_code?: string | null
  error_message?: string | null
  created_at?: string
}

export interface AIFailureStats {
  summary: AICallSummary
  by_error_code: AIFailureGroup[]
  by_service: AIFailureGroup[]
  recent_failures: AIFailureRecord[]
}

export interface AISlowCallGroup {
  service_name: string
  total_calls: number
  avg_latency_ms: number
  p95_latency_ms: number
  p99_latency_ms: number
}

export interface AISlowCallRecord {
  id: string
  user_id?: string | null
  service_name: string
  mode?: string
  model_name?: string
  provider?: string
  total_tokens?: number
  estimated_cost_usd?: number
  latency_ms: number
  status?: string
  error_code?: string | null
  created_at?: string
}

export interface AISlowCallStats {
  summary: AICallSummary
  by_service: AISlowCallGroup[]
  top_calls: AISlowCallRecord[]
}

export interface AIObservabilityQuery {
  start_at?: string
  end_at?: string
  user_id?: string
  service_name?: string
  model_name?: string
  limit?: number
}

export interface AIProviderOption {
  name: string
  display_name: string
  provider_type: string
  base_url?: string | null
  models: string[]
}

export interface AIModelOption {
  provider: string
  model: string
  display_name: string
}

export interface AIModelPreferences {
  provider?: string | null
  model?: string | null
}

export interface AIAvailableModelsResponse {
  providers: AIProviderOption[]
  models: AIModelOption[]
  preferences: AIModelPreferences
}

export interface AIModelPreferenceTestResponse {
  provider: string
  model?: string | null
  available: boolean
  provider_type?: string
  base_url?: string | null
  error?: string | null
}

function cleanParams(params: AIObservabilityQuery = {}): Record<string, string | number> {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '')
  ) as Record<string, string | number>
}

export const aiObservabilityApi = {
  getAdminUsage(params: AIObservabilityQuery = {}) {
    return request.get<AIUsageStats>('/admin/ai/usage', { params: cleanParams(params) })
  },
  getAdminFailures(params: AIObservabilityQuery = {}) {
    return request.get<AIFailureStats>('/admin/ai/failures', { params: cleanParams(params) })
  },
  getAdminSlowCalls(params: AIObservabilityQuery = {}) {
    return request.get<AISlowCallStats>('/admin/ai/slow-calls', { params: cleanParams(params) })
  },
  getMyUsage(params: AIObservabilityQuery = {}) {
    return request.get<AIUsageStats>('/me/ai/usage', { params: cleanParams(params) })
  },
  getMyAvailableModels() {
    return request.get<AIAvailableModelsResponse>('/me/ai/available-models')
  },
  updateMyPreferences(payload: AIModelPreferences) {
    return request.patch<{ preferences: AIModelPreferences }>('/me/ai/preferences', payload)
  },
  testMyPreferences(payload: AIModelPreferences) {
    return request.post<AIModelPreferenceTestResponse>('/me/ai/preferences/test', payload)
  },
}
