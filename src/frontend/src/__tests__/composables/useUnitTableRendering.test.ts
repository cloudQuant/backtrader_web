/**
 * Unit tests for useUnitTableRendering helpers.
 *
 * All exports are pure formatters; we exercise each via small fixtures
 * that hit the visible branches (status mapping, locale-aware unit
 * abbreviations, number formatting edge cases, etc).
 */
import { describe, expect, it } from 'vitest'

import {
  directionLabel,
  formatAmountCompact,
  formatDate,
  formatNumber,
  formatPrice,
  formatQuantity,
  formatSignedNumber,
  formatTime,
  numberClass,
  statusDotClass,
  statusLabel,
} from '@/composables/useUnitTableRendering'
import type { StrategyUnit } from '@/types/workspace'

function unit(overrides: Partial<StrategyUnit> = {}): StrategyUnit {
  return {
    id: 'u-1',
    workspace_id: 'w-1',
    strategy_id: 's-1',
    strategy_name: 'sample',
    symbol_code: 'TEST',
    timeframe: '1d',
    category: 'trend',
    params: {},
    data_source: { type: 'csv' },
    backtest_defaults: {
      start_date: '2024-01-01',
      end_date: '2024-12-31',
      initial_cash: 100000,
      commission: 0.001,
    },
    optimization: null,
    run_status: 'idle',
    trading_mode: 'paper',
    lock_running: false,
    lock_trading: false,
    sort_order: 0,
    created_at: '2024-01-01T00:00:00',
    updated_at: '2024-01-01T00:00:00',
    trading_snapshot: null,
    ...overrides,
  } as unknown as StrategyUnit
}

describe('useUnitTableRendering', () => {
  describe('statusDotClass', () => {
    it('returns is-running when trading_snapshot.instance_status is running', () => {
      expect(statusDotClass(unit({ trading_snapshot: { instance_status: 'running' } as any }))).toBe('is-running')
    })

    it('returns is-queued when status is queued', () => {
      expect(statusDotClass(unit({ run_status: 'queued' }))).toBe('is-queued')
    })

    it('returns is-error when status is error', () => {
      expect(statusDotClass(unit({ run_status: 'error' as any }))).toBe('is-error')
    })

    it('returns is-error when run_status is failed', () => {
      expect(statusDotClass(unit({ run_status: 'failed' }))).toBe('is-error')
    })

    it('returns is-error when trading_snapshot has error', () => {
      expect(statusDotClass(unit({ trading_snapshot: { error: 'oops' } as any }))).toBe('is-error')
    })

    it('returns is-idle when nothing matches', () => {
      expect(statusDotClass(unit({ run_status: 'idle' }))).toBe('is-idle')
    })
  })

  describe('statusLabel', () => {
    it.each([
      ['idle', '空闲'],
      ['queued', '排队中'],
      ['running', '运行中'],
      ['stopped', '已停止'],
      ['completed', '已完成'],
      ['failed', '失败'],
      ['error', '错误'],
      ['cancelled', '已取消'],
    ])('maps %s to localized label %s', (status, expected) => {
      expect(statusLabel(unit({ run_status: status as any }))).toBe(expected)
    })

    it('returns the raw status for unknown values', () => {
      expect(statusLabel(unit({ run_status: 'unknown' as any }))).toBe('unknown')
    })

    it('prefers trading_snapshot.instance_status over run_status', () => {
      expect(statusLabel(unit({
        run_status: 'idle',
        trading_snapshot: { instance_status: 'running' } as any,
      }))).toBe('运行中')
    })
  })

  describe('formatDate', () => {
    it('returns first 10 chars of ISO string', () => {
      expect(formatDate('2024-05-29T12:34:56Z')).toBe('2024-05-29')
    })

    it('returns - for nullish input', () => {
      expect(formatDate(null)).toBe('-')
      expect(formatDate(undefined)).toBe('-')
      expect(formatDate('')).toBe('-')
    })

    it('returns - for whitespace-only string', () => {
      expect(formatDate('   ')).toBe('-')
    })
  })

  describe('formatTime', () => {
    it('returns localized date string', () => {
      const result = formatTime('2024-01-01T00:00:00Z')
      expect(result).not.toBe('-')
      expect(result.length).toBeGreaterThan(0)
    })

    it('returns - for empty input', () => {
      expect(formatTime('')).toBe('-')
    })
  })

  describe('formatNumber', () => {
    it('formats with default digits and trims trailing zeros', () => {
      expect(formatNumber(1.5)).toBe('1.5')
      expect(formatNumber(1.0)).toBe('1')
    })

    it('keeps trailing zeros when trimTrailingZeros is false', () => {
      expect(formatNumber(1.0, 2, false)).toBe('1.00')
    })

    it('respects custom digits', () => {
      expect(formatNumber(1.23456, 4)).toBe('1.2346')
    })

    it('returns - for nullish or NaN input', () => {
      expect(formatNumber(null)).toBe('-')
      expect(formatNumber(undefined)).toBe('-')
      expect(formatNumber(NaN)).toBe('-')
    })
  })

  describe('formatQuantity', () => {
    it('preserves micro nonzero quantities', () => {
      expect(formatQuantity(0.00004)).toBe('0.00004')
      expect(formatQuantity(-0.00004)).toBe('-0.00004')
    })

    it('formats normal quantities with 4 decimals', () => {
      expect(formatQuantity(1.23456)).toBe('1.2346')
    })

    it('returns - for flat or invalid quantities', () => {
      expect(formatQuantity(0)).toBe('-')
      expect(formatQuantity(null)).toBe('-')
      expect(formatQuantity(NaN)).toBe('-')
    })
  })

  describe('formatPrice', () => {
    it('returns integer string for integer input', () => {
      expect(formatPrice(100)).toBe('100')
    })

    it('uses 2 decimals for abs >= 100', () => {
      expect(formatPrice(123.456)).toBe('123.46')
    })

    it('uses 4 decimals for abs < 100', () => {
      expect(formatPrice(0.123456)).toBe('0.1235')
    })

    it('returns - for nullish or NaN input', () => {
      expect(formatPrice(null)).toBe('-')
      expect(formatPrice(NaN)).toBe('-')
    })
  })

  describe('formatSignedNumber', () => {
    it('prefixes positive numbers with +', () => {
      expect(formatSignedNumber(1.5)).toBe('+1.50')
    })

    it('keeps negative sign untouched', () => {
      expect(formatSignedNumber(-1.5)).toBe('-1.50')
    })

    it('omits sign when showSign is false', () => {
      expect(formatSignedNumber(1.5, 2, false)).toBe('1.50')
    })

    it('appends suffix', () => {
      expect(formatSignedNumber(0.05, 2, true, '%')).toBe('+0.05%')
    })

    it('returns - for nullish input', () => {
      expect(formatSignedNumber(null)).toBe('-')
    })
  })

  describe('formatAmountCompact', () => {
    it('formats values >= 1e8 with 亿 suffix', () => {
      expect(formatAmountCompact(2.5e8)).toBe('2.50亿')
    })

    it('formats values >= 1e4 with 万 suffix', () => {
      expect(formatAmountCompact(50000)).toBe('5.00万')
    })

    it('formats small values with default digits', () => {
      expect(formatAmountCompact(123)).toBe('123.00')
    })

    it('handles negative values', () => {
      expect(formatAmountCompact(-50000)).toBe('-5.00万')
    })

    it('returns - for nullish input', () => {
      expect(formatAmountCompact(null)).toBe('-')
    })
  })

  describe('numberClass', () => {
    it('returns text-red-500 for positive', () => {
      expect(numberClass(1)).toBe('text-red-500')
    })

    it('returns text-green-600 for negative', () => {
      expect(numberClass(-1)).toBe('text-green-600')
    })

    it('returns text-gray-500 for zero/null/NaN', () => {
      expect(numberClass(0)).toBe('text-gray-500')
      expect(numberClass(null)).toBe('text-gray-500')
      expect(numberClass(NaN)).toBe('text-gray-500')
    })
  })

  describe('directionLabel', () => {
    it('returns localized 多头 for long direction', () => {
      expect(directionLabel('long')).toBe('多头')
      expect(directionLabel('LONG_POSITION')).toBe('多头')
    })

    it('returns localized 空头 for short direction', () => {
      expect(directionLabel('short')).toBe('空头')
    })

    it('returns the raw value for unrecognized direction', () => {
      expect(directionLabel('flat')).toBe('flat')
    })

    it('returns - for nullish/empty input', () => {
      expect(directionLabel(null)).toBe('-')
      expect(directionLabel(undefined)).toBe('-')
      expect(directionLabel('')).toBe('-')
    })
  })
})
