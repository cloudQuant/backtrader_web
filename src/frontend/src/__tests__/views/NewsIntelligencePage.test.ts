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
      items: [
        {
          headline: 'RB2510 surges after bullish demand shock',
          sentiment: 'BULLISH',
          impact: 'HIGH',
          cluster_id: 'cluster-1',
          source: 'terminal-rss',
          summary: 'Demand shock lifted steel-linked futures.',
          url: 'https://example.com/rss/rb2510',
          tickers: ['RB2510'],
          status: 'ok',
        },
      ],
      total: 1,
    })
    apiMocks.analyzeHeadline.mockResolvedValue({ sentiment: 'NEUTRAL', impact: 'MEDIUM', status: 'degraded' })
  })

  it('creates sources, pulls rss, filters articles, and opens article urls', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
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
    ;(wrapper.vm as any).openArticle((wrapper.vm as any).articles[0])
    await flushPromises()

    expect(apiMocks.createNewsSource).toHaveBeenCalledWith({
      name: 'bloomberg-mkts',
      url: 'https://feeds.bloomberg.com/markets/news.rss',
      tier: 2,
    })
    expect(apiMocks.pullNewsSource).toHaveBeenCalledWith('bloomberg-mkts')
    expect(apiMocks.ingestArticles).toHaveBeenCalled()
    expect(apiMocks.analyzeHeadline).toHaveBeenCalledWith({ headline: 'Unclear macro policy update', allow_ai: true })
    expect(apiMocks.listArticles).toHaveBeenCalledWith({ sentiment: 'BULLISH', ticker: 'RB2510', cluster_id: undefined })
    expect((wrapper.vm as any).articles).toHaveLength(1)
    expect((wrapper.vm as any).articles[0].sentiment).toBe('BULLISH')
    expect(wrapper.text()).toContain('degraded')
    expect(wrapper.text()).toContain('拉取结果')
    expect(wrapper.text()).not.toContain('展开同簇')
    expect(wrapper.text()).not.toContain('Cluster 展开')
    expect(wrapper.text()).not.toContain('新闻内容')
    expect(wrapper.text()).not.toContain('Demand shock lifted steel-linked futures.')
    expect(wrapper.find('.news-article-details').exists()).toBe(false)
    expect(openSpy).toHaveBeenCalledWith('https://example.com/rss/rb2510', '_blank', 'noopener,noreferrer')

    openSpy.mockRestore()
  })

  it('starts from the FinceptTerminal Bloomberg Markets preset and shows an empty state', async () => {
    apiMocks.listArticles.mockResolvedValue({ items: [], total: 0 })

    const wrapper = mountWithPlugins(NewsIntelligencePage)
    await flushPromises()

    expect((wrapper.vm as any).sourceName).toBe('bloomberg-mkts')
    expect((wrapper.vm as any).sourceUrl).toBe('https://feeds.bloomberg.com/markets/news.rss')
    expect(wrapper.text()).not.toContain('https://example.com/rss')
    expect(wrapper.text()).not.toContain('Bloomberg Markets')
    expect(wrapper.text()).not.toContain('Reuters 公共 RSS 已停用')
    expect(wrapper.text()).toContain('暂无新闻，请导入文章或配置真实 RSS 来源。')
    expect(wrapper.find('.news-source-summary').exists()).toBe(false)
    expect(wrapper.find('.news-source-config').exists()).toBe(false)
  })

  it('places rss actions beside refresh and the article import controls on the next row', async () => {
    const wrapper = mountWithPlugins(NewsIntelligencePage)
    await flushPromises()

    const actionRow = wrapper.find('.news-analysis-toolbar')
    const importRow = wrapper.find('.news-import-row')

    expect(actionRow.exists()).toBe(true)
    expect(importRow.exists()).toBe(true)
    expect(actionRow.text()).toContain('刷新列表')
    expect(actionRow.text()).toContain('拉取 RSS')
    expect(actionRow.text()).toContain('配置来源')
    expect(actionRow.text().indexOf('刷新列表')).toBeLessThan(actionRow.text().indexOf('拉取 RSS'))
    expect(actionRow.text().indexOf('拉取 RSS')).toBeLessThan(actionRow.text().indexOf('配置来源'))
    expect(importRow.text()).toContain('导入文章')
    expect(actionRow.element.compareDocumentPosition(importRow.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('opens source configuration dialog beside pull rss and applies multiple built-in presets', async () => {
    const wrapper = mountWithPlugins(NewsIntelligencePage)
    await flushPromises()

    expect((wrapper.vm as any).sourceConfigVisible).toBe(false)
    expect(wrapper.find('.news-source-config').exists()).toBe(false)

    ;(wrapper.vm as any).toggleSourceConfig()
    await flushPromises()
    await wrapper.find('[data-test="news-feed-preset-cnbc-finance"]').trigger('click')
    ;(wrapper.vm as any).applyFeedPresets()
    await (wrapper.vm as any).pullSource()
    await flushPromises()

    expect((wrapper.vm as any).sourceConfigVisible).toBe(true)
    expect((wrapper.vm as any).sourceName).toBe('bloomberg-mkts')
    expect((wrapper.vm as any).sourceUrl).toBe('https://feeds.bloomberg.com/markets/news.rss')
    expect(wrapper.find('.news-source-config').exists()).toBe(true)
    expect(wrapper.text()).toContain('配置来源')
    expect(wrapper.text()).toContain('CNBC Finance')
    expect(wrapper.text()).toContain('已配置来源')
    expect((wrapper.vm as any).selectedFeedPresetIds).toEqual(['bloomberg-mkts', 'cnbc-finance'])
    expect(wrapper.find('.news-source-actions').text()).toContain('新增来源')
    expect(wrapper.find('.news-source-actions').text()).toContain('应用配置')
    expect(apiMocks.createNewsSource).toHaveBeenCalledWith({
      name: 'bloomberg-mkts',
      url: 'https://feeds.bloomberg.com/markets/news.rss',
      tier: 2,
    })
    expect(apiMocks.createNewsSource).toHaveBeenCalledWith({
      name: 'cnbc-finance',
      url: 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114',
      tier: 2,
    })
    expect(apiMocks.pullNewsSource).toHaveBeenCalledWith('bloomberg-mkts')
    expect(apiMocks.pullNewsSource).toHaveBeenCalledWith('cnbc-finance')
  })
})
