<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-2xl font-bold">
        {{ t('quantTools.headerTitle') }}
      </h2>
      <p class="text-sm text-gray-500 mt-1">
        {{ t('quantTools.headerDesc') }}
      </p>
    </div>

    <el-card>
      <div class="flex gap-3 flex-wrap items-center mb-4">
        <el-button
          type="primary"
          :loading="loading"
          @click="load"
        >
          {{ t('quantTools.btnRefreshTools') }}
        </el-button>
        <el-select
          v-model="selectedTool"
          class="min-w-[260px]"
        >
          <el-option
            v-for="tool in tools"
            :key="String(tool.name)"
            :label="String(tool.name)"
            :value="String(tool.name)"
          />
        </el-select>
        <el-button
          :loading="loading"
          @click="callSelectedTool"
        >
          {{ t('quantTools.btnCallTool') }}
        </el-button>
      </div>
      <el-input
        v-model="payloadText"
        type="textarea"
        :rows="8"
        class="mb-4"
      />
      <div
        v-if="tools.length"
        class="space-y-2 mb-4 text-xs text-gray-500"
      >
        <div
          v-for="tool in tools"
          :key="String(tool.name)"
        >
          {{ tool.name }} / {{ tool.auth_level }} / {{ tool.timeout_ms }} / {{ tool.rate_limit_per_user_per_min }} / {{ tool.requires_confirmation }}
        </div>
      </div>
      <el-table :data="tools">
        <el-table-column
          prop="name"
          :label="t('quantTools.colName')"
        />
        <el-table-column
          prop="description"
          :label="t('quantTools.colDesc')"
        />
        <el-table-column
          prop="auth_level"
          :label="t('quantTools.colAuth')"
        />
        <el-table-column
          prop="timeout_ms"
          :label="t('quantTools.colTimeoutMs')"
        />
        <el-table-column
          prop="rate_limit_per_user_per_min"
          :label="t('quantTools.colRateLimit')"
        />
      </el-table>
      <pre
        v-if="result"
        class="mt-4 text-xs bg-slate-900 text-slate-100 rounded p-3 overflow-auto"
      >{{ JSON.stringify(result, null, 2) }}</pre>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { marketIntelApi } from '@/api/marketIntel'

const { t } = useI18n()

const loading = ref(false)
const tools = ref<Array<Record<string, unknown>>>([])
const result = ref<Record<string, unknown> | null>(null)
const selectedTool = ref('markets.get_quote')
const payloadText = ref('{\n  "symbol": "RB2510"\n}')

async function load() {
  loading.value = true
  try {
    const response = await marketIntelApi.listQuantTools()
    tools.value = response.tools
    const firstTool = response.tools[0]
    if (firstTool?.name) {
      selectedTool.value = String(firstTool.name)
    }
  } finally {
    loading.value = false
  }
}

async function callSelectedTool() {
  loading.value = true
  try {
    result.value = await marketIntelApi.callQuantTool({
      tool_name: selectedTool.value,
      input: JSON.parse(payloadText.value || '{}') as Record<string, unknown>,
    })
  } finally {
    loading.value = false
  }
}

void load()
</script>
