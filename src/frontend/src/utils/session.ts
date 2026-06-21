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
const LEGACY_TOKEN_KEY = 'token'
export const AUTH_EXPIRED_EVENT = 'auth:expired'

function hasWindow(): boolean {
  return typeof window !== 'undefined'
}

/**
 * Get the current access token.
 *
 * Reads from sessionStorage (Pinia persisted state) first,
 * falls back to localStorage (legacy) for backward compatibility.
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
    // JSON parse error — fall through to legacy
  }

  // Fallback: legacy localStorage token (for migration)
  return window.localStorage.getItem(LEGACY_TOKEN_KEY)
}

/**
 * Deprecated compatibility shim.
 *
 * Tokens are persisted by the auth store in sessionStorage. Do not write new
 * credentials to legacy localStorage; keep this no-op only so older imports do
 * not reintroduce persistent browser token storage.
 */
export function setAccessToken(_token: string): void {
  return
}

/**
 * Clear access token from all storage locations.
 */
export function clearAccessToken(): void {
  if (!hasWindow()) {
    return
  }
  window.localStorage.removeItem(LEGACY_TOKEN_KEY)
  // Also clear from sessionStorage (Pinia will handle its own state)
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
