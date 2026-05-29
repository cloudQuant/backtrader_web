<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-2xl font-bold">
        {{ t('optionsChain.headerTitle') }}
      </h2>
      <p class="text-sm text-gray-500 mt-1">
        {{ t('optionsChain.headerDesc') }}
      </p>
    </div>

    <el-card>
      <div class="flex gap-3 flex-wrap items-center mb-4">
        <el-input
          v-model="symbol"
          :placeholder="t('optionsChain.formSymbolPlaceholder')"
          class="max-w-xs"
        />
        <el-input
          v-model="expiry"
          :placeholder="t('optionsChain.formExpiryPlaceholder')"
          class="max-w-xs"
        />
        <el-select
          v-model="provider"
          class="max-w-xs"
        >
          <el-option
            label="Auto"
            value="auto"
          />
          <el-option
            label="Data Governance"
            value="data_governance"
          />
          <el-option
            label="Mock"
            value="mock"
          />
        </el-select>
        <el-button
          type="primary"
          :loading="loading"
          @click="load"
        >
          {{ t('optionsChain.btnQuery') }}
        </el-button>
      </div>
      <div
        v-if="summary"
        class="text-sm text-gray-500 mb-3"
      >
        {{ summary.underlying }} / {{ summary.source }} / {{ summary.timestamp }}
      </div>
      <div
        v-if="summary"
        class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4"
      >
        <el-statistic
          title="PCR"
          :value="summary.pcr as number"
        />
        <el-statistic
          title="Max Pain"
          :value="summary.max_pain as number"
        />
        <el-statistic
          title="ATM IV"
          :value="summary.atm_iv as number"
        />
      </div>
      <div
        v-if="summary"
        class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4"
      >
        <el-statistic
          title="Spot"
          :value="summary.spot as number"
        />
        <el-statistic
          :title="t('optionsChain.statStrikeCount')"
          :value="summary.strike_count as number"
        />
        <el-statistic
          :title="t('optionsChain.statStrikeStep')"
          :value="summary.strike_step as number"
        />
      </div>
      <el-table :data="rows">
        <el-table-column
          prop="strike"
          :label="t('optionsChain.colStrike')"
        />
        <el-table-column label="Call OI">
          <template #default="scope">
            {{ scope.row.call?.oi }}
          </template>
        </el-table-column>
        <el-table-column label="Call Vol">
          <template #default="scope">
            {{ scope.row.call?.volume }}
          </template>
        </el-table-column>
        <el-table-column label="Call IV">
          <template #default="scope">
            {{ scope.row.call?.iv }}
          </template>
        </el-table-column>
        <el-table-column label="Put OI">
          <template #default="scope">
            {{ scope.row.put?.oi }}
          </template>
        </el-table-column>
        <el-table-column label="Put Vol">
          <template #default="scope">
            {{ scope.row.put?.volume }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { marketIntelApi } from '@/api/marketIntel'

const { t } = useI18n()

const loading = ref(false)
const symbol = ref('RB2510')
const expiry = ref('2026-12-31')
const provider = ref('auto')
const summary = ref<Record<string, unknown> | null>(null)
const rows = ref<Array<Record<string, any>>>([])

async function load() {
  loading.value = true
  try {
    const response = await marketIntelApi.getOptionsChain(symbol.value, expiry.value, provider.value)
    summary.value = response
    rows.value = (response.rows as Array<Record<string, any>>) || []
  } finally {
    loading.value = false
  }
}

void load()
</script>
