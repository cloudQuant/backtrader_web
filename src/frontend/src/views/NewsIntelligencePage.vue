<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-2xl font-bold">
        {{ t('newsIntel.title') }}
      </h2>
      <p class="text-sm text-gray-500 mt-1">
        {{ t('newsIntel.desc') }}
      </p>
    </div>

    <el-card>
      <el-dialog
        v-if="sourceConfigVisible"
        v-model="sourceConfigVisible"
        :title="t('newsIntel.btnConfigureSource')"
        width="720px"
        class="news-source-config-dialog"
      >
        <div
          class="news-source-config"
        >
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

      <div class="news-analysis-toolbar">
        <el-input
          v-model="analysisHeadline"
          :placeholder="t('newsIntel.analysisPh')"
          class="max-w-xl"
        />
        <el-button
          :loading="loading"
          @click="analyzeHeadline"
        >
          {{ t('newsIntel.btnAnalyze') }}
        </el-button>
        <el-button
          :loading="loading"
          @click="loadArticles"
        >
          {{ t('newsIntel.btnRefreshList') }}
        </el-button>
        <el-button
          type="primary"
          :loading="loading"
          @click="pullSource"
        >
          {{ t('newsIntel.btnPullRss') }}
        </el-button>
        <el-button @click="toggleSourceConfig">
          {{ t('newsIntel.btnConfigureSource') }}
        </el-button>
      </div>
      <div class="news-import-row grid grid-cols-1 md:grid-cols-5 gap-3 mb-4">
        <el-input
          v-model="headline"
          :placeholder="t('newsIntel.headlinePh')"
          class="md:col-span-2"
        />
        <el-input
          v-model="url"
          :placeholder="t('newsIntel.urlPh')"
          class="md:col-span-2"
        />
        <el-button
          :loading="loading"
          @click="ingest"
        >
          {{ t('newsIntel.btnIngest') }}
        </el-button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
        <el-select
          v-model="filterSentiment"
          clearable
          :placeholder="t('newsIntel.sentimentPh')"
        >
          <el-option
            label="BULLISH"
            value="BULLISH"
          />
          <el-option
            label="BEARISH"
            value="BEARISH"
          />
          <el-option
            label="NEUTRAL"
            value="NEUTRAL"
          />
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
          :loading="loading"
          @click="loadArticles"
        >
          {{ t('newsIntel.btnApplyFilter') }}
        </el-button>
      </div>
      <div
        v-if="pullResult"
        class="text-sm text-gray-500 mb-4"
      >
        {{ t('newsIntel.pullResultTpl', { status: pullResult.status, fetched: pullResult.fetched_count, inserted: pullResult.inserted_count }) }}
      </div>
      <div
        v-if="analysisResult"
        class="text-sm text-gray-500 mb-4"
      >
        {{ t('newsIntel.analysisResultTpl', { sentiment: analysisResult.sentiment, impact: analysisResult.impact, status: analysisResult.status }) }}
      </div>
      <div
        v-if="articles.length === 0"
        class="news-empty"
      >
        {{ t('newsIntel.emptyArticles') }}
      </div>
      <el-table
        v-else
        :data="articles"
        :empty-text="t('newsIntel.emptyArticles')"
      >
        <el-table-column
          prop="headline"
          :label="t('newsIntel.colHeadline')"
        />
        <el-table-column
          prop="sentiment"
          :label="t('newsIntel.colSentiment')"
        />
        <el-table-column
          prop="impact"
          :label="t('newsIntel.colImpact')"
        />
        <el-table-column
          prop="cluster_id"
          :label="t('newsIntel.colCluster')"
        />
        <el-table-column
          :label="t('newsIntel.colActions')"
          width="120"
        >
          <template #default="scope">
            <el-button
              link
              type="primary"
              :disabled="!scope.row.url"
              @click="openArticle(scope.row)"
            >
              {{ t('newsIntel.btnOpenArticle') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
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
    url: 'https://feeds.bloomberg.com/markets/news.rss',
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
const loading = ref(false)
const articles = ref<NewsArticleItem[]>([])
const sourceConfigVisible = ref(false)
const selectedFeedPresetIds = ref<string[]>([defaultFeedPreset.id])
const configuredSources = ref<NewsFeedPreset[]>([defaultFeedPreset])
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

const selectedFeedPresets = computed(() => {
  const selected = newsFeedPresets.filter((preset) => selectedFeedPresetIds.value.includes(preset.id))
  return selected.length ? selected : [defaultFeedPreset]
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

async function pullSource() {
  loading.value = true
  try {
    const sources = await saveConfiguredSources()
    const results: Array<Record<string, unknown>> = []
    for (const source of sources) {
      results.push(await marketIntelApi.pullNewsSource(source.name))
    }
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

function openArticle(article: NewsArticleItem) {
  const articleUrl = String(article.url || '').trim()
  if (!articleUrl) return
  window.open(articleUrl, '_blank', 'noopener,noreferrer')
}

void loadArticles()
</script>

<style scoped>
.news-analysis-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.news-analysis-toolbar .el-input {
  min-width: 280px;
  flex: 1;
}

.news-source-config {
  display: grid;
  gap: 12px;
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
  border: 1px solid var(--border-color-light);
  border-radius: 6px;
  color: var(--text-color-regular);
  background: var(--bg-color-card);
}

.news-preset-item {
  display: inline-flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  font: inherit;
  text-align: left;
  background: var(--bg-color-card);
  cursor: pointer;
}

.news-preset-item small {
  color: var(--text-color-secondary);
}

.news-preset-item.is-selected {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.news-empty {
  margin: 12px 0;
  padding: 24px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  color: var(--text-color-secondary);
  text-align: center;
  background: var(--bg-color-page);
}

</style>
