<template>
  <div
    class="data-topics-page"
    data-test="data-topics-page"
  >
    <section class="topics-hero">
      <div class="topics-hero-copy">
        <span class="topics-eyebrow">{{ t('dataPages.topicsHeroKicker') }}</span>
        <h1>{{ t('dataPages.topicsTitle') }}</h1>
        <p>{{ t('dataPages.topicsDesc') }}</p>
      </div>

      <div class="topics-hero-actions">
        <el-button
          :loading="loading"
          @click="loadData"
        >
          <el-icon aria-hidden="true">
            <Refresh />
          </el-icon>
          {{ t('dataPages.topicsRefreshList') }}
        </el-button>
        <el-button
          type="primary"
          :disabled="!selectedTopic"
          :loading="refreshing"
          @click="refreshSelectedTopic"
        >
          <el-icon aria-hidden="true">
            <Refresh />
          </el-icon>
          {{ t('dataPages.topicsRefreshTopic') }}
        </el-button>
      </div>

      <div class="topics-hero-stats">
        <article
          v-for="stat in topicStats"
          :key="stat.key"
          class="topics-stat-card"
          :class="`topics-stat-card--${stat.tone}`"
        >
          <span>{{ stat.label }}</span>
          <strong>{{ stat.value }}</strong>
          <small>{{ stat.helper }}</small>
        </article>
      </div>
    </section>

    <section class="topics-stream-panel">
      <div class="topics-section-heading">
        <div>
          <span class="topics-section-kicker">{{ t('dataPages.topicsStreamKicker') }}</span>
          <h2>{{ t('dataPages.topicsStreamTitle') }}</h2>
          <p>{{ t('dataPages.topicsStreamDesc') }}</p>
        </div>
        <span
          class="topics-status-pill"
          :class="wsConnected ? 'topics-status-pill--success' : 'topics-status-pill--idle'"
        >
          {{ streamStateLabel }}
        </span>
      </div>

      <div class="topics-stream-toolbar">
        <el-input
          v-model="topicPattern"
          :placeholder="t('dataPages.topicsPatternPlaceholder')"
          class="topics-pattern-input"
        />
        <el-button
          :disabled="!selectedTopic"
          @click="clearSelectedTopic"
        >
          {{ t('dataPages.topicsUsePattern') }}
        </el-button>
        <el-button
          v-if="!wsConnected"
          type="success"
          @click="connectStream"
        >
          <el-icon aria-hidden="true">
            <Connection />
          </el-icon>
          {{ t('dataPages.topicsConnectWs') }}
        </el-button>
        <el-button
          v-else
          type="warning"
          @click="disconnectStream"
        >
          <el-icon aria-hidden="true">
            <VideoPause />
          </el-icon>
          {{ t('dataPages.topicsDisconnectWs') }}
        </el-button>
      </div>

      <div class="topics-stream-url">
        <span>{{ t('dataPages.topicsStreamUrlLabel') }}</span>
        <code>{{ currentStreamUrl }}</code>
      </div>

      <div class="topics-gateway-grid">
        <article class="topics-gateway-card">
          <span>{{ t('dataPages.topicsWsGateway') }}</span>
          <strong>{{ wsGatewayLabel }}</strong>
        </article>
        <article class="topics-gateway-card">
          <span>{{ t('dataPages.topicsWsConnections') }}</span>
          <strong>{{ stats?.ws_gateway?.connection_count ?? 0 }}</strong>
        </article>
        <article class="topics-gateway-card">
          <span>{{ t('dataPages.topicsWsSubscriptions') }}</span>
          <strong>{{ stats?.ws_gateway?.subscription_count ?? stats?.subscription_count ?? 0 }}</strong>
        </article>
      </div>
    </section>

    <section class="topics-directory-panel">
      <div class="topics-section-heading">
        <div>
          <span class="topics-section-kicker">{{ t('dataPages.topicsDirectoryKicker') }}</span>
          <h2>{{ t('dataPages.topicsDirectoryTitle') }}</h2>
          <p>{{ t('dataPages.topicsDirectoryDesc') }}</p>
        </div>
        <span class="topics-count-pill">
          {{ t('dataPages.topicsCountLabel', { n: topics.length }) }}
        </span>
      </div>

      <div
        v-if="!loading && topics.length === 0"
        class="topics-empty-state"
      >
        <span class="topics-empty-icon">
          <el-icon aria-hidden="true">
            <DataLine />
          </el-icon>
        </span>
        <strong>{{ t('dataPages.topicsEmptyTitle') }}</strong>
        <p>{{ t('dataPages.topicsEmptyDesc') }}</p>
      </div>

      <template v-else>
        <div class="topic-tags">
          <button
            v-for="item in topics"
            :key="item.topic"
            type="button"
            class="topic-tag"
            :class="{ 'topic-tag--active': selectedTopic === item.topic }"
            @click="selectTopic(item.topic)"
          >
            <span>{{ item.topic }}</span>
            <small>{{ item.subscription_count }}</small>
          </button>
        </div>

        <div class="topics-mobile-list">
          <article
            v-for="item in topics"
            :key="`mobile-${item.topic}`"
            class="topics-mobile-card"
          >
            <div class="topics-mobile-card-head">
              <strong>{{ item.topic }}</strong>
              <span
                class="topics-cache-pill"
                :class="item.has_value ? 'topics-cache-pill--yes' : 'topics-cache-pill--no'"
              >
                {{ item.has_value ? t('dataPages.topicsCacheYes') : t('dataPages.topicsCacheNo') }}
              </span>
            </div>
            <p>{{ policySummary(item.policy) }}</p>
            <dl>
              <div>
                <dt>{{ t('dataPages.topicsColSubs') }}</dt>
                <dd>{{ item.subscription_count }}</dd>
              </div>
              <div>
                <dt>{{ t('dataPages.topicsColUpdated') }}</dt>
                <dd>{{ formatUpdatedAt(item.updated_at_ms) }}</dd>
              </div>
              <div>
                <dt>{{ t('dataPages.topicsColError') }}</dt>
                <dd :class="{ 'topics-error-text--active': item.last_error }">
                  {{ formatTopicError(item.last_error) }}
                </dd>
              </div>
            </dl>
          </article>
        </div>

        <div class="topics-table-wrap">
          <el-table
            v-loading="loading"
            :data="topics"
            class="topics-data-grid"
            :empty-text="t('dataPages.topicsEmptyTitle')"
          >
            <el-table-column
              :label="t('dataPages.topicsColTopic')"
              min-width="260"
            >
              <template #default="{ row }">
                <div class="topics-topic-cell">
                  <strong>{{ row.topic }}</strong>
                  <span>{{ policySummary(row.policy) }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('dataPages.topicsColSubs')"
              width="130"
            >
              <template #default="{ row }">
                <span class="topics-number-pill">{{ row.subscription_count }}</span>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('dataPages.topicsColHasValue')"
              width="130"
            >
              <template #default="{ row }">
                <span
                  class="topics-cache-pill"
                  :class="row.has_value ? 'topics-cache-pill--yes' : 'topics-cache-pill--no'"
                >
                  {{ row.has_value ? t('dataPages.topicsCacheYes') : t('dataPages.topicsCacheNo') }}
                </span>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('dataPages.topicsColUpdated')"
              min-width="170"
            >
              <template #default="{ row }">
                {{ formatUpdatedAt(row.updated_at_ms) }}
              </template>
            </el-table-column>
            <el-table-column
              :label="t('dataPages.topicsColError')"
              min-width="200"
            >
              <template #default="{ row }">
                <span
                  class="topics-error-text"
                  :class="{ 'topics-error-text--active': row.last_error }"
                >
                  {{ formatTopicError(row.last_error) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </section>

    <section class="topics-inspector-panel">
      <div class="topics-section-heading">
        <div>
          <span class="topics-section-kicker">{{ t('dataPages.topicsInspectorKicker') }}</span>
          <h2>{{ t('dataPages.topicsInspectorTitle') }}</h2>
          <p>{{ t('dataPages.topicsInspectorDesc') }}</p>
        </div>
      </div>

      <div class="topics-inspector-grid">
        <article class="topics-selected-card">
          <span>{{ t('dataPages.topicsSelectedLabel') }}</span>
          <strong>{{ selectedTopic || t('dataPages.topicsNoTopicSelected') }}</strong>
          <small>{{ selectedTopicItem ? policySummary(selectedTopicItem.policy) : t('dataPages.topicsPolicyNone') }}</small>
        </article>

        <article class="topics-preview-card">
          <div class="topics-preview-heading">
            <span>{{ t('dataPages.topicsLastRefreshValue') }}</span>
            <span
              class="topics-cache-pill"
              :class="latestValue === null ? 'topics-cache-pill--no' : 'topics-cache-pill--yes'"
            >
              {{ latestValue === null ? t('dataPages.topicsCacheNo') : t('dataPages.topicsCacheYes') }}
            </span>
          </div>
          <pre class="preview-box">{{ latestValueText }}</pre>
        </article>

        <article class="topics-preview-card">
          <div class="topics-preview-heading">
            <span>{{ t('dataPages.topicsLiveEvents') }}</span>
            <span class="topics-number-pill">{{ liveEvents.length }}</span>
          </div>
          <pre class="preview-box">{{ liveEventsText }}</pre>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Connection, DataLine, Refresh, VideoPause } from '@element-plus/icons-vue'
import { dataTopicsApi, type DataTopicItem, type DataTopicPolicy, type DataTopicStats } from '@/api/dataTopics'
import { getErrorMessage } from '@/api/index'
import { useAuthStore } from '@/stores/auth'

type StatTone = 'primary' | 'success' | 'warning' | 'danger'

interface TopicStat {
  key: string
  label: string
  value: string | number
  helper: string
  tone: StatTone
}

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
const selectedTopicItem = computed(() => {
  return topics.value.find((item) => item.topic === selectedTopic.value) ?? null
})
const activeCacheCount = computed(() => topics.value.filter((topic) => topic.has_value).length)
const errorTopicCount = computed(() => topics.value.filter((topic) => topic.last_error).length)
const streamStateLabel = computed(() => (
  wsConnected.value ? t('dataPages.topicsConnected') : t('dataPages.topicsIdle')
))
const wsGatewayLabel = computed(() => (
  stats.value?.ws_gateway ? t('dataPages.topicsConnected') : t('dataPages.topicsWsGatewayUnavailable')
))
const latestValueText = computed(() => {
  if (latestValue.value === null || typeof latestValue.value === 'undefined') {
    return t('dataPages.topicsNoValue')
  }
  return JSON.stringify(latestValue.value, null, 2)
})
const liveEventsText = computed(() => {
  if (liveEvents.value.length === 0) {
    return t('dataPages.topicsNoEvents')
  }
  return JSON.stringify(liveEvents.value, null, 2)
})
const currentStreamUrl = computed(() => {
  if (selectedTopic.value) {
    return dataTopicsApi.buildTopicStreamUrl(selectedTopic.value)
  }
  return dataTopicsApi.buildPatternStreamUrl(topicPattern.value)
})
const topicStats = computed<TopicStat[]>(() => [
  {
    key: 'connection',
    label: t('dataPages.topicsConnState'),
    value: streamStateLabel.value,
    helper: t('dataPages.topicsStatConnHelper'),
    tone: wsConnected.value ? 'success' : 'primary',
  },
  {
    key: 'total',
    label: t('dataPages.topicsTotal'),
    value: stats.value?.total_topics ?? topics.value.length,
    helper: t('dataPages.topicsStatTotalHelper'),
    tone: 'primary',
  },
  {
    key: 'cache',
    label: t('dataPages.topicsActiveCache'),
    value: stats.value?.topics_with_value ?? activeCacheCount.value,
    helper: t('dataPages.topicsStatCacheHelper'),
    tone: 'success',
  },
  {
    key: 'errors',
    label: t('dataPages.topicsErrorCount'),
    value: stats.value?.error_count ?? errorTopicCount.value,
    helper: t('dataPages.topicsStatErrorHelper'),
    tone: errorTopicCount.value > 0 ? 'danger' : 'warning',
  },
])

function selectTopic(topic: string) {
  selectedTopic.value = topic
}

function clearSelectedTopic() {
  selectedTopic.value = ''
}

async function loadData() {
  loading.value = true
  try {
    const response = await dataTopicsApi.listTopics()
    topics.value = response.items
    if (!selectedTopic.value && response.items.length > 0) {
      selectedTopic.value = response.items[0].topic
    }
    if (selectedTopic.value && !response.items.some((item) => item.topic === selectedTopic.value)) {
      selectedTopic.value = response.items[0]?.topic ?? ''
    }
    if (isAdmin.value) {
      stats.value = await dataTopicsApi.getStats()
    } else {
      stats.value = null
    }
  } catch (error) {
    const fallback = t('dataPages.topicsLoadFailed')
    ElMessage.error(`${fallback}: ${getErrorMessage(error, fallback)}`)
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
  } catch (error) {
    const fallback = t('dataPages.topicsRefreshFailed')
    ElMessage.error(`${fallback}: ${getErrorMessage(error, fallback)}`)
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
    ElMessage.error(t('dataPages.topicsTokenMissing'))
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

function formatDuration(ms?: number): string | null {
  if (typeof ms !== 'number' || Number.isNaN(ms)) return null
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`
  return `${Math.round(ms / 60_000)}min`
}

function policySummary(policy: DataTopicPolicy | null | undefined): string {
  if (!policy) return t('dataPages.topicsPolicyNone')
  const parts: string[] = []
  if (policy.push_only) parts.push(t('dataPages.topicsPolicyPushOnly'))
  const ttl = formatDuration(policy.ttl_ms)
  if (ttl) parts.push(t('dataPages.topicsPolicyTtl', { value: ttl }))
  const minInterval = formatDuration(policy.min_interval_ms)
  if (minInterval) parts.push(t('dataPages.topicsPolicyMinInterval', { value: minInterval }))
  const coalesce = formatDuration(policy.coalesce_within_ms)
  if (coalesce) parts.push(t('dataPages.topicsPolicyCoalesce', { value: coalesce }))
  if (policy.drop_on_idle) parts.push(t('dataPages.topicsPolicyDropIdle'))
  if (policy.pause_when_inactive) parts.push(t('dataPages.topicsPolicyPauseInactive'))
  return parts.slice(0, 3).join(' · ') || t('dataPages.topicsPolicyNone')
}

function formatUpdatedAt(updatedAtMs: number | null): string {
  if (!updatedAtMs) return t('dataPages.topicsNeverUpdated')
  const date = new Date(updatedAtMs)
  if (Number.isNaN(date.getTime())) return t('dataPages.topicsNeverUpdated')
  return date.toLocaleString()
}

function formatTopicError(error: Record<string, unknown> | null): string {
  if (!error) return t('dataPages.topicsNoError')
  return JSON.stringify(error)
}

onMounted(() => {
  void loadData()
})

onBeforeUnmount(() => {
  disconnectStream()
})
</script>

<style scoped>
.data-topics-page {
  --topics-surface: var(--bg-color);
  --topics-surface-soft: var(--fill-color-lighter);
  --topics-surface-muted: var(--fill-color-light);
  --topics-border: var(--border-color-light);
  --topics-border-strong: var(--border-color);
  --topics-text: var(--text-color-primary);
  --topics-muted: var(--text-color-secondary);
  --topics-accent: var(--primary-color);
  --topics-success: var(--success-color);
  --topics-warning: var(--warning-color);
  --topics-danger: var(--danger-color);

  display: grid;
  gap: 18px;
  color: var(--topics-text);
}

.topics-hero,
.topics-stream-panel,
.topics-directory-panel,
.topics-inspector-panel {
  border: 1px solid var(--topics-border);
  border-radius: 8px;
  background: var(--topics-surface);
  box-shadow: var(--box-shadow-light);
}

.topics-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 22px;
  align-items: start;
  min-height: 250px;
  padding: 34px;
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--topics-accent) 10%, transparent), transparent 44%),
    var(--topics-surface);
}

.topics-hero-copy {
  display: grid;
  gap: 10px;
  align-self: center;
  min-width: 0;
}

.topics-eyebrow,
.topics-section-kicker {
  color: var(--topics-accent);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  text-transform: uppercase;
}

.topics-hero h1,
.topics-section-heading h2 {
  margin: 0;
  color: var(--topics-text);
  line-height: 1.16;
}

.topics-hero h1 {
  font-size: clamp(32px, 4vw, 48px);
  font-weight: 780;
}

.topics-hero p,
.topics-section-heading p {
  margin: 0;
  color: var(--topics-muted);
  line-height: 1.7;
}

.topics-hero p {
  max-width: 680px;
  font-size: 15px;
}

.topics-hero-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.topics-hero-actions :deep(.el-button),
.topics-stream-toolbar :deep(.el-button) {
  gap: 6px;
}

.topics-hero-actions :deep(.el-button .el-icon),
.topics-stream-toolbar :deep(.el-button .el-icon) {
  margin-right: 4px;
}

.topics-hero-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
  gap: 12px;
  grid-column: 1 / -1;
}

.topics-stat-card {
  display: grid;
  gap: 8px;
  min-width: 0;
  min-height: 118px;
  padding: 17px;
  border: 1px solid var(--topics-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--topics-surface-soft) 78%, transparent);
}

.topics-stat-card span,
.topics-gateway-card span,
.topics-selected-card span {
  color: var(--topics-muted);
  font-size: 12px;
  font-weight: 650;
}

.topics-stat-card strong,
.topics-gateway-card strong,
.topics-selected-card strong {
  overflow-wrap: anywhere;
  color: var(--topics-text);
  font-size: 24px;
  line-height: 1.15;
}

.topics-stat-card small,
.topics-selected-card small {
  color: var(--topics-muted);
  line-height: 1.45;
}

.topics-stat-card--success {
  border-color: color-mix(in srgb, var(--topics-success) 42%, var(--topics-border));
}

.topics-stat-card--warning {
  border-color: color-mix(in srgb, var(--topics-warning) 34%, var(--topics-border));
}

.topics-stat-card--danger {
  border-color: color-mix(in srgb, var(--topics-danger) 42%, var(--topics-border));
}

.topics-stream-panel,
.topics-directory-panel,
.topics-inspector-panel {
  display: grid;
  gap: 18px;
  padding: 24px;
}

.topics-section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
}

.topics-section-heading > div {
  display: grid;
  gap: 7px;
  min-width: 0;
}

.topics-section-heading h2 {
  font-size: 20px;
  font-weight: 760;
}

.topics-status-pill,
.topics-count-pill,
.topics-number-pill,
.topics-cache-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  max-width: 100%;
  min-height: 26px;
  padding: 4px 10px;
  border: 1px solid var(--topics-border);
  border-radius: 999px;
  background: var(--topics-surface-soft);
  color: var(--topics-muted);
  font-size: 12px;
  font-weight: 760;
  line-height: 1.2;
  white-space: nowrap;
}

.topics-status-pill--success,
.topics-cache-pill--yes {
  border-color: color-mix(in srgb, var(--topics-success) 58%, transparent);
  background: color-mix(in srgb, var(--topics-success) 12%, transparent);
  color: var(--topics-success);
}

.topics-status-pill--idle,
.topics-cache-pill--no {
  border-color: var(--topics-border);
  background: var(--topics-surface-soft);
  color: var(--topics-muted);
}

.topics-stream-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.topics-pattern-input {
  width: min(100%, 320px);
}

.topics-stream-url {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 13px 14px;
  border: 1px solid var(--topics-border);
  border-radius: 8px;
  background: var(--topics-surface-soft);
}

.topics-stream-url span {
  color: var(--topics-muted);
  font-size: 12px;
  font-weight: 700;
}

.topics-stream-url code {
  overflow-wrap: anywhere;
  color: var(--topics-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
}

.topics-gateway-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.topics-gateway-card {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 15px;
  border: 1px solid var(--topics-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--topics-surface-soft) 82%, transparent);
}

.topic-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.topic-tag {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  min-height: 34px;
  padding: 7px 10px;
  border: 1px solid var(--topics-border);
  border-radius: 8px;
  background: var(--topics-surface-soft);
  color: var(--topics-text);
  cursor: pointer;
  font: inherit;
  text-align: left;
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease,
    color 0.16s ease;
}

.topic-tag:hover,
.topic-tag:focus-visible,
.topic-tag--active {
  border-color: color-mix(in srgb, var(--topics-accent) 54%, transparent);
  background: color-mix(in srgb, var(--topics-accent) 12%, transparent);
  color: var(--topics-accent);
}

.topic-tag:focus-visible {
  outline: 2px solid var(--topics-accent);
  outline-offset: 2px;
}

.topic-tag span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topic-tag small {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  border-radius: 999px;
  background: var(--topics-surface);
  color: inherit;
  font-size: 11px;
  font-weight: 760;
  flex: none;
}

.topics-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--topics-border);
  border-radius: 8px;
  background: var(--topics-surface);
}

.topics-mobile-list {
  display: none;
  gap: 10px;
}

.topics-mobile-card {
  display: grid;
  gap: 9px;
  min-width: 0;
  padding: 13px;
  border: 1px solid var(--topics-border);
  border-radius: 8px;
  background: var(--topics-surface-soft);
}

.topics-mobile-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
}

.topics-mobile-card-head strong {
  overflow-wrap: anywhere;
  color: var(--topics-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.45;
}

.topics-mobile-card p {
  margin: 0;
  color: var(--topics-muted);
  font-size: 12px;
  line-height: 1.5;
}

.topics-mobile-card dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.topics-mobile-card dl > div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.topics-mobile-card dt {
  color: var(--topics-muted);
  font-size: 11px;
  font-weight: 700;
}

.topics-mobile-card dd {
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--topics-text);
  font-size: 12px;
  line-height: 1.45;
}

.topics-data-grid {
  width: 100%;
  min-width: 850px;
}

.topics-topic-cell {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.topics-topic-cell strong {
  overflow-wrap: anywhere;
  color: var(--topics-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
}

.topics-topic-cell span,
.topics-error-text {
  overflow-wrap: anywhere;
  color: var(--topics-muted);
  font-size: 12px;
}

.topics-error-text--active {
  color: var(--topics-danger);
}

.topics-empty-state {
  display: grid;
  justify-items: center;
  gap: 10px;
  padding: 40px 20px;
  border: 1px dashed var(--topics-border);
  border-radius: 8px;
  background: var(--topics-surface-soft);
  text-align: center;
}

.topics-empty-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--topics-accent) 12%, transparent);
  color: var(--topics-accent);
  font-size: 22px;
}

.topics-empty-state strong {
  color: var(--topics-text);
  font-size: 16px;
}

.topics-empty-state p {
  max-width: 520px;
  margin: 0;
  color: var(--topics-muted);
  line-height: 1.6;
}

.topics-inspector-grid {
  display: grid;
  grid-template-columns: minmax(220px, 0.72fr) minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
}

.topics-selected-card,
.topics-preview-card {
  display: grid;
  align-content: start;
  gap: 10px;
  min-width: 0;
  min-height: 190px;
  padding: 16px;
  border: 1px solid var(--topics-border);
  border-radius: 8px;
  background: var(--topics-surface-soft);
}

.topics-selected-card strong {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 15px;
}

.topics-preview-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--topics-text);
  font-size: 13px;
  font-weight: 760;
}

.preview-box {
  min-height: 138px;
  max-height: 320px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border: 1px solid var(--topics-border);
  border-radius: 8px;
  background: var(--code-bg-color);
  color: var(--code-text-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.topics-data-grid :deep(.el-table__inner-wrapper::before) {
  background: var(--topics-border);
}

.topics-data-grid :deep(.el-table__header-wrapper th),
.topics-data-grid :deep(.el-table__body-wrapper td) {
  border-color: var(--topics-border);
  background: var(--topics-surface);
  color: var(--topics-text);
}

.topics-data-grid :deep(.el-table__header-wrapper th) {
  background: var(--topics-surface-soft);
  color: var(--topics-text);
}

.topics-data-grid :deep(.el-table__row:hover > td) {
  background: var(--topics-surface-muted);
}

.data-topics-page :deep(.el-loading-mask) {
  background-color: color-mix(in srgb, var(--topics-surface) 82%, transparent);
}

@media (max-width: 1100px) {
  .topics-hero {
    grid-template-columns: 1fr;
  }

  .topics-hero-actions {
    justify-content: flex-start;
  }

  .topics-hero-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .topics-inspector-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .data-topics-page {
    gap: 14px;
  }

  .topics-hero,
  .topics-stream-panel,
  .topics-directory-panel,
  .topics-inspector-panel {
    padding: 16px;
  }

  .topics-hero {
    min-height: auto;
  }

  .topics-hero h1 {
    font-size: 30px;
  }

  .topics-hero-stats,
  .topics-gateway-grid {
    grid-template-columns: 1fr;
  }

  .topics-section-heading,
  .topics-stream-toolbar,
  .topics-preview-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .topics-pattern-input,
  .topics-stream-toolbar .el-button {
    width: 100%;
  }

  .topics-table-wrap {
    display: none;
  }

  .topics-mobile-list {
    display: grid;
  }

  .topic-tag {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
