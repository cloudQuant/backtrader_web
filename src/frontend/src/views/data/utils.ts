import dayjs from 'dayjs'

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
    throw new Error('JSON 参数必须是对象')
  }
  return parsed as Record<string, unknown>
}

export function compactCount(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '-'
  }
  return new Intl.NumberFormat('zh-CN').format(value)
}
