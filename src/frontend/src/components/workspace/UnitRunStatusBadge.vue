<template>
  <div class="status-cell">
    <div class="status-cell__main">
      <span
        class="status-dot"
        :class="statusDotClass(unit)"
      />
      <span class="status-text">{{ statusLabel(unit) }}</span>
    </div>
    <div class="status-cell__meta">
      <el-tag
        size="small"
        effect="plain"
        :type="unit.trading_mode === 'live' ? 'danger' : 'info'"
      >
        {{ unit.trading_mode === 'live' ? '实盘' : '模拟' }}
      </el-tag>
      <span
        v-if="unit.lock_trading"
        class="status-flag"
      >锁交</span>
      <span
        v-if="unit.lock_running"
        class="status-flag"
      >锁运</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { StrategyUnit } from '@/types/workspace'
import { statusDotClass, statusLabel } from '@/composables/useUnitTableRendering'

defineProps<{
  unit: StrategyUnit
}>()
</script>

<style scoped>
.status-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.status-cell__main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-text {
  font-weight: 500;
  color: var(--text-color-regular);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  flex: 0 0 auto;
  background: var(--text-color-placeholder);
}

.status-dot.is-running {
  background: var(--success-color);
  box-shadow: 0 0 0 3px rgb(34 197 94 / 0.14);
}

.status-dot.is-queued {
  background: var(--warning-color);
  box-shadow: 0 0 0 3px rgb(245 158 11 / 0.14);
}

.status-dot.is-error {
  background: var(--danger-color);
  box-shadow: 0 0 0 3px rgb(239 68 68 / 0.14);
}

.status-dot.is-idle {
  background: var(--text-color-placeholder);
}

.status-cell__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.status-flag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  padding: 0 6px;
  height: 20px;
  border-radius: 999px;
  font-size: 11px;
  color: var(--warning-text-color);
  background: var(--warning-surface);
}
</style>
