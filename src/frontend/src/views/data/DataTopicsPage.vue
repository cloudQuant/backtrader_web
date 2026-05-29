<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h2 class="text-2xl font-bold">
          {{ t('dataPages.topicsTitle') }}
        </h2>
        <p class="text-sm text-gray-500 mt-1">
          {{ t('dataPages.topicsDesc') }}
        </p>
      </div>
      <div class="flex items-center gap-2 flex-wrap">
        <el-button
          :loading="loading"
          @click="loadData"
        >
          {{ t('dataPages.topicsRefreshList') }}
        </el-button>
        <el-button
          type="primary"
          :disabled="!selectedTopic"
          :loading="refreshing"
          @click="refreshSelectedTopic"
        >
          {{ t('dataPages.topicsRefreshTopic') }}
        </el-button>
      </div>
    </div>

    <el-card>
      <template #header>
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <span class="font-bold">{{ t('dataPages.topicsRealtimeSub') }}</span>
          <div class="flex items-center gap-2 flex-wrap">
            <el-input
              v-model="topicPattern"
              placeholder="market:quote:*"
              style="width: 220px"
            />
            <el-button
              v-if="!wsConnected"
              type="success"
              @click="connectStream"
            >
              {{ t('dataPages.topicsConnectWs') }}
            </el-button>
            <el-button
              v-else
              type="warning"
              @click="disconnectStream"
            >
              {{ t('dataPages.topicsDisconnectWs') }}
            </el-button>
          </div>
        </div>
      </template>
      <div class="grid gap-3 md:grid-cols-4">
        <el-statistic
          :title="t('dataPages.topicsConnState')"
          :value="wsConnected ? 'connected' : 'idle'"
        />
        <el-statistic
          :title="t('dataPages.topicsTotal')"
          :value="stats?.total_topics ?? topics.length"
        />
        <el-statistic
          :title="t('dataPages.topicsActiveCache')"
          :value="stats?.topics_with_value ?? 0"
        />
        <el-statistic
          :title="t('dataPages.topicsErrorCount')"
          :value="stats?.error_count ?? 0"
        />
      </div>
      <div class="mt-3 text-xs text-gray-500 break-all">
        {{ currentStreamUrl }}
      </div>
    </el-card>

    <el-card>
      <template #header>
        <div class="font-bold">
          {{ t('dataPages.topicsList') }}
        </div>
      </template>
      <div class="topic-tags">
        <el-tag
          v-for="item in topics"
          :key="item.topic"
          class="cursor-pointer"
          :type="selectedTopic === item.topic ? 'success' : 'info'"
          @click="selectTopic(item.topic)"
        >
          {{ item.topic }}
        </el-tag>
      </div>
      <el-table
        :data="topics"
        class="mt-4"
      >
        <el-table-column
          prop="topic"
          :label="t('dataPages.topicsColTopic')"
        />
        <el-table-column
          prop="subscription_count"
          :label="t('dataPages.topicsColSubs')"
        />
        <el-table-column
          prop="has_value"
          :label="t('dataPages.topicsColHasValue')"
        />
      </el-table>
    </el-card>

    <el-card>
      <template #header>
        <div class="font-bold">
          {{ t('dataPages.topicsCurrent') }}
        </div>
      </template>
      <div class="space-y-2 text-sm">
        <div>
          <strong>Selected:</strong> {{ selectedTopic || t('dataPages.topicsNotSelected') }}
        </div>
        <div>
          <strong>Last Refresh Value:</strong>
        </div>
        <pre class="preview-box">{{ latestValueText }}</pre>
        <div>
          <strong>Live Events:</strong>
        </div>
        <pre class="preview-box">{{ liveEventsText }}</pre>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { dataTopicsApi, type DataTopicItem, type DataTopicStats } from '@/api/dataTopics'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const authStore = useAuthStore()
const loading = ref(false)
const refreshing = ref(false)
const topics = ref<DataTopicItem[]>([])
const stats = ref<DataTopicStats | null>(null)
const selectedTopic = ref('')
const latestValue = ref<unknown>(null)
const topicPattern = ref('market:quote:*')
const wsConnected = ref(false)
const liveEvents = ref<Array<Record<string, unknown>>>([])
let socket: WebSocket | null = null

const isAdmin = computed(() => authStore.user?.is_admin ?? false)
const latestValueText = computed(() => JSON.stringify(latestValue.value, null, 2))
const liveEventsText = computed(() => JSON.stringify(liveEvents.value, null, 2))
const currentStreamUrl = computed(() => {
  if (selectedTopic.value) {
    return dataTopicsApi.buildTopicStreamUrl(selectedTopic.value)
  }
  return dataTopicsApi.buildPatternStreamUrl(topicPattern.value)
})

function selectTopic(topic: string) {
  selectedTopic.value = topic
}

async function loadData() {
  loading.value = true
  try {
    const response = await dataTopicsApi.listTopics()
    topics.value = response.items
    if (!selectedTopic.value && response.items.length > 0) {
      selectedTopic.value = response.items[0].topic
    }
    if (isAdmin.value) {
      stats.value = await dataTopicsApi.getStats()
    } else {
      stats.value = null
    }
  } finally {
    loading.value = false
  }
}

async function refreshSelectedTopic() {
  if (!selectedTopic.value) {
    return
  }
  refreshing.value = true
  try {
    const response = await dataTopicsApi.refreshTopic(selectedTopic.value)
    latestValue.value = response.value
    await loadData()
  } finally {
    refreshing.value = false
  }
}

function disconnectStream() {
  socket?.close()
  socket = null
  wsConnected.value = false
}

function connectStream() {
  disconnectStream()
  if (typeof window === 'undefined') {
    return
  }
  const protocols = dataTopicsApi.getWebSocketProtocols()
  if (protocols.length === 0) {
    return
  }
  const url = selectedTopic.value
    ? dataTopicsApi.buildTopicStreamUrl(selectedTopic.value)
    : dataTopicsApi.buildPatternStreamUrl(topicPattern.value)
  socket = new window.WebSocket(url, protocols)
  socket.onopen = () => {
    wsConnected.value = true
  }
  socket.onmessage = (event: MessageEvent) => {
    try {
      const payload = JSON.parse(String(event.data)) as Record<string, unknown>
      liveEvents.value = [payload, ...liveEvents.value].slice(0, 10)
      if (payload.type === 'topic_update' || payload.type === 'snapshot') {
        latestValue.value = payload.value
      }
    } catch {
      liveEvents.value = [{ type: 'raw', data: String(event.data) }, ...liveEvents.value].slice(0, 10)
    }
  }
  socket.onclose = () => {
    wsConnected.value = false
    socket = null
  }
  socket.onerror = () => {
    wsConnected.value = false
  }
}

onMounted(() => {
  void loadData()
})

onBeforeUnmount(() => {
  disconnectStream()
})
</script>

<style scoped>
.topic-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.preview-box {
  margin: 0;
  padding: 12px;
  border-radius: 12px;
  background: var(--code-bg-color);
  color: var(--code-text-color);
  overflow: auto;
  min-height: 80px;
}
</style>
