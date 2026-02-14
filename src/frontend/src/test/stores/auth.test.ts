import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'

// Mock the auth API
vi.mock('@/api/auth', () => ({
  authApi: {
    login: vi.fn().mockResolvedValue({ access_token: 'mock-token', token_type: 'bearer', expires_in: 86400 }),
    register: vi.fn().mockResolvedValue({ id: '1', username: 'testuser', email: 'test@test.com' }),
    getMe: vi.fn().mockResolvedValue({ id: '1', username: 'testuser', email: 'test@test.com', is_active: true, created_at: '2024-01-01T00:00:00' }),
  },
}))

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
Object.defineProperty(window, 'localStorage', { value: localStorageMock })

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorageMock.clear()
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
    expect(localStorageMock.setItem).toHaveBeenCalledWith('token', 'mock-token')
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
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('token')
  })

  it('should register without setting token', async () => {
    const store = useAuthStore()
    await store.register({ username: 'newuser', email: 'new@test.com', password: 'password123' })
    expect(store.token).toBeNull()
    expect(store.isAuthenticated).toBe(false)
  })
})
