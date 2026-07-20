import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import NewsIntelligencePage from '@/views/NewsIntelligencePage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  createNewsSource: vi.fn(),
  pullNewsSource: vi.fn(),
  ingestArticles: vi.fn(),
  listArticles: vi.fn(),
  getArticleContent: vi.fn(),
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
          id: 'article-1',
          headline: 'RB2510 surges after bullish demand shock',
          sentiment: 'BULLISH',
          impact: 'HIGH',
          cluster_id: 'cluster-1',
          source: 'terminal-rss',
          summary: 'Demand shock lifted steel-linked futures.',
          has_content: true,
          url: 'https://example.com/rss/rb2510',
          tickers: ['RB2510'],
          status: 'ok',
        },
      ],
      total: 1,
    })
    apiMocks.getArticleContent.mockResolvedValue({
      id: 'article-1',
      headline: 'RB2510 surges after bullish demand shock',
      content: 'Demand shock lifted steel-linked futures.',
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
    await (wrapper.vm as any).showArticleContent((wrapper.vm as any).articles[0])
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
    expect((wrapper.vm as any).analysisResult).toMatchObject({ status: 'degraded' })
    expect((wrapper.vm as any).pullResult).toMatchObject({ status: 'ok' })
    expect(wrapper.text()).not.toContain('展开同簇')
    expect(wrapper.text()).not.toContain('Cluster 展开')
    expect(apiMocks.getArticleContent).toHaveBeenCalledWith('article-1')
    expect((wrapper.vm as any).articleContentVisible).toBe(true)
    expect((wrapper.vm as any).articleContent).toContain('Demand shock')
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

  it('opens each intelligence workflow from one of six live-desk action buttons', async () => {
    const wrapper = mountWithPlugins(NewsIntelligencePage)
    await flushPromises()

    const hero = wrapper.find('.news-hero')
    const deskActions = hero.find('[data-test="news-live-desk-actions"]')
    const actionButtons = deskActions.findAll('.news-desk-command')

    expect(wrapper.find('.news-source-panel').exists()).toBe(false)
    expect(wrapper.find('.news-direct-tools-grid').exists()).toBe(false)
    expect(wrapper.find('.news-table-panel [data-test="news-live-desk-actions"]').exists()).toBe(false)
    expect(actionButtons).toHaveLength(6)
    expect(deskActions.text()).toContain('情绪识别')
    expect(deskActions.text()).toContain('文章导入')
    expect(deskActions.text()).toContain('筛选')
    expect(deskActions.text()).toContain('刷新 RSS')
    expect(deskActions.text()).toContain('自动刷新')
    expect(deskActions.text()).toContain('来源治理')

    await wrapper.find('[data-test="news-desk-action-analysis"]').trigger('click')
    await wrapper.find('[data-test="news-desk-action-import"]').trigger('click')
    await wrapper.find('[data-test="news-desk-action-filter"]').trigger('click')
    await wrapper.find('[data-test="news-desk-action-rss-refresh"]').trigger('click')
    await wrapper.find('[data-test="news-desk-action-rss-schedule"]').trigger('click')
    await wrapper.find('[data-test="news-source-governance-button"]').trigger('click')

    expect((wrapper.vm as any).analysisVisible).toBe(true)
    expect((wrapper.vm as any).importVisible).toBe(true)
    expect((wrapper.vm as any).filterVisible).toBe(true)
    expect((wrapper.vm as any).rssRefreshVisible).toBe(true)
    expect((wrapper.vm as any).rssScheduleVisible).toBe(true)
    expect((wrapper.vm as any).sourceConfigVisible).toBe(true)
    expect((wrapper.vm as any).rssRefreshMinutes).toBe(15)
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
    expect(wrapper.text()).toContain('来源治理')
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
