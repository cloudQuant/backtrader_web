import axios from 'axios'
import type { AxiosInstance, AxiosError } from 'axios'
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

// 创建axios实例
const api: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

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

    if (status === 401) {
      clearAccessToken()
      dispatchAuthExpired()
      ElMessage.error('登录已过期，请重新登录')
    } else if (status === 403) {
      ElMessage.error('没有权限访问')
    } else if (status === 404) {
      ElMessage.error('资源不存在')
    } else if (status === 500) {
      ElMessage.error('服务器错误')
    } else {
      ElMessage.error(extractApiErrorMessage(data))
    }

    return Promise.reject(error)
  }
)

export default api
