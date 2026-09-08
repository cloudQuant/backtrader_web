<template>
  <section class="trusted-panel" aria-labelledby="trusted-ledger-title">
    <header><span>03</span><div><h3 id="trusted-ledger-title">{{ t('strategy.aiResearchTrusted.ledger.title') }}</h3><p>{{ t('strategy.aiResearchTrusted.ledger.description') }}</p></div></header>
    <ol v-if="ledger.length" class="trusted-panel__list">
      <li v-for="item in ledger" :key="String(item.id)">
        <strong>#{{ item.ordinal }} · {{ item.stage }}</strong><span>{{ item.status }}</span><small>{{ item.counts_as_market_trial ? t('strategy.aiResearchTrusted.ledger.marketTrial') : t('strategy.aiResearchTrusted.ledger.technicalRecord') }}</small>
      </li>
    </ol>
    <p v-else class="trusted-panel__empty">{{ t('strategy.aiResearchTrusted.ledger.empty') }}</p>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

withDefaults(defineProps<{ ledger?: Array<Record<string, unknown>> }>(), { ledger: () => [] })
</script>

<style scoped>
.trusted-panel { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border-color-light); border-radius: 10px; background: var(--bg-color); }.trusted-panel header { display: flex; gap: 10px; align-items: flex-start; }.trusted-panel header > span { display: inline-grid; place-items: center; width: 25px; height: 25px; border-radius: 50%; background: var(--primary-color); color: #fff; font-size: 12px; font-weight: 700; }.trusted-panel h3 { margin: 0; font-size: 15px; }.trusted-panel p { margin: 4px 0 0; color: var(--text-color-secondary); font-size: 13px; line-height: 1.5; }.trusted-panel__list { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }.trusted-panel__list li { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 8px; padding: 8px; border-radius: 6px; background: var(--fill-color-lighter); font-size: 12px; }.trusted-panel__list strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.trusted-panel__list span { font-weight: 700; }.trusted-panel__list small { grid-column: 1 / -1; color: var(--text-color-secondary); }.trusted-panel__empty { color: var(--text-color-secondary); }
</style>
