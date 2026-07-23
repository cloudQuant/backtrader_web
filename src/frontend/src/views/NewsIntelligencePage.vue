<template>
  <div
    class="news-intel-page"
    data-test="news-intel-page"
  >
    <section class="news-hero">
      <div class="news-hero-copy">
        <span class="news-eyebrow">{{ t('newsIntel.heroKicker') }}</span>
        <div class="news-hero-title-row">
          <h1>{{ t('newsIntel.title') }}</h1>
        </div>
        <p>{{ t('newsIntel.desc') }}</p>
        <div
          class="news-table-actions news-hero-actions"
          data-test="news-live-desk-actions"
        >
          <button
            type="button"
            class="news-desk-command"
            data-test="news-desk-action-analysis"
            @click="analysisVisible = true"
          >
            <el-icon aria-hidden="true"><Search /></el-icon>
            <span>{{ t('newsIntel.btnSentimentAnalysis') }}</span>
          </button>
          <button
            type="button"
            class="news-desk-command"
            data-test="news-desk-action-import"
            @click="importVisible = true"
          >
            <el-icon aria-hidden="true"><Plus /></el-icon>
            <span>{{ t('newsIntel.btnArticleImport') }}</span>
          </button>
          <button
            type="button"
            class="news-desk-command"
            data-test="news-desk-action-filter"
            @click="filterVisible = true"
          >
            <el-icon aria-hidden="true"><Filter /></el-icon>
            <span>{{ t('newsIntel.btnFiltering') }}</span>
          </button>
          <button
            type="button"
            class="news-desk-command"
            data-test="news-desk-action-rss-refresh"
            @click="rssRefreshVisible = true"
          >
            <el-icon aria-hidden="true"><Refresh /></el-icon>
            <span>{{ t('newsIntel.btnRefreshRss') }}</span>
          </button>
          <button
            type="button"
            class="news-desk-command"
            data-test="news-desk-action-rss-schedule"
            @click="rssScheduleVisible = true"
          >
            <el-icon aria-hidden="true"><Refresh /></el-icon>
            <span>{{ t('newsIntel.btnAutoRefresh') }}</span>
          </button>
          <button
            type="button"
            class="news-desk-command"
            data-test="news-source-governance-button"
            @click="toggleSourceConfig"
          >
            <el-icon aria-hidden="true"><Setting /></el-icon>
            <span>{{ t('newsIntel.btnSourceGovernance') }}</span>
          </button>
        </div>
      </div>

      <div class="news-hero-stats">
        <article
          v-for="stat in newsStats"
          :key="stat.label"
          class="news-stat-card"
        >
          <span>{{ stat.label }}</span>
          <strong>{{ stat.value }}</strong>
          <small>{{ stat.helper }}</small>
        </article>
      </div>
    </section>

    <section class="news-workbench">
      <div class="news-table-panel">
        <div class="news-section-heading">
          <div>
            <span class="news-section-kicker">{{ t('newsIntel.tableKicker') }}</span>
            <h2>{{ t('newsIntel.tableTitle') }}</h2>
            <p>{{ t('newsIntel.tableDesc') }}</p>
          </div>
          <div class="news-section-heading-tools">
            <span class="news-table-count">{{ t('newsIntel.tableCountTpl', { count: articles.length }) }}</span>
          </div>
        </div>

        <div
          v-if="articles.length === 0"
          class="news-empty"
        >
          <span class="news-empty-icon">
            <el-icon aria-hidden="true">
              <Document />
            </el-icon>
          </span>
          <strong>{{ t('newsIntel.emptyTitle') }}</strong>
          <p>{{ t('newsIntel.emptyArticles') }}</p>
        </div>
        <el-table
          v-else
          class="news-table"
          :data="articles"
          :empty-text="t('newsIntel.emptyArticles')"
        >
          <el-table-column
            :label="t('newsIntel.colHeadline')"
            min-width="280"
          >
            <template #default="scope">
              <div class="news-headline-cell">
                <strong>{{ scope.row.headline }}</strong>
                <span>{{ articleMeta(scope.row) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('newsIntel.colSentiment')"
            width="130"
          >
            <template #default="scope">
              <span
                class="news-pill"
                :class="sentimentClass(scope.row.sentiment)"
              >
                {{ displayValue(scope.row.sentiment) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('newsIntel.colImpact')"
            width="120"
          >
            <template #default="scope">
              <span
                class="news-pill news-pill--impact"
                :class="impactClass(scope.row.impact)"
              >
                {{ displayValue(scope.row.impact) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('newsIntel.colCluster')"
            min-width="140"
          >
            <template #default="scope">
              <code class="news-cluster-code">{{ displayValue(scope.row.cluster_id) }}</code>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('newsIntel.colActions')"
            width="220"
          >
            <template #default="scope">
              <el-button
                link
                type="primary"
                :disabled="!scope.row.id"
                @click="showArticleContent(scope.row)"
              >
                <el-icon aria-hidden="true"><Document /></el-icon>
                {{ t('newsIntel.btnViewContent') }}
              </el-button>
              <el-button
                link
                type="primary"
                :disabled="!scope.row.url"
                @click="openArticle(scope.row)"
              >
                <el-icon aria-hidden="true">
                  <Link />
                </el-icon>
                {{ t('newsIntel.btnOpenArticle') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <el-dialog
      v-model="articleContentVisible"
      :title="articleContentTitle || t('newsIntel.articleDetailsTitle')"
      width="min(780px, calc(100vw - 32px))"
      class="news-article-content-dialog"
    >
      <div
        v-loading="articleContentLoading"
        class="news-article-content"
      >
        <p v-if="articleContent">{{ articleContent }}</p>
        <el-empty
          v-else-if="!articleContentLoading"
          :description="t('newsIntel.noSummary')"
        />
      </div>
    </el-dialog>

    <el-dialog
      v-if="analysisVisible"
      v-model="analysisVisible"
      :title="t('newsIntel.analysisTitle')"
      width="min(720px, calc(100vw - 32px))"
      class="news-workflow-dialog"
    >
      <section class="news-dialog-workflow">
        <p>{{ t('newsIntel.analysisDesc') }}</p>
        <div class="news-analysis-toolbar">
          <el-input
            v-model="analysisHeadline"
            :placeholder="t('newsIntel.analysisPh')"
            class="news-primary-input"
          />
          <el-button
            type="primary"
            :loading="loading"
            @click="analyzeHeadline"
          >
            <el-icon aria-hidden="true"><Search /></el-icon>
            {{ t('newsIntel.btnAnalyze') }}
          </el-button>
        </div>
        <div
          v-if="analysisResult"
          class="news-result-grid news-result-grid--single"
        >
          <div class="news-result-card">
            <span>{{ t('newsIntel.analysisStatusLabel') }}</span>
            <strong>{{ displayValue(analysisResult.sentiment) }}</strong>
            <small>
              {{ t('newsIntel.analysisResultTpl', { sentiment: analysisResult.sentiment, impact: analysisResult.impact, status: analysisResult.status }) }}
            </small>
          </div>
        </div>
      </section>
    </el-dialog>

    <el-dialog
      v-if="importVisible"
      v-model="importVisible"
      :title="t('newsIntel.importTitle')"
      width="min(760px, calc(100vw - 32px))"
      class="news-workflow-dialog"
    >
      <section class="news-dialog-workflow">
        <p>{{ t('newsIntel.importDesc') }}</p>
        <div class="news-import-row">
          <el-input
            v-model="headline"
            :placeholder="t('newsIntel.headlinePh')"
          />
          <el-input
            v-model="url"
            :placeholder="t('newsIntel.urlPh')"
          />
          <el-button
            type="primary"
            :loading="loading"
            @click="ingest"
          >
            <el-icon aria-hidden="true"><Plus /></el-icon>
            {{ t('newsIntel.btnIngest') }}
          </el-button>
        </div>
      </section>
    </el-dialog>

    <el-dialog
      v-if="filterVisible"
      v-model="filterVisible"
      :title="t('newsIntel.filterTitle')"
      width="min(760px, calc(100vw - 32px))"
      class="news-workflow-dialog"
    >
      <section class="news-dialog-workflow">
        <p>{{ t('newsIntel.filterDesc') }}</p>
        <div class="news-filter-grid">
          <el-select
            v-model="filterSentiment"
            clearable
            :placeholder="t('newsIntel.sentimentPh')"
          >
            <el-option label="BULLISH" value="BULLISH" />
            <el-option label="BEARISH" value="BEARISH" />
            <el-option label="NEUTRAL" value="NEUTRAL" />
          </el-select>
          <el-input
            v-model="filterTicker"
            :placeholder="t('newsIntel.tickerPh')"
          />
          <el-input
            v-model="filterClusterId"
            :placeholder="t('newsIntel.clusterIdPh')"
          />
          <el-button
            type="primary"
            :loading="loading"
            @click="loadArticles"
          >
            <el-icon aria-hidden="true"><Filter /></el-icon>
            {{ t('newsIntel.btnApplyFilter') }}
          </el-button>
        </div>
      </section>
    </el-dialog>

    <el-dialog
      v-if="rssRefreshVisible"
      v-model="rssRefreshVisible"
      :title="t('newsIntel.btnRefreshRss')"
      width="min(640px, calc(100vw - 32px))"
      class="news-workflow-dialog"
    >
      <section class="news-dialog-workflow">
        <p>{{ t('newsIntel.sourcePanelDesc') }}</p>
        <div class="news-configured-source-list">
          <span
            v-for="source in configuredSources"
            :key="source.id"
            class="news-selected-source"
          >
            {{ source.name }}
          </span>
        </div>
        <el-button
          type="primary"
          :loading="loading"
          @click="pullSource"
        >
          <el-icon aria-hidden="true"><Refresh /></el-icon>
          {{ t('newsIntel.btnRefreshRss') }}
        </el-button>
        <div
          v-if="pullResult"
          class="news-result-grid news-result-grid--single"
        >
          <div class="news-result-card">
            <span>{{ t('newsIntel.pullStatusLabel') }}</span>
            <strong>{{ displayValue(pullResult.status) }}</strong>
            <small>
              {{ t('newsIntel.pullResultTpl', { status: pullResult.status, fetched: pullResult.fetched_count, inserted: pullResult.inserted_count }) }}
            </small>
          </div>
        </div>
      </section>
    </el-dialog>

    <el-dialog
      v-if="rssScheduleVisible"
      v-model="rssScheduleVisible"
      :title="t('newsIntel.rssRefreshInterval')"
      width="min(560px, calc(100vw - 32px))"
      class="news-workflow-dialog"
    >
      <section class="news-dialog-workflow">
        <p>{{ t('newsIntel.rssRefreshMinutes', { minutes: rssRefreshMinutes }) }}</p>
        <el-select
          v-model="rssRefreshMinutes"
          class="news-refresh-interval"
          :aria-label="t('newsIntel.rssRefreshInterval')"
        >
          <el-option :label="t('newsIntel.rssRefreshMinutes', { minutes: 5 })" :value="5" />
          <el-option :label="t('newsIntel.rssRefreshMinutes', { minutes: 15 })" :value="15" />
          <el-option :label="t('newsIntel.rssRefreshMinutes', { minutes: 30 })" :value="30" />
          <el-option :label="t('newsIntel.rssRefreshMinutes', { minutes: 60 })" :value="60" />
        </el-select>
      </section>
    </el-dialog>

    <el-dialog
      v-if="sourceConfigVisible"
      v-model="sourceConfigVisible"
      :title="t('newsIntel.sourceGovernanceTitle')"
      width="min(760px, calc(100vw - 32px))"
      class="news-source-config-dialog"
    >
      <div class="news-source-config">
        <div class="news-source-config-main">
          <el-select
            v-model="selectedFeedPresetIds"
            multiple
            collapse-tags
            collapse-tags-tooltip
            :placeholder="t('newsIntel.sourcePresetLabel')"
          >
            <el-option
              v-for="preset in newsFeedPresets"
              :key="preset.id"
              :label="preset.name"
              :value="preset.id"
            />
          </el-select>
        </div>
        <div class="news-source-form">
          <el-input
            v-model="sourceName"
            :placeholder="t('newsIntel.sourceNamePh')"
          />
          <el-input
            v-model="sourceUrl"
            :placeholder="t('newsIntel.sourceUrlPh')"
          />
        </div>
        <div class="news-source-actions">
          <el-button
            type="primary"
            :loading="loading"
            @click="createSource"
          >
            {{ t('newsIntel.btnAddSource') }}
          </el-button>
          <el-button
            type="primary"
            @click="applyFeedPresets"
          >
            {{ t('newsIntel.btnApplySourcePreset') }}
          </el-button>
        </div>
        <div class="news-selected-sources">
          <span class="news-selected-sources-label">{{ t('newsIntel.selectedSources') }}</span>
          <span
            v-for="source in configuredSources"
            :key="source.id"
            class="news-selected-source"
          >
            {{ source.name }}
          </span>
        </div>
        <div class="news-preset-list">
          <button
            v-for="preset in newsFeedPresets"
            :key="preset.id"
            type="button"
            class="news-preset-item"
            :class="{ 'is-selected': isFeedPresetSelected(preset.id) }"
            :aria-pressed="isFeedPresetSelected(preset.id)"
            :data-test="`news-feed-preset-${preset.id}`"
            @click="toggleFeedPreset(preset.id)"
          >
            <strong>{{ preset.name }}</strong>
            <small>{{ preset.category }} · {{ preset.region }}</small>
          </button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Document, Filter, Link, Plus, Refresh, Search, Setting } from '@element-plus/icons-vue'
import { marketIntelApi, type NewsArticleItem } from '@/api/marketIntel'

const { t } = useI18n()

type NewsFeedPreset = {
  id: string
  name: string
  url: string
  category: string
  region: string
  tier: number
}

const newsFeedPresets: NewsFeedPreset[] = [
  {
    id: 'bloomberg-mkts',
    name: 'Bloomberg Markets',
    url: 'https://www.bloomberg.com/feeds/markets/news.rss',
    category: 'MARKETS',
    region: 'GLOBAL',
    tier: 2,
  },
  {
    id: 'wsj-markets',
    name: 'WSJ Markets',
    url: 'https://feeds.a.dj.com/rss/RSSMarketsMain.xml',
    category: 'MARKETS',
    region: 'US',
    tier: 2,
  },
  {
    id: 'marketwatch',
    name: 'MarketWatch',
    url: 'https://feeds.marketwatch.com/marketwatch/topstories/',
    category: 'MARKETS',
    region: 'US',
    tier: 2,
  },
  {
    id: 'cnbc-finance',
    name: 'CNBC Finance',
    url: 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114',
    category: 'MARKETS',
    region: 'US',
    tier: 2,
  },
  {
    id: 'bbc-business',
    name: 'BBC Business',
    url: 'http://feeds.bbci.co.uk/news/business/rss.xml',
    category: 'MARKETS',
    region: 'GLOBAL',
    tier: 2,
  },
  {
    id: 'investing-news',
    name: 'Investing.com',
    url: 'https://www.investing.com/rss/news.rss',
    category: 'MARKETS',
    region: 'GLOBAL',
    tier: 2,
  },
]

const defaultFeedPreset = newsFeedPresets[0]
const defaultFeedPresets = newsFeedPresets.filter((preset) => {
  return preset.id === 'bloomberg-mkts' || preset.id === 'cnbc-finance'
})
const loading = ref(false)
const articles = ref<NewsArticleItem[]>([])
const analysisVisible = ref(false)
const importVisible = ref(false)
const filterVisible = ref(false)
const rssRefreshVisible = ref(false)
const rssScheduleVisible = ref(false)
const sourceConfigVisible = ref(false)
const articleContentVisible = ref(false)
const articleContentLoading = ref(false)
const articleContent = ref('')
const articleContentTitle = ref('')
const rssRefreshMinutes = ref(15)
const selectedFeedPresetIds = ref<string[]>(defaultFeedPresets.map((preset) => preset.id))
const configuredSources = ref<NewsFeedPreset[]>([...defaultFeedPresets])
const sourceName = ref(defaultFeedPreset.id)
const sourceUrl = ref(defaultFeedPreset.url)
const headline = ref('RB2510 surges after bullish demand shock')
const url = ref('https://example.com/news/rb2510')
const analysisHeadline = ref('Unclear macro policy update')
const analysisResult = ref<Record<string, unknown> | null>(null)
const pullResult = ref<Record<string, unknown> | null>(null)
const filterSentiment = ref('')
const filterTicker = ref('')
const filterClusterId = ref('')

const uniqueClusterCount = computed(() => {
  return new Set(articles.value.map((article) => article.cluster_id).filter(Boolean)).size
})

const signalCount = computed(() => {
  return articles.value.filter((article) => {
    const sentiment = String(article.sentiment ?? '').toUpperCase()
    return sentiment === 'BULLISH' || sentiment === 'BEARISH'
  }).length
})

const newsStats = computed(() => [
  {
    label: t('newsIntel.statArticles'),
    value: String(articles.value.length),
    helper: t('newsIntel.statArticlesHelper'),
  },
  {
    label: t('newsIntel.statSignals'),
    value: String(signalCount.value),
    helper: t('newsIntel.statSignalsHelper'),
  },
  {
    label: t('newsIntel.statClusters'),
    value: String(uniqueClusterCount.value),
    helper: t('newsIntel.statClustersHelper'),
  },
  {
    label: t('newsIntel.statSources'),
    value: String(configuredSources.value.length),
    helper: t('newsIntel.statSourcesHelper'),
  },
])

const selectedFeedPresets = computed(() => {
  const selected = newsFeedPresets.filter((preset) => selectedFeedPresetIds.value.includes(preset.id))
  return selected.length ? selected : defaultFeedPresets
})

function toggleSourceConfig() {
  sourceConfigVisible.value = !sourceConfigVisible.value
}

function applyFeedPresets() {
  configuredSources.value = [...selectedFeedPresets.value]
  const preset = configuredSources.value[0] ?? defaultFeedPreset
  sourceName.value = preset.id
  sourceUrl.value = preset.url
}

function isFeedPresetSelected(presetId: string) {
  return selectedFeedPresetIds.value.includes(presetId)
}

function toggleFeedPreset(presetId: string) {
  const selectedIds = new Set(selectedFeedPresetIds.value)
  if (selectedIds.has(presetId)) {
    if (selectedIds.size === 1) return
    selectedIds.delete(presetId)
  } else {
    selectedIds.add(presetId)
  }
  selectedFeedPresetIds.value = newsFeedPresets
    .filter((preset) => selectedIds.has(preset.id))
    .map((preset) => preset.id)
}

async function createSource() {
  loading.value = true
  try {
    await saveConfiguredSources()
  } finally {
    loading.value = false
  }
}

function getConfiguredSourcePayloads() {
  const payloads = new Map<string, { name: string, url: string, tier: number }>()
  for (const source of configuredSources.value) {
    payloads.set(source.id, { name: source.id, url: source.url, tier: source.tier })
  }

  const manualName = sourceName.value.trim()
  const manualUrl = sourceUrl.value.trim()
  if (manualName && manualUrl) {
    payloads.set(manualName, { name: manualName, url: manualUrl, tier: 2 })
  }

  return Array.from(payloads.values())
}

async function saveConfiguredSources() {
  const payloads = getConfiguredSourcePayloads()
  for (const payload of payloads) {
    await marketIntelApi.createNewsSource(payload)
  }
  return payloads
}

function sumPullValue(results: Array<Record<string, unknown>>, key: string) {
  return results.reduce((total, result) => total + Number(result[key] ?? 0), 0)
}

function mergePullResults(results: Array<Record<string, unknown>>, sources: Array<{ name: string }>) {
  const totals = results.map((result) => Number(result.total ?? 0))
  const status = results.some((result) => result.status && result.status !== 'ok') ? 'degraded' : 'ok'
  return {
    source: sources.map((source) => source.name).join(', '),
    status,
    fetched_count: sumPullValue(results, 'fetched_count'),
    inserted_count: sumPullValue(results, 'inserted_count'),
    total: totals.length ? Math.max(...totals) : 0,
  }
}

function degradedPullResult(sourceName: string, reason: string): Record<string, unknown> {
  return {
    source: sourceName,
    status: 'degraded',
    reason,
    fetched_count: 0,
    inserted_count: 0,
    total: 0,
  }
}

async function pullSource() {
  loading.value = true
  try {
    const sources = getConfiguredSourcePayloads()
    await Promise.allSettled(sources.map((source) => marketIntelApi.createNewsSource(source)))
    const results = await Promise.all(sources.map(async (source) => {
      try {
        return await marketIntelApi.pullNewsSource(source.name)
      } catch {
        return degradedPullResult(source.name, 'fetch_failed')
      }
    }))
    pullResult.value = mergePullResults(results, sources)
    await loadArticles()
  } finally {
    loading.value = false
  }
}

async function ingest() {
  loading.value = true
  try {
    await marketIntelApi.ingestArticles({
      articles: [
        { headline: headline.value, url: url.value, source: sourceName.value, tickers: ['RB2510'] },
      ],
    })
    await loadArticles()
  } finally {
    loading.value = false
  }
}

async function analyzeHeadline() {
  loading.value = true
  try {
    analysisResult.value = await marketIntelApi.analyzeHeadline({ headline: analysisHeadline.value, allow_ai: true })
  } finally {
    loading.value = false
  }
}

async function loadArticles() {
  const response = await marketIntelApi.listArticles({
    sentiment: filterSentiment.value || undefined,
    ticker: filterTicker.value || undefined,
    cluster_id: filterClusterId.value || undefined,
  })
  articles.value = response.items
}

async function showArticleContent(article: NewsArticleItem) {
  if (!article.id) return
  articleContentVisible.value = true
  articleContentLoading.value = true
  articleContent.value = ''
  articleContentTitle.value = article.headline
  try {
    const response = await marketIntelApi.getArticleContent(article.id)
    articleContent.value = response.content || response.summary || ''
  } finally {
    articleContentLoading.value = false
  }
}

function openArticle(article: NewsArticleItem) {
  const articleUrl = String(article.url || '').trim()
  if (!articleUrl) return
  window.open(articleUrl, '_blank', 'noopener,noreferrer')
}

function displayValue(value: unknown) {
  const text = String(value ?? '').trim()
  return text || '--'
}

function sentimentClass(sentiment: unknown) {
  const value = String(sentiment ?? '').toUpperCase()
  if (value === 'BULLISH') return 'news-pill--bullish'
  if (value === 'BEARISH') return 'news-pill--bearish'
  return 'news-pill--neutral'
}

function impactClass(impact: unknown) {
  const value = String(impact ?? '').toUpperCase()
  if (value === 'HIGH') return 'news-pill--high'
  if (value === 'LOW') return 'news-pill--low'
  return 'news-pill--medium'
}

function articleMeta(article: NewsArticleItem) {
  const parts = [
    article.source || t('newsIntel.unknownSource'),
    ...(article.tickers ?? []),
  ].filter(Boolean)
  return parts.join(' · ')
}

let rssRefreshTimer: ReturnType<typeof setInterval> | null = null

function stopRssRefresh() {
  if (rssRefreshTimer) {
    clearInterval(rssRefreshTimer)
    rssRefreshTimer = null
  }
}

function startRssRefresh() {
  stopRssRefresh()
  rssRefreshTimer = setInterval(() => {
    void pullSource()
  }, rssRefreshMinutes.value * 60_000)
}

watch(rssRefreshMinutes, startRssRefresh)

onMounted(() => {
  void loadArticles()
  startRssRefresh()
})

onUnmounted(stopRssRefresh)
</script>

<style scoped>
.news-intel-page {
  --news-page-bg: var(--bg-color-page);
  --news-panel-bg: color-mix(in srgb, var(--bg-color) 92%, transparent);
  --news-panel-strong: color-mix(in srgb, var(--bg-color) 82%, var(--el-color-primary) 18%);
  --news-text: var(--text-color-primary);
  --news-text-muted: var(--text-color-secondary);
  --news-border: color-mix(in srgb, var(--border-color) 78%, transparent);
  --news-border-strong: color-mix(in srgb, var(--border-color) 68%, var(--el-color-primary) 32%);
  --news-shadow: 0 18px 48px color-mix(in srgb, #000 16%, transparent);
  --news-accent: var(--el-color-primary);
  --news-good: var(--success-color, #16a34a);
  --news-bad: var(--danger-color, #dc2626);
  --news-warn: var(--warning-color, #d97706);
  display: grid;
  gap: 18px;
  color: var(--news-text);
}

.news-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(360px, 0.92fr);
  gap: 18px;
  padding: clamp(22px, 3.2vw, 34px);
  border: 1px solid var(--news-border);
  border-radius: 8px;
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--bg-color) 94%, var(--el-color-primary) 6%), transparent),
    var(--news-panel-bg);
  background-color: var(--news-panel-bg);
  box-shadow: var(--news-shadow);
}

.news-hero-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
}

.news-eyebrow,
.news-section-kicker {
  color: var(--news-accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.news-hero h1,
.news-section-heading h2 {
  margin: 0;
  color: var(--news-text);
  letter-spacing: 0;
}

.news-hero h1 {
  font-size: clamp(30px, 4vw, 46px);
  line-height: 1.06;
}

.news-hero-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.news-hero p,
.news-section-heading p {
  max-width: 760px;
  margin: 0;
  color: var(--news-text-muted);
  line-height: 1.68;
}

.news-hero-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.news-stat-card,
.news-source-metric,
.news-result-card {
  min-width: 0;
  border: 1px solid var(--news-border);
  border-radius: 8px;
  background: var(--news-panel-bg);
}

.news-stat-card {
  display: grid;
  align-content: center;
  gap: 8px;
  min-height: 118px;
  padding: 16px;
}

.news-stat-card span,
.news-source-metric span,
.news-result-card span,
.news-stat-card small,
.news-result-card small {
  color: var(--news-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.news-stat-card strong,
.news-source-metric strong,
.news-result-card strong {
  color: var(--news-text);
  font-size: 26px;
  line-height: 1.1;
}

.news-source-panel,
.news-control-panel,
.news-table-panel {
  border: 1px solid var(--news-border);
  border-radius: 8px;
  background: var(--news-panel-bg);
  background-color: var(--news-panel-bg);
  box-shadow: 0 12px 30px color-mix(in srgb, #000 10%, transparent);
}

.news-source-panel,
.news-control-panel {
  padding: 18px;
}

.news-section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.news-section-heading > div {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.news-section-heading h2 {
  font-size: 18px;
  line-height: 1.28;
}

.news-section-heading-tools {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.news-section-heading--compact h2 {
  font-size: 16px;
}

.news-icon-command {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--news-border-strong);
  border-radius: 8px;
  color: var(--news-text);
  background: var(--news-panel-strong);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.news-quick-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.news-refresh-interval {
  width: 176px;
}

.news-source-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.news-source-metric {
  display: flex;
  min-height: 76px;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  padding: 12px;
}

.news-source-metric strong {
  font-size: 18px;
}

.news-workbench {
  display: grid;
  gap: 16px;
}

.news-direct-tools-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.news-control-panel--analysis {
  grid-column: 1 / -1;
}

.news-article-content {
  min-height: 120px;
  color: var(--text-color-primary);
}

.news-article-content p {
  margin: 0;
  line-height: 1.8;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.news-analysis-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 16px;
}

.news-analysis-toolbar .el-input {
  min-width: 280px;
  flex: 1;
}

.news-primary-input {
  max-width: 660px;
}

.news-import-row,
.news-filter-grid {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.news-import-row {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
}

.news-filter-grid {
  grid-template-columns: minmax(160px, 0.75fr) minmax(0, 1fr) minmax(0, 1fr) auto;
}

.news-result-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.news-result-card {
  display: grid;
  gap: 6px;
  padding: 14px;
}

.news-result-card strong {
  font-size: 18px;
}

.news-result-grid--single {
  grid-template-columns: minmax(0, 1fr);
}

.news-dialog-workflow {
  display: grid;
  gap: 16px;
}

.news-dialog-workflow > p {
  margin: 0;
  color: var(--news-text-muted);
  font-size: 13px;
  line-height: 1.65;
}

.news-dialog-workflow .news-analysis-toolbar,
.news-dialog-workflow .news-import-row,
.news-dialog-workflow .news-filter-grid {
  margin-top: 0;
}

.news-configured-source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.news-source-config {
  display: grid;
  gap: 14px;
}

.news-source-config-main,
.news-source-form,
.news-source-actions,
.news-preset-list {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.news-source-config-main .el-select {
  min-width: 260px;
}

.news-source-form .el-input {
  min-width: 220px;
  flex: 1;
}

.news-source-actions {
  justify-content: flex-end;
}

.news-preset-list {
  margin-top: 4px;
}

.news-selected-sources {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.news-selected-sources-label {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.news-selected-source {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 3px 8px;
  border: 1px solid var(--news-border);
  border-radius: 6px;
  color: var(--news-text);
  background: var(--news-panel-bg);
}

.news-preset-item {
  display: inline-flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid var(--news-border);
  border-radius: 8px;
  color: var(--news-text);
  font: inherit;
  text-align: left;
  background: var(--news-panel-bg);
  cursor: pointer;
}

.news-preset-item small {
  color: var(--text-color-secondary);
}

.news-preset-item.is-selected {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary) 12%, var(--bg-color));
}

.news-table-panel {
  overflow: hidden;
}

.news-table-panel > .news-section-heading {
  padding: 18px 18px 14px;
  border-bottom: 1px solid var(--news-border);
}

.news-table-actions {
  display: flex;
  flex: 0 1 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.news-hero-actions {
  justify-content: flex-start;
  margin-top: 4px;
}

.news-desk-command {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid var(--news-border);
  border-radius: 7px;
  color: var(--news-text);
  background: var(--news-panel-bg);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease;
}

.news-desk-command:hover,
.news-desk-command:focus-visible {
  border-color: var(--news-border-strong);
  color: var(--news-accent);
  background: var(--news-panel-strong);
  outline: 0;
}

.news-table-count {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--news-border);
  border-radius: 999px;
  color: var(--news-text-muted);
  background: var(--news-panel-strong);
  font-size: 12px;
}

.news-empty {
  display: grid;
  justify-items: center;
  gap: 8px;
  margin: 18px;
  padding: 36px 18px;
  border: 1px dashed var(--news-border-strong);
  border-radius: 8px;
  color: var(--news-text-muted);
  text-align: center;
  background: color-mix(in srgb, var(--bg-color-page) 68%, var(--bg-color) 32%);
}

.news-empty strong {
  color: var(--news-text);
}

.news-empty p {
  max-width: 520px;
  margin: 0;
  line-height: 1.6;
}

.news-empty-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border: 1px solid var(--news-border);
  border-radius: 8px;
  color: var(--news-accent);
  background: var(--news-panel-bg);
}

.news-table {
  --el-table-bg-color: var(--news-panel-bg);
  --el-table-tr-bg-color: var(--news-panel-bg);
  --el-table-header-bg-color: color-mix(in srgb, var(--bg-color-page) 62%, var(--bg-color) 38%);
  --el-table-text-color: var(--news-text);
  --el-table-header-text-color: var(--news-text);
  --el-table-border-color: var(--news-border);
}

.news-headline-cell {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.news-headline-cell strong {
  color: var(--news-text);
  font-size: 13px;
  line-height: 1.45;
}

.news-headline-cell span {
  overflow: hidden;
  color: var(--news-text-muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.news-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 26px;
  min-width: 78px;
  padding: 0 9px;
  border: 1px solid var(--news-border);
  border-radius: 999px;
  color: var(--news-text);
  background: var(--news-panel-strong);
  font-size: 12px;
  font-weight: 700;
}

.news-pill--bullish,
.news-pill--low {
  border-color: color-mix(in srgb, var(--news-good) 55%, transparent);
  color: var(--news-good);
  background: color-mix(in srgb, var(--news-good) 12%, var(--bg-color));
}

.news-pill--bearish,
.news-pill--high {
  border-color: color-mix(in srgb, var(--news-bad) 55%, transparent);
  color: var(--news-bad);
  background: color-mix(in srgb, var(--news-bad) 12%, var(--bg-color));
}

.news-pill--neutral,
.news-pill--medium {
  border-color: color-mix(in srgb, var(--news-warn) 55%, transparent);
  color: var(--news-warn);
  background: color-mix(in srgb, var(--news-warn) 12%, var(--bg-color));
}

.news-cluster-code {
  display: inline-flex;
  max-width: 100%;
  padding: 4px 7px;
  border: 1px solid var(--news-border);
  border-radius: 6px;
  color: var(--news-text-muted);
  background: color-mix(in srgb, var(--bg-color-page) 72%, var(--bg-color) 28%);
  font-size: 12px;
}

:global(.news-source-config-dialog.el-dialog) {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

:global(.news-source-config-dialog.el-dialog .el-dialog__title) {
  color: var(--text-color-primary);
}

:global(.news-source-config-dialog.el-dialog .el-dialog__body) {
  color: var(--text-color-primary);
}

:global(.news-workflow-dialog.el-dialog) {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

:global(.news-workflow-dialog.el-dialog .el-dialog__title),
:global(.news-workflow-dialog.el-dialog .el-dialog__body) {
  color: var(--text-color-primary);
}

:global(.news-article-content-dialog.el-dialog) {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

@media (max-width: 1120px) {
  .news-hero {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .news-intel-page {
    gap: 14px;
  }

  .news-hero,
  .news-source-panel,
  .news-control-panel {
    padding: 16px;
  }

  .news-hero-stats,
  .news-source-metrics,
  .news-direct-tools-grid,
  .news-result-grid,
  .news-import-row,
  .news-filter-grid {
    grid-template-columns: 1fr;
  }

  .news-section-heading {
    flex-direction: column;
  }

  .news-hero-title-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .news-table-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .news-section-heading-tools {
    width: 100%;
    justify-content: flex-start;
  }

  .news-desk-command {
    flex: 1 1 calc(50% - 4px);
  }

  .news-icon-command,
  .news-quick-actions,
  .news-analysis-toolbar .el-button,
  .news-import-row .el-button,
  .news-filter-grid .el-button {
    width: 100%;
  }

  .news-analysis-toolbar .el-input,
  .news-refresh-interval,
  .news-source-form .el-input,
  .news-source-config-main .el-select {
    min-width: 0;
    width: 100%;
  }
}

</style>
