/** Gateway status display formatting helpers (pure functions). */

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
      return '运行中'
    case 'starting':
      return '启动中'
    case 'stopping':
      return '停止中'
    case 'error':
      return '异常'
    case 'registered':
      return '已注册'
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
      return '已连接'
    case 'connecting':
      return '连接中'
    case 'reconnecting':
      return '重连中'
    case 'error':
      return '异常'
    case 'disconnected':
      return '已断开'
    case 'not_started':
      return '未启动'
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

export function getHeartbeatAge(gateway: GatewayHealthInfo): number | null {
  const lastHeartbeat = gateway.last_heartbeat
  if (lastHeartbeat != null && Number.isFinite(lastHeartbeat)) {
    return Math.max(0, Math.floor(nowMs.value / 1000 - lastHeartbeat))
  }
  if (gateway.heartbeat_age_sec == null || !Number.isFinite(gateway.heartbeat_age_sec)) {
    return null
  }
  const elapsedSinceFetch = Math.floor(Math.max(0, nowMs.value - lastHealthFetchMs.value) / 1000)
  return Math.max(0, Math.floor(gateway.heartbeat_age_sec) + elapsedSinceFetch)
}

export function formatHeartbeatAge(gateway: GatewayHealthInfo): string {
  const age = getHeartbeatAge(gateway)
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
