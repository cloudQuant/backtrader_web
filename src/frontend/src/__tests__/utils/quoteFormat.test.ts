import { describe, expect, it } from 'vitest'

import { formatQuoteChange, formatQuotePrice, getQuotePricePrecision } from '@/utils/quoteFormat'

describe('quoteFormat', () => {
  it('keeps five decimals for mt5 major fx pairs when present', () => {
    expect(formatQuotePrice(1.12345, { source: 'MT5', symbol: 'EURUSD' })).toBe('1.12345')
  })

  it('keeps at least five decimals for mt5 non-jpy fx pairs', () => {
    expect(formatQuotePrice(1.12, { source: 'MT5', symbol: 'EURUSD' })).toBe('1.12000')
    expect(formatQuotePrice(0.6322, { source: 'MT5', symbol: 'AUDUSD' })).toBe('0.63220')
    expect(formatQuotePrice(0.8841, { source: 'MT5', symbol: 'USDCHF' })).toBe('0.88410')
    expect(formatQuotePrice(0.5913, { source: 'MT5', symbol: 'NZDUSD' })).toBe('0.59130')
    expect(formatQuotePrice(0.8562, { source: 'MT5', symbol: 'EURGBP' })).toBe('0.85620')
  })

  it('keeps three decimals for mt5 jpy pairs', () => {
    expect(formatQuotePrice(145.678, { source: 'MT5', symbol: 'USDJPY' })).toBe('145.678')
    expect(getQuotePricePrecision(145.6, { source: 'MT5', symbol: 'USDJPY' })).toBe(3)
  })

  it('keeps two decimals for mt5 metals', () => {
    expect(formatQuotePrice(4742.67, { source: 'MT5', symbol: 'XAUUSD' })).toBe('4742.67')
  })

  it('keeps default two decimals for non-mt5 quotes', () => {
    expect(formatQuotePrice(212.34, { source: 'IB_WEB', symbol: 'AAPL' })).toBe('212.34')
  })

  it('formats mt5 changes with matching precision', () => {
    expect(formatQuoteChange(0.0012, { source: 'MT5', symbol: 'EURUSD' })).toBe('+0.00120')
  })
})
