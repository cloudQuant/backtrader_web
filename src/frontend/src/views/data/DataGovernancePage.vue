<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h2 class="text-2xl font-bold">
          {{ t('dataPages.governanceTitle') }}
        </h2>
        <p class="text-sm text-gray-500 mt-1">
          {{ t('dataPages.governanceDesc') }}
        </p>
      </div>
      <el-button
        type="primary"
        :loading="loading"
        @click="bootstrapAndLoad"
      >
        {{ t('dataPages.governanceRefresh') }}
      </el-button>
    </div>

    <el-card>
      <template #header>
        <div class="font-bold">
          {{ t('dataPages.governanceProvider') }}
        </div>
      </template>
      <el-table :data="providers">
        <el-table-column
          prop="provider_id"
          :label="t('dataPages.governanceProvider')"
        />
        <el-table-column
          prop="category"
          :label="t('dataPages.governanceCategory')"
        />
        <el-table-column
          prop="auth_type"
          :label="t('dataPages.governanceAuth')"
        />
      </el-table>
    </el-card>

    <el-card>
      <template #header>
        <div class="font-bold">
          {{ t('dataPages.governanceEndpoints') }}
        </div>
      </template>
      <el-table :data="endpoints">
        <el-table-column
          prop="provider_id"
          :label="t('dataPages.governanceProvider')"
        />
        <el-table-column
          prop="endpoint_name"
          :label="t('dataPages.governanceEndpointName')"
        />
        <el-table-column
          prop="incremental_sync_key"
          :label="t('dataPages.governanceIncrementalKey')"
        />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { dataGovernanceApi, type DataGovernanceEndpoint, type DataGovernanceProvider } from '@/api/dataGovernance'

const { t } = useI18n()
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
