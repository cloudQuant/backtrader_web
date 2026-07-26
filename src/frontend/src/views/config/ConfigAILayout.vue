<template>
  <div class="space-y-6">
    <el-card class="config-ai-shell">
      <div class="config-ai-hero">
        <div>
          <h1>{{ t('configPages.aiTitle') }}</h1>
          <p>{{ t('configPages.aiDesc') }}</p>
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

type ConfigAITab = {
  label: string
  path: string
}

const tabs = computed<ConfigAITab[]>(() => [
  { label: t('nav.aiConfig'), path: '/config/ai/providers' },
  { label: t('nav.promptGovernance'), path: '/config/ai/prompt-governance' },
  { label: t('nav.aiCost'), path: '/config/ai/observability' },
])

const activeTab = computed(() => {
  const matched = tabs.value.find(
    (tab) => route.path === tab.path || route.path.startsWith(`${tab.path}/`),
  )
  return matched?.path ?? '/config/ai/providers'
})

function handleTabChange(path: string | number) {
  const nextPath = String(path)
  if (nextPath !== activeTab.value) {
    void router.push(nextPath)
  }
}
</script>

<style scoped>
.config-ai-shell {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
}

.config-ai-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 8px;
}

.config-ai-hero h1 {
  margin: 6px 0 8px;
  font-size: 28px;
  line-height: 1.1;
  color: var(--text-color-primary);
}

.config-ai-hero p {
  margin: 0;
  max-width: 720px;
  color: var(--text-color-regular);
}

.config-ai-shell :deep(.el-tabs__nav-wrap::after) {
  background: var(--border-color);
}

.config-ai-shell :deep(.el-tabs__item) {
  color: var(--text-color-secondary);
}

.config-ai-shell :deep(.el-tabs__item.is-active) {
  color: var(--primary-color);
}

.config-ai-shell :deep(.el-tabs__active-bar) {
  background: var(--primary-color);
}

@media (max-width: 768px) {
  .config-ai-hero {
    flex-direction: column;
  }

  .config-ai-hero h1 {
    font-size: 24px;
  }
}
</style>
