<template>
  <el-dropdown
    trigger="click"
    @command="handleChange"
  >
    <button
      type="button"
      class="language-switcher"
      :aria-label="t('nav.languageSwitcher')"
    >
      <el-icon><Promotion /></el-icon>
      <span class="language-label">{{ currentLabel }}</span>
    </button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="entry in LOCALE_ENTRIES"
          :key="entry.code"
          :command="entry.code"
          :class="{ 'is-active': currentLocale === entry.code }"
        >
          {{ entry.label }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Promotion } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { setLocale, getLocaleLabel } from '@/i18n'
import { LOCALE_ENTRIES } from '@/i18n/locales/registry'

const { t, locale } = useI18n()

const currentLocale = computed(() => locale.value)
const currentLabel = computed(() => getLocaleLabel(currentLocale.value))

function handleChange(code: string): void {
  if (locale.value === code) {
    return
  }
  const result = setLocale(code)
  if (result.ok && result.reason === 'persist-failed') {
    ElMessage.warning(t('common.localePersistFailed'))
  }
}
</script>

<style scoped>
.language-switcher {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 8px 12px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  transition: background-color 0.2s;
}

.language-switcher:hover {
  background-color: var(--el-fill-color-light);
}

.language-switcher:focus-visible {
  outline: 2px solid var(--el-color-primary, #409eff);
  outline-offset: 2px;
}

.language-label {
  font-size: 14px;
}

:deep(.el-dropdown-menu__item.is-active) {
  color: var(--el-color-primary);
  font-weight: 600;
}
</style>
