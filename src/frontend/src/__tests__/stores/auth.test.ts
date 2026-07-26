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

  it('fetchUser is a no-op when token is null', async () => {
    const { authApi } = await import('@/api/auth')
    const store = useAuthStore()
    await store.fetchUser()
    expect(authApi.getMe).not.toHaveBeenCalled()
  })

  it('fetchUser logs out on API error', async () => {
    const { authApi } = await import('@/api/auth')
    const store = useAuthStore()
    await store.login({ username: 'testuser', password: 'password123' })
    expect(store.token).toBe('mock-token')

    // Now make getMe fail and trigger fetchUser explicitly
    vi.mocked(authApi.getMe).mockRejectedValueOnce(new Error('expired'))
    await store.fetchUser()
    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
  })

  it('initialize is a no-op when already initialized', async () => {
    const { authApi } = await import('@/api/auth')
    const store = useAuthStore()
    await store.login({ username: 'testuser', password: 'password123' })
    expect(store.initialized).toBe(true)

    vi.mocked(authApi.getMe).mockClear()
    await store.initialize()
    expect(authApi.getMe).not.toHaveBeenCalled()
  })

  it('initialize validates a session-persisted token', async () => {
    const { authApi } = await import('@/api/auth')

    const store = useAuthStore()
    store.token = 'session-token'
    await store.initialize()

    expect(store.token).toBe('session-token')
    expect(authApi.getMe).toHaveBeenCalled()
    expect(store.initialized).toBe(true)
  })

  it('initialize without a session token does nothing extra', async () => {
    const { authApi } = await import('@/api/auth')

    const store = useAuthStore()
    await store.initialize()

    expect(store.token).toBeNull()
    expect(authApi.getMe).not.toHaveBeenCalled()
    expect(store.initialized).toBe(true)
  })

  it('initialize de-duplicates concurrent calls', async () => {
    const { authApi } = await import('@/api/auth')

    const store = useAuthStore()
    store.token = 'token-x'
    const p1 = store.initialize()
    const p2 = store.initialize()
    await Promise.all([p1, p2])

    // getMe should be called exactly once despite two concurrent initialize() calls
    expect(authApi.getMe).toHaveBeenCalledTimes(1)
  })

  it('logout is resilient when business stores are not registered', () => {
    // Build a fresh store without first installing the strategy/backtest/sim
    // stores. The catch block in logout() should swallow any thrown errors.
    const store = useAuthStore()
    expect(() => store.logout()).not.toThrow()
    expect(store.token).toBeNull()
  })
})
