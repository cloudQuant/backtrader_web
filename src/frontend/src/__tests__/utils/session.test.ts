/**
 * Unit tests for src/utils/session.ts.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AUTH_EXPIRED_EVENT,
  clearAccessToken,
  dispatchAuthExpired,
  getAccessToken,
  setAccessToken,
} from '@/utils/session'

function createMockStorage() {
  const store = new Map<string, string>()
  return {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v) },
    removeItem: (k: string) => { store.delete(k) },
    clear: () => { store.clear() },
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    get length() { return store.size },
  } as unknown as Storage
}

describe('session utils', () => {
  let originalLocal: Storage
  let originalSession: Storage

  beforeEach(() => {
    originalLocal = window.localStorage
    originalSession = window.sessionStorage
    Object.defineProperty(window, 'localStorage', {
      value: createMockStorage(), writable: true, configurable: true,
    })
    Object.defineProperty(window, 'sessionStorage', {
      value: createMockStorage(), writable: true, configurable: true,
    })
  })

  afterEach(() => {
    Object.defineProperty(window, 'localStorage', { value: originalLocal, writable: true, configurable: true })
    Object.defineProperty(window, 'sessionStorage', { value: originalSession, writable: true, configurable: true })
  })

  describe('getAccessToken', () => {
    it('returns Pinia-persisted token from sessionStorage', () => {
      window.sessionStorage.setItem('auth', JSON.stringify({ token: 'pinia-token' }))
      expect(getAccessToken()).toBe('pinia-token')
    })

    it('falls back to legacy localStorage when sessionStorage has no token', () => {
      window.localStorage.setItem('token', 'legacy-token')
      expect(getAccessToken()).toBe('legacy-token')
    })

    it('falls back when sessionStorage value has empty token', () => {
      window.sessionStorage.setItem('auth', JSON.stringify({ token: '' }))
      window.localStorage.setItem('token', 'legacy')
      expect(getAccessToken()).toBe('legacy')
    })

    it('falls back when sessionStorage JSON cannot be parsed', () => {
      window.sessionStorage.setItem('auth', '{not json')
      window.localStorage.setItem('token', 'legacy')
      expect(getAccessToken()).toBe('legacy')
    })

    it('returns null when neither store has a token', () => {
      expect(getAccessToken()).toBeNull()
    })
  })

  describe('setAccessToken', () => {
    it('does not write new tokens to legacy localStorage', () => {
      setAccessToken('my-token')
      expect(window.localStorage.getItem('token')).toBeNull()
    })
  })

  describe('clearAccessToken', () => {
    it('removes the legacy localStorage entry', () => {
      window.localStorage.setItem('token', 'legacy')
      clearAccessToken()
      expect(window.localStorage.getItem('token')).toBeNull()
    })

    it('zeroes the token+refreshToken inside the Pinia auth payload', () => {
      window.sessionStorage.setItem('auth', JSON.stringify({
        token: 'pinia-token', refreshToken: 'rt', user: { id: 1 },
      }))
      clearAccessToken()
      const updated = JSON.parse(window.sessionStorage.getItem('auth')!)
      expect(updated.token).toBeNull()
      expect(updated.refreshToken).toBeNull()
      expect(updated.user).toEqual({ id: 1 })
    })

    it('is a no-op when sessionStorage payload is invalid JSON', () => {
      window.sessionStorage.setItem('auth', '{not json')
      expect(() => clearAccessToken()).not.toThrow()
    })

    it('is a no-op when sessionStorage payload is empty', () => {
      expect(() => clearAccessToken()).not.toThrow()
    })
  })

  describe('dispatchAuthExpired', () => {
    it('emits the AUTH_EXPIRED_EVENT on window', () => {
      const handler = vi.fn()
      window.addEventListener(AUTH_EXPIRED_EVENT, handler)
      dispatchAuthExpired()
      expect(handler).toHaveBeenCalled()
      window.removeEventListener(AUTH_EXPIRED_EVENT, handler)
    })
  })
})
