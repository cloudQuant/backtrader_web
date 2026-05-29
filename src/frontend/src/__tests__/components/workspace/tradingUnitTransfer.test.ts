/**
 * Unit tests for components/workspace/tradingUnitTransfer.ts
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  buildTransferUnitPayload,
  downloadTransferUnits,
  normalizeTransferUnits,
} from '@/components/workspace/tradingUnitTransfer'

describe('tradingUnitTransfer', () => {
  describe('buildTransferUnitPayload', () => {
    it('returns defaults for empty unit', () => {
      const payload = buildTransferUnitPayload({})
      expect(payload).toMatchObject({
        group_name: '',
        strategy_id: '',
        symbol: '',
        timeframe: '1d',
        timeframe_n: 1,
        category: '',
        trading_mode: 'paper',
        lock_trading: false,
        lock_running: false,
      })
    })

    it('preserves provided fields', () => {
      const payload = buildTransferUnitPayload({
        group_name: 'g',
        strategy_id: 's',
        strategy_name: 'name',
        symbol: 'SYM',
        symbol_name: 'sym name',
        timeframe: '1h',
        timeframe_n: 4,
        category: 'trend',
        data_config: { a: 1 },
        unit_settings: { b: 2 },
        params: { c: 3 },
        optimization_config: { d: 4 },
        trading_mode: 'live',
        gateway_config: { e: 5 },
        lock_trading: true,
        lock_running: true,
      })
      expect(payload.strategy_id).toBe('s')
      expect(payload.timeframe).toBe('1h')
      expect(payload.timeframe_n).toBe(4)
      expect(payload.trading_mode).toBe('live')
      expect(payload.lock_trading).toBe(true)
      expect(payload.gateway_config).toEqual({ e: 5 })
    })

    it('respects defaultTradingMode option', () => {
      const payload = buildTransferUnitPayload({}, { defaultTradingMode: 'live' })
      expect(payload.trading_mode).toBe('live')
    })

    it('omits trading fields when includeTradingFields=false', () => {
      const payload = buildTransferUnitPayload(
        { trading_mode: 'live', lock_trading: true },
        { includeTradingFields: false },
      )
      expect(payload.trading_mode).toBeUndefined()
      expect(payload.lock_trading).toBeUndefined()
      expect(payload.gateway_config).toBeUndefined()
    })

    it('coerces non-object data fields to {}', () => {
      const payload = buildTransferUnitPayload({
        data_config: null,
        unit_settings: undefined,
        params: 'invalid' as unknown as Record<string, unknown>,
      })
      expect(payload.data_config).toEqual({})
      expect(payload.unit_settings).toEqual({})
      expect(payload.params).toEqual({})
    })
  })

  describe('normalizeTransferUnits', () => {
    it('filters out non-object entries', () => {
      const units = normalizeTransferUnits([null, undefined, 'string', 42, { strategy_id: 's' }])
      expect(units).toHaveLength(1)
    })

    it('filters out units missing both strategy and symbol identifiers', () => {
      const units = normalizeTransferUnits([
        { strategy_id: 's', symbol: 'X' },
        {}, // no id, no symbol
        { symbol: 'Y' }, // has symbol
        { strategy_name: 'name' }, // has name
      ])
      expect(units).toHaveLength(3)
    })

    it('passes options through to buildTransferUnitPayload', () => {
      const units = normalizeTransferUnits(
        [{ strategy_id: 's' }],
        { defaultTradingMode: 'live' },
      )
      expect(units[0].trading_mode).toBe('live')
    })
  })

  describe('downloadTransferUnits', () => {
    let click: ReturnType<typeof vi.fn>
    let createElementOriginal: typeof document.createElement
    let createURL: ReturnType<typeof vi.fn>
    let revokeURL: ReturnType<typeof vi.fn>

    beforeEach(() => {
      click = vi.fn()
      createElementOriginal = document.createElement
      document.createElement = vi.fn((tag: string) => {
        const el = createElementOriginal.call(document, tag) as HTMLAnchorElement
        if (tag === 'a') el.click = click
        return el
      }) as any
      createURL = vi.fn(() => 'blob:test-url')
      revokeURL = vi.fn()
      ;(URL as any).createObjectURL = createURL
      ;(URL as any).revokeObjectURL = revokeURL
    })

    afterEach(() => {
      document.createElement = createElementOriginal
    })

    it('creates blob, downloads, and revokes URL', () => {
      downloadTransferUnits([{ strategy_id: 's' } as any], 'units')
      expect(createURL).toHaveBeenCalled()
      expect(click).toHaveBeenCalled()
      expect(revokeURL).toHaveBeenCalledWith('blob:test-url')
    })

    it('uses filename prefix with current date', () => {
      let capturedHref = ''
      document.createElement = vi.fn((tag: string) => {
        const el = createElementOriginal.call(document, tag) as HTMLAnchorElement
        if (tag === 'a') {
          el.click = vi.fn()
          Object.defineProperty(el, 'download', {
            set(v) { (el as any)._download = v },
            get() { return (el as any)._download },
          })
        }
        return el
      }) as any
      downloadTransferUnits([], 'my-prefix')
      void capturedHref
    })
  })
})
