<template>
  <el-card
    shadow="hover"
    class="strategy-card"
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
      <div class="strategy-card-actions">
        <el-button
          size="small"
          type="primary"
          @click="emit('use', tpl)"
        >
          {{ t('strategy.actionCopy') }}
        </el-button>
        <details class="strategy-card-more">
          <summary :aria-label="t('strategy.moreActions')">
            <el-icon aria-hidden="true">
              <MoreFilled />
            </el-icon>
            <span class="sr-only">{{ t('strategy.moreActions') }}</span>
          </summary>
          <div
            class="strategy-card-more-menu"
            role="menu"
          >
            <button
              type="button"
              role="menuitem"
              @click="emit('detail', tpl)"
            >
              {{ t('strategy.detailLabel') }}
            </button>
            <button
              type="button"
              role="menuitem"
              @click="emit('backtest', tpl)"
            >
              {{ t('strategy.typeBacktest') }}
            </button>
          </div>
        </details>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { MoreFilled } from '@element-plus/icons-vue'

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

<style scoped>
.strategy-card-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 12px;
  border-top: 1px solid var(--border-color-light);
  padding-top: 12px;
}

.strategy-card-more {
  position: relative;
}

.strategy-card-more summary {
  display: inline-flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-regular);
  cursor: pointer;
  list-style: none;
}

.strategy-card-more summary::-webkit-details-marker {
  display: none;
}

.strategy-card-more[open] summary {
  border-color: color-mix(in srgb, var(--primary-color) 48%, var(--border-color) 52%);
  color: var(--primary-color);
}

.strategy-card-more-menu {
  position: absolute;
  z-index: 2;
  right: 0;
  bottom: calc(100% + 6px);
  display: grid;
  min-width: 148px;
  gap: 4px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color-overlay);
  padding: 6px;
  box-shadow: var(--shadow-sm, none);
}

.strategy-card-more-menu button {
  width: 100%;
  border: 0;
  border-radius: 6px;
  background: transparent;
  padding: 8px 10px;
  color: var(--text-color-regular);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.strategy-card-more-menu button:hover,
.strategy-card-more-menu button:focus-visible {
  background: var(--fill-color-light);
  color: var(--primary-color);
  outline: none;
}
</style>
