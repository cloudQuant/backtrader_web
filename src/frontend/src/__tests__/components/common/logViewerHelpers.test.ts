/**
 * Unit tests for components/common/logViewerHelpers.ts
 */
import { describe, expect, it } from 'vitest'

import {
  formatLogLine,
  formatLogTime,
  formatSize,
  lineMatchesSearch,
} from '@/components/common/logViewerHelpers'

describe('logViewerHelpers', () => {
  describe('formatLogLine', () => {
    it('returns minimal entry for empty string', () => {
      const r = formatLogLine('')
      expect(r.raw).toBe('')
      expect(r.text).toBe(' ')
    })

    it('returns plain entry for non-JSON line', () => {
      const r = formatLogLine('plain text log')
      expect(r.raw).toBe('plain text log')
      expect(r.text).toBeUndefined()
    })

    it('parses tick event JSON with badge=TICK', () => {
      const line = JSON.stringify({
        event_type: 'tick',
        symbol: 'IF2510',
        price: 4250,
        volume: 100,
        bid_price: 4249,
        ask_price: 4251,
        bid_volume: 5,
        ask_volume: 8,
        openinterest: 200000,
        strategy_name: 'sample',
        log_time: '2024-05-29T03:30:15.123',
      })
      const r = formatLogLine(line)
      expect(r.badge).toBe('TICK')
      expect(r.text).toContain('IF2510')
      expect(r.text).toContain('4250')
      expect(r.text).toContain('sample')
    })

    it('parses bar event JSON with badge=BAR', () => {
      const line = JSON.stringify({
        event_type: 'bar',
        symbol: 'IF2510',
        open: 100, high: 105, low: 99, close: 102, volume: 1000,
        interval: '1m',
        strategy_name: 'sample',
        log_time: '2024-05-29T03:30:15',
      })
      const r = formatLogLine(line)
      expect(r.badge).toBe('BAR')
      expect(r.text).toContain('O:100')
      expect(r.text).toContain('C:102')
    })

    it('returns raw object for unrecognized JSON', () => {
      const line = JSON.stringify({ random: 'data' })
      const r = formatLogLine(line)
      expect(r.raw).toBe(line)
    })

    it('falls back gracefully on malformed JSON', () => {
      const r = formatLogLine('{broken json')
      expect(r.raw).toBe('{broken json')
      expect(r.text).toBeUndefined()
    })

    it('parses tab-separated columns line', () => {
      const r = formatLogLine('col1\tcol2\tcol3')
      expect(r.text).toContain('[0]: col1')
      expect(r.text).toContain('[1]: col2')
      expect(r.text).toContain('[2]: col3')
    })

    it('parses generic system event log with INFO level', () => {
      const line = JSON.stringify({
        event_type: 'gateway_connect',
        level: 'INFO',
        status: 'connected',
        provider: 'CTP',
        account_id_masked: '****1234',
        log_time: '2024-05-29T03:30:15.000',
      })
      const r = formatLogLine(line)
      expect(r.badge).toBe('INFO')
      expect(r.text).toContain('gateway_connect')
      expect(r.text).toContain('[connected]')
      expect(r.text).toContain('CTP')
      expect(r.levelClass).toContain('blue')
    })

    it('parses ERROR-level system event with error_code/error_msg', () => {
      const line = JSON.stringify({
        event_type: 'order_send',
        level: 'ERROR',
        error_code: 'E1001',
        error_msg: 'connection refused',
        details: { stack: 'trace...' },
      })
      const r = formatLogLine(line)
      expect(r.badge).toBe('ERROR')
      expect(r.text).toContain('E1001')
      expect(r.text).toContain('connection refused')
      expect(r.levelClass).toContain('red')
    })

    it('parses WARNING-level event', () => {
      const line = JSON.stringify({ event_type: 'risk_warning', level: 'WARNING' })
      const r = formatLogLine(line)
      expect(r.badge).toBe('WARNING')
      expect(r.levelClass).toContain('amber')
    })

    it('parses DEBUG-level event', () => {
      const line = JSON.stringify({ event_type: 'cache_hit', level: 'DEBUG' })
      const r = formatLogLine(line)
      expect(r.badge).toBe('DEBUG')
    })

    it('parses position log entry', () => {
      const line = JSON.stringify({
        data_name: 'IF2510',
        size: 5,
        price: 4250.5,
        value: 21252.5,
      })
      const r = formatLogLine(line)
      expect(r.text).toBeTruthy()
      expect(r.levelClass).toContain('emerald')
    })

    it('parses indicator log with BtApiFeed_* keys', () => {
      const line = JSON.stringify({
        data_BtApiFeed_open: 100,
        data_BtApiFeed_high: 105,
        data_BtApiFeed_low: 99,
        data_BtApiFeed_close: 102,
        data_BtApiFeed_volume: 1000,
        data_BtApiFeed_openinterest: 50000,
        strategy_name: 'sample',
      })
      const r = formatLogLine(line)
      expect(r.text).toContain('O:100.0')
      expect(r.text).toContain('C:102.0')
      expect(r.text).toContain('V:1000')
      expect(r.text).toContain('OI:50000')
      expect(r.text).toContain('sample')
    })

    it('falls through to pretty-print for unrecognized JSON', () => {
      const line = JSON.stringify({
        log_time: '2024-05-29T03:30:15.000',
        custom_field: 'value',
        another: 42,
      })
      const r = formatLogLine(line)
      // Should pretty-print key fields
      expect(r.text).toBeTruthy()
    })
  })

  describe('formatLogTime', () => {
    it('returns empty string for undefined or empty', () => {
      expect(formatLogTime(undefined)).toBe('')
      expect(formatLogTime('')).toBe('')
    })

    it('returns empty string for "1970-01-01" sentinel', () => {
      expect(formatLogTime('1970-01-01T00:00:00.000Z')).toBe('')
    })

    it('parses ISO with milliseconds (UTC, gets Z suffix)', () => {
      const result = formatLogTime('2024-05-29T03:30:15.123')
      // Just verify it parses to YYYY-MM-DD HH:MM:SS format
      expect(result).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
    })

    it('parses event_time format (space-separated, local time)', () => {
      const result = formatLogTime('2024-05-29 11:30:15')
      expect(result).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
    })

    it('falls back to first 19 chars when parsing fails', () => {
      // 'invalid time' -> Date is NaN -> returns first 19 chars
      const result = formatLogTime('invalid time string')
      expect(result.length).toBeLessThanOrEqual(19)
    })
  })

  describe('lineMatchesSearch', () => {
    it('returns false for empty/whitespace search text', () => {
      expect(lineMatchesSearch('any line', '')).toBe(false)
      expect(lineMatchesSearch('any line', '   ')).toBe(false)
    })

    it('matches case-insensitively', () => {
      expect(lineMatchesSearch('ERROR: something failed', 'error')).toBe(true)
      expect(lineMatchesSearch('Error: x', 'ERROR')).toBe(true)
    })

    it('returns false when text is not present', () => {
      expect(lineMatchesSearch('hello world', 'foo')).toBe(false)
    })
  })

  describe('formatSize', () => {
    it('formats bytes with B suffix when < 1KB', () => {
      expect(formatSize(0)).toBe('0 B')
      expect(formatSize(1023)).toBe('1023 B')
    })

    it('formats kilobytes when < 1MB', () => {
      expect(formatSize(1024)).toBe('1.0 KB')
      expect(formatSize(1024 * 100)).toBe('100.0 KB')
    })

    it('formats megabytes when >= 1MB', () => {
      expect(formatSize(1024 * 1024)).toBe('1.00 MB')
      expect(formatSize(1024 * 1024 * 5)).toBe('5.00 MB')
    })
  })
})
