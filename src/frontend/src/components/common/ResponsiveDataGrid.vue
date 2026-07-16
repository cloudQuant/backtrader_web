<template>
  <div class="responsive-data-grid">
    <div class="responsive-data-grid__desktop">
      <slot name="desktop" />
    </div>
    <section
      class="responsive-data-grid__mobile"
      :aria-label="mobileLabel"
    >
      <slot name="mobile" />
    </section>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  /** Accessible name for the mobile list/card representation. */
  mobileLabel: string
}>()
</script>

<style scoped>
.responsive-data-grid__mobile {
  display: none;
}

@media (max-width: 700px) {
  .responsive-data-grid__desktop {
    display: none;
  }

  .responsive-data-grid__mobile {
    display: block;
  }
}
</style>
