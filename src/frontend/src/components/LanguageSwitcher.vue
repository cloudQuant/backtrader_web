<template>
  <el-dropdown
    trigger="click"
    @command="handleChange"
  >
    <span class="language-switcher">
      <el-icon><Promotion /></el-icon>
      <span class="language-label">{{ currentLabel }}</span>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item 
          v-for="loc in locales" 
          :key="loc.value" 
          :command="loc.value"
          :class="{ 'is-active': currentLocale === loc.value }"
        >
          {{ loc.label }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Promotion } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { setLocale, getLocaleLabel } from '@/i18n'

const { locale } = useI18n()

const locales = [
  { value: 'zh-CN', label: '中文' },
  { value: 'en-US', label: 'English' },
]

const currentLocale = computed(() => locale.value)

const currentLabel = computed(() => getLocaleLabel(currentLocale.value))

function handleChange(lang: string): void {
  if (locale.value !== lang) {
    setLocale(lang)
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
  transition: background-color 0.2s;
}

.language-switcher:hover {
  background-color: var(--el-fill-color-light);
}

.language-label {
  font-size: 14px;
}

:deep(.el-dropdown-menu__item.is-active) {
  color: var(--el-color-primary);
  font-weight: 600;
}
</style>
