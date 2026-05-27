<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-2xl font-bold">权益研究</h2>
      <p class="text-sm text-gray-500 mt-1">检索标的、查看画像、财务、行情历史与因子信号。</p>
    </div>

    <el-card>
      <div class="flex gap-3 flex-wrap items-center mb-4">
        <el-input v-model="keyword" placeholder="输入标的代码或名称" class="max-w-sm" />
        <el-button type="primary" :loading="loading" @click="load">查询</el-button>
      </div>
      <el-table :data="items" @row-click="handleRowClick">
        <el-table-column prop="symbol" label="代码" />
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="asset_type" label="类型" />
        <el-table-column prop="exchange" label="交易所" />
      </el-table>
    </el-card>

    <el-card v-if="selectedSymbol">
      <template #header>
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <div class="font-bold">{{ selectedSymbol }}</div>
          <div class="text-sm text-gray-500">{{ quote?.provider }} / {{ info?.exchange }}</div>
        </div>
      </template>
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
        <el-statistic title="最新价" :value="Number(quote?.price || 0)" />
        <el-statistic title="昨收" :value="Number(quote?.previous_close || 0)" />
        <el-statistic title="涨跌幅" :value="Number(quote?.change_pct || 0)" />
        <el-statistic title="币种" :value="String(quote?.currency || '')" />
      </div>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="画像" name="info">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <div>名称：{{ info?.name }}</div>
            <div>行业：{{ info?.industry }}</div>
            <div>板块：{{ info?.sector }}</div>
            <div>国家：{{ info?.country }}</div>
            <div class="md:col-span-2">说明：{{ info?.description }}</div>
          </div>
        </el-tab-pane>
        <el-tab-pane label="财务" name="financials">
          <el-table :data="annualRows">
            <el-table-column prop="period" label="期间" />
            <el-table-column prop="revenue" label="营收" />
            <el-table-column prop="net_income" label="净利润" />
            <el-table-column prop="eps" label="EPS" />
            <el-table-column prop="roe" label="ROE" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="技术面" name="technicals">
          <pre class="text-xs bg-slate-900 text-slate-100 rounded p-3 overflow-auto">{{ JSON.stringify(technicals?.factors || {}, null, 2) }}</pre>
        </el-tab-pane>
        <el-tab-pane label="可比" name="peers">
          <el-table :data="peerRows">
            <el-table-column prop="symbol" label="代码" />
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="reason" label="可比逻辑" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="历史" name="history">
          <el-table :data="historyRows">
            <el-table-column prop="date" label="日期" />
            <el-table-column prop="open" label="开盘" />
            <el-table-column prop="high" label="最高" />
            <el-table-column prop="low" label="最低" />
            <el-table-column prop="close" label="收盘" />
            <el-table-column prop="volume" label="成交量" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { marketIntelApi } from '@/api/marketIntel'

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
