/**
 * In-memory token reference shared between auth store and API interceptor.
 * This module has NO imports to avoid circular dependencies.
 */

let _token: string | null = null

export function getToken(): string | null {
  return _token
}

export function setToken(token: string | null): void {
  _token = token
}
