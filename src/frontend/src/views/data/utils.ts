import dayjs from 'dayjs'
import i18n from '@/i18n'

function tt(key: string): string {
  return i18n.global.t(key)
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '-'
  }
  return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
}

export function formatShortDate(value: string | null | undefined): string {
  if (!value) {
    return '-'
  }
  return dayjs(value).format('YYYY-MM-DD')
}

export function toJsonText(value: unknown): string {
  if (value === null || value === undefined) {
    return '{}'
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return '{}'
  }
}

export function parseJsonText(value: string, fallback: Record<string, unknown> = {}): Record<string, unknown> {
  const normalized = value.trim()
  if (!normalized) {
    return fallback
  }

  const parsed = JSON.parse(normalized)
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error(tt('dataUtils.errJsonParamsObject'))
  }
  return parsed as Record<string, unknown>
}

export function compactCount(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '-'
  }
  return new Intl.NumberFormat('zh-CN').format(value)
}
