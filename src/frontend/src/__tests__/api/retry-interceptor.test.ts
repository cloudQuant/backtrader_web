/**
 * Retry Interceptor 单元测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { AxiosError, InternalAxiosRequestConfig } from 'axios'

import {
  isRetryableError,
  isIdempotentRequest,
  calculateRetryDelay,
  RETRY_CONFIG,
} from '@/api/index'

// Mock Element Plus
vi.mock('element-plus', () => ({
  ElMessage: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

describe('Retry Interceptor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('isRetryableError', () => {
    it('should return true for ERR_NETWORK error code', () => {
      const error = {
        code: 'ERR_NETWORK',
        response: undefined,
      } as unknown as AxiosError
      expect(isRetryableError(error)).toBe(true)
    })

    it('should return true for ECONNABORTED error code', () => {
      const error = {
        code: 'ECONNABORTED',
        response: undefined,
      } as unknown as AxiosError
      expect(isRetryableError(error)).toBe(true)
    })

    it.each([408, 429, 500, 502, 503, 504])(
      'should return true for status %d',
      (status) => {
        const error = {
          code: undefined,
          response: { status },
        } as unknown as AxiosError
        expect(isRetryableError(error)).toBe(true)
      }
    )

    it('should return false for non-retryable status codes', () => {
      const error = {
        code: undefined,
        response: { status: 400 },
      } as unknown as AxiosError
      expect(isRetryableError(error)).toBe(false)
    })

    it('should return false for 401 status', () => {
      const error = {
        code: undefined,
        response: { status: 401 },
      } as unknown as AxiosError
      expect(isRetryableError(error)).toBe(false)
    })

    it('should return false for 404 status', () => {
      const error = {
        code: undefined,
        response: { status: 404 },
      } as unknown as AxiosError
      expect(isRetryableError(error)).toBe(false)
    })
  })

  describe('isIdempotentRequest', () => {
    it.each(['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE'])(
      'should return true for %s method',
      (method) => {
        const config = {
          method: method.toLowerCase(),
          headers: {},
        } as unknown as InternalAxiosRequestConfig
        expect(isIdempotentRequest(config)).toBe(true)
      }
    )

    it('should return false for POST without Idempotency-Key', () => {
      const config = {
        method: 'post',
        headers: {},
      } as unknown as InternalAxiosRequestConfig
      expect(isIdempotentRequest(config)).toBe(false)
    })

    it('should return true for POST with Idempotency-Key header', () => {
      const config = {
        method: 'post',
        headers: { 'Idempotency-Key': 'unique-key-123' },
      } as unknown as InternalAxiosRequestConfig
      expect(isIdempotentRequest(config)).toBe(true)
    })

    it('should return false for PATCH method', () => {
      const config = {
        method: 'patch',
        headers: {},
      } as unknown as InternalAxiosRequestConfig
      expect(isIdempotentRequest(config)).toBe(false)
    })
  })

  describe('calculateRetryDelay', () => {
    it('should calculate base delay of 1000ms for first retry (retryCount=0)', () => {
      vi.spyOn(Math, 'random').mockReturnValue(0.5) // jitter = 0
      const delay = calculateRetryDelay(0)
      expect(delay).toBe(1000) // 1000 * 2^0 + 0 jitter
    })

    it('should calculate base delay of 2000ms for second retry (retryCount=1)', () => {
      vi.spyOn(Math, 'random').mockReturnValue(0.5) // jitter = 0
      const delay = calculateRetryDelay(1)
      expect(delay).toBe(2000) // 1000 * 2^1 + 0 jitter
    })

    it('should calculate base delay of 4000ms for third retry (retryCount=2)', () => {
      vi.spyOn(Math, 'random').mockReturnValue(0.5) // jitter = 0
      const delay = calculateRetryDelay(2)
      expect(delay).toBe(4000) // 1000 * 2^2 + 0 jitter
    })

    it('should apply ±10% jitter to the delay', () => {
      // Test with random = 0 (minimum jitter: -10%)
      vi.spyOn(Math, 'random').mockReturnValue(0)
      const minDelay = calculateRetryDelay(0)
      expect(minDelay).toBe(900) // 1000 - 100

      // Test with random = 1 (maximum jitter: +10%)
      vi.spyOn(Math, 'random').mockReturnValue(1)
      const maxDelay = calculateRetryDelay(0)
      expect(maxDelay).toBe(1100) // 1000 + 100
    })

    it('should produce delays within ±10% range for all retry counts', () => {
      vi.spyOn(Math, 'random').mockRestore()
      for (let i = 0; i < 100; i++) {
        const delay0 = calculateRetryDelay(0)
        expect(delay0).toBeGreaterThanOrEqual(900)
        expect(delay0).toBeLessThanOrEqual(1100)

        const delay1 = calculateRetryDelay(1)
        expect(delay1).toBeGreaterThanOrEqual(1800)
        expect(delay1).toBeLessThanOrEqual(2200)

        const delay2 = calculateRetryDelay(2)
        expect(delay2).toBeGreaterThanOrEqual(3600)
        expect(delay2).toBeLessThanOrEqual(4400)
      }
    })
  })

  describe('RETRY_CONFIG', () => {
    it('should have correct default values', () => {
      expect(RETRY_CONFIG.maxRetries).toBe(3)
      expect(RETRY_CONFIG.initialDelay).toBe(1000)
      expect(RETRY_CONFIG.backoffFactor).toBe(2)
      expect(RETRY_CONFIG.jitterRange).toBe(0.1)
      expect(RETRY_CONFIG.retryableStatuses).toEqual([408, 429, 500, 502, 503, 504])
      expect(RETRY_CONFIG.idempotentMethods).toEqual(['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE'])
    })
  })

  describe('Retry Interceptor Integration (response interceptor behavior)', () => {
    /**
     * These tests verify the retry logic by simulating the interceptor behavior
     * directly, without going through a real axios instance (which would hang
     * due to adapter issues in test environments).
     */

    async function simulateRetryInterceptor(
      error: { config: any; code?: string; response?: { status: number; data?: any } },
      requestFn: (config: any) => Promise<any>
    ): Promise<any> {
      const config = error.config
      const retryCount = config.__retryCount || 0

      const axiosError = error as unknown as AxiosError
      if (
        retryCount < RETRY_CONFIG.maxRetries &&
        isRetryableError(axiosError) &&
        isIdempotentRequest(config)
      ) {
        config.__retryCount = retryCount + 1
        config.__isRetrying = true
        // In real code, there's a delay here. We skip it in tests.
        return requestFn(config)
      }
      throw error
    }

    it('should retry GET request 3 times on 503 then reject', async () => {
      let callCount = 0
      const config = { method: 'get', headers: {}, url: '/test' } as any

      const requestFn = async (cfg: any): Promise<any> => {
        callCount++
        const err = { config: cfg, response: { status: 503, data: {} } }
        return simulateRetryInterceptor(err, requestFn)
      }

      const initialError = { config, response: { status: 503, data: {} } }
      await expect(simulateRetryInterceptor(initialError, requestFn)).rejects.toBeDefined()
      // 3 retries (the initial call is outside the interceptor)
      expect(callCount).toBe(3)
      expect(config.__retryCount).toBe(3)
    })

    it('should not retry POST without Idempotency-Key', async () => {
      let callCount = 0
      const config = { method: 'post', headers: {}, url: '/test' } as any

      const requestFn = async (cfg: any): Promise<any> => {
        callCount++
        const err = { config: cfg, response: { status: 503, data: {} } }
        return simulateRetryInterceptor(err, requestFn)
      }

      const initialError = { config, response: { status: 503, data: {} } }
      await expect(simulateRetryInterceptor(initialError, requestFn)).rejects.toBeDefined()
      // No retries for non-idempotent POST
      expect(callCount).toBe(0)
      expect(config.__retryCount).toBeUndefined()
    })

    it('should retry POST with Idempotency-Key header', async () => {
      let callCount = 0
      const config = { method: 'post', headers: { 'Idempotency-Key': 'key-123' }, url: '/test' } as any

      const requestFn = async (cfg: any): Promise<any> => {
        callCount++
        const err = { config: cfg, response: { status: 503, data: {} } }
        return simulateRetryInterceptor(err, requestFn)
      }

      const initialError = { config, response: { status: 503, data: {} } }
      await expect(simulateRetryInterceptor(initialError, requestFn)).rejects.toBeDefined()
      // 3 retries for POST with Idempotency-Key
      expect(callCount).toBe(3)
      expect(config.__retryCount).toBe(3)
    })

    it('should succeed on retry if server recovers', async () => {
      let callCount = 0
      const config = { method: 'get', headers: {}, url: '/test' } as any

      const requestFn = async (cfg: any): Promise<any> => {
        callCount++
        if (callCount >= 2) {
          return { data: { success: true }, status: 200 }
        }
        const err = { config: cfg, response: { status: 503, data: {} } }
        return simulateRetryInterceptor(err, requestFn)
      }

      const initialError = { config, response: { status: 503, data: {} } }
      const result = await simulateRetryInterceptor(initialError, requestFn)
      expect(result.data).toEqual({ success: true })
      expect(callCount).toBe(2) // 1 retry failure + 1 success
    })

    it('should not retry on non-retryable status codes (e.g. 400)', async () => {
      let callCount = 0
      const config = { method: 'get', headers: {}, url: '/test' } as any

      const requestFn = async (cfg: any): Promise<any> => {
        callCount++
        const err = { config: cfg, response: { status: 400, data: {} } }
        return simulateRetryInterceptor(err, requestFn)
      }

      const initialError = { config, response: { status: 400, data: {} } }
      await expect(simulateRetryInterceptor(initialError, requestFn)).rejects.toBeDefined()
      expect(callCount).toBe(0)
    })

    it('should retry on ERR_NETWORK error', async () => {
      let callCount = 0
      const config = { method: 'get', headers: {}, url: '/test' } as any

      const requestFn = async (cfg: any): Promise<any> => {
        callCount++
        const err = { config: cfg, code: 'ERR_NETWORK', response: undefined }
        return simulateRetryInterceptor(err, requestFn)
      }

      const initialError = { config, code: 'ERR_NETWORK', response: undefined }
      await expect(simulateRetryInterceptor(initialError, requestFn)).rejects.toBeDefined()
      // 3 retries
      expect(callCount).toBe(3)
      expect(config.__retryCount).toBe(3)
    })

    it('should set __isRetrying flag during retries', async () => {
      const config = { method: 'get', headers: {}, url: '/test' } as any

      const requestFn = async (cfg: any): Promise<any> => {
        const err = { config: cfg, response: { status: 503, data: {} } }
        return simulateRetryInterceptor(err, requestFn)
      }

      const initialError = { config, response: { status: 503, data: {} } }
      await expect(simulateRetryInterceptor(initialError, requestFn)).rejects.toBeDefined()
      expect(config.__isRetrying).toBe(true)
    })
  })
})
