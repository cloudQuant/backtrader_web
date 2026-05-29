<template>
  <component
    :is="'div'"
    :key="retryKey"
    style="display: contents"
  >
    <slot v-if="!hasError" />
  </component>
  <div
    v-if="hasError"
    class="error-boundary"
  >
    <el-result
      icon="error"
      :title="fallbackTitle"
      :sub-title="truncatedMessage"
    >
      <template #extra>
        <el-button
          type="primary"
          @click="handleRetry"
        >
          {{ t('commonUi.errorRetry') }}
        </el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onErrorCaptured } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface Props {
  fallbackTitle?: string
}

const props = withDefaults(defineProps<Props>(), {
  fallbackTitle: '',
})
const fallbackTitle = computed(() => props.fallbackTitle || t('commonUi.errorPageTitle'))

const emit = defineEmits<{
  (e: 'error', error: Error, info: string): void
  (e: 'retry'): void
}>()

const hasError = ref(false)
const errorMessage = ref('')
const retryKey = ref(0)

const truncatedMessage = computed(() => {
  if (errorMessage.value.length <= 200) {
    return errorMessage.value
  }
  return errorMessage.value.slice(0, 200) + '...'
})

onErrorCaptured((error: Error, _instance, info: string) => {
  hasError.value = true
  errorMessage.value = error.message || String(error)

  // Always log to console.error
  console.error('[ErrorBoundary]', error, info)

  emit('error', error, info)

  // Prevent error from propagating further
  return false
})

function handleRetry() {
  hasError.value = false
  errorMessage.value = ''
  retryKey.value++
  emit('retry')
}
</script>

<style scoped>
.error-boundary {
  padding: 40px 20px;
  text-align: center;
}
</style>
