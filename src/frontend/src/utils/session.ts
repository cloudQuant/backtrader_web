const TOKEN_KEY = 'token'
export const AUTH_EXPIRED_EVENT = 'auth:expired'

function hasWindow(): boolean {
  return typeof window !== 'undefined'
}

export function getAccessToken(): string | null {
  if (!hasWindow()) {
    return null
  }
  return window.localStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token: string): void {
  if (!hasWindow()) {
    return
  }
  window.localStorage.setItem(TOKEN_KEY, token)
}

export function clearAccessToken(): void {
  if (!hasWindow()) {
    return
  }
  window.localStorage.removeItem(TOKEN_KEY)
}

export function dispatchAuthExpired(): void {
  if (!hasWindow()) {
    return
  }
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
}
