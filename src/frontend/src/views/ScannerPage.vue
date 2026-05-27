<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-2xl font-bold">条件扫描</h2>
      <p class="text-sm text-gray-500 mt-1">基于安全 DSL 的多维量化筛选器。</p>
    </div>

    <el-card>
      <div class="flex gap-3 flex-wrap items-center mb-4">
        <el-input v-model="universeText" placeholder="RB2510,IF2510" class="max-w-sm" />
        <el-input v-model="condition" placeholder="indicator > 0.6 and news_sentiment > 0.5" class="max-w-xl" />
        <el-input-number v-model="lookbackDays" :min="1" :max="365" />
        <el-select v-model="timeframe" class="max-w-xs">
          <el-option label="1d" value="1d" />
          <el-option label="4h" value="4h" />
          <el-option label="1h" value="1h" />
        </el-select>
        <el-button type="primary" :loading="loading" @click="run">运行</el-button>
      </div>
      <div v-if="taskId" class="text-sm text-gray-500 mb-3">任务：{{ taskId }} / {{ taskStatus }}</div>
      <el-table :data="matches">
        <el-table-column prop="symbol" label="标的" />
        <el-table-column prop="price" label="价格" />
        <el-table-column prop="volume" label="成交量" />
        <el-table-column prop="indicator" label="指标" />
        <el-table-column prop="factor" label="因子" />
        <el-table-column prop="news_sentiment" label="新闻情绪" />
        <el-table-column prop="portfolio_exposure" label="组合暴露" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { marketIntelApi } from '@/api/marketIntel'

const universeText = ref('RB2510,IF2510')
const condition = ref('indicator > 0.6 and news_sentiment > 0.5')
const lookbackDays = ref(20)
const timeframe = ref('1d')
const loading = ref(false)
const matches = ref<Array<Record<string, unknown>>>([])
const taskId = ref('')
const taskStatus = ref('idle')

async function run() {
  loading.value = true
  try {
    const universe = universeText.value.split(',').map((item) => item.trim()).filter(Boolean)
    const response = await marketIntelApi.runScanner({
      universe,
      condition: condition.value,
      lookback_days: lookbackDays.value,
      timeframe: timeframe.value,
    })
    taskId.value = String(response.task_id || '')
    taskStatus.value = String(response.status || 'submitted')
    if (!taskId.value) {
      matches.value = (response.matches as Array<Record<string, unknown>>) || []
      return
    }
    const task = await marketIntelApi.getScannerTask(taskId.value)
    taskStatus.value = String(task.status || taskStatus.value)
    matches.value = (task.matches as Array<Record<string, unknown>>) || []
  } finally {
    loading.value = false
  }
}

void run()
</script>
