import type { StrategyUnit } from '@/types/workspace'
import i18n from '@/i18n'

function tt(key: string): string {
  return i18n.global.t(key)
}

export function statusDotClass(row: StrategyUnit): string {
  const status = row.trading_snapshot?.instance_status || row.run_status
  if (status === 'running') return 'is-running'
  if (status === 'queued') return 'is-queued'
  if (status === 'error' || row.trading_snapshot?.error || row.run_status === 'failed') return 'is-error'
  return 'is-idle'
}

export function statusLabel(row: StrategyUnit): string {
  const status = row.trading_snapshot?.instance_status || row.run_status
  switch (status) {
    case 'idle':
      return tt('unitRendering.statusIdle')
    case 'queued':
      return tt('unitRendering.statusQueued')
    case 'running':
      return tt('unitRendering.statusRunning')
    case 'stopped':
      return tt('unitRendering.statusStopped')
    case 'completed':
      return tt('unitRendering.statusCompleted')
    case 'failed':
      return tt('unitRendering.statusFailed')
    case 'error':
      return tt('unitRendering.statusError')
    case 'cancelled':
      return tt('unitRendering.statusCancelled')
    default:
      return status
  }
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
    return `${(number / 100000000).toFixed(digits)}${tt('unitRendering.unitYi')}`
  }
  if (abs >= 10000) {
    return `${(number / 10000).toFixed(digits)}${tt('unitRendering.unitWan')}`
  }
  return number.toFixed(digits)
}

export function numberClass(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value) || value === 0) return 'text-gray-500'
  return value > 0 ? 'text-red-500' : 'text-green-600'
}

export function directionLabel(value: string | null | undefined): string {
  const text = String(value || '').toLowerCase()
  if (text.includes('long')) return tt('unitRendering.dirLong')
  if (text.includes('short')) return tt('unitRendering.dirShort')
  return value || '-'
}
