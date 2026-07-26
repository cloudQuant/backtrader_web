<template>
  <div
    class="data-table-skeleton"
    role="status"
    :aria-label="label"
  >
    <span class="sr-only">{{ label }}</span>
    <div
      class="data-table-skeleton__header"
      :style="gridStyle"
    >
      <span
        v-for="column in columns"
        :key="`header-${column}`"
      />
    </div>
    <div
      v-for="row in rows"
      :key="row"
      class="data-table-skeleton__row"
      :style="gridStyle"
    >
      <span
        v-for="column in columns"
        :key="`${row}-${column}`"
        :class="{ 'data-table-skeleton__cell--short': column === columns }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  label: string
  rows?: number
  columns?: number
}>(), {
  rows: 6,
  columns: 5,
})

const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${props.columns}, minmax(0, 1fr))`,
}))
</script>

<style scoped>
.data-table-skeleton {
  display: grid;
  gap: 8px;
  min-height: 260px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  padding: 12px;
}

.data-table-skeleton__header,
.data-table-skeleton__row {
  display: grid;
  gap: 12px;
}

.data-table-skeleton__header {
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-color-light);
}

.data-table-skeleton span:not(.sr-only) {
  display: block;
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(
    90deg,
    var(--fill-color-light) 25%,
    var(--fill-color) 50%,
    var(--fill-color-light) 75%
  );
  background-size: 200% 100%;
  animation: data-table-skeleton-shimmer 1.2s ease-in-out infinite;
}

.data-table-skeleton__header span:not(.sr-only) {
  height: 11px;
}

.data-table-skeleton__cell--short {
  width: 62%;
}

@keyframes data-table-skeleton-shimmer {
  0% {
    background-position: 100% 0;
  }

  100% {
    background-position: -100% 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .data-table-skeleton span:not(.sr-only) {
    animation: none;
  }
}
</style>
