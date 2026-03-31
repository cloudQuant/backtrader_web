/**
 * Unit tests for useBacktestStore.
 *
 * Tests cover:
 * - Initial state
 * - Run backtest
 * - Fetch result
 * - Fetch results list
 * - Delete result
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { backtestApi } from '@/api/backtest'
import type { BacktestResult, BacktestResponse, BacktestRequest } from '@/types'

import { useBacktestStore } from '../backtest'

// Mock dependencies
vi.mock('@/api/backtest', () => ({
  backtestApi: {
    run: vi.fn(),
    getResult: vi.fn(),
    list: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('useBacktestStore', () => {
  let store: ReturnType<typeof useBacktestStore>

  const mockResult: BacktestResult = {
    task_id: 'task-123',
    status: 'completed',
    strategy_id: 'test-strategy',
    symbol: 'BTCUSDT',
    start_date: '2024-01-01',
    end_date: '2024-01-31',
    total_return: 0.15,
    annual_return: 0.45,
    sharpe_ratio: 1.5,
    max_drawdown: -0.08,
    win_rate: 0.6,
    total_trades: 10,
    profitable_trades: 6,
    losing_trades: 4,
    equity_curve: [100000, 105000, 110000, 115000],
    equity_dates: ['2024-01-01', '2024-01-10', '2024-01-20', '2024-01-31'],
    drawdown_curve: [0, -0.02, -0.03, -0.01],
    trades: [],
    created_at: '2024-01-31T12:00:00Z',
  }

  const mockRunResponse: BacktestResponse = {
    task_id: 'task-123',
    status: 'pending',
    message: 'Task created',
  }

  const defaultRequest: BacktestRequest = {
    strategy_id: 'test-strategy',
    symbol: 'BTCUSDT',
    start_date: '2024-01-01',
    end_date: '2024-01-31',
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    store = useBacktestStore()
  })

  describe('initial state', () => {
    it('should have empty initial state', () => {
      expect(store.results).toEqual([])
      expect(store.currentResult).toBeNull()
      expect(store.loading).toBe(false)
      expect(store.total).toBe(0)
    })
  })

  describe('runBacktest', () => {
    it('should run backtest and return response', async () => {
      vi.mocked(backtestApi.run).mockResolvedValue(mockRunResponse)

      const response = await store.runBacktest(defaultRequest)

      expect(response).toEqual(mockRunResponse)
      expect(backtestApi.run).toHaveBeenCalledWith(defaultRequest)
    })

    it('should set loading during backtest run', async () => {
      vi.mocked(backtestApi.run).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockRunResponse), 100))
      )

      const promise = store.runBacktest(defaultRequest)

      // Loading should be true during the call
      expect(store.loading).toBe(true)

      await promise

      // Loading should be false after completion
      expect(store.loading).toBe(false)
    })

    it('should reset loading even on error', async () => {
      vi.mocked(backtestApi.run).mockRejectedValue(new Error('Backtest failed'))

      await expect(
        store.runBacktest(defaultRequest)
      ).rejects.toThrow('Backtest failed')

      expect(store.loading).toBe(false)
    })
  })

  describe('fetchResult', () => {
    it('should fetch and set current result', async () => {
      vi.mocked(backtestApi.getResult).mockResolvedValue(mockResult)

      const result = await store.fetchResult('task-123')

      expect(result).toEqual(mockResult)
      expect(store.currentResult).toEqual(mockResult)
      expect(backtestApi.getResult).toHaveBeenCalledWith('task-123')
    })

    it('should set loading during fetch', async () => {
      vi.mocked(backtestApi.getResult).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockResult), 100))
      )

      const promise = store.fetchResult('task-123')

      expect(store.loading).toBe(true)

      await promise

      expect(store.loading).toBe(false)
    })
  })

  describe('fetchResults', () => {
    it('should fetch results list with pagination', async () => {
      vi.mocked(backtestApi.list).mockResolvedValue({
        items: [mockResult],
        total: 1,
      })

      await store.fetchResults(20, 0)

      expect(store.results).toEqual([mockResult])
      expect(store.total).toBe(1)
      expect(backtestApi.list).toHaveBeenCalledWith(20, 0)
    })

    it('should use default pagination', async () => {
      vi.mocked(backtestApi.list).mockResolvedValue({
        items: [],
        total: 0,
      })

      await store.fetchResults()

      expect(backtestApi.list).toHaveBeenCalledWith(20, 0)
    })
  })

  describe('deleteResult', () => {
    it('should delete result and remove from list', async () => {
      // First, populate the results list
      vi.mocked(backtestApi.list).mockResolvedValue({
        items: [mockResult],
        total: 1,
      })
      await store.fetchResults()

      vi.mocked(backtestApi.delete).mockResolvedValue(undefined)

      await store.deleteResult('task-123')

      expect(backtestApi.delete).toHaveBeenCalledWith('task-123')
      expect(store.results).toEqual([])
    })

    it('should only remove matching result from list', async () => {
      const anotherResult = { ...mockResult, task_id: 'task-456' }
      vi.mocked(backtestApi.list).mockResolvedValue({
        items: [mockResult, anotherResult],
        total: 2,
      })
      await store.fetchResults()

      vi.mocked(backtestApi.delete).mockResolvedValue(undefined)

      await store.deleteResult('task-123')

      expect(store.results).toHaveLength(1)
      expect(store.results[0].task_id).toBe('task-456')
    })
  })
})
