<template>
  <el-card class="overfitting-panel">
    <template #header>
      <div class="flex items-center justify-between gap-3">
        <div>
          <h3 class="text-lg font-semibold text-gray-900">
            {{ t('backtestComp.ofTitle') }}
          </h3>
          <p
            class="text-sm text-gray-500 mt-1"
          >
            {{ t('backtestComp.ofDesc') }}
          </p>
        </div>
        <div class="text-right shrink-0">
          <div
            v-if="result"
            class="text-2xl font-bold text-gray-900"
          >
            {{ result.robustness_score.toFixed(1) }}
          </div>
          <el-tag :type="riskTagType">
            {{ riskLabel }}
          </el-tag>
        </div>
      </div>
    </template>

    <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
      <div class="flex flex-wrap items-center gap-3 text-sm text-gray-600">
        <el-checkbox
          :model-value="isMethodSelected('walk_forward')"
          :disabled="loading"
          @update:model-value="toggleMethod('walk_forward', Boolean($event))"
        >
          Walk-forward
        </el-checkbox>
        <el-checkbox
          :model-value="isMethodSelected('out_of_sample')"
          :disabled="loading"
          @update:model-value="toggleMethod('out_of_sample', Boolean($event))"
        >
          {{ t('backtestComp.ofSampleOut') }}
        </el-checkbox>
        <el-checkbox
          :model-value="isMethodSelected('monte_carlo')"
          :disabled="loading"
          @update:model-value="toggleMethod('monte_carlo', Boolean($event))"
        >
          Monte Carlo
        </el-checkbox>
        <el-checkbox
          :model-value="isMethodSelected('parameter_sensitivity')"
          :disabled="loading"
          @update:model-value="toggleMethod('parameter_sensitivity', Boolean($event))"
        >
          参数敏感性
        </el-checkbox>
      </div>
      <el-button
        size="small"
        :loading="loading"
        @click="handleRerun"
      >
        {{ t('backtestComp.ofRerun') }}
      </el-button>
    </div>

    <div
      v-if="loading"
      class="text-sm text-gray-500"
    >
      {{ progressMessage || t('backtestComp.ofLoading') }}
    </div>

    <div
      v-else-if="result"
      class="space-y-4"
    >
      <p class="text-sm text-gray-700 leading-6">
        {{ result.summary }}
      </p>

      <section
        v-if="activeMethod"
        class="rounded-lg border border-blue-100 bg-blue-50 p-4"
      >
        <div class="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div class="text-sm font-medium text-blue-900">
            {{ t('backtestComp.ofMethodChartTitle') }}
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="method in result.methods"
              :key="`tab-${method.method}`"
              type="button"
              class="rounded-full border px-3 py-1 text-xs"
              :class="activeMethod.method === method.method ? 'border-blue-500 bg-blue-600 text-white' : 'border-blue-200 bg-white text-blue-700'"
              :data-test="`method-tab-${method.method}`"
              @click="activeMethodKey = method.method"
            >
              {{ formatMethodName(method.method) }}
            </button>
          </div>
        </div>
        <div
          :data-test="`overfitting-chart-${activeMethod.method}`"
          class="rounded-lg bg-white p-4"
        >
          <template v-if="activeMethod.method === 'walk_forward'">
            <div class="mb-3 text-xs text-gray-500">
              {{ t('backtestComp.ofIsOosSharpe') }}
            </div>
            <div class="space-y-3">
              <div
                v-for="window in walkForwardWindows"
                :key="window.label"
                class="space-y-1"
              >
                <div class="flex items-center justify-between text-xs text-gray-600">
                  <span>{{ window.label }}</span>
                  <span>IS {{ window.isSharpe }} / OOS {{ window.oosSharpe }}</span>
                </div>
                <div class="grid grid-cols-2 gap-2">
                  <div class="h-2 rounded bg-blue-100">
                    <div
                      class="h-2 rounded bg-blue-500"
                      :style="{ width: `${window.isWidth}%` }"
                    />
                  </div>
                  <div class="h-2 rounded bg-emerald-100">
                    <div
                      class="h-2 rounded bg-emerald-500"
                      :style="{ width: `${window.oosWidth}%` }"
                    />
                  </div>
                </div>
              </div>
            </div>
          </template>
          <template v-else-if="activeMethod.method === 'out_of_sample'">
            <div class="mb-3 text-xs text-gray-500">
              {{ t('backtestComp.ofIsOosReturnSig') }}
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div class="rounded border border-gray-100 p-3">
                <div class="text-xs text-gray-500">
                  {{ t('backtestComp.ofIsAnnual') }}
                </div>
                <div class="mt-1 text-lg font-semibold text-gray-900">
                  {{ formatMetricValue(activeMethod.metrics.is_annual_return, 'percent') }}
                </div>
              </div>
              <div class="rounded border border-gray-100 p-3">
                <div class="text-xs text-gray-500">
                  {{ t('backtestComp.ofOosAnnual') }}
                </div>
                <div class="mt-1 text-lg font-semibold text-gray-900">
                  {{ formatMetricValue(activeMethod.metrics.oos_annual_return, 'percent') }}
                </div>
              </div>
              <div class="rounded border border-gray-100 p-3">
                <div class="text-xs text-gray-500">
                  p-value
                </div>
                <div class="mt-1 text-lg font-semibold text-gray-900">
                  {{ formatMetricValue(activeMethod.metrics.p_value) }}
                </div>
              </div>
            </div>
          </template>
          <template v-else-if="activeMethod.method === 'parameter_sensitivity'">
            <div class="mb-3 text-xs text-gray-500">
              参数扰动后的 Sharpe 与年化收益衰减。
            </div>
            <div
              v-if="parameterSensitivityTrials.length"
              class="space-y-2"
            >
              <div
                v-for="trial in parameterSensitivityTrials"
                :key="`${trial.parameter}-${trial.direction}-${trial.value}`"
                class="grid grid-cols-4 gap-2 rounded border border-gray-100 p-2 text-xs text-gray-700"
              >
                <span>{{ trial.parameter }} {{ trial.direction }}</span>
                <span>{{ trial.value }}</span>
                <span>Sharpe {{ trial.sharpe }}</span>
                <span>衰减 {{ trial.decay }}%</span>
              </div>
            </div>
            <p
              v-else
              class="text-sm text-gray-500"
            >
              未返回可展示的参数扰动样本。
            </p>
          </template>
          <template v-else>
            <div class="mb-3 text-xs text-gray-500">
              {{ t('backtestComp.ofRandomDist') }}
            </div>
            <div class="flex items-end gap-1 h-28">
              <div
                v-for="bar in monteCarloBars"
                :key="bar.index"
                class="flex-1 rounded-t bg-purple-300"
                :style="{ height: `${bar.height}%` }"
                :title="bar.label"
              />
            </div>
            <div class="mt-3 text-xs text-gray-600">
              {{ t('backtestComp.ofActualPercentile', { value: formatMetricValue(activeMethod.metrics.bootstrap_percentile, 'percent') }) }}
            </div>
          </template>
        </div>
      </section>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div
          v-for="method in result.methods"
          :key="method.method"
          class="rounded-lg border border-gray-200 bg-gray-50 p-4"
        >
          <div class="flex items-center justify-between gap-3 mb-2">
            <div class="text-sm font-medium text-gray-900">
              {{ formatMethodName(method.method) }}
            </div>
            <div class="text-lg font-semibold text-gray-900">
              {{ method.score.toFixed(1) }}
            </div>
          </div>

          <p class="text-sm text-gray-600 leading-6 mb-3">
            {{ method.explanation }}
          </p>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
            <div
              v-for="evidence in buildEvidenceItems(method)"
              :key="`${method.method}-${evidence.label}`"
              class="rounded border border-white bg-white px-3 py-2"
            >
              <div class="text-gray-500">
                {{ evidence.label }}
              </div>
              <div class="mt-1 font-semibold text-gray-800">
                {{ evidence.value }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-else
      class="text-sm text-gray-500"
    >
      {{ t('backtestComp.ofEmpty') }}
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  StrategyOverfittingMethod,
  StrategyOverfittingMethodResult,
  StrategyOverfittingTaskResult,
} from '@/api/strategy'

const { t } = useI18n()

interface EvidenceItem {
  label: string
  value: string
}

const props = defineProps<{
  result?: StrategyOverfittingTaskResult | null
  loading?: boolean
  progressMessage?: string
}>()

const emit = defineEmits<{
  rerun: [methods: StrategyOverfittingMethod[]]
}>()

const selectedMethods = ref<StrategyOverfittingMethod[]>([
  'walk_forward',
  'out_of_sample',
  'monte_carlo',
  'parameter_sensitivity',
])
const activeMethodKey = ref<StrategyOverfittingMethod>('walk_forward')

const riskLabel = computed(() => {
  if (!props.result) return t('backtestComp.ofRiskPending')
  if (props.result.overall_level === 'low') return t('backtestComp.ofRiskLow')
  if (props.result.overall_level === 'medium') return t('backtestComp.ofRiskMedium')
  return t('backtestComp.ofRiskHigh')
})

const riskTagType = computed(() => {
  if (!props.result) return 'info'
  if (props.result.overall_level === 'low') return 'success'
  if (props.result.overall_level === 'medium') return 'warning'
  return 'danger'
})

const activeMethod = computed(() => {
  if (!props.result?.methods.length) return null
  return props.result.methods.find((item) => item.method === activeMethodKey.value)
    ?? props.result.methods[0]
})

const walkForwardWindows = computed(() => {
  if (!activeMethod.value || activeMethod.value.method !== 'walk_forward') return []
  const rawWindows = Array.isArray(activeMethod.value.metrics.windows)
    ? activeMethod.value.metrics.windows
    : []
  return rawWindows.map((item, index) => {
    const record = item as Record<string, unknown>
    const isSharpe = numberFromMetric(record.is_sharpe)
    const oosSharpe = numberFromMetric(record.oos_sharpe)
    const scale = Math.max(Math.abs(isSharpe), Math.abs(oosSharpe), 1)
    return {
      label: t('backtestComp.ofWindowLabel', { n: index + 1 }),
      isSharpe: isSharpe.toFixed(2),
      oosSharpe: oosSharpe.toFixed(2),
      isWidth: Math.max(4, Math.min(100, Math.abs(isSharpe) / scale * 100)),
      oosWidth: Math.max(4, Math.min(100, Math.abs(oosSharpe) / scale * 100)),
    }
  })
})

const monteCarloBars = computed(() => {
  if (!activeMethod.value || activeMethod.value.method !== 'monte_carlo') return []
  const rawDistribution = Array.isArray(activeMethod.value.metrics.bootstrap_distribution_pct)
    ? activeMethod.value.metrics.bootstrap_distribution_pct
    : []
  const values = rawDistribution.map((item) => numberFromMetric(item))
  const maxAbs = Math.max(...values.map((item) => Math.abs(item)), 1)
  return values.map((value, index) => ({
    index,
    height: Math.max(6, Math.min(100, Math.abs(value) / maxAbs * 100)),
    label: `${value.toFixed(2)}%`,
  }))
})

const parameterSensitivityTrials = computed(() => {
  if (!activeMethod.value || activeMethod.value.method !== 'parameter_sensitivity') return []
  const trials = activeMethod.value.metrics.trials
  if (!Array.isArray(trials)) return []
  return trials.map((item) => {
    const record = item as Record<string, unknown>
    return {
      parameter: String(record.parameter ?? '-'),
      direction: String(record.direction ?? '-'),
      value: formatMetricValue(record.value),
      sharpe: formatMetricValue(record.sharpe_ratio),
      decay: formatMetricValue(record.sharpe_decay_pct),
    }
  })
})

watch(
  () => props.result?.methods.map((item) => item.method).join('|'),
  () => {
    if (!props.result?.methods.length) return
    if (!props.result.methods.some((item) => item.method === activeMethodKey.value)) {
      activeMethodKey.value = props.result.methods[0].method
    }
  },
  { immediate: true },
)

function formatMethodName(method: string): string {
  if (method === 'monte_carlo') return 'Monte Carlo'
  if (method === 'walk_forward') return 'Walk-forward'
  if (method === 'out_of_sample') return 'Out-of-Sample'
  if (method === 'parameter_sensitivity') return '参数敏感性'
  return method
}

function isMethodSelected(method: StrategyOverfittingMethod): boolean {
  return selectedMethods.value.includes(method)
}

function toggleMethod(method: StrategyOverfittingMethod, checked: boolean) {
  if (checked) {
    if (!selectedMethods.value.includes(method)) {
      selectedMethods.value = [...selectedMethods.value, method]
    }
    return
  }
  if (selectedMethods.value.length <= 1) {
    return
  }
  selectedMethods.value = selectedMethods.value.filter((item) => item !== method)
}

function handleRerun() {
  emit('rerun', [...selectedMethods.value])
}

function buildEvidenceItems(method: StrategyOverfittingMethodResult): EvidenceItem[] {
  if (method.method === 'monte_carlo') {
    return compactEvidence([
      evidenceFromMetric(method.metrics, 'actual_compound_return_pct', t('backtestComp.ofEvActualCompound'), 'percent'),
      evidenceFromMetric(method.metrics, 'bootstrap_percentile', t('backtestComp.ofEvBootstrapPercentile'), 'percent'),
      evidenceFromMetric(method.metrics, 'iterations', t('backtestComp.ofEvIterations')),
      evidenceFromMetric(method.metrics, 'trade_return_count', t('backtestComp.ofEvTradeSampleCount')),
      evidenceFromMetric(method.metrics, 'bootstrap_mean_return_pct', t('backtestComp.ofEvBootstrapMean'), 'percent'),
      evidenceFromMetric(method.metrics, 'bootstrap_p95_return_pct', t('backtestComp.ofEvBootstrap95'), 'percent'),
    ])
  }
  if (method.method === 'walk_forward') {
    return compactEvidence([
      evidenceFromMetric(method.metrics, 'window_count', t('backtestComp.ofEvWindowCount')),
      evidenceFromMetric(method.metrics, 'avg_is_sharpe', t('backtestComp.ofEvAvgIsSharpe')),
      evidenceFromMetric(method.metrics, 'avg_oos_sharpe', t('backtestComp.ofEvAvgOosSharpe')),
      evidenceFromMetric(method.metrics, 'sharpe_decay_pct', t('backtestComp.ofEvSharpeDecay'), 'percent'),
      evidenceFromMetric(method.metrics, 'return_decay_pct', t('backtestComp.ofEvReturnDecay'), 'percent'),
    ])
  }
  if (method.method === 'out_of_sample') {
    return compactEvidence([
      evidenceFromMetric(method.metrics, 'is_sharpe', t('backtestComp.ofEvIsSharpe')),
      evidenceFromMetric(method.metrics, 'oos_sharpe', t('backtestComp.ofEvOosSharpe')),
      evidenceFromMetric(method.metrics, 'sharpe_decay_pct', t('backtestComp.ofEvSharpeDecay'), 'percent'),
      evidenceFromMetric(method.metrics, 'return_decay_pct', t('backtestComp.ofEvReturnDecay'), 'percent'),
      evidenceFromMetric(method.metrics, 'p_value', 'p-value'),
    ])
  }
  if (method.method === 'parameter_sensitivity') {
    return compactEvidence([
      evidenceFromMetric(method.metrics, 'parameter_count', '参数数量'),
      evidenceFromMetric(method.metrics, 'trial_count', '扰动样本数'),
      evidenceFromMetric(method.metrics, 'base_sharpe', '基准 Sharpe'),
      evidenceFromMetric(method.metrics, 'base_annual_return', '基准年化收益', 'percent'),
      evidenceFromMetric(method.metrics, 'worst_decay_pct', '最大衰减', 'percent'),
    ])
  }
  return Object.entries(method.metrics).map(([key, value]) => ({
    label: key,
    value: formatMetricValue(value),
  }))
}

function compactEvidence(items: Array<EvidenceItem | null>): EvidenceItem[] {
  return items.filter((item): item is EvidenceItem => item !== null)
}

function evidenceFromMetric(
  metrics: Record<string, unknown>,
  key: string,
  label: string,
  format: 'plain' | 'percent' = 'plain',
): EvidenceItem | null {
  if (!(key in metrics)) {
    return null
  }
  return {
    label,
    value: formatMetricValue(metrics[key], format),
  }
}

function formatMetricValue(value: unknown, format: 'plain' | 'percent' = 'plain'): string {
  if (typeof value === 'number') {
    if (format === 'percent') {
      return `${value.toFixed(2)}%`
    }
    return Number.isInteger(value) ? String(value) : value.toFixed(2)
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false'
  }
  if (value === null || value === undefined) {
    return '--'
  }
  return String(value)
}

function numberFromMetric(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}
</script>
