<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h2 class="text-2xl font-bold">数据连接治理</h2>
        <p class="text-sm text-gray-500 mt-1">统一查看外部 Provider、连接器端点与预览结果。</p>
      </div>
      <el-button type="primary" :loading="loading" @click="bootstrapAndLoad">刷新</el-button>
    </div>

    <el-card>
      <template #header>
        <div class="font-bold">Provider</div>
      </template>
      <el-table :data="providers">
        <el-table-column prop="provider_id" label="Provider" />
        <el-table-column prop="category" label="分类" />
        <el-table-column prop="auth_type" label="鉴权" />
      </el-table>
    </el-card>

    <el-card>
      <template #header>
        <div class="font-bold">端点</div>
      </template>
      <el-table :data="endpoints">
        <el-table-column prop="provider_id" label="Provider" />
        <el-table-column prop="endpoint_name" label="端点" />
        <el-table-column prop="incremental_sync_key" label="增量键" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { dataGovernanceApi, type DataGovernanceEndpoint, type DataGovernanceProvider } from '@/api/dataGovernance'

const loading = ref(false)
const providers = ref<DataGovernanceProvider[]>([])
const endpoints = ref<DataGovernanceEndpoint[]>([])

async function bootstrapAndLoad() {
  loading.value = true
  try {
    await dataGovernanceApi.bootstrap()
    const [providerResp, endpointResp] = await Promise.all([
      dataGovernanceApi.listProviders(),
      dataGovernanceApi.listEndpoints(),
    ])
    providers.value = providerResp.items
    endpoints.value = endpointResp.items
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void bootstrapAndLoad()
})
</script>
