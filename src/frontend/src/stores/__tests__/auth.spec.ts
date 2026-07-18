/**
 * Unit tests for useAuthStore.
 *
 * Tests cover:
 * - Initial state
 * - Login flow
 * - Logout flow
 * - Token persistence
 * - User fetch on init
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import {
  clearAccessToken,
  getAccessToken,
} from '@/utils/session'
import { authApi } from '@/api/auth'

import { useAuthStore } from '../auth'

// Mock dependencies
vi.mock('@/api/auth', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    getMe: vi.fn(),
  },
}))

vi.mock('@/utils/session', () => ({
  getAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
}))

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('should have null token when no stored token', () => {
      vi.mocked(getAccessToken).mockReturnValue(null)
      const store = useAuthStore()

      expect(store.token).toBeNull()
      expect(store.user).toBeNull()
      expect(store.isAuthenticated).toBe(false)
    })

    it('should validate a session-persisted token on init', async () => {
      vi.mocked(authApi.getMe).mockResolvedValue({
        id: '1',
        username: 'testuser',
        email: 'test@example.com',
        is_active: true,
        created_at: '2024-01-01',
      })

      const store = useAuthStore()
      store.token = 'stored-token'
      await store.initialize()

      expect(store.token).toBe('stored-token')
      expect(store.isAuthenticated).toBe(true)
    })
  })

  describe('login', () => {
    it('should set token and fetch user on successful login', async () => {
      vi.mocked(getAccessToken).mockReturnValue(null)
      vi.mocked(authApi.login).mockResolvedValue({
        access_token: 'new-token',
        token_type: 'bearer',
        expires_in: 3600,
      })
      vi.mocked(authApi.getMe).mockResolvedValue({
        id: '1',
        username: 'testuser',
        email: 'test@example.com',
        is_active: true,
        created_at: '2024-01-01',
      })

      const store = useAuthStore()
      await store.login({ username: 'testuser', password: 'password123' })

      expect(store.token).toBe('new-token')
      expect(store.user).toEqual({
        id: '1',
        username: 'testuser',
        email: 'test@example.com',
        is_active: true,
        created_at: '2024-01-01',
      })
    })

    it('should throw on login failure', async () => {
      vi.mocked(getAccessToken).mockReturnValue(null)
      vi.mocked(authApi.login).mockRejectedValue(new Error('Invalid credentials'))

      const store = useAuthStore()

      await expect(
        store.login({ username: 'testuser', password: 'wrong' })
      ).rejects.toThrow('Invalid credentials')

      expect(store.token).toBeNull()
    })
  })

  describe('logout', () => {
    it('should clear token and user on logout', async () => {
      vi.mocked(authApi.getMe).mockResolvedValue({
        id: '1',
        username: 'testuser',
        email: 'test@example.com',
        is_active: true,
        created_at: '2024-01-01',
      })

      const store = useAuthStore()
      // Simulate logged-in state
      store.token = 'stored-token'
      await store.fetchUser()

      store.logout()

      expect(store.token).toBeNull()
      expect(store.user).toBeNull()
      expect(clearAccessToken).toHaveBeenCalled()
      expect(store.isAuthenticated).toBe(false)
    })
  })

  describe('register', () => {
    it('should call register API', async () => {
      vi.mocked(getAccessToken).mockReturnValue(null)
      vi.mocked(authApi.register).mockResolvedValue({
        id: '1',
        username: 'newuser',
        email: 'new@example.com',
        is_active: true,
        created_at: '2024-01-01',
      })

      const store = useAuthStore()
      await store.register({
        username: 'newuser',
        password: 'password123',
        email: 'new@example.com',
      })

      expect(authApi.register).toHaveBeenCalledWith({
        username: 'newuser',
        password: 'password123',
        email: 'new@example.com',
      })
    })
  })

  describe('fetchUser', () => {
    it('should fetch user when token exists', async () => {
      vi.mocked(authApi.getMe).mockResolvedValue({
        id: '1',
        username: 'testuser',
        email: 'test@example.com',
        is_active: true,
        created_at: '2024-01-01',
      })

      const store = useAuthStore()
      // Set token directly (simulating persistence plugin hydration)
      store.token = 'stored-token'
      await store.fetchUser()

      expect(store.user).toEqual({
        id: '1',
        username: 'testuser',
        email: 'test@example.com',
        is_active: true,
        created_at: '2024-01-01',
      })
    })

    it('should logout on fetchUser failure', async () => {
      vi.mocked(authApi.getMe).mockRejectedValue(new Error('Unauthorized'))

      const store = useAuthStore()
      // Set token directly (simulating persistence plugin hydration)
      store.token = 'invalid-token'
      await store.fetchUser()

      expect(store.token).toBeNull()
      expect(clearAccessToken).toHaveBeenCalled()
    })
  })

  describe('initialize', () => {
    it('should initialize only once for stored token', async () => {
      vi.mocked(authApi.getMe).mockResolvedValue({
        id: '1',
        username: 'testuser',
        email: 'test@example.com',
        is_active: true,
        created_at: '2024-01-01',
      })

      const store = useAuthStore()
      store.token = 'stored-token'
      await store.initialize()
      await store.initialize()

      expect(store.initialized).toBe(true)
      // getMe is called once while validating the session-persisted token.
      expect(authApi.getMe).toHaveBeenCalledTimes(1)
    })
  })
})
