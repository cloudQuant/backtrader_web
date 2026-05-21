import axios from 'axios'
import type { AxiosInstance, AxiosError, AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

import {
  clearAccessToken,
  dispatchAuthExpired,
  getAccessToken,
} from '@/utils/session'

type ErrorField = {
  field?: string
  message?: string
  type?: string
}

type ApiErrorPayload = {
  detail?: unknown
  message?: unknown
  error?: unknown
  request_id?: unknown
  path?: unknown
  details?: {
    fields?: ErrorField[]
    [k: string]: unknown
  }
  [k: string]: unknown
}

interface ApiClient extends AxiosInstance {
  request<T = unknown, D = unknown>(config: AxiosRequestConfig<D>): Promise<T>
  get<T = unknown, D = unknown>(url: string, config?: AxiosRequestConfig<D>): Promise<T>
  delete<T = unknown, D = unknown>(url: string, config?: AxiosRequestConfig<D>): Promise<T>
  post<T = unknown, D = unknown>(url: string, data?: D, config?: AxiosRequestConfig<D>): Promise<T>
  put<T = unknown, D = unknown>(url: string, data?: D, config?: AxiosRequestConfig<D>): Promise<T>
  patch<T = unknown, D = unknown>(url: string, data?: D, config?: AxiosRequestConfig<D>): Promise<T>
}

// --- Retry Interceptor Configuration ---

export interface RetryConfig {
  maxRetries: number
  initialDelay: number
  backoffFactor: number
  jitterRange: number
  retryableStatuses: number[]
  idempotentMethods: string[]
}

export const RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  initialDelay: 1000,
  backoffFactor: 2,
  jitterRange: 0.1,
  retryableStatuses: [408, 429, 500, 502, 503, 504],
  idempotentMethods: ['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE'],
}

/** Check if the error is retryable based on status code or network error */
export function isRetryableError(error: AxiosError): boolean {
  if (error.code === 'ERR_NETWORK' || error.code === 'ECONNABORTED') {
    return true
  }
  const status = error.response?.status
  if (status && RETRY_CONFIG.retryableStatuses.includes(status)) {
    return true
  }
  return false
}

/** Check if the request method is idempotent (or POST with Idempotency-Key) */
export function isIdempotentRequest(config: InternalAxiosRequestConfig): boolean {
  const method = (config.method || '').toUpperCase()
  if (RETRY_CONFIG.idempotentMethods.includes(method)) {
    return true
  }
  // POST is retryable only if the request has an Idempotency-Key header
  if (method === 'POST') {
    const headers = config.headers
    if (headers && headers['Idempotency-Key']) {
      return true
    }
  }
  return false
}

/** Calculate delay with exponential backoff and ±10% jitter */
export function calculateRetryDelay(retryCount: number): number {
  const baseDelay = RETRY_CONFIG.initialDelay * Math.pow(RETRY_CONFIG.backoffFactor, retryCount)
  const jitter = baseDelay * RETRY_CONFIG.jitterRange * (2 * Math.random() - 1)
  return baseDelay + jitter
}

/** Sleep utility for retry delays */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function stringifyDetail(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI default 422 shape: [{loc, msg, type}, ...]
    const first = detail[0] as { msg?: unknown }
    if (typeof first?.msg === 'string') return first.msg
    return undefined
  }
  if (detail && typeof detail === 'object') {
    const msg = (detail as { message?: unknown }).message
    if (typeof msg === 'string') return msg
  }
  return undefined
}

function extractApiErrorMessage(payload: unknown): string {
  const data = (payload ?? {}) as ApiErrorPayload

  const msg =
    (typeof data.message === 'string' ? data.message : undefined) ??
    stringifyDetail(data.detail) ??
    (typeof data.detail === 'string' ? data.detail : undefined)

  if (msg) {
    const requestId = typeof data.request_id === 'string' ? data.request_id : undefined
    return requestId ? `${msg} (request_id: ${requestId})` : msg
  }

  const fields = data.details?.fields
  if (Array.isArray(fields) && fields.length > 0) {
    const first = fields[0]
    const field = typeof first.field === 'string' ? first.field : undefined
    const fieldMsg = typeof first.message === 'string' ? first.message : '参数错误'
    return field ? `${field}: ${fieldMsg}` : fieldMsg
  }

  return '请求失败'
}

/** Extract user-friendly error message from caught unknown. Use in catch blocks instead of (e: any). */
export function getErrorMessage(e: unknown, fallback: string): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const ax = e as { response?: { data?: unknown } }
    if (ax.response?.data) {
      const msg = extractApiErrorMessage(ax.response.data)
      if (msg !== '请求失败') return msg
    }
  }
  if (e instanceof Error) return e.message || fallback
  return fallback
}

const env = (import.meta as ImportMeta & { env: Record<string, string | undefined> }).env

// 创建axios实例
const api = axios.create({
  baseURL: env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
}) as ApiClient

// 请求拦截器 — reads token from in-memory ref (set by auth store)
import { getToken } from '@/utils/tokenRef'

api.interceptors.request.use(
  (config) => {
    // Priority: in-memory token (set by auth store) > sessionStorage (persisted)
    const token = getToken() || getAccessToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response.data
  },
  async (error: AxiosError) => {
    const config = error.config as InternalAxiosRequestConfig & {
      __retryCount?: number
      __isRetrying?: boolean
    }

    // --- Retry Logic ---
    if (config) {
      const retryCount = config.__retryCount || 0

      if (
        retryCount < RETRY_CONFIG.maxRetries &&
        isRetryableError(error) &&
        isIdempotentRequest(config)
      ) {
        config.__retryCount = retryCount + 1
        config.__isRetrying = true

        const delay = calculateRetryDelay(retryCount)
        await sleep(delay)

        return api.request(config)
      }
    }

    // --- Error Handling (only fires once after all retries exhausted) ---
    // Skip ElMessage if this was a retrying request that just completed its final retry
    const isRetrying = config?.__isRetrying && (config.__retryCount || 0) < RETRY_CONFIG.maxRetries
    if (isRetrying) {
      return Promise.reject(error)
    }

    const status = error.response?.status
    const data = error.response?.data
    const msg = extractApiErrorMessage(data)
    const isGenericMsg = msg === '请求失败'

    if (status === 401) {
      clearAccessToken()
      dispatchAuthExpired()
      ElMessage.error(isGenericMsg ? '登录已过期，请重新登录' : msg)
    } else if (status === 403) {
      ElMessage.error(isGenericMsg ? '没有权限访问' : msg)
    } else if (status === 404) {
      ElMessage.error(isGenericMsg ? '资源不存在' : msg)
    } else if (status === 500) {
      ElMessage.error(isGenericMsg ? '服务器错误' : msg)
    } else {
      ElMessage.error(msg)
    }

    return Promise.reject(error)
  }
)

export default api
