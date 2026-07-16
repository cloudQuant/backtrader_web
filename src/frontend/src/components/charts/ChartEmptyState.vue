<template>
  <div
    class="chart-empty-state"
    role="status"
  >
    <strong>{{ title }}</strong>
    <span>{{ description }}</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description: string
}>()
</script>

<style scoped>
.chart-empty-state {
  display: grid;
  min-height: 180px;
  place-content: center;
  gap: 6px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-regular);
  text-align: center;
}

.chart-empty-state strong {
  color: var(--text-color-primary);
  font-size: 14px;
}

.chart-empty-state span {
  max-width: 360px;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}
</style>
