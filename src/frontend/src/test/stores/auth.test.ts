import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import * as sessionUtils from '@/utils/session'

// Mock the auth API
vi.mock('@/api/auth', () => ({
  authApi: {
    login: vi.fn().mockResolvedValue({
      access_token: 'mock-token',
      token_type: 'bearer',
      expires_in: 86400,
    }),
    register: vi.fn().mockResolvedValue({
      id: '1',
      username: 'testuser',
      email: 'test@test.com',
      is_active: true,
      created_at: '2024-01-01T00:00:00',
    }),
    getMe: vi.fn().mockResolvedValue({
      id: '1',
      username: 'testuser',
      email: 'test@test.com',
      is_active: true,
      created_at: '2024-01-01T00:00:00',
    }),
  },
}))

// Mock strategy API
vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({ templates: [], total: 0 }),
  },
}))

// Mock session utils
vi.mock('@/utils/session', () => ({
  getAccessToken: vi.fn(() => null),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
}))

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('should start unauthenticated', () => {
    const store = useAuthStore()
    expect(store.isAuthenticated).toBe(false)
    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
  })

  it('should login and set token', async () => {
    const store = useAuthStore()
    await store.login({ username: 'testuser', password: 'password123' })
    expect(store.token).toBe('mock-token')
    expect(store.isAuthenticated).toBe(true)
    expect(sessionUtils.setAccessToken).toHaveBeenCalledWith('mock-token')
  })

  it('should fetch user after login', async () => {
    const store = useAuthStore()
    await store.login({ username: 'testuser', password: 'password123' })
    expect(store.user).not.toBeNull()
    expect(store.user?.username).toBe('testuser')
  })

  it('should logout and clear state', async () => {
    const store = useAuthStore()
    await store.login({ username: 'testuser', password: 'password123' })
    store.logout()
    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(sessionUtils.clearAccessToken).toHaveBeenCalled()
  })

  it('should register without setting token', async () => {
    const store = useAuthStore()
    await store.register({ username: 'newuser', email: 'new@test.com', password: 'password123' })
    expect(store.token).toBeNull()
    expect(store.isAuthenticated).toBe(false)
  })
})
