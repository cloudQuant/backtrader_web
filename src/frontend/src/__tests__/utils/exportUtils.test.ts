import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  downloadFile,
  exportBacktestResult,
  exportEquityCurve,
  exportMultipleFormats,
  exportStrategies,
  exportToCSV,
  exportToJSON,
  exportTrades,
} from '@/utils/exportUtils'

describe('exportUtils', () => {
  it('protects formula-like strings in CSV cells', () => {
    const csv = exportToCSV([
      {
        name: '=SUM(A1:A2)',
        email: '+cmd',
        note: '@malicious',
        plain: 'hello',
      },
    ])

    expect(csv).toContain("'=SUM(A1:A2)")
    expect(csv).toContain("'+cmd")
    expect(csv).toContain("'@malicious")
    expect(csv).toContain('hello')
  })

  it('escapes formula-like strings inside serialized objects', () => {
    const csv = exportToCSV([
      {
        payload: {
          formula: '=1+1',
        },
      },
    ])

    expect(csv).toContain(`"{""formula"":""=1+1""}"`)
  })

  describe('exportToCSV branches', () => {
    it('returns empty string when data is empty or undefined', () => {
      expect(exportToCSV([])).toBe('')
      expect(exportToCSV(undefined as never)).toBe('')
    })

    it('omits headers when includeHeaders is false', () => {
      const csv = exportToCSV([{ a: 1 }], { includeHeaders: false })
      expect(csv).toBe('1')
    })

    it('formats numbers as locale strings when numberFormat=formatted', () => {
      const csv = exportToCSV([{ n: 1234567 }], { numberFormat: 'formatted' })
      // toLocaleString varies by env; just ensure separators were added
      expect(csv).not.toContain('1234567')
    })

    it('quotes values containing commas, quotes, or newlines', () => {
      const csv = exportToCSV([{ s: 'a,b' }, { s: '"q"' }, { s: 'line\nbreak' }])
      expect(csv).toContain('"a,b"')
      expect(csv).toContain('"""q"""')
      expect(csv).toContain('"line\nbreak"')
    })

    it('renders Date as ISO/locale/timestamp', () => {
      const date = new Date('2024-05-29T00:00:00Z')
      const isoCsv = exportToCSV([{ d: date }], { dateFormat: 'iso' })
      expect(isoCsv).toContain('2024-05-29')
      const tsCsv = exportToCSV([{ d: date }], { dateFormat: 'timestamp' })
      expect(tsCsv).toContain(String(date.getTime()))
    })

    it('handles null/undefined values gracefully', () => {
      const csv = exportToCSV([{ a: null, b: undefined, c: '' }])
      expect(csv).toContain('a,b,c')
    })
  })

  describe('exportToJSON', () => {
    it('serializes data as pretty-printed JSON', () => {
      const json = exportToJSON({ a: 1 })
      expect(json).toBe('{\n  "a": 1\n}')
    })

    it('formats Date as ISO by default', () => {
      const date = new Date('2024-05-29T00:00:00Z')
      const json = exportToJSON({ d: date })
      expect(json).toContain('2024-05-29')
    })

    it('processes nested arrays recursively', () => {
      const date = new Date('2024-05-29T00:00:00Z')
      const json = exportToJSON([{ d: date }, { d: date }])
      expect(JSON.parse(json)).toHaveLength(2)
    })

    it('formats numbers as locale strings when numberFormat=formatted', () => {
      const json = exportToJSON({ n: 1234567 }, { numberFormat: 'formatted' })
      expect(json).not.toContain('1234567')
    })
  })

  describe('downloadFile', () => {
    it('triggers browser download via temporary anchor', () => {
      const click = vi.fn()
      const orig = document.createElement
      document.createElement = vi.fn((tag: string) => {
        const el = orig.call(document, tag) as HTMLAnchorElement
        if (tag === 'a') {
          el.click = click
        }
        return el
      }) as any

      // jsdom-style stubs for blob URL helpers
      const createURL = vi.fn(() => 'blob:test')
      const revokeURL = vi.fn()
      ;(URL as any).createObjectURL = createURL
      ;(URL as any).revokeObjectURL = revokeURL

      downloadFile('content', 'test.csv', 'text/csv')

      expect(createURL).toHaveBeenCalled()
      expect(click).toHaveBeenCalled()
      expect(revokeURL).toHaveBeenCalledWith('blob:test')

      document.createElement = orig
    })
  })

  describe('exportBacktestResult / exportTrades / exportStrategies / exportEquityCurve', () => {
    const result = {
      task_id: 't-1',
      strategy_id: 's-1',
      symbol: '000001.SZ',
      start_date: '2024-01-01',
      end_date: '2024-12-31',
      total_return: 15.5,
      annual_return: 12.0,
      sharpe_ratio: 1.5,
      max_drawdown: 8.0,
      total_trades: 10,
      win_rate: 60,
      profitable_trades: 6,
      losing_trades: 4,
      trades: [
        { entry_date: '2024-01-01', exit_date: '2024-01-05', symbol: '000001.SZ', side: 'long', size: 100, pnl: 200 },
      ],
      equity_curve: [100000, 102000],
      equity_dates: ['2024-01-01', '2024-01-02'],
      drawdown_curve: [],
      created_at: '2024-01-01T00:00:00',
      status: 'completed',
    } as any

    let createURL: ReturnType<typeof vi.fn<[], string>>
    let revokeURL: ReturnType<typeof vi.fn>
    let click: ReturnType<typeof vi.fn>
    let createElementOriginal: typeof document.createElement

    beforeEach(() => {
      click = vi.fn()
      createElementOriginal = document.createElement
      document.createElement = vi.fn((tag: string) => {
        const el = createElementOriginal.call(document, tag) as HTMLAnchorElement
        if (tag === 'a') el.click = click
        return el
      }) as any
      createURL = vi.fn(() => 'blob:test')
      revokeURL = vi.fn()
      ;(URL as any).createObjectURL = createURL
      ;(URL as any).revokeObjectURL = revokeURL
    })

    afterEach(() => {
      document.createElement = createElementOriginal
    })

    it('exportBacktestResult triggers a CSV download', () => {
      exportBacktestResult(result, 'csv')
      expect(click).toHaveBeenCalled()
    })

    it('exportBacktestResult triggers a JSON download', () => {
      exportBacktestResult(result, 'json')
      expect(click).toHaveBeenCalled()
    })

    it('exportBacktestResult throws for unsupported excel format', () => {
      expect(() => exportBacktestResult(result, 'excel')).toThrow(/xlsx/)
    })

    it('exportBacktestResult throws for html format', () => {
      expect(() => exportBacktestResult(result, 'html')).toThrow(/HTML/)
    })

    it('exportTrades triggers a CSV download', () => {
      exportTrades(result.trades, 'csv')
      expect(click).toHaveBeenCalled()
    })

    it('exportStrategies triggers a JSON download', () => {
      const strategies = [{
        id: 's-1', name: 'sample', category: 'trend', description: 'd',
        params: {}, code: '', created_at: '2024-01-01T00:00:00',
      }] as any
      exportStrategies(strategies, 'json')
      expect(click).toHaveBeenCalled()
    })

    it('exportEquityCurve triggers a CSV download', () => {
      exportEquityCurve(
        [
          { date: '2024-01-01', value: 100000 },
          { date: '2024-01-02', value: 102000 },
        ],
        'csv',
      )
      expect(click).toHaveBeenCalled()
    })
  })

  describe('exportMultipleFormats', () => {
    it('invokes the exporter for each requested format', () => {
      const exporter = vi.fn()
      exportMultipleFormats({ a: 1 }, ['csv', 'json'], exporter)
      expect(exporter).toHaveBeenCalledTimes(2)
      expect(exporter).toHaveBeenCalledWith({ a: 1 }, 'csv')
      expect(exporter).toHaveBeenCalledWith({ a: 1 }, 'json')
    })

    it('continues when one format throws', () => {
      const exporter = vi.fn((_data: unknown, fmt: string) => {
        if (fmt === 'csv') throw new Error('boom')
      })
      expect(() => exportMultipleFormats({ a: 1 }, ['csv', 'json'], exporter)).not.toThrow()
      expect(exporter).toHaveBeenCalledTimes(2)
    })

    it('does nothing when no formats requested', () => {
      const exporter = vi.fn()
      exportMultipleFormats({ a: 1 }, [], exporter)
      expect(exporter).not.toHaveBeenCalled()
    })
  })
})
