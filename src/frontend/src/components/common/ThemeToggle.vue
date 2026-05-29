<template>
  <el-dropdown
    trigger="click"
    placement="bottom"
    @command="handleCommand"
  >
    <el-button 
      circle 
      data-shortcut="toggle-dark-mode"
      :title="t('commonUi.themeCurrentLabel', { label: themeStore.currentThemeLabel })"
    >
      <span class="theme-toggle-icon">{{ themeStore.currentThemeIcon }}</span>
    </el-button>
    
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item 
          v-for="theme in themeStore.themes"
          :key="theme.value"
          :command="theme.value" 
          :class="{ 'is-active': themeStore.mode === theme.value }"
        >
          <span class="theme-toggle-option">
            <span>{{ theme.icon }}</span>
            <span class="ml-2">{{ theme.label }}</span>
          </span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useThemeStore, type ThemeMode } from '@/stores/theme'

const { t } = useI18n()
const themeStore = useThemeStore()

function handleCommand(command: string) {
  themeStore.setTheme(command as ThemeMode)
}
</script>

<style scoped>
.theme-toggle-icon {
  font-size: 16px;
  line-height: 1;
}

.theme-toggle-option {
  display: flex;
  align-items: center;
  gap: 4px;
}

.is-active {
  background-color: var(--el-dropdown-menuitem-hover-fill);
  color: var(--el-color-primary);
}
</style>
