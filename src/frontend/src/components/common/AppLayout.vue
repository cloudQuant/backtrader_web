<template>
  <el-container class="min-h-screen">
    <!-- 桌面端侧边栏 -->
    <el-aside
      width="220px"
      class="app-sidebar-desktop"
    >
      <div class="p-4">
        <h1 class="text-xl font-bold sidebar-title flex items-center gap-2">
          <el-icon><TrendCharts /></el-icon>
          Backtrader Web
        </h1>
      </div>
      
      <el-menu
        :default-active="currentRoute"
        class="!border-none bg-transparent sidebar-menu"
        router
      >
        <el-menu-item index="/">
          <el-icon><HomeFilled /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/ai-chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>AI助手</span>
        </el-menu-item>
        <el-menu-item index="/data">
          <el-icon><Grid /></el-icon>
          <span>数据管理</span>
        </el-menu-item>
        <el-menu-item index="/quote">
          <el-icon><Stopwatch /></el-icon>
          <span>行情报价</span>
        </el-menu-item>
        <el-menu-item index="/workspace">
          <el-icon><Aim /></el-icon>
          <span>策略研究</span>
        </el-menu-item>
        <el-menu-item index="/trading">
          <el-icon><TrendCharts /></el-icon>
          <span>策略交易</span>
        </el-menu-item>
        <el-menu-item index="/strategy">
          <el-icon><Document /></el-icon>
          <span>策略管理</span>
        </el-menu-item>
        <el-menu-item index="/portfolio">
          <el-icon><TrendCharts /></el-icon>
          <span>组合管理</span>
        </el-menu-item>
        <el-menu-item index="/gateways">
          <el-icon><Monitor /></el-icon>
          <span>账户管理</span>
        </el-menu-item>
        <el-menu-item index="/knowledge-base">
          <el-icon><Collection /></el-icon>
          <span>知识库</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 移动端侧边栏抽屉 -->
    <el-drawer
      v-model="mobileMenuOpen"
      direction="ltr"
      :size="280"
      :show-close="false"
      class="mobile-sidebar-drawer"
      :z-index="2000"
    >
      <template #header>
        <div class="flex items-center justify-between w-full">
          <h1 class="text-lg font-bold sidebar-title flex items-center gap-2">
            <el-icon><TrendCharts /></el-icon>
            Backtrader Web
          </h1>
          <el-icon
            class="sidebar-title cursor-pointer text-xl"
            @click="mobileMenuOpen = false"
          >
            <Close />
          </el-icon>
        </div>
      </template>
      <el-menu
        :default-active="currentRoute"
        class="!border-none bg-transparent sidebar-menu mobile-sidebar-menu"
        @select="handleMobileMenuSelect"
      >
        <el-menu-item index="/">
          <el-icon><HomeFilled /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/ai-chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>AI助手</span>
        </el-menu-item>
        <el-menu-item index="/data">
          <el-icon><Grid /></el-icon>
          <span>数据管理</span>
        </el-menu-item>
        <el-menu-item index="/quote">
          <el-icon><Stopwatch /></el-icon>
          <span>行情报价</span>
        </el-menu-item>
        <el-menu-item index="/workspace">
          <el-icon><Aim /></el-icon>
          <span>策略研究</span>
        </el-menu-item>
        <el-menu-item index="/trading">
          <el-icon><TrendCharts /></el-icon>
          <span>策略交易</span>
        </el-menu-item>
        <el-menu-item index="/strategy">
          <el-icon><Document /></el-icon>
          <span>策略管理</span>
        </el-menu-item>
        <el-menu-item index="/portfolio">
          <el-icon><TrendCharts /></el-icon>
          <span>组合管理</span>
        </el-menu-item>
        <el-menu-item index="/gateways">
          <el-icon><Monitor /></el-icon>
          <span>账户管理</span>
        </el-menu-item>
        <el-menu-item index="/knowledge-base">
          <el-icon><Collection /></el-icon>
          <span>知识库</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
    </el-drawer>
    
    <!-- 主内容区 -->
    <el-container>
      <!-- 顶部栏 -->
      <el-header class="app-header flex items-center justify-between border-b px-6">
        <div class="app-header-left flex items-center gap-4 flex-1 min-w-0 flex-wrap">
          <!-- 移动端汉堡按钮 -->
          <div
            class="hamburger-btn"
            @click="mobileMenuOpen = true"
          >
            <el-icon :size="22"><Fold /></el-icon>
          </div>
          <div class="flex items-center gap-3 min-w-0 flex-wrap">
            <div class="text-lg font-medium shrink-0">
              {{ pageTitle }}
            </div>
            <div
              id="page-header-title-extra"
              class="app-header-extras flex items-center gap-2 min-w-0 flex-wrap"
            />
          </div>
          <div
            id="page-header-actions"
            class="app-header-extras flex items-center gap-3 flex-wrap"
          />
          <div
            v-if="route.path === '/portfolio'"
            class="app-header-portfolio-toggle"
          >
            <el-radio-group
              v-model="portfolioUiStore.tradingType"
              size="large"
            >
              <el-radio-button value="simulate">
                模拟交易
              </el-radio-button>
              <el-radio-button value="live">
                实盘交易
              </el-radio-button>
            </el-radio-group>
          </div>
        </div>
        
        <div class="flex items-center gap-4 shrink-0">
          <ThemeSwitcher />
          <el-dropdown @command="handleCommand">
            <span class="flex items-center gap-2 cursor-pointer">
              <el-avatar :size="32">
                {{ user?.username?.charAt(0).toUpperCase() }}
              </el-avatar>
              <span class="app-header-user-name">{{ user?.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  个人设置
                </el-dropdown-item>
                <el-dropdown-item
                  command="logout"
                  divided
                >
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      
      <!-- 页面内容 -->
      <el-main class="app-main-content bg-gray-50 p-6">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePortfolioUiStore } from '@/stores/portfolioUi'
import { useThemeStore } from '@/stores/theme'
import ThemeSwitcher from '@/components/common/ThemeSwitcher.vue'
import {
  Aim,
  ChatDotRound,
  Close,
  Collection,
  Fold,
  HomeFilled,
  Document,
  Grid,
  Setting,
  ArrowDown,
  TrendCharts,
  Monitor,
  Stopwatch,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const portfolioUiStore = usePortfolioUiStore()
const themeStore = useThemeStore()

// Mobile sidebar state
const mobileMenuOpen = ref(false)
const isMobile = ref(false)

const MOBILE_BREAKPOINT = 768

function checkMobile() {
  isMobile.value = window.innerWidth < MOBILE_BREAKPOINT
  // Close mobile menu when resizing to desktop
  if (!isMobile.value) {
    mobileMenuOpen.value = false
  }
}

onMounted(() => {
  themeStore.init()
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

function handleMobileMenuSelect(index: string) {
  router.push(index)
  mobileMenuOpen.value = false
}

const currentRoute = computed(() => {
  const p = route.path
  if (p === '/backtest' || p.startsWith('/backtest/')) {
    return '/workspace'
  }
  // Match top-level menu items for nested routes
  const prefixes = ['/ai-chat', '/workspace', '/trading', '/strategy', '/data', '/gateways', '/knowledge-base', '/quote', '/portfolio', '/settings']
  for (const prefix of prefixes) {
    if (p.startsWith(prefix + '/') || p === prefix) return prefix
  }
  return p
})
const user = computed(() => authStore.user)

const pageTitle = computed(() => {
  const titles: Record<string, string> = {
    '/': '仪表盘',
    '/ai-chat': 'AI助手',
    '/strategy': '策略管理',
    '/data': '数据管理',
    '/gateways': '账户管理',
    '/knowledge-base': '知识库',
    '/quote': '行情报价',
    '/workspace': '策略研究',
    '/trading': '策略交易',
    '/portfolio': '组合管理',
    '/settings': '系统设置',
  }
  // Use prefix matching for nested routes (Bug-11 fix)
  return titles[route.path] || titles[currentRoute.value] || 'Backtrader Web'
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

.app-header {
  background-color: var(--bg-color, #ffffff);
  border-color: var(--border-color, #e4e7ed);
}

.sidebar-title {
  color: var(--sidebar-text-color, #303133);
}
</style>
