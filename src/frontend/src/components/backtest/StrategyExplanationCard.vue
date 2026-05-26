<template>
  <el-card class="strategy-explanation-card">
    <template #header>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="text-lg font-semibold text-gray-900">
            策略解释
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
          一句话总结
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
          静态分析证据
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div class="rounded bg-gray-50 p-3">
            <div class="text-gray-500 mb-1">
              指标
            </div>
            <div class="font-medium text-gray-800">
              {{ indicatorNames }}
            </div>
          </div>
          <div class="rounded bg-gray-50 p-3">
            <div class="text-gray-500 mb-1">
              参数
            </div>
            <div class="font-medium text-gray-800">
              {{ paramNames }}
            </div>
          </div>
          <div class="rounded bg-gray-50 p-3">
            <div class="text-gray-500 mb-1">
              解析状态
            </div>
            <div class="font-medium text-gray-800">
              {{ explanation.ast.parsable ? '已解析' : '降级解析' }}
            </div>
          </div>
        </div>
      </section>

      <section class="rounded-lg border border-indigo-100 bg-indigo-50 p-4">
        <div class="text-sm font-medium text-indigo-900 mb-3">
          信号示意
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div class="rounded bg-white p-3">
            <div class="text-indigo-700 mb-2">
              买入条件
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
              卖出/退出条件
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
          仓位/风控
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
          风险提示
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
import type { StrategyExplanation, StrategyRiskControl, StrategySignal } from '@/api/strategy'

const props = defineProps<{
  explanation: StrategyExplanation
}>()

const sourceLabel = computed(() => {
  if (props.explanation.cached) return '缓存结果'
  if (props.explanation.reason_code === 'ai_generated') return 'AI 解释'
  return '静态解释'
})

const sections = computed(() => [
  { title: '指标说明', content: props.explanation.indicators_explanation },
  { title: '买入逻辑', content: props.explanation.entry_explanation },
  { title: '卖出逻辑', content: props.explanation.exit_explanation },
  { title: '参数说明', content: props.explanation.params_explanation },
  { title: '市场适配', content: props.explanation.market_fit },
])

const indicatorNames = computed(() => {
  const names = props.explanation.ast.indicators.map((item) => item.name)
  return names.length ? names.join(' / ') : '未识别'
})

const paramNames = computed(() => {
  const names = props.explanation.ast.params.map((item) => item.name)
  return names.length ? names.join(' / ') : '未识别'
})

const entrySignals = computed<StrategySignal[]>(() =>
  props.explanation.ast.entry_signals.length
    ? props.explanation.ast.entry_signals
    : [{ condition: '未识别到明确买入条件', side: 'buy' }],
)

const exitSignals = computed<StrategySignal[]>(() =>
  props.explanation.ast.exit_signals.length
    ? props.explanation.ast.exit_signals
    : [{ condition: '未识别到明确卖出/退出条件', side: 'sell' }],
)

const riskControls = computed<StrategyRiskControl[]>(() =>
  props.explanation.ast.risk_controls.length
    ? props.explanation.ast.risk_controls
    : [{ type: 'not_detected', value: '未识别到明确仓位控制', source: null }],
)

function formatRiskControl(control: StrategyRiskControl): string {
  if (control.source) return control.source
  if (control.value === null || control.value === undefined) return '--'
  if (typeof control.value === 'object') return JSON.stringify(control.value)
  return String(control.value)
}
</script>
