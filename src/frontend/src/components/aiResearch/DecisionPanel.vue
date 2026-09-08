<template>
  <section class="trusted-panel" aria-labelledby="trusted-decision-title">
    <header><span>05</span><div><h3 id="trusted-decision-title">{{ t('strategy.aiResearchTrusted.decision.title') }}</h3><p>{{ t('strategy.aiResearchTrusted.decision.description') }}</p></div></header>
    <ul v-if="decisions.length" class="trusted-panel__list"><li v-for="decision in decisions" :key="String(decision.id)"><strong>{{ decision.decision }}</strong><span>{{ decision.approval_mode }}</span><small>{{ t('strategy.aiResearchTrusted.decision.evidence', { value: decision.evidence_package_hash }) }}</small></li></ul>
    <p v-else class="trusted-panel__empty">{{ t('strategy.aiResearchTrusted.decision.empty') }}</p>
    <button v-if="canCancel" type="button" class="trusted-panel__cancel" @click="emit('cancel')">{{ t('strategy.aiResearchTrusted.decision.cancel') }}</button>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

withDefaults(defineProps<{ decisions?: Array<Record<string, unknown>>; canCancel?: boolean }>(), { decisions: () => [], canCancel: false })
const emit = defineEmits<{ cancel: [] }>()
</script>

<style scoped>
.trusted-panel { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border-color-light); border-radius: 10px; background: var(--bg-color); }.trusted-panel header { display: flex; gap: 10px; align-items: flex-start; }.trusted-panel header > span { display: inline-grid; place-items: center; width: 25px; height: 25px; border-radius: 50%; background: var(--primary-color); color: #fff; font-size: 12px; font-weight: 700; }.trusted-panel h3 { margin: 0; font-size: 15px; }.trusted-panel p { margin: 4px 0 0; color: var(--text-color-secondary); font-size: 13px; line-height: 1.5; }.trusted-panel__list { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }.trusted-panel__list li { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 8px; padding: 8px; border-radius: 6px; background: var(--fill-color-lighter); font-size: 12px; }.trusted-panel__list small { grid-column: 1 / -1; overflow: hidden; color: var(--text-color-secondary); text-overflow: ellipsis; white-space: nowrap; }.trusted-panel__empty { color: var(--text-color-secondary); }.trusted-panel__cancel { justify-self: start; padding: 7px 10px; border: 1px solid var(--danger-border-color); border-radius: 6px; background: transparent; color: var(--danger-text-color); cursor: pointer; }
</style>
