<template>
  <el-dropdown
    trigger="click"
    @command="handleThemeChange"
  >
    <el-button circle>
      <span class="theme-icon">{{ themeStore.currentThemeIcon }}</span>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="theme in themeStore.themes"
          :key="theme.value"
          :command="theme.value"
          :class="{ 'is-active': themeStore.mode === theme.value }"
        >
          <span class="theme-option">
            <span class="theme-option-icon">{{ theme.icon }}</span>
            <span class="theme-option-text">
              <span class="theme-option-label">{{ theme.label }}</span>
              <span class="theme-option-desc">{{ theme.description }}</span>
            </span>
            <el-icon
              v-if="themeStore.mode === theme.value"
              class="theme-check"
            >
              <Check />
            </el-icon>
          </span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { Check } from '@element-plus/icons-vue'
import { useThemeStore, type ThemeMode } from '@/stores/theme'

const themeStore = useThemeStore()

function handleThemeChange(theme: ThemeMode) {
  themeStore.setTheme(theme)
}
</script>

<style scoped>
.theme-icon {
  font-size: 16px;
  line-height: 1;
}

.theme-option {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 160px;
}

.theme-option-icon {
  font-size: 18px;
  width: 24px;
  text-align: center;
}

.theme-option-text {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.theme-option-label {
  font-size: 14px;
  font-weight: 500;
}

.theme-option-desc {
  font-size: 12px;
  color: var(--text-color-secondary, #909399);
}

.theme-check {
  color: var(--accent-color, #409eff);
  margin-left: auto;
}

:deep(.is-active) {
  background-color: var(--fill-color-light, #f5f7fa);
}
</style>
