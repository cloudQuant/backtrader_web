import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/api/index'
import { aiObservabilityApi } from '@/api/aiObservability'

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), patch: vi.fn(), post: vi.fn() },
}))

describe('aiObservabilityApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads admin usage with optional filters', async () => {
    vi.mocked(request.get).mockResolvedValue({ summary: { total_calls: 0 } })

    await aiObservabilityApi.getAdminUsage({ service_name: 'ai_chat', model_name: 'gpt-4o-mini' })

    expect(request.get).toHaveBeenCalledWith('/admin/ai/usage', {
      params: { service_name: 'ai_chat', model_name: 'gpt-4o-mini' },
    })
  })

  it('loads failure diagnostics with limit', async () => {
    vi.mocked(request.get).mockResolvedValue({ summary: { failed_calls: 0 } })

    await aiObservabilityApi.getAdminFailures({ limit: 20 })

    expect(request.get).toHaveBeenCalledWith('/admin/ai/failures', {
      params: { limit: 20 },
    })
  })

  it('loads slow calls with limit', async () => {
    vi.mocked(request.get).mockResolvedValue({ summary: { p95_latency_ms: 0 } })

    await aiObservabilityApi.getAdminSlowCalls({ limit: 10 })

    expect(request.get).toHaveBeenCalledWith('/admin/ai/slow-calls', {
      params: { limit: 10 },
    })
  })

  it('loads current user usage', async () => {
    vi.mocked(request.get).mockResolvedValue({ summary: { total_calls: 1 } })

    await aiObservabilityApi.getMyUsage()

    expect(request.get).toHaveBeenCalledWith('/me/ai/usage', { params: {} })
  })

  it('loads current user available AI models', async () => {
    vi.mocked(request.get).mockResolvedValue({ providers: [], models: [], preferences: {} })

    await aiObservabilityApi.getMyAvailableModels()

    expect(request.get).toHaveBeenCalledWith('/me/ai/available-models')
  })

  it('updates current user AI preferences', async () => {
    vi.mocked(request.patch).mockResolvedValue({ preferences: { provider: 'ollama', model: 'ollama/qwen2.5-coder:7b' } })

    await aiObservabilityApi.updateMyPreferences({
      provider: 'ollama',
      model: 'ollama/qwen2.5-coder:7b',
    })

    expect(request.patch).toHaveBeenCalledWith('/me/ai/preferences', {
      provider: 'ollama',
      model: 'ollama/qwen2.5-coder:7b',
    })
  })

  it('tests current user AI preferences connectivity', async () => {
    vi.mocked(request.post).mockResolvedValue({ provider: 'ollama', model: 'ollama/qwen2.5-coder:7b', available: true })

    await aiObservabilityApi.testMyPreferences({
      provider: 'ollama',
      model: 'ollama/qwen2.5-coder:7b',
    })

    expect(request.post).toHaveBeenCalledWith('/me/ai/preferences/test', {
      provider: 'ollama',
      model: 'ollama/qwen2.5-coder:7b',
    })
  })
})
