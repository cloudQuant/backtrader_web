import axios from 'axios'
import type { AxiosInstance, AxiosError, AxiosRequestConfig } from 'axios'
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

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const token = getAccessToken()
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
  (error: AxiosError) => {
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
