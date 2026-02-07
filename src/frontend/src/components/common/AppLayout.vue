<template>
  <el-container class="min-h-screen">
    <!-- 侧边栏 -->
    <el-aside width="220px" class="bg-slate-900">
      <div class="p-4">
        <h1 class="text-xl font-bold text-white flex items-center gap-2">
          <el-icon><TrendCharts /></el-icon>
          Backtrader Web
        </h1>
      </div>
      
      <el-menu
        :default-active="currentRoute"
        class="!border-none bg-transparent"
        text-color="#94a3b8"
        active-text-color="#3b82f6"
        router
      >
        <el-menu-item index="/">
          <el-icon><HomeFilled /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/backtest">
          <el-icon><DataLine /></el-icon>
          <span>回测分析</span>
        </el-menu-item>
        <el-menu-item index="/optimization">
          <el-icon><MagicStick /></el-icon>
          <span>参数优化</span>
        </el-menu-item>
        <el-menu-item index="/strategy">
          <el-icon><Document /></el-icon>
          <span>策略管理</span>
        </el-menu-item>
        <el-menu-item index="/data">
          <el-icon><Grid /></el-icon>
          <span>数据查询</span>
        </el-menu-item>
        <el-menu-item index="/live-trading">
          <el-icon><VideoPlay /></el-icon>
          <span>实盘交易</span>
        </el-menu-item>
        <el-menu-item index="/portfolio">
          <el-icon><TrendCharts /></el-icon>
          <span>组合管理</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    
    <!-- 主内容区 -->
    <el-container>
      <!-- 顶部栏 -->
      <el-header class="flex items-center justify-between bg-white border-b px-6">
        <div class="text-lg font-medium">{{ pageTitle }}</div>
        
        <div class="flex items-center gap-4">
          <el-tooltip :content="isDark ? '切换亮色模式' : '切换暗色模式'">
            <el-button circle @click="toggleTheme">
              <el-icon><Sunny v-if="isDark" /><Moon v-else /></el-icon>
            </el-button>
          </el-tooltip>
          <el-dropdown @command="handleCommand">
            <span class="flex items-center gap-2 cursor-pointer">
              <el-avatar :size="32">
                {{ user?.username?.charAt(0).toUpperCase() }}
              </el-avatar>
              <span>{{ user?.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人设置</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      
      <!-- 页面内容 -->
      <el-main class="bg-gray-50 p-6">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  HomeFilled,
  DataLine,
  Document,
  Grid,
  Setting,
  ArrowDown,
  TrendCharts,
  Sunny,
  Moon,
  VideoPlay,
  MagicStick,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const currentRoute = computed(() => route.path)
const user = computed(() => authStore.user)

const isDark = ref(localStorage.getItem('theme') === 'dark')

function toggleTheme() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}

onMounted(() => {
  if (isDark.value) {
    document.documentElement.classList.add('dark')
  }
})

const pageTitle = computed(() => {
  const titles: Record<string, string> = {
    '/': '仪表盘',
    '/backtest': '回测分析',
    '/optimization': '参数优化',
    '/strategy': '策略管理',
    '/data': '数据查询',
    '/live-trading': '实盘交易',
    '/portfolio': '组合管理',
    '/settings': '系统设置',
  }
  return titles[route.path] || 'Backtrader Web'
})

function handleCommand(command: string) {
  if (command === 'logout') {
    authStore.logout()
    router.push('/login')
  } else if (command === 'profile') {
    router.push('/settings')
  }
}
</script>

<style scoped>
.el-aside {
  transition: width 0.3s;
}

.el-menu-item {
  margin: 4px 8px;
  border-radius: 8px;
}

.el-menu-item:hover {
  background-color: rgba(255, 255, 255, 0.1) !important;
}

.el-menu-item.is-active {
  background-color: rgba(59, 130, 246, 0.2) !important;
}
</style>
