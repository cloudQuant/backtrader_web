<template>
  <div class="space-y-6">
    <el-card>
      <template #header>
        <span class="font-bold">数据管理</span>
      </template>

      <el-tabs v-model="activeTab">
        <!-- 股票数据 Tab -->
        <el-tab-pane label="股票数据" name="stock">
          <el-form
            :inline="true"
            :model="queryForm"
            class="mt-2"
          >
            <el-form-item label="股票代码">
              <el-input
                v-model="queryForm.symbol"
                placeholder="如: 000001.SZ"
              />
            </el-form-item>
            <el-form-item label="开始日期">
              <el-date-picker
                v-model="queryForm.startDate"
                type="date"
                placeholder="开始日期"
              />
            </el-form-item>
            <el-form-item label="结束日期">
              <el-date-picker
                v-model="queryForm.endDate"
                type="date"
                placeholder="结束日期"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="loading"
                @click="queryData"
              >
                查询
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 期货数据 Tab -->
        <el-tab-pane label="期货数据" name="futures">
          <div class="mt-2 space-y-4">
            <!-- Gateway 选择器 -->
            <div class="flex items-center gap-3">
              <el-select
                v-model="selectedGateway"
                placeholder="选择已连接的 Gateway"
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
              <el-button :loading="futuresLoading" @click="refreshFuturesData">
                <el-icon><Refresh /></el-icon>刷新
              </el-button>
              <el-button
                v-if="futuresPositions.length > 0"
                type="success"
                size="small"
                @click="exportFuturesPositions"
              >
                导出持仓CSV
              </el-button>
            </div>

            <el-empty
              v-if="connectedGateways.length === 0"
              description="暂无已连接的 Gateway，请先在 Gateway 状态页面连接"
            />

            <!-- 账户信息卡片 -->
            <el-card v-if="futuresAccount" shadow="never">
              <template #header>
                <span class="font-bold">账户信息</span>
              </template>
              <el-descriptions :column="3" border size="small">
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
            <el-card v-if="futuresPositions.length > 0" shadow="never">
              <template #header>
                <div class="flex justify-between items-center">
                  <span class="font-bold">持仓明细 ({{ futuresPositions.length }})</span>
                </div>
              </template>
              <el-table :data="futuresPositions" stripe max-height="400" size="small">
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
        <span class="font-bold">K线图 - {{ queryForm.symbol }}</span>
      </template>
      <div class="h-96">
        <KlineChart :data="klineData" />
      </div>
    </el-card>
    
    <!-- 数据表格 -->
    <el-card v-if="activeTab === 'stock' && tableData.length">
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-bold">历史数据</span>
          <el-button
            type="success"
            size="small"
            @click="exportData"
          >
            导出CSV
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
          label="日期"
          width="120"
        />
        <el-table-column
          prop="open"
          label="开盘"
          width="100"
        />
        <el-table-column
          prop="high"
          label="最高"
          width="100"
        />
        <el-table-column
          prop="low"
          label="最低"
          width="100"
        />
        <el-table-column
          prop="close"
          label="收盘"
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
          label="成交量"
          width="120"
        />
        <el-table-column
          prop="change"
          label="涨跌幅"
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
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '@/api/index'
import { liveTradingApi } from '@/api/liveTrading'
import KlineChart from '@/components/charts/KlineChart.vue'
import type { KlineData, KlineRecord, KlineResponse } from '@/types'
import dayjs from 'dayjs'

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
    ElMessage.error('查询失败，请确认 Gateway 已连接')
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
  ElMessage.success('导出成功')
}

// ---- Stock Tab ----
async function queryData() {
  loading.value = true
  try {
    const start = dayjs(queryForm.startDate).format('YYYY-MM-DD')
    const end = dayjs(queryForm.endDate).format('YYYY-MM-DD')
    
    const resp = await api.get<KlineResponse>('/data/kline', {
      params: { symbol: queryForm.symbol, start_date: start, end_date: end },
    })

    klineData.value = resp.kline
    tableData.value = resp.records.slice().reverse()
    ElMessage.success(`查询到 ${resp.count} 条数据`)
  } catch {
    // error handled by interceptor
  } finally {
    loading.value = false
  }
}

function exportData() {
  if (!tableData.value.length) return
  
  const headers = ['日期', '开盘', '最高', '最低', '收盘', '成交量', '涨跌幅']
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
  
  ElMessage.success('导出成功')
}

onMounted(() => {
  fetchConnectedGateways()
})
</script>
