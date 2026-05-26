import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AIObservabilityPage from '@/views/AIObservabilityPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  getAdminUsage: vi.fn(),
  getAdminFailures: vi.fn(),
  getAdminSlowCalls: vi.fn(),
}))

vi.mock('@/api/aiObservability', () => ({
  aiObservabilityApi: apiMocks,
}))

const usageFixture = {
  summary: {
    total_calls: 3,
    successful_calls: 2,
    failed_calls: 1,
    total_tokens: 340,
    estimated_cost_usd: 0.0074,
    avg_latency_ms: 183,
  },
  by_day: [{ date: '2026-05-24', total_calls: 2, total_tokens: 140, estimated_cost_usd: 0.0014 }],
  by_service: [{ service_name: 'ai_chat', total_calls: 2, total_tokens: 140, estimated_cost_usd: 0.0014 }],
  by_model: [{ model_name: 'gpt-4o-mini', total_calls: 2, total_tokens: 140, estimated_cost_usd: 0.0014 }],
  by_user: [{ user_id: 'user-1', total_calls: 2, total_tokens: 140, estimated_cost_usd: 0.0014 }],
}

const failureFixture = {
  summary: { total_calls: 3, failed_calls: 1, failure_rate: 1 / 3 },
  by_error_code: [{ error_code: 'HTTPError', failed_calls: 1 }],
  by_service: [{ service_name: 'ai_chat', failed_calls: 1 }],
  recent_failures: [{ id: 'log-1', service_name: 'ai_chat', error_code: 'HTTPError', created_at: '2026-05-24T00:00:00Z' }],
}

const slowFixture = {
  summary: { total_calls: 3, avg_latency_ms: 183, p95_latency_ms: 900, p99_latency_ms: 900 },
  by_service: [{ service_name: 'ai_chat', p95_latency_ms: 900, p99_latency_ms: 900 }],
  top_calls: [{ id: 'log-2', service_name: 'ai_chat', latency_ms: 900, model_name: 'gpt-4o-mini' }],
}

describe('AIObservabilityPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.getAdminUsage.mockResolvedValue(usageFixture)
    apiMocks.getAdminFailures.mockResolvedValue(failureFixture)
    apiMocks.getAdminSlowCalls.mockResolvedValue(slowFixture)
  })

  it('loads all dashboard datasets on mount', async () => {
    mountWithPlugins(AIObservabilityPage)
    await flushPromises()

    expect(apiMocks.getAdminUsage).toHaveBeenCalledWith({})
    expect(apiMocks.getAdminFailures).toHaveBeenCalledWith({ limit: 50 })
    expect(apiMocks.getAdminSlowCalls).toHaveBeenCalledWith({ limit: 20 })
  })

  it('renders summary cards and tab content', async () => {
    const wrapper = mountWithPlugins(AIObservabilityPage)
    await flushPromises()

    expect(wrapper.text()).toContain('AI 成本看板')
    expect(wrapper.text()).toContain('总调用数')
    expect(wrapper.text()).toContain('340')
    expect(wrapper.text()).toContain('$0.007400')
    expect(wrapper.text()).toContain('失败诊断')
    expect(wrapper.text()).toContain('HTTPError')
    expect(wrapper.text()).toContain('慢调用排查')
    expect(wrapper.text()).toContain('P95 延迟')
  })
})
