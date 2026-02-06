<template>
  <div class="metric-card bg-white rounded-lg border p-4 hover:shadow-md transition-shadow">
    <div class="flex items-center justify-between mb-2">
      <span class="text-gray-500 text-sm">{{ title }}</span>
      <el-tooltip v-if="tooltip" :content="tooltip" placement="top">
        <el-icon class="text-gray-400 cursor-help"><QuestionFilled /></el-icon>
      </el-tooltip>
    </div>
    <div class="flex items-end gap-2">
      <span class="text-2xl font-bold" :class="valueColorClass">
        {{ formattedValue }}
      </span>
      <span v-if="change !== undefined" class="text-sm mb-1" :class="changeColorClass">
        {{ changeText }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  title: string
  value: number | null | undefined
  format?: 'currency' | 'percent' | 'number' | 'days'
  precision?: number
  change?: number
  color?: 'default' | 'success' | 'danger' | 'warning'
  tooltip?: string
}>()

const formattedValue = computed(() => {
  if (props.value === null || props.value === undefined) {
    return '--'
  }
  
  const precision = props.precision ?? 2
  
  switch (props.format) {
    case 'currency':
      return `¥${props.value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    case 'percent':
      return `${(props.value * 100).toFixed(precision)}%`
    case 'days':
      return `${props.value.toFixed(1)}天`
    case 'number':
    default:
      return props.value.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: precision })
  }
})

const changeText = computed(() => {
  if (props.change === undefined) return ''
  const sign = props.change >= 0 ? '+' : ''
  return `${sign}${(props.change * 100).toFixed(2)}%`
})

const valueColorClass = computed(() => {
  if (props.color === 'success') return 'text-green-600'
  if (props.color === 'danger') return 'text-red-600'
  if (props.color === 'warning') return 'text-yellow-600'
  
  // 自动判断颜色
  if (props.format === 'percent' && props.value !== null && props.value !== undefined) {
    return props.value >= 0 ? 'text-green-600' : 'text-red-600'
  }
  
  return 'text-gray-900'
})

const changeColorClass = computed(() => {
  if (props.change === undefined) return ''
  return props.change >= 0 ? 'text-green-500' : 'text-red-500'
})
</script>
