import { describe, expect, it } from 'vitest'
import { APP_PATHS, LEGACY_PATHS, toAppChildPath } from '@/navigation/routes'

describe('primary workflow route contract', () => {
  it('defines the canonical research-to-backtest paths', () => {
    expect(APP_PATHS.research.strategies).toBe('/research/strategies')
    expect(APP_PATHS.backtest.list).toBe('/backtest')
    expect(APP_PATHS.backtest.result(42)).toBe('/backtest/result/42')
    expect(APP_PATHS.ai.chat).toBe('/ai/chat')
    expect(APP_PATHS.ai.knowledgeBase).toBe('/ai/knowledge-base')
  })

  it('keeps legacy aliases separate from new navigation', () => {
    expect(LEGACY_PATHS.aiChat).toBe('/ai-chat')
    expect(LEGACY_PATHS.strategy).toBe('/strategy')
    expect(LEGACY_PATHS.backtestResultPattern).toBe('/backtest/:id')
  })

  it('converts absolute paths for routes nested under the app shell', () => {
    expect(toAppChildPath(APP_PATHS.dashboard)).toBe('')
    expect(toAppChildPath(APP_PATHS.backtest.list)).toBe('backtest')
  })
})
