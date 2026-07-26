/** Gateway status display formatting helpers (pure functions). */
import i18n from '@/i18n'
import type { GatewayHealthInfo } from '@/api/liveTrading'

function t(key: string): string {
  return i18n.global.t(key)
}

export function stateTagType(state: string) {
  switch (state) {
    case 'running':
      return 'success'
    case 'starting':
    case 'stopping':
      return 'warning'
    case 'error':
      return 'danger'
    default:
      return 'info'
  }
}

export function stateLabel(state: string) {
  switch (state) {
    case 'running':
      return t('gatewayStatus.stateRunning')
    case 'starting':
      return t('gatewayStatus.stateStarting')
    case 'stopping':
      return t('gatewayStatus.stateStopping')
    case 'error':
      return t('gatewayStatus.stateError')
    case 'registered':
      return t('gatewayStatus.stateRegistered')
    default:
      return state
  }
}

export function connTagType(conn: string) {
  switch (conn) {
    case 'connected':
      return 'success'
    case 'connecting':
    case 'reconnecting':
      return 'warning'
    case 'error':
      return 'danger'
    default:
      return 'info'
  }
}

export function connLabel(conn: string) {
  switch (conn) {
    case 'connected':
      return t('gatewayStatus.connConnected')
    case 'connecting':
      return t('gatewayStatus.connConnecting')
    case 'reconnecting':
      return t('gatewayStatus.connReconnecting')
    case 'error':
      return t('gatewayStatus.connError')
    case 'disconnected':
      return t('gatewayStatus.connDisconnected')
    case 'not_started':
      return t('gatewayStatus.connNotStarted')
    default:
      return conn
  }
}

export function heartbeatClass(age: number | null) {
  if (age == null) return 'text-gray-400'
  if (age < 5) return 'text-green-600 font-medium'
  if (age < 30) return 'text-yellow-600 font-medium'
  return 'text-red-600 font-medium'
}

// Note: getHeartbeatAge needs reactive nowMs / lastHealthFetchMs from caller;
// pass plain number values (templates auto-unwrap refs to numbers).
export function getHeartbeatAge(
  gateway: GatewayHealthInfo,
  nowMs?: number,
  lastHealthFetchMs?: number,
): number | null {
  const lastHeartbeat = gateway.last_heartbeat
  const now = nowMs ?? Date.now()
  const lastFetch = lastHealthFetchMs ?? now
  if (lastHeartbeat != null && Number.isFinite(lastHeartbeat)) {
    return Math.max(0, Math.floor(now / 1000 - lastHeartbeat))
  }
  if (gateway.heartbeat_age_sec == null || !Number.isFinite(gateway.heartbeat_age_sec)) {
    return null
  }
  const elapsedSinceFetch = Math.floor(Math.max(0, now - lastFetch) / 1000)
  return Math.max(0, Math.floor(gateway.heartbeat_age_sec) + elapsedSinceFetch)
}

export function formatHeartbeatAge(
  gateway: GatewayHealthInfo,
  nowMs?: number,
  lastHealthFetchMs?: number,
): string {
  const age = getHeartbeatAge(gateway, nowMs, lastHealthFetchMs)
  return age != null ? `${age}s` : '-'
}

export function formatUptime(sec: number) {
  if (!sec || sec <= 0) return '-'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

export function formatNumber(n: number) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}
