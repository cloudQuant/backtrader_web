<template>
  <section class="asset-detail-panel" aria-labelledby="futures-panel-title">
    <div class="panel-head">
      <span class="panel-kicker">期货合约</span>
      <h3 id="futures-panel-title">合约结构</h3>
    </div>
    <dl class="detail-grid">
      <div>
        <dt>到期时间</dt>
        <dd>{{ identity?.details.expiry_at || '未提供' }}</dd>
      </div>
      <div>
        <dt>合约乘数</dt>
        <dd>{{ identity?.details.contract_multiplier || '未提供' }}</dd>
      </div>
      <div>
        <dt>交易日历</dt>
        <dd>{{ identity?.details.trading_calendar_id || '未提供' }}</dd>
      </div>
      <div>
        <dt>场所</dt>
        <dd>{{ identity?.venue || '未提供' }}</dd>
      </div>
      <div>
        <dt>基差/展期</dt>
        <dd>{{ details?.basis ?? '未提供' }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup lang="ts">
import type { InstrumentIdentity } from '@/api/assetResearch'

defineProps<{
  identity?: InstrumentIdentity | null
  details?: Record<string, unknown> | null
}>()
</script>

<style scoped>
.asset-detail-panel { padding: 20px; border: 1px solid var(--el-border-color-light); border-radius: 8px; }
.panel-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; }
.panel-kicker { color: var(--el-color-primary); font-size: 12px; }
h3 { margin: 4px 0 0; font-size: 18px; }
.detail-grid { display: grid; gap: 10px; margin: 16px 0 0; }
.detail-grid div { display: grid; gap: 4px; }
dt { color: var(--el-text-color-secondary); font-size: 12px; }
dd { margin: 0; font-size: 13px; overflow-wrap: anywhere; }
</style>

