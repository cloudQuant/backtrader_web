<template>
  <div class="space-y-6">
    <el-card class="data-shell">
      <div class="hero">
        <div>
          <h1>{{ t('dataPages.layoutHeroTitle') }}</h1>
          <p>{{ t('dataPages.layoutHeroDesc') }}</p>
        </div>
        <div class="hero-tags">
          <el-tag :type="isAdmin ? 'danger' : 'info'">
            {{ isAdmin ? t('dataPages.layoutAdminMode') : t('dataPages.layoutReadOnly') }}
          </el-tag>
          <el-tag type="success">
            {{ t('dataPages.layoutMarketMerged') }}
          </el-tag>
        </div>
      </div>

      <el-tabs
        :model-value="activeTab"
        stretch
        @tab-change="handleTabChange"
      >
        <el-tab-pane
          v-for="tab in tabs"
          :key="tab.path"
          :name="tab.path"
          :label="tab.label"
        />
      </el-tabs>
    </el-card>

    <router-view />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()

type DataTab = {
  label: string
  path: string
}

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isAdmin = computed(() => authStore.user?.is_admin ?? false)

const tabs = computed<DataTab[]>(() => {
  const items: DataTab[] = [
    { label: t('nav.quote'), path: '/data/quote' },
    { label: t('dataPages.layoutTabMarket'), path: '/data/market' },
    { label: t('dataPages.layoutTabTopics'), path: '/data/topics' },
    { label: t('dataPages.layoutTabScripts'), path: '/data/scripts' },
    { label: t('dataPages.layoutTabTasks'), path: '/data/tasks' },
    { label: t('dataPages.layoutTabExecutions'), path: '/data/executions' },
    { label: t('dataPages.layoutTabTables'), path: '/data/tables' },
    { label: t('nav.equityResearch'), path: '/data/intelligence/equity' },
    { label: t('nav.newsIntelligence'), path: '/data/intelligence/news' },
    { label: t('nav.optionsChain'), path: '/data/intelligence/options' },
    { label: t('nav.scanners'), path: '/data/intelligence/scanners' },
  ]

  if (isAdmin.value) {
    items.push({ label: t('dataPages.layoutTabSync'), path: '/data/sync' })
    items.push({ label: t('dataPages.layoutTabInterfaces'), path: '/data/interfaces' })
    items.push({ label: t('dataPages.layoutTabGovernance'), path: '/data/governance' })
  }

  return items
})

const activeTab = computed(() => {
  const matched = tabs.value.find(
    (tab) => route.path === tab.path || route.path.startsWith(`${tab.path}/`)
  )
  return matched?.path ?? '/data/market'
})

function handleTabChange(path: string | number) {
  const nextPath = String(path)
  if (nextPath !== activeTab.value) {
    void router.push(nextPath)
  }
}
</script>

<style scoped>
.data-shell {
  border: none;
  background:
    radial-gradient(circle at top left, rgba(13, 148, 136, 0.12), transparent 34%),
    linear-gradient(135deg, var(--info-surface) 0%, var(--bg-color-card) 55%, var(--bg-color-page) 100%);
}

.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 8px;
}

.hero h1 {
  margin: 6px 0 8px;
  font-size: 28px;
  line-height: 1.1;
  color: var(--text-color-primary);
}

.hero p {
  margin: 0;
  max-width: 720px;
  color: var(--text-color-regular);
}

.eyebrow {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent-color);
}

.hero-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .hero {
    flex-direction: column;
  }

  .hero h1 {
    font-size: 24px;
  }
}
</style>
