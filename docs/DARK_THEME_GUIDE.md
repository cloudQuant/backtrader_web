# Backtrader Web - 暗色主题实现指南

> 本文档提供暗色主题的完整实现方案

---

## 设计规范

### 颜色系统

#### 亮色主题 (Light Mode)

```css
--color-primary: #409EFF
--color-success: #67C23A
--color-warning: #E6A23C
--color-danger: #F56C6C
--color-info: #909399

--bg-color: #FFFFFF
--bg-color-page: #F2F3F5
--bg-color-overlay: #FFFFFF

--text-color-primary: #303133
--text-color-regular: #606266
--text-color-secondary: #909399
--text-color-placeholder: #C0C4CC

--border-color: #DCDFE6
--border-color-light: #E4E7ED
--border-color-lighter: #EBEEF5
```

#### 暗色主题 (Dark Mode)

```css
--color-primary: #409EFF
--color-success: #67C23A
--color-warning: #E6A23C
--color-danger: #F56C6C
--color-info: #909399

--bg-color: #141414
--bg-color-page: #0A0A0A
--bg-color-overlay: #1D1D1D

--text-color-primary: #E5EAF3
--text-color-regular: #CFD3DC
--text-color-secondary: #A3A6AD
--text-color-placeholder: #8D9095

--border-color: #4C4D4F
--border-color-light: #414243
--border-color-lighter: #363637
```

---

## 实现步骤

### 步骤1: 创建主题配置

创建 `src/frontend/src/stores/theme.ts`:

```typescript
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'auto'

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(
    (localStorage.getItem('theme-mode') as ThemeMode) || 'light'
  )

  // 应用主题
  function applyTheme(theme: 'light' | 'dark') {
    const html = document.documentElement
    
    if (theme === 'dark') {
      html.classList.add('dark')
    } else {
      html.classList.remove('dark')
    }
    
    // 更新 CSS 变量
    updateCSSVariables(theme)
  }

  // 更新 CSS 变量
  function updateCSSVariables(theme: 'light' | 'dark') {
    const root = document.documentElement
    
    if (theme === 'dark') {
      root.style.setProperty('--bg-color', '#141414')
      root.style.setProperty('--bg-color-page', '#0A0A0A')
      root.style.setProperty('--text-color-primary', '#E5EAF3')
      root.style.setProperty('--text-color-regular', '#CFD3DC')
      root.style.setProperty('--border-color', '#4C4D4F')
    } else {
      root.style.setProperty('--bg-color', '#FFFFFF')
      root.style.setProperty('--bg-color-page', '#F2F3F5')
      root.style.setProperty('--text-color-primary', '#303133')
      root.style.setProperty('--text-color-regular', '#606266')
      root.style.setProperty('--border-color', '#DCDFE6')
    }
  }

  // 切换主题
  function toggleTheme() {
    const currentTheme = mode.value === 'dark' ? 'light' : 'dark'
    setTheme(currentTheme)
  }

  // 设置主题
  function setTheme(theme: ThemeMode) {
    mode.value = theme
    localStorage.setItem('theme-mode', theme)
    
    if (theme === 'auto') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      applyTheme(prefersDark ? 'dark' : 'light')
    } else {
      applyTheme(theme)
    }
  }

  // 初始化
  function init() {
    if (mode.value === 'auto') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      applyTheme(prefersDark ? 'dark' : 'light')
      
      // 监听系统主题变化
      window.matchMedia('(prefers-color-scheme: dark)')
        .addEventListener('change', (e) => {
          if (mode.value === 'auto') {
            applyTheme(e.matches ? 'dark' : 'light')
          }
        })
    } else {
      applyTheme(mode.value)
    }
  }

  return {
    mode,
    toggleTheme,
    setTheme,
    init
  }
})
```

### 步骤2: 更新 Tailwind 配置

更新 `tailwind.config.js`:

```javascript
module.exports = {
  darkMode: 'class', // 使用 class 策略
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 亮色主题
        light: {
          bg: '#FFFFFF',
          'bg-page': '#F2F3F5',
          'text-primary': '#303133',
          'text-regular': '#606266',
          border: '#DCDFE6',
        },
        // 暗色主题
        dark: {
          bg: '#141414',
          'bg-page': '#0A0A0A',
          'text-primary': '#E5EAF3',
          'text-regular': '#CFD3DC',
          border: '#4C4D4F',
        }
      }
    },
  },
  plugins: [],
}
```

### 步骤3: 创建主题切换组件

创建 `src/frontend/src/components/common/ThemeToggle.vue`:

```vue
<template>
  <el-dropdown @command="handleCommand" trigger="click">
    <el-button circle>
      <el-icon v-if="themeStore.mode === 'dark'">
        <Moon />
      </el-icon>
      <el-icon v-else-if="themeStore.mode === 'light'">
        <Sunny />
      </el-icon>
      <el-icon v-else>
        <Monitor />
      </el-icon>
    </el-button>
    
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="light" :class="{ 'is-active': themeStore.mode === 'light' }">
          <el-icon><Sunny /></el-icon>
          <span class="ml-2">亮色模式</span>
        </el-dropdown-item>
        <el-dropdown-item command="dark" :class="{ 'is-active': themeStore.mode === 'dark' }">
          <el-icon><Moon /></el-icon>
          <span class="ml-2">暗色模式</span>
        </el-dropdown-item>
        <el-dropdown-item command="auto" :class="{ 'is-active': themeStore.mode === 'auto' }">
          <el-icon><Monitor /></el-icon>
          <span class="ml-2">跟随系统</span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { useThemeStore } from '@/stores/theme'
import { Moon, Sunny, Monitor } from '@element-plus/icons-vue'

const themeStore = useThemeStore()

function handleCommand(command: string) {
  themeStore.setTheme(command as any)
}
</script>
```

### 步骤4: 更新全局样式

更新 `src/frontend/src/style.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  /* 亮色主题变量 */
  --bg-color: #FFFFFF;
  --bg-color-page: #F2F3F5;
  --bg-color-overlay: #FFFFFF;
  --text-color-primary: #303133;
  --text-color-regular: #606266;
  --text-color-secondary: #909399;
  --border-color: #DCDFE6;
}

.dark {
  /* 暗色主题变量 */
  --bg-color: #141414;
  --bg-color-page: #0A0A0A;
  --bg-color-overlay: #1D1D1D;
  --text-color-primary: #E5EAF3;
  --text-color-regular: #CFD3DC;
  --text-color-secondary: #A3A6AD;
  --border-color: #4C4D4F;
}

body {
  background-color: var(--bg-color-page);
  color: var(--text-color-primary);
  transition: background-color 0.3s, color 0.3s;
}

/* Element Plus 暗色主题覆盖 */
.dark .el-card {
  background-color: var(--bg-color-overlay);
  border-color: var(--border-color);
}

.dark .el-table {
  background-color: var(--bg-color);
  color: var(--text-color-primary);
}

.dark .el-table th.el-table__cell {
  background-color: var(--bg-color-page);
}

.dark .el-table tr {
  background-color: var(--bg-color);
}

.dark .el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell {
  background: var(--bg-color-page);
}

/* 自定义组件暗色主题 */
.dark .bg-gray-50 {
  background-color: rgba(255, 255, 255, 0.05) !important;
}

.dark .text-gray-500 {
  color: var(--text-color-secondary) !important;
}

.dark .text-gray-800 {
  color: var(--text-color-primary) !important;
}
```

### 步骤5: 在 App.vue 中初始化

```vue
<script setup lang="ts">
import { onMounted } from 'vue'
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()

onMounted(() => {
  themeStore.init()
})
</script>
```

---

## Element Plus 暗色主题

### 安装依赖

```bash
npm install @element-plus/theme-chalk
```

### 导入暗色主题

在 `main.ts` 中:

```typescript
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css' // 暗色主题
import App from './App.vue'

const app = createApp(App)
app.use(ElementPlus)
app.mount('#app')
```

---

## 图表暗色主题

### Echarts 暗色配置

```typescript
const darkTheme = {
  backgroundColor: 'transparent',
  textStyle: {
    color: '#CFD3DC'
  },
  title: {
    textStyle: {
      color: '#E5EAF3'
    }
  },
  legend: {
    textStyle: {
      color: '#CFD3DC'
    }
  },
  xAxis: {
    axisLine: {
      lineStyle: {
        color: '#4C4D4F'
      }
    },
    axisLabel: {
      color: '#A3A6AD'
    }
  },
  yAxis: {
    axisLine: {
      lineStyle: {
        color: '#4C4D4F'
      }
    },
    axisLabel: {
      color: '#A3A6AD'
    },
    splitLine: {
      lineStyle: {
        color: '#363637'
      }
    }
  },
  grid: {
    borderColor: '#4C4D4F'
  }
}
```

---

## 测试检查清单

### 功能测试

- [ ] 点击主题切换按钮，主题正确切换
- [ ] 刷新页面后主题保持
- [ ] "跟随系统"模式正确响应系统主题变化
- [ ] 所有页面在暗色模式下可读
- [ ] 图表在暗色模式下显示正常
- [ ] 表格在暗色模式下显示正常
- [ ] 表单在暗色模式下显示正常

### 视觉测试

- [ ] 颜色对比度符合 WCAG AA 标准
- [ ] 文本在两种主题下都清晰可读
- [ ] 边框和分隔线在暗色模式下可见
- [ ] 悬停状态在两种主题下都明显
- [ ] 聚焦状态在两种主题下都明显

---

## 最佳实践

1. **使用 CSS 变量** - 便于动态切换
2. **避免硬编码颜色** - 使用 Tailwind 类或 CSS 变量
3. **测试两种主题** - 确保所有组件在两种模式下都正常
4. **考虑可访问性** - 确保颜色对比度足够
5. **平滑过渡** - 使用 CSS transition 避免突兀切换

---

## 快捷键集成

在 `useKeyboardShortcuts.ts` 中添加:

```typescript
// 切换暗色模式: Ctrl/Cmd + D
registerShortcut({
  key: 'd',
  ctrlKey: true,
  description: '切换暗色模式',
  action: () => themeStore.toggleTheme()
})
```

---

**预计开发时间**: 1-2 天  
**优先级**: P0（高用户体验价值）
