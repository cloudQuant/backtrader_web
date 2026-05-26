import type { StrategyUnit } from '@/types/workspace'

export function statusDotClass(row: StrategyUnit): string {
  const status = row.trading_snapshot?.instance_status || row.run_status
  if (status === 'running') return 'is-running'
  if (status === 'queued') return 'is-queued'
  if (status === 'error' || row.trading_snapshot?.error || row.run_status === 'failed') return 'is-error'
  return 'is-idle'
}

export function statusLabel(row: StrategyUnit): string {
  const status = row.trading_snapshot?.instance_status || row.run_status
  const map: Record<string, string> = {
    idle: '空闲',
    queued: '排队中',
    running: '运行中',
    stopped: '已停止',
    completed: '已完成',
    failed: '失败',
    error: '错误',
    cancelled: '已取消',
  }
  return map[status] || status
}

export function formatDate(value: unknown): string {
  const text = String(value ?? '').trim()
  return text ? text.slice(0, 10) : '-'
}

export function formatTime(value: string): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

export function formatNumber(
  value: number | null | undefined,
  digits = 2,
  trimTrailingZeros = true,
): string {
  if (value == null || Number.isNaN(value)) return '-'
  const formatted = Number(value).toFixed(digits)
  return trimTrailingZeros && digits > 0
    ? formatted.replace(/\.?0+$/, '')
    : formatted
}

export function formatPrice(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  if (Number.isInteger(number)) {
    return String(number)
  }
  return Math.abs(number) >= 100 ? number.toFixed(2) : number.toFixed(4)
}

export function formatSignedNumber(
  value: number | null | undefined,
  digits = 2,
  showSign = true,
  suffix = '',
): string {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  const prefix = showSign && number >= 0 ? '+' : ''
  return `${prefix}${number.toFixed(digits)}${suffix}`
}

export function formatAmountCompact(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  const abs = Math.abs(number)
  if (abs >= 100000000) {
    return `${(number / 100000000).toFixed(digits)}亿`
  }
  if (abs >= 10000) {
    return `${(number / 10000).toFixed(digits)}万`
  }
  return number.toFixed(digits)
}

export function numberClass(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value) || value === 0) return 'text-gray-500'
  return value > 0 ? 'text-red-500' : 'text-green-600'
}

export function directionLabel(value: string | null | undefined): string {
  const text = String(value || '').toLowerCase()
  if (text.includes('long')) return '多头'
  if (text.includes('short')) return '空头'
  return value || '-'
}
