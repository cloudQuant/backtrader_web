<template>
  <div class="space-y-6">
    <el-card class="config-data-shell">
      <div class="config-data-hero">
        <div>
          <h1>{{ t('configPages.dataTitle') }}</h1>
          <p>{{ t('configPages.dataDesc') }}</p>
        </div>
        <el-tag type="danger">
          {{ t('dataPages.layoutAdminMode') }}
        </el-tag>
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

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

type ConfigDataTab = {
  label: string
  path: string
}

const tabs = computed<ConfigDataTab[]>(() => [
  { label: t('dataPages.layoutTabScripts'), path: '/config/data/scripts' },
  { label: t('dataPages.layoutTabTasks'), path: '/config/data/tasks' },
  { label: t('dataPages.layoutTabExecutions'), path: '/config/data/executions' },
  { label: t('dataPages.layoutTabSync'), path: '/config/data/sync' },
  { label: t('dataPages.layoutTabInterfaces'), path: '/config/data/interfaces' },
  { label: t('dataPages.layoutTabGovernance'), path: '/config/data/governance' },
  { label: 'Airflow', path: '/config/data/airflow' },
])

const activeTab = computed(() => {
  const matched = tabs.value.find(
    (tab) => route.path === tab.path || route.path.startsWith(`${tab.path}/`),
  )
  return matched?.path ?? '/config/data/scripts'
})

function handleTabChange(path: string | number) {
  const nextPath = String(path)
  if (nextPath !== activeTab.value) {
    void router.push(nextPath)
  }
}
</script>

<style scoped>
.config-data-shell {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
}

.config-data-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 8px;
}

.config-data-hero h1 {
  margin: 6px 0 8px;
  font-size: 28px;
  line-height: 1.1;
  color: var(--text-color-primary);
}

.config-data-hero p {
  margin: 0;
  max-width: 720px;
  color: var(--text-color-regular);
}

.config-data-shell :deep(.el-tabs__nav-wrap::after) {
  background: var(--border-color);
}

.config-data-shell :deep(.el-tabs__item) {
  color: var(--text-color-secondary);
}

.config-data-shell :deep(.el-tabs__item.is-active) {
  color: var(--primary-color);
}

.config-data-shell :deep(.el-tabs__active-bar) {
  background: var(--primary-color);
}

@media (max-width: 768px) {
  .config-data-hero {
    flex-direction: column;
  }

  .config-data-hero h1 {
    font-size: 24px;
  }
}
</style>
