<template>
  <el-card
    shadow="hover"
    class="strategy-card cursor-pointer"
    role="button"
    tabindex="0"
    :aria-label="`${t('strategy.title')} ${tpl.name}`"
    @click="emit('detail', tpl)"
    @keydown.enter="emit('detail', tpl)"
    @keydown.space.prevent="emit('detail', tpl)"
  >
    <div class="flex flex-col h-full">
      <div class="flex justify-between items-start mb-2">
        <h3 class="font-bold text-base leading-tight">
          {{ tpl.name }}
        </h3>
        <el-tag
          size="small"
          :type="getCategoryType(tpl.category)"
          effect="light"
        >
          {{ getCategoryLabel(tpl.category) }}
        </el-tag>
      </div>
      <p class="text-gray-500 text-sm mb-3 line-clamp-2 flex-1">
        {{ stripStrategyMeta(tpl.description) }}
      </p>
      <div class="flex items-center justify-between text-xs text-gray-400">
        <span>{{ t('strategy.parameterCount', { count: getStrategyParamCount(tpl.params) }) }}</span>
        <span>{{ tpl.id }}</span>
      </div>
      <div class="flex gap-2 mt-3 pt-3 border-t">
        <el-button
          size="small"
          type="primary"
          @click.stop="emit('detail', tpl)"
        >
          {{ t('strategy.detailLabel') }}
        </el-button>
        <el-button
          size="small"
          @click.stop="emit('use', tpl)"
        >
          {{ t('strategy.actionCopy') }}
        </el-button>
        <el-button
          size="small"
          type="success"
          @click.stop="emit('backtest', tpl)"
        >
          {{ t('strategy.typeBacktest') }}
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import {
  getCategoryLabel,
  getCategoryType,
  getStrategyParamCount,
  stripStrategyMeta,
} from '@/constants/strategy'
import type { StrategyTemplate } from '@/types'

defineProps<{ tpl: StrategyTemplate }>()
const emit = defineEmits<{
  (e: 'detail', tpl: StrategyTemplate): void
  (e: 'use', tpl: StrategyTemplate): void
  (e: 'backtest', tpl: StrategyTemplate): void
}>()

const { t } = useI18n()
</script>
