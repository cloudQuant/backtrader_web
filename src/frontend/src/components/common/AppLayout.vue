<template>
  <el-container class="min-h-screen">
    <!-- 桌面端侧边栏 -->
    <el-aside
      width="220px"
      class="app-sidebar-desktop"
      role="navigation"
      :aria-label="t('nav.primary')"
    >
      <div class="p-4">
        <h1 class="text-xl font-bold sidebar-title flex items-center gap-2">
          <el-icon aria-hidden="true">
            <TrendCharts />
          </el-icon>
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
          <span>{{ t('nav.home') }}</span>
        </el-menu-item>
        <el-menu-item index="/ai-chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>{{ t('nav.aiChat') }}</span>
        </el-menu-item>
        <el-menu-item
          v-if="user?.is_admin"
          index="/admin/ai-observability"
        >
          <el-icon><ChatDotRound /></el-icon>
          <span>{{ t('nav.aiCost') }}</span>
        </el-menu-item>
        <el-menu-item
          v-if="user?.is_admin"
          index="/admin/prompt-templates"
        >
          <el-icon><Document /></el-icon>
          <span>{{ t('nav.promptGovernance') }}</span>
        </el-menu-item>
        <el-menu-item index="/data">
          <el-icon><Grid /></el-icon>
          <span>{{ t('nav.data') }}</span>
        </el-menu-item>
        <el-menu-item index="/quote">
          <el-icon><Stopwatch /></el-icon>
          <span>{{ t('nav.quote') }}</span>
        </el-menu-item>
        <el-menu-item index="/workspace">
          <el-icon><Aim /></el-icon>
          <span>{{ t('nav.workspace') }}</span>
        </el-menu-item>
        <el-menu-item index="/trading">
          <el-icon><TrendCharts /></el-icon>
          <span>{{ t('nav.trading') }}</span>
        </el-menu-item>
        <el-menu-item index="/strategy">
          <el-icon><Document /></el-icon>
          <span>{{ t('nav.strategy') }}</span>
        </el-menu-item>
        <el-menu-item index="/portfolio">
          <el-icon><TrendCharts /></el-icon>
          <span>{{ t('nav.portfolio') }}</span>
        </el-menu-item>
        <el-menu-item index="/brokers">
          <el-icon><Monitor /></el-icon>
          <span>{{ t('nav.brokers') }}</span>
        </el-menu-item>
        <el-menu-item index="/portfolio-ledger">
          <el-icon><TrendCharts /></el-icon>
          <span>{{ t('nav.portfolioLedger') }}</span>
        </el-menu-item>
        <el-menu-item index="/equity-research">
          <el-icon><Document /></el-icon>
          <span>{{ t('nav.equityResearch') }}</span>
        </el-menu-item>
        <el-menu-item index="/news-intelligence">
          <el-icon><Document /></el-icon>
          <span>{{ t('nav.newsIntelligence') }}</span>
        </el-menu-item>
        <el-menu-item index="/options-chain">
          <el-icon><Document /></el-icon>
          <span>{{ t('nav.optionsChain') }}</span>
        </el-menu-item>
        <el-menu-item index="/scanners">
          <el-icon><Aim /></el-icon>
          <span>{{ t('nav.scanners') }}</span>
        </el-menu-item>
        <el-menu-item index="/quant-tools">
          <el-icon><ChatDotRound /></el-icon>
          <span>{{ t('nav.quantTools') }}</span>
        </el-menu-item>
        <el-menu-item index="/gateways">
          <el-icon><Monitor /></el-icon>
          <span>{{ t('nav.gateways') }}</span>
        </el-menu-item>
        <el-menu-item index="/knowledge-base">
          <el-icon><Collection /></el-icon>
          <span>{{ t('nav.knowledgeBase') }}</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>{{ t('nav.settings') }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 移动端侧边栏抽屉 -->
    <el-drawer
      id="mobile-sidebar-drawer"
      v-model="mobileMenuOpen"
      direction="ltr"
      :size="280"
      :show-close="false"
      class="mobile-sidebar-drawer"
      :z-index="2000"
      role="dialog"
      :aria-label="t('nav.primary')"
      aria-modal="true"
    >
      <template #header>
        <div class="flex items-center justify-between w-full">
          <h1 class="text-lg font-bold sidebar-title flex items-center gap-2">
            <el-icon aria-hidden="true">
              <TrendCharts />
            </el-icon>
            Backtrader Web
          </h1>
          <button
            type="button"
            class="sidebar-title cursor-pointer text-xl drawer-close-btn"
            :aria-label="t('nav.closeMenu')"
            @click="mobileMenuOpen = false"
          >
            <el-icon aria-hidden="true">
              <Close />
            </el-icon>
          </button>
        </div>
      </template>
      <el-menu
        :default-active="currentRoute"
        class="!border-none bg-transparent sidebar-menu mobile-sidebar-menu"
        @select="handleMobileMenuSelect"
      >
        <el-menu-item index="/">
          <el-icon><HomeFilled /></el-icon>
          <span>{{ t('nav.home') }}</span>
        </el-menu-item>
        <el-menu-item index="/ai-chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>{{ t('nav.aiChat') }}</span>
        </el-menu-item>
        <el-menu-item
          v-if="user?.is_admin"
          index="/admin/ai-observability"
        >
          <el-icon><ChatDotRound /></el-icon>
          <span>{{ t('nav.aiCost') }}</span>
        </el-menu-item>
        <el-menu-item
          v-if="user?.is_admin"
          index="/admin/prompt-templates"
        >
          <el-icon><Document /></el-icon>
          <span>{{ t('nav.promptGovernance') }}</span>
        </el-menu-item>
        <el-menu-item index="/data">
          <el-icon><Grid /></el-icon>
          <span>{{ t('nav.data') }}</span>
        </el-menu-item>
        <el-menu-item index="/quote">
          <el-icon><Stopwatch /></el-icon>
          <span>{{ t('nav.quote') }}</span>
        </el-menu-item>
        <el-menu-item index="/workspace">
          <el-icon><Aim /></el-icon>
          <span>{{ t('nav.workspace') }}</span>
        </el-menu-item>
        <el-menu-item index="/trading">
          <el-icon><TrendCharts /></el-icon>
          <span>{{ t('nav.trading') }}</span>
        </el-menu-item>
        <el-menu-item index="/strategy">
          <el-icon><Document /></el-icon>
          <span>{{ t('nav.strategy') }}</span>
        </el-menu-item>
        <el-menu-item index="/portfolio">
          <el-icon><TrendCharts /></el-icon>
          <span>{{ t('nav.portfolio') }}</span>
        </el-menu-item>
        <el-menu-item index="/brokers">
          <el-icon><Monitor /></el-icon>
          <span>{{ t('nav.brokers') }}</span>
        </el-menu-item>
        <el-menu-item index="/portfolio-ledger">
          <el-icon><TrendCharts /></el-icon>
          <span>{{ t('nav.portfolioLedger') }}</span>
        </el-menu-item>
        <el-menu-item index="/equity-research">
          <el-icon><Document /></el-icon>
          <span>{{ t('nav.equityResearch') }}</span>
        </el-menu-item>
        <el-menu-item index="/news-intelligence">
          <el-icon><Document /></el-icon>
          <span>{{ t('nav.newsIntelligence') }}</span>
        </el-menu-item>
        <el-menu-item index="/options-chain">
          <el-icon><Document /></el-icon>
          <span>{{ t('nav.optionsChain') }}</span>
        </el-menu-item>
        <el-menu-item index="/scanners">
          <el-icon><Aim /></el-icon>
          <span>{{ t('nav.scanners') }}</span>
        </el-menu-item>
        <el-menu-item index="/quant-tools">
          <el-icon><ChatDotRound /></el-icon>
          <span>{{ t('nav.quantTools') }}</span>
        </el-menu-item>
        <el-menu-item index="/gateways">
          <el-icon><Monitor /></el-icon>
          <span>{{ t('nav.gateways') }}</span>
        </el-menu-item>
        <el-menu-item index="/knowledge-base">
          <el-icon><Collection /></el-icon>
          <span>{{ t('nav.knowledgeBase') }}</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>{{ t('nav.settings') }}</span>
        </el-menu-item>
      </el-menu>
    </el-drawer>
    
    <!-- 主内容区 -->
    <el-container>
      <!-- 顶部栏 -->
      <el-header class="app-header flex items-center justify-between border-b px-6">
        <div class="app-header-left flex items-center gap-4 flex-1 min-w-0 flex-wrap">
          <!-- 移动端汉堡按钮 -->
          <button
            type="button"
            class="hamburger-btn"
            :aria-label="t('nav.openMenu')"
            aria-controls="mobile-sidebar-drawer"
            :aria-expanded="mobileMenuOpen"
            @click="mobileMenuOpen = true"
          >
            <el-icon
              :size="22"
              aria-hidden="true"
            >
              <Fold />
            </el-icon>
          </button>
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
                {{ t('nav.paperTrading') }}
              </el-radio-button>
              <el-radio-button value="live">
                {{ t('nav.liveTrading') }}
              </el-radio-button>
            </el-radio-group>
          </div>
        </div>
        
        <div class="flex items-center gap-4 shrink-0">
          <ThemeSwitcher />
          <el-dropdown @command="handleCommand">
            <button
              type="button"
              class="user-dropdown-trigger flex items-center gap-2 cursor-pointer"
              :aria-label="user?.username ? `${t('nav.userMenu')} (${user.username})` : t('nav.userMenu')"
            >
              <el-avatar
                :size="32"
                :alt="user?.username || ''"
              >
                {{ user?.username?.charAt(0).toUpperCase() }}
              </el-avatar>
              <span class="app-header-user-name">{{ user?.username }}</span>
              <el-icon aria-hidden="true">
                <ArrowDown />
              </el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  {{ t('nav.profile') }}
                </el-dropdown-item>
                <el-dropdown-item
                  command="logout"
                  divided
                >
                  {{ t('auth.logout') }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      
      <!-- 页面内容 -->
      <el-main
        class="app-main-content bg-gray-50 p-6"
        role="main"
      >
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
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

const { t } = useI18n()
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
  const prefixes = ['/ai-chat', '/admin/ai-observability', '/admin/prompt-templates', '/workspace', '/trading', '/strategy', '/data', '/gateways', '/knowledge-base', '/quote', '/portfolio', '/portfolio-ledger', '/equity-research', '/news-intelligence', '/options-chain', '/scanners', '/quant-tools', '/settings']
  for (const prefix of prefixes) {
    if (p.startsWith(prefix + '/') || p === prefix) return prefix
  }
  return p
})
const user = computed(() => authStore.user)

const pageTitle = computed(() => {
  const titles: Record<string, string> = {
    '/': t('nav.dashboard'),
    '/ai-chat': t('nav.aiChat'),
    '/admin/ai-observability': t('nav.aiCost'),
    '/admin/prompt-templates': t('nav.promptGovernance'),
    '/strategy': t('nav.strategy'),
    '/data': t('nav.data'),
    '/gateways': t('nav.gateways'),
    '/knowledge-base': t('nav.knowledgeBase'),
    '/quote': t('nav.quote'),
    '/workspace': t('nav.workspace'),
    '/trading': t('nav.trading'),
    '/portfolio': t('nav.portfolio'),
    '/portfolio-ledger': t('nav.portfolioLedger'),
    '/equity-research': t('nav.equityResearch'),
    '/news-intelligence': t('nav.newsIntelligence'),
    '/options-chain': t('nav.optionsChain'),
    '/scanners': t('nav.scanners'),
    '/quant-tools': t('nav.quantTools'),
    '/settings': t('nav.settings'),
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
  background-color: var(--bg-color);
  border-color: var(--border-color);
}

.sidebar-title {
  color: var(--sidebar-text-color);
}

/* Iteration 175 §3 — a11y: keep button visual presentation matching prior
 * <span>/<div> elements while gaining keyboard focus / role semantics. */
.hamburger-btn {
  background: none;
  border: none;
  padding: 0;
}

.drawer-close-btn {
  background: none;
  border: none;
  padding: 0;
}

.drawer-close-btn:focus-visible,
.hamburger-btn:focus-visible,
.user-dropdown-trigger:focus-visible {
  outline: 2px solid var(--el-color-primary, #409eff);
  outline-offset: 2px;
}

.user-dropdown-trigger {
  background: none;
  border: none;
  padding: 0;
  color: inherit;
  font: inherit;
}
</style>
