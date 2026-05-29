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
      <div class="flex gap-3 flex-wrap items-center mb-4">
        <el-input
          v-model="sourceName"
          :placeholder="t('newsIntel.sourceNamePh')"
          class="max-w-xs"
        />
        <el-input
          v-model="sourceUrl"
          :placeholder="t('newsIntel.sourceUrlPh')"
          class="max-w-md"
        />
        <el-button
          type="primary"
          :loading="loading"
          @click="createSource"
        >
          {{ t('newsIntel.btnAddSource') }}
        </el-button>
        <el-button
          :loading="loading"
          @click="pullSource"
        >
          {{ t('newsIntel.btnPullRss') }}
        </el-button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-5 gap-3 mb-4">
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
      <div class="flex gap-3 flex-wrap items-center mb-4">
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
      <el-table :data="articles">
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
              @click="expandCluster(String(scope.row.cluster_id || ''))"
            >
              {{ t('newsIntel.btnExpandCluster') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div
        v-if="selectedClusterId"
        class="mt-4"
      >
        <div class="font-medium mb-2">
          {{ t('newsIntel.clusterExpand', { id: selectedClusterId }) }}
        </div>
        <el-table :data="clusterArticles">
          <el-table-column
            prop="headline"
            :label="t('newsIntel.colHeadline')"
          />
          <el-table-column
            prop="source"
            :label="t('newsIntel.colSource')"
          />
          <el-table-column
            prop="sentiment"
            :label="t('newsIntel.colSentiment')"
          />
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { marketIntelApi, type NewsArticleItem } from '@/api/marketIntel'

const { t } = useI18n()

const loading = ref(false)
const articles = ref<NewsArticleItem[]>([])
const clusterArticles = ref<NewsArticleItem[]>([])
const sourceName = ref('terminal-rss')
const sourceUrl = ref('https://example.com/rss')
const headline = ref('RB2510 surges after bullish demand shock')
const url = ref('https://example.com/news/rb2510')
const analysisHeadline = ref('Unclear macro policy update')
const analysisResult = ref<Record<string, unknown> | null>(null)
const pullResult = ref<Record<string, unknown> | null>(null)
const filterSentiment = ref('')
const filterTicker = ref('')
const filterClusterId = ref('')
const selectedClusterId = ref('')

async function createSource() {
  loading.value = true
  try {
    await marketIntelApi.createNewsSource({ name: sourceName.value, url: sourceUrl.value, tier: 2 })
  } finally {
    loading.value = false
  }
}

async function pullSource() {
  loading.value = true
  try {
    pullResult.value = await marketIntelApi.pullNewsSource(sourceName.value)
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
  if (selectedClusterId.value) {
    const clusterResponse = await marketIntelApi.listArticles({ cluster_id: selectedClusterId.value })
    clusterArticles.value = clusterResponse.items
  }
}

async function expandCluster(clusterId: string) {
  if (!clusterId) return
  selectedClusterId.value = clusterId
  const response = await marketIntelApi.listArticles({ cluster_id: clusterId })
  clusterArticles.value = response.items
}

void loadArticles()
</script>
