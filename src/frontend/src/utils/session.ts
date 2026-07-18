/**
 * Session token management utilities.
 *
 * The auth store persists tokens to sessionStorage via pinia-plugin-persistedstate.
 * This module provides a consistent interface for the axios interceptor to read
 * the token from the same location.
 *
 * Storage key format: Pinia persists as JSON under key 'auth' in sessionStorage.
 * The token is at: sessionStorage['auth'] -> JSON.parse -> .token
 */

const PINIA_AUTH_KEY = 'auth'
export const AUTH_EXPIRED_EVENT = 'auth:expired'

function hasWindow(): boolean {
  return typeof window !== 'undefined'
}

/**
 * Get the current access token.
 *
 * Reads only from the session-scoped Pinia persisted state.
 */
export function getAccessToken(): string | null {
  if (!hasWindow()) {
    return null
  }

  // Primary: read from Pinia persisted state in sessionStorage
  try {
    const raw = window.sessionStorage.getItem(PINIA_AUTH_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed.token === 'string' && parsed.token) {
        return parsed.token
      }
    }
  } catch {
    // Invalid persisted state is treated as unauthenticated.
  }

  return null
}

/**
 * Clear access token from the session-scoped Pinia payload.
 */
export function clearAccessToken(): void {
  if (!hasWindow()) {
    return
  }
  try {
    const raw = window.sessionStorage.getItem(PINIA_AUTH_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed) {
        parsed.token = null
        parsed.refreshToken = null
        window.sessionStorage.setItem(PINIA_AUTH_KEY, JSON.stringify(parsed))
      }
    }
  } catch {
    // Best effort
  }
}

/**
 * Dispatch auth expired event to trigger logout across the app.
 */
export function dispatchAuthExpired(): void {
  if (!hasWindow()) {
    return
  }
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
}
