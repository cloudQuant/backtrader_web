<template>
  <div class="space-y-6">
    <el-card>
      <template #header>
        <span class="font-bold">{{ t('dataMgmt.headerTitle') }}</span>
      </template>

      <el-tabs v-model="activeTab">
        <!-- 股票数据 Tab -->
        <el-tab-pane
          :label="t('dataMgmt.tabStock')"
          name="stock"
        >
          <el-form
            :inline="true"
            :model="queryForm"
            class="mt-2"
          >
            <el-form-item :label="t('dataMgmt.formSymbol')">
              <el-input
                v-model="queryForm.symbol"
                :placeholder="t('dataMgmt.formSymbolPlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('dataMgmt.formStartDate')">
              <el-date-picker
                v-model="queryForm.startDate"
                type="date"
                :placeholder="t('dataMgmt.formStartDate')"
              />
            </el-form-item>
            <el-form-item :label="t('dataMgmt.formEndDate')">
              <el-date-picker
                v-model="queryForm.endDate"
                type="date"
                :placeholder="t('dataMgmt.formEndDate')"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="loading"
                @click="queryData"
              >
                {{ t('dataMgmt.btnQuery') }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 期货数据 Tab -->
        <el-tab-pane
          :label="t('dataMgmt.tabFutures')"
          name="futures"
        >
          <div class="mt-2 space-y-4">
            <!-- Gateway 选择器 -->
            <div class="flex items-center gap-3">
              <el-select
                v-model="selectedGateway"
                :placeholder="t('dataMgmt.selectGatewayPlaceholder')"
                class="w-80"
                @change="onGatewaySelect"
              >
                <el-option
                  v-for="gw in connectedGateways"
                  :key="gw.gateway_key"
                  :label="`${gw.exchange_type} — ${gw.account_id || gw.gateway_key}`"
                  :value="gw.gateway_key"
                />
              </el-select>
              <el-button
                :loading="futuresLoading"
                @click="refreshFuturesData"
              >
                <el-icon><Refresh /></el-icon>{{ t('dataMgmt.btnRefresh') }}
              </el-button>
              <el-button
                v-if="futuresPositions.length > 0"
                type="success"
                size="small"
                @click="exportFuturesPositions"
              >
                {{ t('dataMgmt.btnExportPositionsCsv') }}
              </el-button>
            </div>

            <el-empty
              v-if="connectedGateways.length === 0"
              :description="t('dataMgmt.emptyNoGateway')"
            />

            <!-- 账户信息卡片 -->
            <el-card
              v-if="futuresAccount"
              shadow="never"
            >
              <template #header>
                <span class="font-bold">{{ t('dataMgmt.cardAccount') }}</span>
              </template>
              <el-descriptions
                :column="3"
                border
                size="small"
              >
                <el-descriptions-item
                  v-for="(val, key) in futuresAccount"
                  :key="String(key)"
                  :label="String(key)"
                >
                  {{ val }}
                </el-descriptions-item>
              </el-descriptions>
            </el-card>

            <!-- 持仓表 -->
            <el-card
              v-if="futuresPositions.length > 0"
              shadow="never"
            >
              <template #header>
                <div class="flex justify-between items-center">
                  <span class="font-bold">{{ t('dataMgmt.cardPositionsTitle', { count: futuresPositions.length }) }}</span>
                </div>
              </template>
              <el-table
                :data="futuresPositions"
                stripe
                max-height="400"
                size="small"
              >
                <el-table-column
                  v-for="col in futuresPositionCols"
                  :key="col"
                  :prop="col"
                  :label="col"
                  min-width="120"
                />
              </el-table>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
    
    <!-- K线图 -->
    <el-card v-if="activeTab === 'stock' && klineData">
      <template #header>
        <span class="font-bold">{{ t('dataMgmt.cardKlineTitle', { symbol: queryForm.symbol }) }}</span>
      </template>
      <div class="h-96">
        <KlineChart :data="klineData" />
      </div>
    </el-card>
    
    <!-- 数据表格 -->
    <el-card v-if="activeTab === 'stock' && tableData.length">
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-bold">{{ t('dataMgmt.cardHistory') }}</span>
          <el-button
            type="success"
            size="small"
            @click="exportData"
          >
            {{ t('dataMgmt.btnExportCsv') }}
          </el-button>
        </div>
      </template>
      
      <el-table
        :data="tableData"
        stripe
        max-height="400"
      >
        <el-table-column
          prop="date"
          :label="t('dataMgmt.colDate')"
          width="120"
        />
        <el-table-column
          prop="open"
          :label="t('dataMgmt.colOpen')"
          width="100"
        />
        <el-table-column
          prop="high"
          :label="t('dataMgmt.colHigh')"
          width="100"
        />
        <el-table-column
          prop="low"
          :label="t('dataMgmt.colLow')"
          width="100"
        />
        <el-table-column
          prop="close"
          :label="t('dataMgmt.colClose')"
          width="100"
        >
          <template #default="{ row }">
            <span :class="row.close >= row.open ? 'text-red-500' : 'text-green-500'">
              {{ row.close }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          prop="volume"
          :label="t('dataMgmt.colVolume')"
          width="120"
        />
        <el-table-column
          prop="change"
          :label="t('dataMgmt.colChange')"
          width="100"
        >
          <template #default="{ row }">
            <span :class="row.change >= 0 ? 'text-red-500' : 'text-green-500'">
              {{ row.change?.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '@/api/index'
import { liveTradingApi } from '@/api/liveTrading'
import KlineChart from '@/components/charts/KlineChart.vue'
import type { KlineData, KlineRecord, KlineResponse } from '@/types'
import dayjs from 'dayjs'

const { t } = useI18n()

const activeTab = ref('stock')
const loading = ref(false)
const klineData = ref<KlineData | null>(null)
const tableData = ref<KlineRecord[]>([])

const queryForm = reactive({
  symbol: '000001.SZ',
  startDate: dayjs().subtract(6, 'month').toDate(),
  endDate: new Date(),
})

// ---- Futures Tab State ----
const futuresLoading = ref(false)
const selectedGateway = ref('')
const connectedGateways = ref<{ gateway_key: string; exchange_type: string; account_id: string; has_runtime: boolean }[]>([])
const futuresAccount = ref<Record<string, unknown> | null>(null)
const futuresPositions = ref<Record<string, unknown>[]>([])

const futuresPositionCols = computed(() => {
  if (futuresPositions.value.length === 0) return []
  return Object.keys(futuresPositions.value[0])
})

async function fetchConnectedGateways() {
  try {
    const res = await liveTradingApi.listConnectedGateways()
    connectedGateways.value = res.gateways
  } catch {
    // silent
  }
}

async function onGatewaySelect() {
  if (!selectedGateway.value) return
  await refreshFuturesData()
}

async function refreshFuturesData() {
  if (!selectedGateway.value) return
  futuresLoading.value = true
  try {
    const [acct, pos] = await Promise.all([
      liveTradingApi.queryGatewayAccount(selectedGateway.value),
      liveTradingApi.queryGatewayPositions(selectedGateway.value),
    ])
    futuresAccount.value = acct
    futuresPositions.value = pos.positions
  } catch {
    ElMessage.error(t('dataMgmt.msgQueryFail'))
  } finally {
    futuresLoading.value = false
  }
}

function exportFuturesPositions() {
  if (futuresPositions.value.length === 0) return
  const cols = futuresPositionCols.value
  const csv = [
    cols.join(','),
    ...futuresPositions.value.map(row =>
      cols.map(c => String(row[c] ?? '')).join(',')
    ),
  ].join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `positions_${selectedGateway.value}_${dayjs().format('YYYYMMDD')}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success(t('dataMgmt.msgExportSuccess'))
}

// ---- Stock Tab ----
async function queryData() {
  loading.value = true
  try {
    const start = dayjs(queryForm.startDate).format('YYYY-MM-DD')
    const end = dayjs(queryForm.endDate).format('YYYY-MM-DD')
    
    const data = await api.get<KlineResponse>('/data/kline', {
      params: { symbol: queryForm.symbol, start_date: start, end_date: end },
    })

    klineData.value = data.kline
    tableData.value = data.records.slice().reverse()
    ElMessage.success(t('dataMgmt.msgQueriedCount', { count: data.count }))
  } catch {
    // error handled by interceptor
  } finally {
    loading.value = false
  }
}

function exportData() {
  if (!tableData.value.length) return
  
  const headers = [
    t('dataMgmt.colDate'),
    t('dataMgmt.colOpen'),
    t('dataMgmt.colHigh'),
    t('dataMgmt.colLow'),
    t('dataMgmt.colClose'),
    t('dataMgmt.colVolume'),
    t('dataMgmt.colChange'),
  ]
  const csv = [
    headers.join(','),
    ...tableData.value.map(row => 
      `${row.date},${row.open},${row.high},${row.low},${row.close},${row.volume},${row.change?.toFixed(2)}%`
    )
  ].join('\n')
  
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${queryForm.symbol}_${dayjs().format('YYYYMMDD')}.csv`
  a.click()
  URL.revokeObjectURL(url)
  
  ElMessage.success(t('dataMgmt.msgExportSuccess'))
}

onMounted(() => {
  fetchConnectedGateways()
})
</script>
