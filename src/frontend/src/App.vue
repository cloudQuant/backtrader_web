<template>
  <el-config-provider :locale="elementLocale">
    <ErrorBoundary>
      <router-view />
    </ErrorBoundary>
  </el-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  DEFAULT_LOCALE,
  getEntry,
  isSupportedLocale,
} from '@/i18n/locales/registry'
import ErrorBoundary from './components/common/ErrorBoundary.vue'

const { locale } = useI18n()

// Map the active i18n locale to the matching Element Plus locale bundle.
const elementLocale = computed(() => {
  const code = isSupportedLocale(locale.value) ? locale.value : DEFAULT_LOCALE
  return getEntry(code).elementLocale
})
</script>

<style>
#app {
  width: 100%;
  min-height: 100vh;
}
</style>
