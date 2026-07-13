<template>
  <el-container class="app-shell min-h-screen">
    <!-- Desktop sidebar -->
    <el-aside
      width="244px"
      class="app-sidebar-desktop"
      role="navigation"
      :aria-label="t('nav.primary')"
    >
      <div class="sidebar-brand">
        <span class="sidebar-brand-mark">
          <el-icon aria-hidden="true">
            <TrendCharts />
          </el-icon>
        </span>
        <span class="sidebar-brand-copy">
          <span class="sidebar-brand-name">AI for Investor</span>
          <span class="sidebar-brand-context">{{ currentDomainLabel }}</span>
        </span>
      </div>

      <el-menu
        :default-active="currentRoute"
        class="sidebar-menu"
        router
      >
        <el-menu-item
          v-for="domain in visibleDomains"
          :key="domain.id"
          :index="domain.path"
          class="sidebar-menu-item"
        >
          <el-icon aria-hidden="true">
            <component :is="resolveIcon(domain.icon)" />
          </el-icon>
          <span class="sidebar-menu-label">{{ t(domain.labelKey) }}</span>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-footer">
        <span class="sidebar-footer-dot" />
        <span>{{ pageTitle }}</span>
      </div>
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
        <div class="mobile-drawer-header">
          <div class="sidebar-brand sidebar-brand--mobile">
            <span class="sidebar-brand-mark">
              <el-icon aria-hidden="true">
                <TrendCharts />
              </el-icon>
            </span>
            <span class="sidebar-brand-copy">
              <span class="sidebar-brand-name">AI for Investor</span>
              <span class="sidebar-brand-context">{{ currentDomainLabel }}</span>
            </span>
          </div>
          <button
            type="button"
            class="app-icon-button drawer-close-btn"
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
        class="sidebar-menu mobile-sidebar-menu"
        @select="handleMobileMenuSelect"
      >
        <el-menu-item
          v-for="domain in visibleDomains"
          :key="domain.id"
          :index="domain.path"
          class="sidebar-menu-item"
        >
          <el-icon aria-hidden="true">
            <component :is="resolveIcon(domain.icon)" />
          </el-icon>
          <span class="sidebar-menu-label">{{ t(domain.labelKey) }}</span>
        </el-menu-item>
      </el-menu>
    </el-drawer>
    
    <!-- Main content -->
    <el-container>
      <!-- Top header -->
      <el-header class="app-header">
        <div class="app-header-left">
          <!-- Mobile hamburger button -->
          <button
            type="button"
            class="app-icon-button hamburger-btn"
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

          <div class="app-header-main">
            <div class="app-page-heading">
              <span class="app-page-domain">{{ currentDomainLabel }}</span>
              <h2 class="app-page-title">
                {{ pageTitle }}
              </h2>
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
              class="app-header-extras app-header-title-extra"
            />
          </div>
          <div
            id="page-header-actions"
            class="app-header-extras app-header-page-actions"
          />
        </div>

        <div class="app-header-controls">
          <ThemeSwitcher />
          <LanguageSwitcher />
          <el-dropdown @command="handleCommand">
            <button
              type="button"
              class="user-dropdown-trigger"
              :aria-label="user?.username ? `${t('nav.userMenu')} (${user.username})` : t('nav.userMenu')"
            >
              <el-avatar
                :size="32"
                :alt="user?.username || ''"
              >
                {{ user?.username?.charAt(0).toUpperCase() }}
              </el-avatar>
              <span class="app-header-user-name">{{ user?.username || 'User' }}</span>
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
        class="app-main-content"
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
  return currentDomainLabel.value || 'AI for Investor'
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
.app-shell {
  min-height: 100vh;
  background: var(--bg-color-page);
  color: var(--text-color-primary);
}

.app-sidebar-desktop {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-color-sidebar);
  border-right: 1px solid var(--sidebar-border-color);
  transition: width 0.2s ease;
}

.sidebar-brand {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  min-height: 72px;
  padding: 16px;
}

.sidebar-brand--mobile {
  min-height: auto;
  padding: 0;
}

.sidebar-brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 1px solid var(--info-border-color);
  border-radius: 8px;
  background: var(--fill-color-light);
  color: var(--primary-color);
  font-size: 20px;
  flex: none;
}

.sidebar-brand-copy {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.sidebar-brand-name {
  overflow: hidden;
  color: var(--sidebar-text-color);
  font-size: 17px;
  font-weight: 760;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-brand-context {
  overflow: hidden;
  color: var(--sidebar-text-color-muted);
  font-size: 12px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-menu {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px 10px 12px;
  border-right: none;
  background: transparent;
}

.sidebar-menu :deep(.el-menu) {
  border-right: none;
  background: transparent;
}

.sidebar-menu :deep(.el-menu-item),
.sidebar-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  height: 42px;
  margin: 3px 0;
  padding: 0 12px !important;
  border: 1px solid transparent;
  border-radius: 8px;
  color: var(--sidebar-text-color-muted);
  line-height: 1;
}

.sidebar-menu :deep(.el-menu-item:hover),
.sidebar-menu :deep(.el-menu-item:focus),
.sidebar-menu-item:hover,
.sidebar-menu-item:focus {
  border-color: var(--border-color-light);
  background: var(--sidebar-hover-bg);
  color: var(--sidebar-text-color);
}

.sidebar-menu :deep(.el-menu-item.is-active),
.sidebar-menu-item.is-active {
  border-color: var(--info-border-color);
  background: var(--sidebar-active-bg);
  color: var(--sidebar-active-color);
  font-weight: 700;
}

.sidebar-menu :deep(.el-icon),
.sidebar-menu-item .el-icon {
  width: 18px;
  margin-right: 0;
  color: inherit;
  flex: none;
}

.sidebar-menu-label {
  overflow: hidden;
  min-width: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  margin: 0 12px 12px;
  padding: 10px 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--sidebar-text-color-muted);
  font-size: 12px;
  line-height: 1.2;
}

.sidebar-footer span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-footer-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--success-color);
  flex: none;
}

.mobile-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.mobile-sidebar-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: 18px 18px 12px;
  border-bottom: 1px solid var(--border-color-light);
}

.mobile-sidebar-drawer :deep(.el-drawer__body) {
  padding: 10px 8px 16px;
  background: var(--bg-color-sidebar);
}

.app-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  height: auto !important;
  min-height: 72px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-color);
}

.app-header-left {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.app-header-main {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 14px;
  align-items: center;
  min-width: 0;
}

.app-page-heading {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.app-page-domain {
  overflow: hidden;
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-page-title {
  overflow: hidden;
  margin: 0;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 760;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-header-title-extra,
.app-header-page-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex-wrap: wrap;
}

.app-header-page-actions {
  margin-left: auto;
}

.app-header-controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  min-width: 0;
}

.app-icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-primary);
  cursor: pointer;
  font: inherit;
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease,
    color 0.16s ease;
}

.app-icon-button:hover {
  border-color: var(--info-border-color);
  background: var(--fill-color-light);
  color: var(--primary-color);
}

.hamburger-btn {
  display: none;
  flex: none;
}

.drawer-close-btn,
.hamburger-btn,
.user-dropdown-trigger {
  color: inherit;
}

.drawer-close-btn:focus-visible,
.hamburger-btn:focus-visible,
.user-dropdown-trigger:focus-visible,
.app-icon-button:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.user-dropdown-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  max-width: 190px;
  padding: 3px 8px 3px 4px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  cursor: pointer;
  font: inherit;
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease;
}

.user-dropdown-trigger:hover {
  border-color: var(--info-border-color);
  background: var(--fill-color-light);
}

.app-header-user-name {
  overflow: hidden;
  color: var(--text-color-primary);
  font-size: 13px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  gap: 6px;
  min-height: 30px;
  max-width: 190px;
  padding: 5px 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-regular);
  font-size: 12px;
  line-height: 1.2;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    color 0.15s ease,
    background-color 0.15s ease;
}

.domain-subnav-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.domain-subnav-item:hover,
.domain-subnav-item:focus-visible,
.domain-subnav-item-active {
  border-color: var(--info-border-color);
  color: var(--text-color-primary);
  background: var(--fill-color-light);
}

.domain-subnav-item:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.app-main-content {
  min-width: 0;
  padding: 24px;
  background: var(--bg-color-page);
}

@media (max-width: 1024px) {
  .app-header {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .app-header-controls {
    justify-content: flex-start;
  }

  .app-header-main {
    grid-template-columns: 1fr;
    gap: 10px;
  }
}

@media (max-width: 768px) {
  .app-sidebar-desktop {
    display: none;
  }

  .app-header {
    padding: 12px;
  }

  .app-header-left {
    align-items: flex-start;
  }

  .hamburger-btn {
    display: inline-flex;
    margin-top: 3px;
  }

  .domain-subnav {
    width: 100%;
  }

  .domain-subnav-item {
    max-width: 44vw;
  }

  .app-main-content {
    padding: 16px;
  }
}

@media (max-width: 560px) {
  .app-header-controls {
    flex-wrap: wrap;
  }

  .user-dropdown-trigger {
    max-width: 100%;
  }

  .domain-subnav-item {
    max-width: calc(50vw - 24px);
  }
}
</style>
