<template>
  <section
    class="task-event-timeline"
    aria-labelledby="trusted-research-events-title"
    :aria-busy="loading ? 'true' : 'false'"
    data-test="trusted-research-events"
  >
    <header>
      <h3 id="trusted-research-events-title">{{ t('strategy.aiResearchTrusted.timeline.title') }}</h3>
      <p>{{ t('strategy.aiResearchTrusted.timeline.description') }}</p>
    </header>

    <p v-if="!taskId" class="task-event-timeline__empty">{{ t('strategy.aiResearchTrusted.timeline.noTask') }}</p>
    <p v-else-if="events.length === 0 && !loading" class="task-event-timeline__empty">{{ t('strategy.aiResearchTrusted.timeline.empty') }}</p>
    <ol v-else class="task-event-timeline__list" :aria-label="t('strategy.aiResearchTrusted.timeline.title')">
      <li v-for="event in events" :key="event.id">
        <div class="task-event-timeline__event">
          <strong>{{ t('strategy.aiResearchTrusted.timeline.sequence', { value: event.sequence_no }) }}</strong>
          <span>{{ event.event_type }}</span>
          <span v-if="event.stage">{{ t('strategy.aiResearchTrusted.timeline.stage', { value: event.stage }) }}</span>
          <span v-if="event.status">{{ t('strategy.aiResearchTrusted.timeline.status', { value: event.status }) }}</span>
          <span v-if="event.error_code">{{ t('strategy.aiResearchTrusted.timeline.error', { value: event.error_code }) }}</span>
          <span v-if="event.stage_attempt_id">{{ t('strategy.aiResearchTrusted.timeline.attempt', { value: event.stage_attempt_id }) }}</span>
          <span v-if="event.trace_id">{{ t('strategy.aiResearchTrusted.timeline.trace', { value: event.trace_id }) }}</span>
          <time :datetime="event.created_at">{{ t('strategy.aiResearchTrusted.timeline.occurredAt', { value: event.created_at }) }}</time>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { AiResearchV2TaskEvent } from '@/types/aiResearchV2'

defineProps<{
  taskId?: string | null
  events: AiResearchV2TaskEvent[]
  loading?: boolean
}>()

const { t } = useI18n()
</script>

<style scoped>
.task-event-timeline { display: grid; gap: 10px; padding: 14px; border: 1px solid var(--border-color); border-radius: 8px; background: var(--fill-color-lighter); }
.task-event-timeline h3 { margin: 0; font-size: 15px; }
.task-event-timeline header p, .task-event-timeline__empty { margin: 4px 0 0; color: var(--text-color-secondary); font-size: 12px; line-height: 1.45; }
.task-event-timeline__list { display: grid; gap: 7px; max-height: 310px; margin: 0; padding: 0; overflow: auto; list-style: none; }
.task-event-timeline__event { display: grid; gap: 3px; padding: 8px; border-left: 3px solid var(--primary-light-5); background: var(--bg-color); font-size: 12px; }
.task-event-timeline__event span, .task-event-timeline__event time { overflow-wrap: anywhere; color: var(--text-color-secondary); }
</style>
