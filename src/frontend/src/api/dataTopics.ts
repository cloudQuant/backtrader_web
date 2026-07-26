import request from './index'
import { getAccessToken } from '@/utils/session'

export interface DataTopicPolicy {
  ttl_ms?: number
  min_interval_ms?: number
  refresh_timeout_ms?: number
  push_only?: boolean
  coalesce_within_ms?: number
  drop_on_idle?: boolean
  pause_when_inactive?: boolean
}

export interface DataTopicItem {
  topic: string
  has_value: boolean
  updated_at_ms: number | null
  policy: DataTopicPolicy
  subscription_count: number
  last_error: Record<string, unknown> | null
}

export interface DataTopicStats {
  total_topics: number
  topics_with_value: number
  subscription_count: number
  error_count: number
  ws_gateway: {
    connection_count: number
    subscription_count: number
  } | null
}

function toWebSocketBase(): string {
  if (typeof window === 'undefined') {
    return 'ws://localhost'
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

export const dataTopicsApi = {
  listTopics() {
    return request.get<{ items: DataTopicItem[]; total: number }>('/data-topics')
  },
  peekTopic(topic: string) {
    return request.get<{ topic: string; value: unknown }>(`/data-topics/${topic}/peek`)
  },
  refreshTopic(topic: string) {
    return request.post<{ topic: string; value: unknown }>(`/data-topics/${topic}/refresh`)
  },
  getStats() {
    return request.get<DataTopicStats>('/data-topics/stats')
  },
  buildTopicStreamUrl(topic: string) {
    return `${toWebSocketBase()}/ws/data-topics/${encodeURIComponent(topic)}`
  },
  buildPatternStreamUrl(pattern: string) {
    return `${toWebSocketBase()}/ws/data-topics?pattern=${encodeURIComponent(pattern)}`
  },
  getWebSocketProtocols() {
    const token = getAccessToken()
    return token ? ['access-token', token] : []
  },
}
