/**
 * API 模块测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import { AUTH_EXPIRED_EVENT } from '@/utils/session'

// The auth store persists its session-scoped Pinia payload under this key.
const sessionStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value }),
    removeItem: vi.fn((key: string) => { delete store[key] }),
    clear: vi.fn(() => { store = {} }),
  }
})()
Object.defineProperty(global, 'sessionStorage', { value: sessionStorageMock })

// Mock Element Plus
vi.mock('element-plus', () => ({
  ElMessage: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

// Mock i18n: return Chinese fallback strings used by api/index.ts so existing
// assertions stay locale-stable across iteration 176 §C i18n refactor.
vi.mock('@/i18n', () => ({
  default: {
    global: {
      t: (key: string) => {
        const map: Record<string, string> = {
          'apiClient.errFieldFallback': '参数错误',
          'apiClient.errGenericFailure': '请求失败',
          'apiClient.errAuthExpired': '登录已过期，请重新登录',
          'apiClient.errForbidden': '没有权限访问',
          'apiClient.errNotFound': '资源不存在',
          'apiClient.errServerError': '服务器错误',
        }
        return map[key] ?? key
      },
    },
  },
}))

describe('API module', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorageMock.clear()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('基础配置', () => {
    it('应该导出默认的 axios 实例', async () => {
      const api = (await import('@/api/index')).default
      expect(api).toBeDefined()
      expect(api.defaults.baseURL).toBe('/api/v1')
      expect(api.defaults.timeout).toBe(30000)
    })

    it('应该设置正确的默认 headers', async () => {
      const api = (await import('@/api/index')).default
      expect(api.defaults.headers['Content-Type']).toBe('application/json')
    })
  })

  describe('拦截器', () => {
    it('应该注册请求拦截器', async () => {
      const api = (await import('@/api/index')).default
      expect(api.interceptors.request).toBeDefined()
      expect(api.interceptors.response).toBeDefined()
    })

    it('请求拦截器数量应该大于0', async () => {
      const api = (await import('@/api/index')).default
      expect((api.interceptors.request as any).handlers.length).toBeGreaterThan(0)
    })

    it('响应拦截器数量应该大于0', async () => {
      const api = (await import('@/api/index')).default
      expect((api.interceptors.response as any).handlers.length).toBeGreaterThan(0)
    })
  })

  describe('Token 处理', () => {
    it('应该能够从 sessionStorage 获取 Pinia auth token', () => {
      sessionStorageMock.setItem('auth', JSON.stringify({ token: 'test-token-123' }))
      expect(sessionStorageMock.getItem('auth')).toContain('test-token-123')
    })

    it('sessionStorage 没有 auth payload 时应该返回 null', () => {
      expect(sessionStorageMock.getItem('auth')).toBeNull()
    })

    it('应该能够清除 auth payload', () => {
      sessionStorageMock.setItem('auth', JSON.stringify({ token: 'test-token-123' }))
      sessionStorageMock.removeItem('auth')
      expect(sessionStorageMock.getItem('auth')).toBeNull()
    })
  })

  describe('请求拦截器逻辑', () => {
    it('should add token to request headers when token exists', async () => {
      const api = (await import('@/api/index')).default
      sessionStorageMock.setItem('auth', JSON.stringify({ token: 'my-jwt-token' }))
      const handler = (api.interceptors.request as any).handlers[0]
      const config = { headers: {} as any }
      const result = handler.fulfilled(config)
      expect(result.headers.Authorization).toBe('Bearer my-jwt-token')
    })

    it('should not add Authorization when no token', async () => {
      const api = (await import('@/api/index')).default
      const handler = (api.interceptors.request as any).handlers[0]
      const config = { headers: {} as any }
      const result = handler.fulfilled(config)
      expect(result.headers.Authorization).toBeUndefined()
    })

    it('request error handler rejects', async () => {
      const api = (await import('@/api/index')).default
      const handler = (api.interceptors.request as any).handlers[0]
      const err = new Error('req error')
      await expect(handler.rejected(err)).rejects.toThrow('req error')
    })
  })

  describe('响应拦截器逻辑', () => {
    it('should return response.data on success', async () => {
      const api = (await import('@/api/index')).default
      const handler = (api.interceptors.response as any).handlers[0]
      const result = handler.fulfilled({ data: { foo: 'bar' }, status: 200 })
      expect(result).toEqual({ foo: 'bar' })
    })

    it('should handle 401 error', async () => {
      const { ElMessage } = await import('element-plus')
      const api = (await import('@/api/index')).default
      const handler = (api.interceptors.response as any).handlers[0]
      const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
      sessionStorageMock.setItem('auth', JSON.stringify({ token: 'my-jwt-token' }))
      const error = { response: { status: 401, data: {} } }
      await expect(handler.rejected(error)).rejects.toBe(error)
      expect(sessionStorageMock.setItem).toHaveBeenCalledWith(
        'auth',
        expect.stringContaining('"token":null'),
      )
      expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: AUTH_EXPIRED_EVENT }))
      expect(ElMessage.error).toHaveBeenCalledWith('登录已过期，请重新登录')
    })

    it('should handle 403 error', async () => {
      const { ElMessage } = await import('element-plus')
      const api = (await import('@/api/index')).default
      const handler = (api.interceptors.response as any).handlers[0]
      const error = { response: { status: 403, data: {} } }
      await expect(handler.rejected(error)).rejects.toBe(error)
      expect(ElMessage.error).toHaveBeenCalledWith('没有权限访问')
    })

    it('should handle 404 error', async () => {
      const { ElMessage } = await import('element-plus')
      const api = (await import('@/api/index')).default
      const handler = (api.interceptors.response as any).handlers[0]
      const error = { response: { status: 404, data: {} } }
      await expect(handler.rejected(error)).rejects.toBe(error)
      expect(ElMessage.error).toHaveBeenCalledWith('资源不存在')
    })

    it('should handle 500 error', async () => {
      const { ElMessage } = await import('element-plus')
      const api = (await import('@/api/index')).default
      const handler = (api.interceptors.response as any).handlers[0]
      const error = { response: { status: 500, data: {} } }
      await expect(handler.rejected(error)).rejects.toBe(error)
      expect(ElMessage.error).toHaveBeenCalledWith('服务器错误')
    })

    it('should handle generic error with detail', async () => {
      const { ElMessage } = await import('element-plus')
      const api = (await import('@/api/index')).default
      const handler = (api.interceptors.response as any).handlers[0]
      const error = { response: { status: 422, data: { detail: '验证错误' } } }
      await expect(handler.rejected(error)).rejects.toBe(error)
      expect(ElMessage.error).toHaveBeenCalledWith('验证错误')
    })

    it('should handle generic error without detail', async () => {
      const { ElMessage } = await import('element-plus')
      const api = (await import('@/api/index')).default
      const handler = (api.interceptors.response as any).handlers[0]
      const error = { response: { status: 422, data: {} } }
      await expect(handler.rejected(error)).rejects.toBe(error)
      expect(ElMessage.error).toHaveBeenCalledWith('请求失败')
    })
  })

  describe('API 导出', () => {
    it('应该有默认导出', async () => {
      const module = await import('@/api/index')
      expect(module.default).toBeDefined()
    })
  })

  describe('getErrorMessage helper', () => {
    it('returns fallback for unknown shape', async () => {
      const { getErrorMessage } = await import('@/api/index')
      expect(getErrorMessage('plain string', 'fallback')).toBe('fallback')
      expect(getErrorMessage(null, 'fallback')).toBe('fallback')
      expect(getErrorMessage(undefined, 'fallback')).toBe('fallback')
    })

    it('returns Error.message when given an Error instance', async () => {
      const { getErrorMessage } = await import('@/api/index')
      expect(getErrorMessage(new Error('boom'), 'fallback')).toBe('boom')
    })

    it('falls back when Error has empty message', async () => {
      const { getErrorMessage } = await import('@/api/index')
      const err = new Error('')
      expect(getErrorMessage(err, 'fallback')).toBe('fallback')
    })

    it('returns axios response message when available', async () => {
      const { getErrorMessage } = await import('@/api/index')
      const e = { response: { data: { message: 'server says hi' } } }
      expect(getErrorMessage(e, 'fallback')).toBe('server says hi')
    })

    it('appends request_id when present', async () => {
      const { getErrorMessage } = await import('@/api/index')
      const e = { response: { data: { message: 'failed', request_id: 'req-123' } } }
      expect(getErrorMessage(e, 'fallback')).toBe('failed (request_id: req-123)')
    })

    it('extracts FastAPI 422 array detail', async () => {
      const { getErrorMessage } = await import('@/api/index')
      const e = { response: { data: { detail: [{ loc: ['body', 'foo'], msg: 'is required', type: 'value_error.missing' }] } } }
      expect(getErrorMessage(e, 'fallback')).toBe('is required')
    })

    it('handles object detail with message', async () => {
      const { getErrorMessage } = await import('@/api/index')
      const e = { response: { data: { detail: { message: 'nested object' } } } }
      expect(getErrorMessage(e, 'fallback')).toBe('nested object')
    })

    it('handles string detail directly', async () => {
      const { getErrorMessage } = await import('@/api/index')
      const e = { response: { data: { detail: 'string detail' } } }
      expect(getErrorMessage(e, 'fallback')).toBe('string detail')
    })

    it('extracts field-level error from details.fields', async () => {
      const { getErrorMessage } = await import('@/api/index')
      const e = { response: { data: { details: { fields: [{ field: 'username', message: 'too short' }] } } } }
      expect(getErrorMessage(e, 'fallback')).toBe('username: too short')
    })

    it('uses field-fallback when message missing in field error', async () => {
      const { getErrorMessage } = await import('@/api/index')
      const e = { response: { data: { details: { fields: [{ field: 'email' }] } } } }
      expect(getErrorMessage(e, 'fallback')).toBe('email: 参数错误')
    })

    it('uses field message alone when field name missing', async () => {
      const { getErrorMessage } = await import('@/api/index')
      const e = { response: { data: { details: { fields: [{ message: 'invalid' }] } } } }
      expect(getErrorMessage(e, 'fallback')).toBe('invalid')
    })

    it('falls back to user-provided message when extracted text equals generic 请求失败', async () => {
      const { getErrorMessage } = await import('@/api/index')
      const e = { response: { data: {} } } // would extract '请求失败'
      // generic message should NOT be returned; fallback used instead
      expect(getErrorMessage(e, 'my fallback')).toBe('my fallback')
    })

    it('returns extracted msg when not generic', async () => {
      const { getErrorMessage } = await import('@/api/index')
      const e = { response: { data: { message: 'specific' } } }
      expect(getErrorMessage(e, 'my fallback')).toBe('specific')
    })
  })

  describe('Retry behavior on response interceptor', () => {
    it('should not duplicate ElMessage on retried failures (skip generic)', async () => {
      const { ElMessage } = await import('element-plus')
      const api = (await import('@/api/index')).default
      const handler = (api.interceptors.response as any).handlers[0]

      // Configure error to look like an in-progress retry where final retry exhausted
      const error = {
        config: { __isRetrying: true, __retryCount: 5 },
        response: { status: 500, data: {} },
      }
      // Since __retryCount (5) >= maxRetries (3), the early-skip branch fires
      // and ElMessage.error is called.
      await expect(handler.rejected(error)).rejects.toBe(error)
      expect(ElMessage.error).toHaveBeenCalled()
    })
  })
})
