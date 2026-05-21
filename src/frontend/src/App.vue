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
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import en from 'element-plus/dist/locale/en.mjs'
import ErrorBoundary from './components/common/ErrorBoundary.vue'

const { locale } = useI18n()

// 根据当前语言返回对应的Element Plus locale
const elementLocale = computed(() => {
  return locale.value === 'zh-CN' ? zhCn : en
})
</script>

<style>
#app {
  width: 100%;
  min-height: 100vh;
}
</style>
