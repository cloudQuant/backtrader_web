<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-2xl font-bold">新闻情报</h2>
      <p class="text-sm text-gray-500 mt-1">聚合新闻、规则分类与实时主题分发入口。</p>
    </div>

    <el-card>
      <div class="flex gap-3 flex-wrap items-center mb-4">
        <el-input v-model="sourceName" placeholder="来源名称" class="max-w-xs" />
        <el-input v-model="sourceUrl" placeholder="来源 URL / RSS" class="max-w-md" />
        <el-button type="primary" :loading="loading" @click="createSource">新增来源</el-button>
        <el-button :loading="loading" @click="pullSource">拉取 RSS</el-button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-5 gap-3 mb-4">
        <el-input v-model="headline" placeholder="新闻标题" class="md:col-span-2" />
        <el-input v-model="url" placeholder="文章 URL" class="md:col-span-2" />
        <el-button :loading="loading" @click="ingest">导入文章</el-button>
      </div>
      <div class="flex gap-3 flex-wrap items-center mb-4">
        <el-input v-model="analysisHeadline" placeholder="分析标题情绪" class="max-w-xl" />
        <el-button :loading="loading" @click="analyzeHeadline">分析</el-button>
        <el-button :loading="loading" @click="loadArticles">刷新列表</el-button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
        <el-select v-model="filterSentiment" clearable placeholder="情绪过滤">
          <el-option label="BULLISH" value="BULLISH" />
          <el-option label="BEARISH" value="BEARISH" />
          <el-option label="NEUTRAL" value="NEUTRAL" />
        </el-select>
        <el-input v-model="filterTicker" placeholder="标的过滤，如 RB2510" />
        <el-input v-model="filterClusterId" placeholder="Cluster ID" />
        <el-button :loading="loading" @click="loadArticles">应用过滤</el-button>
      </div>
      <div v-if="pullResult" class="text-sm text-gray-500 mb-4">
        拉取结果：{{ pullResult.status }} / fetched={{ pullResult.fetched_count }} / inserted={{ pullResult.inserted_count }}
      </div>
      <div v-if="analysisResult" class="text-sm text-gray-500 mb-4">
        分析结果：{{ analysisResult.sentiment }} / {{ analysisResult.impact }} / {{ analysisResult.status }}
      </div>
      <el-table :data="articles">
        <el-table-column prop="headline" label="标题" />
        <el-table-column prop="sentiment" label="情绪" />
        <el-table-column prop="impact" label="影响" />
        <el-table-column prop="cluster_id" label="Cluster" />
        <el-table-column label="操作" width="120">
          <template #default="scope">
            <el-button link type="primary" @click="expandCluster(String(scope.row.cluster_id || ''))">展开同簇</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="selectedClusterId" class="mt-4">
        <div class="font-medium mb-2">Cluster 展开：{{ selectedClusterId }}</div>
        <el-table :data="clusterArticles">
          <el-table-column prop="headline" label="标题" />
          <el-table-column prop="source" label="来源" />
          <el-table-column prop="sentiment" label="情绪" />
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { marketIntelApi, type NewsArticleItem } from '@/api/marketIntel'

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
