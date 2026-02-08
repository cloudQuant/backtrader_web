<template>
  <div class="space-y-6">
    <el-card>
      <template #header>
        <span class="font-bold">数据查询</span>
      </template>
      
      <el-form :inline="true" :model="queryForm">
        <el-form-item label="股票代码">
          <el-input v-model="queryForm.symbol" placeholder="如: 000001.SZ" />
        </el-form-item>
        <el-form-item label="开始日期">
          <el-date-picker v-model="queryForm.startDate" type="date" placeholder="开始日期" />
        </el-form-item>
        <el-form-item label="结束日期">
          <el-date-picker v-model="queryForm.endDate" type="date" placeholder="结束日期" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="queryData" :loading="loading">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- K线图 -->
    <el-card v-if="klineData">
      <template #header>
        <span class="font-bold">K线图 - {{ queryForm.symbol }}</span>
      </template>
      <div class="h-96">
        <KlineChart :data="klineData" />
      </div>
    </el-card>
    
    <!-- 数据表格 -->
    <el-card v-if="tableData.length">
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-bold">历史数据</span>
          <el-button type="success" size="small" @click="exportData">
            导出CSV
          </el-button>
        </div>
      </template>
      
      <el-table :data="tableData" stripe max-height="400">
        <el-table-column prop="date" label="日期" width="120" />
        <el-table-column prop="open" label="开盘" width="100" />
        <el-table-column prop="high" label="最高" width="100" />
        <el-table-column prop="low" label="最低" width="100" />
        <el-table-column prop="close" label="收盘" width="100">
          <template #default="{ row }">
            <span :class="row.close >= row.open ? 'text-red-500' : 'text-green-500'">
              {{ row.close }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="volume" label="成交量" width="120" />
        <el-table-column prop="change" label="涨跌幅" width="100">
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
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api/index'
import KlineChart from '@/components/charts/KlineChart.vue'
import type { KlineData } from '@/types'
import dayjs from 'dayjs'

const loading = ref(false)
const klineData = ref<KlineData | null>(null)
const tableData = ref<any[]>([])

const queryForm = reactive({
  symbol: '000001.SZ',
  startDate: dayjs().subtract(6, 'month').toDate(),
  endDate: new Date(),
})

async function queryData() {
  loading.value = true
  try {
    const start = dayjs(queryForm.startDate).format('YYYY-MM-DD')
    const end = dayjs(queryForm.endDate).format('YYYY-MM-DD')
    
    const resp: any = await api.get('/data/kline', {
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
</script>
