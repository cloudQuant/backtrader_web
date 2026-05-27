import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import NewsIntelligencePage from '@/views/NewsIntelligencePage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  createNewsSource: vi.fn(),
  pullNewsSource: vi.fn(),
  ingestArticles: vi.fn(),
  listArticles: vi.fn(),
  analyzeHeadline: vi.fn(),
}))

vi.mock('@/api/marketIntel', () => ({
  marketIntelApi: apiMocks,
}))

describe('NewsIntelligencePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.createNewsSource.mockResolvedValue({ id: 'source-1' })
    apiMocks.pullNewsSource.mockResolvedValue({ source: 'terminal-rss', status: 'ok', fetched_count: 2, inserted_count: 2, total: 2 })
    apiMocks.ingestArticles.mockResolvedValue({ inserted_count: 1, total: 1 })
    apiMocks.listArticles.mockResolvedValue({
      items: [{ headline: 'RB2510 surges after bullish demand shock', sentiment: 'BULLISH', impact: 'HIGH', cluster_id: 'cluster-1', source: 'terminal-rss' }],
      total: 1,
    })
    apiMocks.analyzeHeadline.mockResolvedValue({ sentiment: 'NEUTRAL', impact: 'MEDIUM', status: 'degraded' })
  })

  it('creates sources, pulls rss, filters articles, and expands clusters', async () => {
    const wrapper = mountWithPlugins(NewsIntelligencePage)
    expect(wrapper.text()).toContain('新闻情报')

    await flushPromises()
    await (wrapper.vm as any).createSource()
    await (wrapper.vm as any).pullSource()
    await (wrapper.vm as any).ingest()
    await (wrapper.vm as any).analyzeHeadline()
    ;(wrapper.vm as any).filterSentiment = 'BULLISH'
    ;(wrapper.vm as any).filterTicker = 'RB2510'
    await (wrapper.vm as any).loadArticles()
    await (wrapper.vm as any).expandCluster('cluster-1')
    await flushPromises()

    expect(apiMocks.createNewsSource).toHaveBeenCalledWith({ name: 'terminal-rss', url: 'https://example.com/rss', tier: 2 })
    expect(apiMocks.pullNewsSource).toHaveBeenCalledWith('terminal-rss')
    expect(apiMocks.ingestArticles).toHaveBeenCalled()
    expect(apiMocks.analyzeHeadline).toHaveBeenCalledWith({ headline: 'Unclear macro policy update', allow_ai: true })
    expect(apiMocks.listArticles).toHaveBeenCalledWith({ sentiment: 'BULLISH', ticker: 'RB2510', cluster_id: undefined })
    expect(apiMocks.listArticles).toHaveBeenLastCalledWith({ cluster_id: 'cluster-1' })
    expect((wrapper.vm as any).articles).toHaveLength(1)
    expect((wrapper.vm as any).articles[0].sentiment).toBe('BULLISH')
    expect((wrapper.vm as any).clusterArticles).toHaveLength(1)
    expect(wrapper.text()).toContain('degraded')
    expect(wrapper.text()).toContain('拉取结果')
    expect(wrapper.text()).toContain('Cluster 展开')
  })
})
