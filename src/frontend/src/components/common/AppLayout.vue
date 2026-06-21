<template>
  <el-container class="min-h-screen">
    <!-- Desktop sidebar -->
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
          AI for Trader
        </h1>
      </div>
      
      <el-menu
        :default-active="currentRoute"
        class="!border-none bg-transparent sidebar-menu"
        router
      >
        <el-menu-item
          v-for="domain in visibleDomains"
          :key="domain.id"
          :index="domain.path"
        >
          <el-icon>
            <component :is="resolveIcon(domain.icon)" />
          </el-icon>
          <span>{{ t(domain.labelKey) }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- Mobile sidebar drawer -->
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
            AI for Trader
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
        <el-menu-item
          v-for="domain in visibleDomains"
          :key="domain.id"
          :index="domain.path"
        >
          <el-icon>
            <component :is="resolveIcon(domain.icon)" />
          </el-icon>
          <span>{{ t(domain.labelKey) }}</span>
        </el-menu-item>
      </el-menu>
    </el-drawer>
    
    <!-- Main content -->
    <el-container>
      <!-- Top header -->
      <el-header class="app-header flex items-center justify-between border-b px-6">
        <div class="app-header-left flex items-center gap-4 flex-1 min-w-0 flex-wrap">
          <!-- Mobile hamburger button -->
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
            <nav
              v-if="currentDomainCapabilities.length > 0"
              class="domain-subnav"
              :aria-label="`${currentDomainLabel} ${t('nav.primary')}`"
            >
              <button
                v-for="capability in currentDomainCapabilities"
                :key="capability.id"
                type="button"
                class="domain-subnav-item"
                :class="{ 'domain-subnav-item-active': isCapabilityActive(capability.id) }"
                @click="goToCapability(capability.path)"
              >
                <el-icon aria-hidden="true">
                  <component :is="resolveIcon(capability.icon)" />
                </el-icon>
                <span>{{ capabilityLabel(capability) }}</span>
              </button>
            </nav>
            <div
              id="page-header-title-extra"
              class="app-header-extras flex items-center gap-2 min-w-0 flex-wrap"
            />
          </div>
          <div
            id="page-header-actions"
            class="app-header-extras flex items-center gap-3 flex-wrap"
          />
        </div>
        
        <div class="flex items-center gap-4 shrink-0">
          <ThemeSwitcher />
          <LanguageSwitcher />
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
      
      <!-- Page body -->
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
import { computed, ref, onMounted, onUnmounted, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import ThemeSwitcher from '@/components/common/ThemeSwitcher.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import {
  findCapabilityByPath,
  getCapabilitiesForDomain,
  getDomainByPath,
  getVisibleDomains,
  type Capability,
} from '@/navigation/capabilities'
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

const iconComponents: Record<string, Component> = {
  Aim,
  ChatDotRound,
  Collection,
  Document,
  Grid,
  HomeFilled,
  Monitor,
  Setting,
  Stopwatch,
  TrendCharts,
}

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
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

const user = computed(() => authStore.user)
const isAdmin = computed(() => user.value?.is_admin ?? false)
const visibleDomains = computed(() => getVisibleDomains(isAdmin.value))
const activeDomain = computed(() => getDomainByPath(route.path))
const activeCapability = computed(() => findCapabilityByPath(route.path))
const currentRoute = computed(() => activeDomain.value.path)
const currentDomainCapabilities = computed(() =>
  getCapabilitiesForDomain(activeDomain.value.id, isAdmin.value),
)
const currentDomainLabel = computed(() => t(activeDomain.value.labelKey))

const pageTitle = computed(() => {
  if (activeCapability.value) {
    return capabilityLabel(activeCapability.value)
  }
  return currentDomainLabel.value || 'AI for Trader'
})

function resolveIcon(name: string): Component {
  return iconComponents[name] ?? Document
}

function capabilityLabel(capability: Capability): string {
  if (capability.labelKey) {
    return t(capability.labelKey)
  }
  return capability.label ?? capability.id
}

function isCapabilityActive(capabilityId: string): boolean {
  return activeCapability.value?.id === capabilityId
}

function goToCapability(path: string) {
  void router.push(path)
}

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

.domain-subnav {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 100%;
  flex-wrap: wrap;
}

.domain-subnav-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 28px;
  max-width: 180px;
  padding: 4px 9px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-color-card);
  color: var(--text-color-regular);
  font-size: 12px;
  line-height: 1.2;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background-color 0.15s ease;
}

.domain-subnav-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.domain-subnav-item:hover,
.domain-subnav-item:focus-visible,
.domain-subnav-item-active {
  border-color: var(--el-color-primary, #409eff);
  color: var(--el-color-primary, #409eff);
  background: var(--el-color-primary-light-9, #ecf5ff);
}

.domain-subnav-item:focus-visible {
  outline: 2px solid var(--el-color-primary, #409eff);
  outline-offset: 2px;
}

@media (max-width: 768px) {
  .domain-subnav {
    width: 100%;
  }

  .domain-subnav-item {
    max-width: 44vw;
  }
}
</style>
