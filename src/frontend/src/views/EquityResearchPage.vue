<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-2xl font-bold">
        {{ t('equityResearch.headerTitle') }}
      </h2>
      <p class="text-sm text-gray-500 mt-1">
        {{ t('equityResearch.headerDesc') }}
      </p>
    </div>

    <el-card>
      <div class="flex gap-3 flex-wrap items-center mb-4">
        <el-input
          v-model="keyword"
          :placeholder="t('equityResearch.searchPlaceholder')"
          class="max-w-sm"
        />
        <el-button
          type="primary"
          :loading="loading"
          @click="load"
        >
          {{ t('equityResearch.btnQuery') }}
        </el-button>
      </div>
      <el-table
        :data="items"
        @row-click="handleRowClick"
      >
        <el-table-column
          prop="symbol"
          :label="t('equityResearch.colSymbol')"
        />
        <el-table-column
          prop="name"
          :label="t('equityResearch.colName')"
        />
        <el-table-column
          prop="asset_type"
          :label="t('equityResearch.colAssetType')"
        />
        <el-table-column
          prop="exchange"
          :label="t('equityResearch.colExchange')"
        />
      </el-table>
    </el-card>

    <el-card v-if="selectedSymbol">
      <template #header>
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <div class="font-bold">
            {{ selectedSymbol }}
          </div>
          <div class="text-sm text-gray-500">
            {{ quote?.provider }} / {{ info?.exchange }}
          </div>
        </div>
      </template>
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
        <el-statistic
          :title="t('equityResearch.statLatestPrice')"
          :value="Number(quote?.price || 0)"
        />
        <el-statistic
          :title="t('equityResearch.statPrevClose')"
          :value="Number(quote?.previous_close || 0)"
        />
        <el-statistic
          :title="t('equityResearch.statChangePct')"
          :value="Number(quote?.change_pct || 0)"
        />
        <el-statistic
          :title="t('equityResearch.statCurrency')"
          :value="String(quote?.currency || '')"
        />
      </div>
      <el-tabs v-model="activeTab">
        <el-tab-pane
          :label="t('equityResearch.tabInfo')"
          name="info"
        >
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <div>{{ t('equityResearch.infoName') }}：{{ info?.name }}</div>
            <div>{{ t('equityResearch.infoIndustry') }}：{{ info?.industry }}</div>
            <div>{{ t('equityResearch.infoSector') }}：{{ info?.sector }}</div>
            <div>{{ t('equityResearch.infoCountry') }}：{{ info?.country }}</div>
            <div class="md:col-span-2">
              {{ t('equityResearch.infoDescription') }}：{{ info?.description }}
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane
          :label="t('equityResearch.tabFinancials')"
          name="financials"
        >
          <el-table :data="annualRows">
            <el-table-column
              prop="period"
              :label="t('equityResearch.finPeriod')"
            />
            <el-table-column
              prop="revenue"
              :label="t('equityResearch.finRevenue')"
            />
            <el-table-column
              prop="net_income"
              :label="t('equityResearch.finNetIncome')"
            />
            <el-table-column
              prop="eps"
              label="EPS"
            />
            <el-table-column
              prop="roe"
              label="ROE"
            />
          </el-table>
        </el-tab-pane>
        <el-tab-pane
          :label="t('equityResearch.tabTechnicals')"
          name="technicals"
        >
          <pre class="text-xs bg-slate-900 text-slate-100 rounded p-3 overflow-auto">{{ JSON.stringify(technicals?.factors || {}, null, 2) }}</pre>
        </el-tab-pane>
        <el-tab-pane
          :label="t('equityResearch.tabPeers')"
          name="peers"
        >
          <el-table :data="peerRows">
            <el-table-column
              prop="symbol"
              :label="t('equityResearch.peerSymbol')"
            />
            <el-table-column
              prop="name"
              :label="t('equityResearch.peerName')"
            />
            <el-table-column
              prop="reason"
              :label="t('equityResearch.peerReason')"
            />
          </el-table>
        </el-tab-pane>
        <el-tab-pane
          :label="t('equityResearch.tabHistory')"
          name="history"
        >
          <el-table :data="historyRows">
            <el-table-column
              prop="date"
              :label="t('equityResearch.histDate')"
            />
            <el-table-column
              prop="open"
              :label="t('equityResearch.histOpen')"
            />
            <el-table-column
              prop="high"
              :label="t('equityResearch.histHigh')"
            />
            <el-table-column
              prop="low"
              :label="t('equityResearch.histLow')"
            />
            <el-table-column
              prop="close"
              :label="t('equityResearch.histClose')"
            />
            <el-table-column
              prop="volume"
              :label="t('equityResearch.histVolume')"
            />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { marketIntelApi } from '@/api/marketIntel'

const { t } = useI18n()

const keyword = ref('RB')
const loading = ref(false)
const items = ref<Array<Record<string, unknown>>>([])
const selectedSymbol = ref('')
const activeTab = ref('info')
const quote = ref<Record<string, unknown> | null>(null)
const info = ref<Record<string, unknown> | null>(null)
const financials = ref<Record<string, unknown> | null>(null)
const technicals = ref<Record<string, unknown> | null>(null)
const peers = ref<Record<string, unknown> | null>(null)
const history = ref<Record<string, unknown> | null>(null)

const annualRows = ref<Array<Record<string, unknown>>>([])
const peerRows = ref<Array<Record<string, unknown>>>([])
const historyRows = ref<Array<Record<string, unknown>>>([])

async function load() {
  loading.value = true
  try {
    const response = await marketIntelApi.searchEquities(keyword.value)
    items.value = response.items
    const first = response.items[0]
    if (first?.symbol) {
      await loadSymbol(String(first.symbol))
    }
  } finally {
    loading.value = false
  }
}

async function loadSymbol(symbol: string) {
  selectedSymbol.value = symbol
  const [quoteResp, infoResp, historyResp, financialsResp, technicalsResp, peersResp] = await Promise.all([
    marketIntelApi.getEquityQuote(symbol),
    marketIntelApi.getEquityInfo(symbol),
    marketIntelApi.getEquityHistory(symbol),
    marketIntelApi.getEquityFinancials(symbol),
    marketIntelApi.getTechnicals(symbol),
    marketIntelApi.getEquityPeers(symbol),
  ])
  quote.value = quoteResp
  info.value = infoResp
  history.value = historyResp
  financials.value = financialsResp
  technicals.value = technicalsResp
  peers.value = peersResp
  annualRows.value = (financialsResp.annual as Array<Record<string, unknown>>) || []
  peerRows.value = (peersResp.items as Array<Record<string, unknown>>) || []
  historyRows.value = (historyResp.rows as Array<Record<string, unknown>>) || []
}

async function handleRowClick(row: Record<string, unknown>) {
  if (row.symbol) {
    loading.value = true
    try {
      await loadSymbol(String(row.symbol))
    } finally {
      loading.value = false
    }
  }
}

void load()
</script>
