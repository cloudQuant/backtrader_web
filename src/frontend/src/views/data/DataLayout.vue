<template>
  <div class="space-y-6">
    <el-card class="data-shell">
      <div class="hero">
        <div>
          <h1>数据治理中心</h1>
          <p>统一管理 akshare 脚本、调度任务、执行记录、数据表和接口元信息。</p>
        </div>
        <div class="hero-tags">
          <el-tag :type="isAdmin ? 'danger' : 'info'">
            {{ isAdmin ? '管理员模式' : '只读模式' }}
          </el-tag>
          <el-tag type="success">市场数据已并入</el-tag>
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
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

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
    { label: '市场数据', path: '/data/market' },
    { label: '数据接口', path: '/data/scripts' },
    { label: '定时任务', path: '/data/tasks' },
    { label: '执行记录', path: '/data/executions' },
    { label: '数据表', path: '/data/tables' },
  ]

  if (isAdmin.value) {
    items.push({ label: '接口管理', path: '/data/interfaces' })
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
    linear-gradient(135deg, #f7fbfb 0%, #ffffff 55%, #f5f7fa 100%);
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
  color: #0f172a;
}

.hero p {
  margin: 0;
  max-width: 720px;
  color: #475569;
}

.eyebrow {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #0f766e;
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
