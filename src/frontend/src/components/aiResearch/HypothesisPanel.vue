<template>
  <section class="trusted-panel" aria-labelledby="trusted-hypothesis-title">
    <header>
      <span>01</span>
      <div>
        <h3 id="trusted-hypothesis-title">{{ t('strategy.aiResearchTrusted.hypothesis.title') }}</h3>
        <p>{{ t('strategy.aiResearchTrusted.hypothesis.description') }}</p>
      </div>
    </header>
    <dl v-if="hypothesis" class="trusted-panel__facts">
      <div><dt>{{ t('strategy.aiResearchTrusted.hypothesis.status') }}</dt><dd>{{ hypothesis.status || t('strategy.aiResearchTrusted.unavailable') }}</dd></div>
      <div><dt>{{ t('strategy.aiResearchTrusted.hypothesis.contentHash') }}</dt><dd class="trusted-panel__hash">{{ hypothesis.content_hash || t('strategy.aiResearchTrusted.unavailable') }}</dd></div>
    </dl>
    <p v-else class="trusted-panel__empty">{{ t('strategy.aiResearchTrusted.hypothesis.empty') }}</p>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{ hypothesis?: Record<string, unknown> | null }>()
</script>

<style scoped>
.trusted-panel { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border-color-light); border-radius: 10px; background: var(--bg-color); }
.trusted-panel header { display: flex; gap: 10px; align-items: flex-start; }
.trusted-panel header > span { display: inline-grid; place-items: center; width: 25px; height: 25px; border-radius: 50%; background: var(--primary-color); color: #fff; font-size: 12px; font-weight: 700; }
.trusted-panel h3 { margin: 0; font-size: 15px; }.trusted-panel p { margin: 4px 0 0; color: var(--text-color-secondary); font-size: 13px; line-height: 1.5; }
.trusted-panel__facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 0; }.trusted-panel__facts div { min-width: 0; }.trusted-panel dt { color: var(--text-color-secondary); font-size: 12px; }.trusted-panel dd { margin: 3px 0 0; font-size: 13px; }.trusted-panel__hash { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--font-family-mono, monospace); }.trusted-panel__empty { color: var(--text-color-secondary); }
</style>
