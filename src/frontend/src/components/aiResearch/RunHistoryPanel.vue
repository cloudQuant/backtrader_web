<template>
  <section
    class="run-history-panel"
    aria-labelledby="trusted-research-history-title"
    :aria-busy="loading ? 'true' : 'false'"
    data-test="trusted-research-history"
  >
    <header class="run-history-panel__header">
      <div>
        <h3 id="trusted-research-history-title">{{ t('strategy.aiResearchTrusted.history.title') }}</h3>
        <p>{{ t('strategy.aiResearchTrusted.history.description') }}</p>
      </div>
      <button type="button" :disabled="loading" data-test="trusted-research-history-refresh" @click="emit('refresh')">
        {{ t('strategy.aiResearchTrusted.history.refresh') }}
      </button>
    </header>

    <p v-if="tasks.length === 0 && !loading" class="run-history-panel__empty">
      {{ t('strategy.aiResearchTrusted.history.empty') }}
    </p>
    <ol v-else class="run-history-panel__list" :aria-label="t('strategy.aiResearchTrusted.history.title')">
      <li v-for="task in tasks" :key="task.id">
        <button
          type="button"
          class="run-history-panel__item"
          :class="{ 'run-history-panel__item--selected': task.id === selectedTaskId }"
          :aria-current="task.id === selectedTaskId ? 'true' : undefined"
          :aria-label="t('strategy.aiResearchTrusted.history.selectTask', { taskId: task.id })"
          @click="emit('select', task)"
        >
          <strong><code>{{ task.id }}</code></strong>
          <span>{{ t('strategy.aiResearchTrusted.history.run', { value: task.run_id }) }}</span>
          <span>{{ t('strategy.aiResearchTrusted.history.status', { value: task.status }) }}</span>
          <span>{{ t('strategy.aiResearchTrusted.history.stage', { value: task.stage_cursor }) }}</span>
          <span v-if="task.error_code">{{ t('strategy.aiResearchTrusted.history.error', { value: task.error_code }) }}</span>
          <span v-if="task.trace_id">{{ t('strategy.aiResearchTrusted.history.trace', { value: task.trace_id }) }}</span>
          <time :datetime="task.created_at">{{ t('strategy.aiResearchTrusted.history.createdAt', { value: task.created_at }) }}</time>
        </button>
      </li>
    </ol>

    <button
      v-if="hasMore"
      type="button"
      class="run-history-panel__more"
      :disabled="loading"
      data-test="trusted-research-history-load-more"
      @click="emit('load-more')"
    >
      {{ t('strategy.aiResearchTrusted.history.loadMore') }}
    </button>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { AiResearchV2Task } from '@/types/aiResearchV2'

const props = defineProps<{
  tasks: AiResearchV2Task[]
  selectedTaskId?: string | null
  nextCursor?: string | null
  loading?: boolean
}>()

const emit = defineEmits<{
  select: [task: AiResearchV2Task]
  refresh: []
  'load-more': []
}>()

const { t } = useI18n()
const hasMore = computed(() => Boolean(props.nextCursor))
</script>

<style scoped>
.run-history-panel { display: grid; gap: 10px; padding: 14px; border: 1px solid var(--border-color); border-radius: 8px; background: var(--fill-color-lighter); }
.run-history-panel__header { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.run-history-panel__header h3 { margin: 0; font-size: 15px; }
.run-history-panel__header p, .run-history-panel__empty { margin: 4px 0 0; color: var(--text-color-secondary); font-size: 12px; line-height: 1.45; }
.run-history-panel button { min-height: 32px; padding: 6px 9px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--bg-color); color: var(--text-color-primary); cursor: pointer; }
.run-history-panel button:disabled { cursor: not-allowed; opacity: .55; }
.run-history-panel__list { display: grid; gap: 7px; max-height: 310px; margin: 0; padding: 0; overflow: auto; list-style: none; }
.run-history-panel__item { display: grid; grid-template-columns: minmax(140px, 1fr) repeat(3, minmax(0, auto)); gap: 4px 10px; width: 100%; text-align: left; }
.run-history-panel__item strong, .run-history-panel__item code { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-history-panel__item span, .run-history-panel__item time { min-width: 0; overflow-wrap: anywhere; color: var(--text-color-secondary); font-size: 12px; }
.run-history-panel__item--selected { border-color: var(--primary-color) !important; box-shadow: inset 0 0 0 1px var(--primary-light-5); }
.run-history-panel__more { justify-self: start; }
@media (max-width: 720px) { .run-history-panel__header { display: grid; }.run-history-panel__item { grid-template-columns: 1fr; } }
</style>
