<template>
  <el-dropdown @command="handleCommand" trigger="click" placement="bottom">
    <el-button 
      circle 
      :icon="currentIcon"
      data-shortcut="toggle-dark-mode"
      :title="`当前主题: ${themeText}`"
    />
    
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item 
          command="light" 
          :class="{ 'is-active': themeStore.mode === 'light' }"
        >
          <el-icon><Sunny /></el-icon>
          <span class="ml-2">亮色模式</span>
        </el-dropdown-item>
        <el-dropdown-item 
          command="dark" 
          :class="{ 'is-active': themeStore.mode === 'dark' }"
        >
          <el-icon><Moon /></el-icon>
          <span class="ml-2">暗色模式</span>
        </el-dropdown-item>
        <el-dropdown-item 
          command="auto" 
          :class="{ 'is-active': themeStore.mode === 'auto' }"
          divided
        >
          <el-icon><Monitor /></el-icon>
          <span class="ml-2">跟随系统</span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useThemeStore, type ThemeMode } from '@/stores/theme'
import { Moon, Sunny, Monitor } from '@element-plus/icons-vue'

const themeStore = useThemeStore()

const currentIcon = computed(() => {
  switch (themeStore.mode) {
    case 'dark':
      return Moon
    case 'light':
      return Sunny
    case 'auto':
      return Monitor
    default:
      return Sunny
  }
})

const themeText = computed(() => {
  switch (themeStore.mode) {
    case 'dark':
      return '暗色'
    case 'light':
      return '亮色'
    case 'auto':
      return '自动'
    default:
      return '亮色'
  }
})

function handleCommand(command: string) {
  themeStore.setTheme(command as ThemeMode)
}
</script>

<style scoped>
.is-active {
  background-color: var(--el-dropdown-menuitem-hover-fill);
  color: var(--el-color-primary);
}
</style>
