<template>
  <el-card class="strategy-score-card">
    <template #header>
      <div class="flex items-center justify-between gap-3">
        <div>
          <h3 class="text-lg font-semibold text-gray-900">
            策略评分
          </h3>
          <p class="text-sm text-gray-500 mt-1">
            {{ score.disclaimer }}
          </p>
        </div>
        <div class="text-right shrink-0">
          <div class="text-3xl font-bold text-blue-600">
            {{ score.total_score.toFixed(1) }}
          </div>
          <el-tag type="success">
            {{ score.level }} 级
          </el-tag>
        </div>
      </div>
    </template>

    <section class="rounded-lg border border-blue-100 bg-blue-50 p-4 mb-4">
      <div class="flex items-center justify-between gap-3 mb-3">
        <div class="text-sm font-medium text-blue-900">
          维度雷达图
        </div>
        <div class="text-xs text-blue-700">
          点击下方维度查看子指标
        </div>
      </div>
      <div
        data-test="score-radar-chart"
        class="relative mx-auto h-64 max-w-xl"
      >
        <svg
          viewBox="0 0 240 240"
          class="h-full w-full"
          role="img"
          aria-label="策略评分维度雷达图"
        >
          <polygon
            v-for="level in radarLevels"
            :key="level"
            :points="buildRadarPolygon(level)"
            fill="none"
            stroke="var(--info-border-color)"
            stroke-width="1"
          />
          <line
            v-for="point in radarAxisPoints"
            :key="point.label"
            x1="120"
            y1="120"
            :x2="point.x"
            :y2="point.y"
            stroke="var(--color-primary-100)"
            stroke-width="1"
          />
          <polygon
            :points="scorePolygon"
            fill="rgba(37, 99, 235, 0.22)"
            stroke="var(--primary-color-dark)"
            stroke-width="2"
          />
          <circle
            v-for="point in radarScorePoints"
            :key="point.label"
            :cx="point.x"
            :cy="point.y"
            r="3"
            fill="var(--primary-color-dark)"
          />
          <text
            v-for="point in radarAxisPoints"
            :key="`${point.label}-label`"
            :x="point.labelX"
            :y="point.labelY"
            text-anchor="middle"
            dominant-baseline="middle"
            class="fill-blue-900 text-[9px]"
          >
            {{ point.label }}
          </text>
        </svg>
      </div>
    </section>

    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <div
        v-for="dimension in score.dimensions"
        :key="dimension.key"
        class="rounded-lg border border-gray-200 bg-gray-50 p-4"
        :class="{ 'ring-2 ring-blue-200 bg-white': expandedDimension === dimension.key }"
        :data-test="`dimension-${dimension.key}`"
        role="button"
        tabindex="0"
        @click="toggleDimension(dimension.key)"
        @keydown.enter.prevent="toggleDimension(dimension.key)"
      >
        <div class="flex items-start justify-between gap-3 mb-2">
          <div>
            <div class="text-sm font-medium text-gray-900">
              {{ dimension.label }}
            </div>
            <div class="text-xs text-gray-500 mt-1">
              权重 {{ (dimension.weight * 100).toFixed(0) }}%
            </div>
          </div>
          <div class="text-xl font-semibold text-gray-900">
            {{ dimension.score.toFixed(1) }}
          </div>
        </div>

        <p class="text-sm text-gray-600 leading-6 mb-3">
          {{ dimension.explanation }}
        </p>

        <div
          v-if="expandedDimension === dimension.key"
          class="space-y-1 text-xs text-gray-500"
        >
          <div
            v-for="(value, key) in dimension.sub_metrics"
            :key="`${dimension.key}-${key}`"
            class="flex items-center justify-between gap-3"
          >
            <span class="truncate">{{ key }}</span>
            <span class="font-medium text-gray-700">{{ formatMetricValue(value) }}</span>
          </div>
        </div>

        <div
          v-if="dimension.degraded"
          class="mt-3 text-xs text-amber-600"
        >
          当前维度为降级结果，后续会接入更完整检测。
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { StrategyScoreResponse } from '@/api/strategy'

const props = defineProps<{
  score: StrategyScoreResponse
}>()

const expandedDimension = ref<string | null>(null)
const radarLevels = [100, 75, 50, 25]
const radarRadius = 82
const radarCenter = 120

const radarAxisPoints = computed(() =>
  props.score.dimensions.map((dimension, index, dimensions) => {
    const angle = angleForIndex(index, dimensions.length)
    const axis = pointForScore(angle, 100)
    const label = pointForScore(angle, 116)
    return {
      label: dimension.label,
      x: axis.x,
      y: axis.y,
      labelX: label.x,
      labelY: label.y,
    }
  }),
)

const radarScorePoints = computed(() =>
  props.score.dimensions.map((dimension, index, dimensions) => {
    const angle = angleForIndex(index, dimensions.length)
    const point = pointForScore(angle, dimension.score)
    return {
      label: dimension.label,
      x: point.x,
      y: point.y,
    }
  }),
)

const scorePolygon = computed(() =>
  radarScorePoints.value.map((point) => `${point.x},${point.y}`).join(' '),
)

function toggleDimension(key: string) {
  expandedDimension.value = expandedDimension.value === key ? null : key
}

function buildRadarPolygon(level: number): string {
  return props.score.dimensions
    .map((_, index, dimensions) => {
      const angle = angleForIndex(index, dimensions.length)
      const point = pointForScore(angle, level)
      return `${point.x},${point.y}`
    })
    .join(' ')
}

function angleForIndex(index: number, count: number): number {
  return -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(count, 1)
}

function pointForScore(angle: number, score: number): { x: number; y: number } {
  const radius = radarRadius * Math.max(0, Math.min(100, score)) / 100
  return {
    x: Number((radarCenter + Math.cos(angle) * radius).toFixed(2)),
    y: Number((radarCenter + Math.sin(angle) * radius).toFixed(2)),
  }
}

function formatMetricValue(value: unknown): string {
  if (typeof value === 'number') {
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
</script>
