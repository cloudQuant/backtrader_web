export interface QuoteFormatContext {
  source?: string
  symbol?: string
}

function countDecimals(value: number): number {
  if (!Number.isFinite(value)) return 0
  const normalized = value.toFixed(8).replace(/\.?0+$/, '')
  const dotIndex = normalized.indexOf('.')
  return dotIndex >= 0 ? normalized.length - dotIndex - 1 : 0
}

function getMt5MinimumPrecision(symbol: string): number {
  const normalized = symbol.toUpperCase()
  if (/^(XAU|XAG)/.test(normalized)) return 2
  if (normalized.includes('JPY')) return 3
  if (/^[A-Z]{6}$/.test(normalized)) return 5
  return 2
}

export function getQuotePricePrecision(value: number, context?: QuoteFormatContext): number {
  if (!Number.isFinite(value)) return 2
  const source = String(context?.source || '').toUpperCase()
  if (source !== 'MT5') return 2
  const symbol = String(context?.symbol || '').trim()
  const actualPrecision = countDecimals(value)
  const minimumPrecision = getMt5MinimumPrecision(symbol)
  return Math.max(actualPrecision, minimumPrecision)
}

export function formatQuotePrice(value: number | null | undefined, context?: QuoteFormatContext): string {
  if (value == null || !Number.isFinite(value)) return '--'
  return value.toFixed(getQuotePricePrecision(value, context))
}

export function formatQuoteChange(value: number | null | undefined, context?: QuoteFormatContext): string {
  if (value == null || !Number.isFinite(value)) return '--'
  const sign = value >= 0 ? '+' : ''
  return sign + value.toFixed(getQuotePricePrecision(Math.abs(value), context))
}
