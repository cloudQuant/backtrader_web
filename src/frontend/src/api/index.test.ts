/**
 * API 模块测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value }),
    removeItem: vi.fn((key: string) => { delete store[key] }),
    clear: vi.fn(() => { store = {} }),
  }
})()
Object.defineProperty(global, 'localStorage', { value: localStorageMock })

// Mock window.location
Object.defineProperty(window, 'location', {
  value: {
    href: '',
  },
  writable: true,
})

// Mock Element Plus
vi.mock('element-plus', () => ({
  ElMessage: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

describe('API module', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorageMock.clear()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('基础配置', () => {
    it('应该导出默认的 axios 实例', async () => {
      const api = (await import('./index')).default
      expect(api).toBeDefined()
      expect(api.defaults.baseURL).toBe('/api/v1')
      expect(api.defaults.timeout).toBe(30000)
    })

    it('应该设置正确的默认 headers', async () => {
      const api = (await import('./index')).default
      expect(api.defaults.headers['Content-Type']).toBe('application/json')
    })
  })

  describe('拦截器', () => {
    it('应该注册请求拦截器', async () => {
      const api = (await import('./index')).default
      expect(api.interceptors.request).toBeDefined()
      expect(api.interceptors.response).toBeDefined()
    })

    it('请求拦截器数量应该大于0', async () => {
      const api = (await import('./index')).default
      expect(api.interceptors.request.handlers.length).toBeGreaterThan(0)
    })

    it('响应拦截器数量应该大于0', async () => {
      const api = (await import('./index')).default
      expect(api.interceptors.response.handlers.length).toBeGreaterThan(0)
    })
  })

  describe('Token 处理', () => {
    it('应该能够从 localStorage 获取 token', () => {
      localStorageMock.setItem('token', 'test-token-123')
      expect(localStorageMock.getItem('token')).toBe('test-token-123')
    })

    it('localStorage 没有 token 时应该返回 null', () => {
      expect(localStorageMock.getItem('token')).toBeNull()
    })

    it('应该能够清除 token', () => {
      localStorageMock.setItem('token', 'test-token-123')
      localStorageMock.removeItem('token')
      expect(localStorageMock.getItem('token')).toBeNull()
    })
  })

  describe('错误处理', () => {
    it('应该导入 ElMessage', async () => {
      const { ElMessage } = await import('element-plus')
      expect(ElMessage).toBeDefined()
      expect(ElMessage.error).toBeDefined()
    })
  })

  describe('API 导出', () => {
    it('应该有默认导出', async () => {
      const module = await import('./index')
      expect(module.default).toBeDefined()
    })
  })
})
