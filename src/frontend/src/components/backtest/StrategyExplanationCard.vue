<template>
  <el-card class="strategy-explanation-card">
    <template #header>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="text-lg font-semibold text-gray-900">
            {{ t('backtestComp.seTitle') }}
          </h3>
          <p class="text-sm text-gray-500 mt-1">
            {{ explanation.disclaimer }}
          </p>
        </div>
        <el-tag :type="explanation.cached ? 'success' : 'info'">
          {{ sourceLabel }}
        </el-tag>
      </div>
    </template>

    <div class="space-y-4">
      <section class="rounded-lg border border-blue-100 bg-blue-50 p-4">
        <div class="text-sm font-medium text-blue-900 mb-2">
          {{ t('backtestComp.seSummaryHeading') }}
        </div>
        <p class="text-sm text-blue-800 leading-6">
          {{ explanation.summary }}
        </p>
      </section>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <section
          v-for="section in sections"
          :key="section.title"
          class="rounded-lg border border-gray-200 bg-gray-50 p-4"
        >
          <div class="text-sm font-medium text-gray-900 mb-2">
            {{ section.title }}
          </div>
          <p class="text-sm text-gray-600 leading-6">
            {{ section.content }}
          </p>
        </section>
      </div>

      <section class="rounded-lg border border-gray-200 p-4">
        <div class="text-sm font-medium text-gray-900 mb-3">
          {{ t('backtestComp.seStaticEvidence') }}
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div class="rounded bg-gray-50 p-3">
            <div class="text-gray-500 mb-1">
              {{ t('backtestComp.seFieldIndicators') }}
            </div>
            <div class="font-medium text-gray-800">
              {{ indicatorNames }}
            </div>
          </div>
          <div class="rounded bg-gray-50 p-3">
            <div class="text-gray-500 mb-1">
              {{ t('backtestComp.seFieldParams') }}
            </div>
            <div class="font-medium text-gray-800">
              {{ paramNames }}
            </div>
          </div>
          <div class="rounded bg-gray-50 p-3">
            <div class="text-gray-500 mb-1">
              {{ t('backtestComp.seFieldParseStatus') }}
            </div>
            <div class="font-medium text-gray-800">
              {{ explanation.ast.parsable ? t('backtestComp.seParseOk') : t('backtestComp.seParseDegraded') }}
            </div>
          </div>
        </div>
      </section>

      <section class="rounded-lg border border-indigo-100 bg-indigo-50 p-4">
        <div class="text-sm font-medium text-indigo-900 mb-3">
          {{ t('backtestComp.seSignalIllustration') }}
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div class="rounded bg-white p-3">
            <div class="text-indigo-700 mb-2">
              {{ t('backtestComp.seBuyConditions') }}
            </div>
            <div
              v-for="signal in entrySignals"
              :key="`entry-${signal.condition}`"
              class="mb-2 last:mb-0 rounded border border-indigo-100 px-2 py-1 text-gray-700"
            >
              {{ signal.condition }}
            </div>
          </div>
          <div class="rounded bg-white p-3">
            <div class="text-indigo-700 mb-2">
              {{ t('backtestComp.seSellConditions') }}
            </div>
            <div
              v-for="signal in exitSignals"
              :key="`exit-${signal.condition}`"
              class="mb-2 last:mb-0 rounded border border-indigo-100 px-2 py-1 text-gray-700"
            >
              {{ signal.condition }}
            </div>
          </div>
        </div>
      </section>

      <section class="rounded-lg border border-gray-200 p-4">
        <div class="text-sm font-medium text-gray-900 mb-3">
          {{ t('backtestComp.seRiskBlock') }}
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div
            v-for="control in riskControls"
            :key="`${control.type}-${control.source}`"
            class="rounded bg-gray-50 p-3"
          >
            <div class="text-gray-500 mb-1">
              {{ control.type }}
            </div>
            <div class="font-medium text-gray-800">
              {{ formatRiskControl(control) }}
            </div>
          </div>
        </div>
      </section>

      <section
        v-if="explanation.risk_notes.length"
        class="rounded-lg border border-amber-200 bg-amber-50 p-4"
      >
        <div class="text-sm font-medium text-amber-900 mb-2">
          {{ t('backtestComp.seRiskNotes') }}
        </div>
        <ul class="list-disc pl-5 text-sm text-amber-800 leading-6">
          <li
            v-for="note in explanation.risk_notes"
            :key="note"
          >
            {{ note }}
          </li>
        </ul>
      </section>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { StrategyExplanation, StrategyRiskControl, StrategySignal } from '@/api/strategy'

const { t } = useI18n()

const props = defineProps<{
  explanation: StrategyExplanation
}>()

const sourceLabel = computed(() => {
  if (props.explanation.cached) return t('backtestComp.seSourceCached')
  if (props.explanation.reason_code === 'ai_generated') return t('backtestComp.seSourceAi')
  return t('backtestComp.seSourceStatic')
})

const sections = computed(() => [
  { title: t('backtestComp.seSecIndicators'), content: props.explanation.indicators_explanation },
  { title: t('backtestComp.seSecEntry'), content: props.explanation.entry_explanation },
  { title: t('backtestComp.seSecExit'), content: props.explanation.exit_explanation },
  { title: t('backtestComp.seSecParams'), content: props.explanation.params_explanation },
  { title: t('backtestComp.seSecMarket'), content: props.explanation.market_fit },
])

const indicatorNames = computed(() => {
  const names = props.explanation.ast.indicators.map((item) => item.name)
  return names.length ? names.join(' / ') : t('backtestComp.seUnknown')
})

const paramNames = computed(() => {
  const names = props.explanation.ast.params.map((item) => item.name)
  return names.length ? names.join(' / ') : t('backtestComp.seUnknown')
})

const entrySignals = computed<StrategySignal[]>(() =>
  props.explanation.ast.entry_signals.length
    ? props.explanation.ast.entry_signals
    : [{ condition: t('backtestComp.seNoEntrySig'), side: 'buy' }],
)

const exitSignals = computed<StrategySignal[]>(() =>
  props.explanation.ast.exit_signals.length
    ? props.explanation.ast.exit_signals
    : [{ condition: t('backtestComp.seNoExitSig'), side: 'sell' }],
)

const riskControls = computed<StrategyRiskControl[]>(() =>
  props.explanation.ast.risk_controls.length
    ? props.explanation.ast.risk_controls
    : [{ type: 'not_detected', value: t('backtestComp.seNoRiskCtrl'), source: null }],
)

function formatRiskControl(control: StrategyRiskControl): string {
  if (control.source) return control.source
  if (control.value === null || control.value === undefined) return '--'
  if (typeof control.value === 'object') return JSON.stringify(control.value)
  return String(control.value)
}
</script>

