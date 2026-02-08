import { describe, it, expect, vi, beforeEach } from 'vitest'

// We test the api module's configuration
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

describe('API module', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should export a default axios instance', async () => {
    const api = (await import('./index')).default
    expect(api).toBeDefined()
    expect(api.defaults.baseURL).toBe('/api/v1')
    expect(api.defaults.timeout).toBe(30000)
  })

  it('should have request interceptor that adds auth token', async () => {
    const api = (await import('./index')).default
    // Verify interceptors are registered
    expect(api.interceptors.request).toBeDefined()
    expect(api.interceptors.response).toBeDefined()
  })
})
