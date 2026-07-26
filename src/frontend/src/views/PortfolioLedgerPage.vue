<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-2xl font-bold">
        {{ t('portfolioLedger.headerTitle') }}
      </h2>
      <p class="text-sm text-gray-500 mt-1">
        {{ t('portfolioLedger.headerDesc') }}
      </p>
    </div>

    <el-card>
      <template #header>
        <div class="font-bold">
          {{ t('portfolioLedger.cardOverview') }}
        </div>
      </template>
      <div class="space-y-3">
        <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
          <el-input
            v-model="portfolioName"
            placeholder="组合名称"
          />
          <el-input
            v-model="baseCurrency"
            placeholder="基础货币"
          />
          <el-input
            v-model="sourceType"
            placeholder="来源类型"
          />
          <el-button
            type="primary"
            :loading="loading"
            @click="createPortfolio"
          >
            创建账本
          </el-button>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-6 gap-3">
          <el-input
            v-model="txSymbol"
            placeholder="标的代码"
          />
          <el-select v-model="txTradeType">
            <el-option
              label="buy"
              value="buy"
            />
            <el-option
              label="sell"
              value="sell"
            />
          </el-select>
          <el-input-number
            v-model="txQuantity"
            :min="1"
          />
          <el-input-number
            v-model="txPrice"
            :min="0"
            :step="1"
          />
          <el-input
            v-model="txTradeDate"
            placeholder="交易日 YYYY-MM-DD"
          />
          <el-button
            :loading="loading || !portfolioId"
            @click="importTransaction"
          >
            导入交易
          </el-button>
        </div>
        <div class="flex gap-3 flex-wrap">
          <el-button
            :loading="loading || !portfolioId"
            @click="refreshPortfolio"
          >
            刷新数据
          </el-button>
          <el-button
            :loading="loading || !portfolioId"
            @click="backfillOnly"
          >
            回填快照
          </el-button>
        </div>
        <div
          v-if="portfolioId"
          class="text-sm text-gray-500"
        >
          当前账本：{{ portfolioId }}
        </div>
        <div
          v-if="portfolio"
          class="text-sm text-gray-500"
        >
          交易数：{{ portfolio.transaction_count ?? 0 }}
        </div>
        <div
          v-if="exportPayload"
          class="text-sm text-gray-500"
        >
          导出 schema：{{ exportPayload.schema_version }}
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <h3 class="font-medium mb-2">
              持仓
            </h3>
            <el-table :data="holdings">
              <el-table-column
                prop="symbol"
                label="标的"
              />
              <el-table-column
                prop="quantity"
                label="数量"
              />
              <el-table-column
                prop="cost_basis"
                label="成本"
              />
            </el-table>
          </div>
          <div>
            <h3 class="font-medium mb-2">
              快照
            </h3>
            <el-table :data="snapshots">
              <el-table-column
                prop="date"
                label="日期"
              />
              <el-table-column
                prop="nav"
                label="净值"
              />
            </el-table>
          </div>
        </div>
        <div>
          <h3 class="font-medium mb-2">
            风险分析
          </h3>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <el-card shadow="never">
              <div class="text-sm text-gray-500 mb-2">
                VaR / CVaR
              </div>
              <div
                v-if="varCvar"
                class="space-y-1 text-sm"
              >
                <div>状态：{{ varCvar.status }}</div>
                <div>样本数：{{ varCvar.observation_count }}</div>
                <div>VaR 95：{{ formatMetric(varCvar.var_95) }}</div>
                <div>CVaR 95：{{ formatMetric(varCvar.cvar_95) }}</div>
              </div>
              <div
                v-else
                class="text-sm text-gray-400"
              >
                暂无数据
              </div>
            </el-card>
            <el-card shadow="never">
              <div class="text-sm text-gray-500 mb-2">
                仓位建议
              </div>
              <div
                v-if="positionSizing"
                class="space-y-1 text-sm"
              >
                <div>状态：{{ positionSizing.status }}</div>
                <div>波动率：{{ formatMetric(positionSizing.annualized_volatility) }}</div>
                <div>目标波动：{{ formatMetric(positionSizing.target_volatility) }}</div>
                <div>建议仓位：{{ formatMetric(positionSizing.recommended_position) }}</div>
              </div>
              <div
                v-else
                class="text-sm text-gray-400"
              >
                暂无数据
              </div>
            </el-card>
            <el-card shadow="never">
              <div class="text-sm text-gray-500 mb-2">
                基准指标
              </div>
              <div
                v-if="benchmarkMetrics"
                class="space-y-1 text-sm"
              >
                <div>状态：{{ benchmarkMetrics.status }}</div>
                <div>基准：{{ benchmarkMetrics.benchmark_id }}</div>
                <div>Alpha：{{ formatMetric(benchmarkMetrics.alpha) }}</div>
                <div>Beta：{{ formatMetric(benchmarkMetrics.beta) }}</div>
                <div>信息比率：{{ formatMetric(benchmarkMetrics.information_ratio) }}</div>
              </div>
              <div
                v-else
                class="text-sm text-gray-400"
              >
                暂无数据
              </div>
            </el-card>
          </div>
        </div>
        <div>
          <h3 class="font-medium mb-2">
            交易
          </h3>
          <el-table :data="transactions">
            <el-table-column
              prop="symbol"
              label="标的"
            />
            <el-table-column
              prop="trade_type"
              label="方向"
            />
            <el-table-column
              prop="quantity"
              label="数量"
            />
            <el-table-column
              prop="price"
              label="价格"
            />
            <el-table-column
              prop="trade_date"
              label="交易日"
            />
          </el-table>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  portfolioLedgerApi,
  type PortfolioLedgerBenchmarkMetricsResult,
  type PortfolioHolding,
  type PortfolioLedgerExportPayload,
  type PortfolioLedgerPositionSizingResult,
  type PortfolioLedgerSummary,
  type PortfolioSnapshot,
  type PortfolioTransaction,
  type PortfolioLedgerVarCvarResult,
} from '@/api/portfolioLedger'

const { t } = useI18n()

const loading = ref(false)
const portfolioName = ref('研究组合')
const baseCurrency = ref('CNY')
const sourceType = ref('manual')
const portfolioId = ref('')
const portfolio = ref<PortfolioLedgerSummary | null>(null)
const holdings = ref<PortfolioHolding[]>([])
const transactions = ref<PortfolioTransaction[]>([])
const snapshots = ref<PortfolioSnapshot[]>([])
const exportPayload = ref<PortfolioLedgerExportPayload | null>(null)
const varCvar = ref<PortfolioLedgerVarCvarResult | null>(null)
const positionSizing = ref<PortfolioLedgerPositionSizingResult | null>(null)
const benchmarkMetrics = ref<PortfolioLedgerBenchmarkMetricsResult | null>(null)
const txSymbol = ref('RB2510')
const txTradeType = ref('buy')
const txQuantity = ref(1)
const txPrice = ref(3500)
const txTradeDate = ref('2026-05-26')

function formatMetric(value: number | null | undefined, digits = 4) {
  return typeof value === 'number' ? value.toFixed(digits) : '--'
}

async function createPortfolio() {
  loading.value = true
  try {
    const created = await portfolioLedgerApi.create({ name: portfolioName.value, base_currency: baseCurrency.value, source_type: sourceType.value })
    portfolioId.value = created.id
    await refreshPortfolio()
  } finally {
    loading.value = false
  }
}

async function importTransaction() {
  if (!portfolioId.value) return
  loading.value = true
  try {
    await portfolioLedgerApi.importTransactions(portfolioId.value, {
      format: 'json',
      idempotency_key: `${portfolioId.value}:${txSymbol.value}:${txTradeDate.value}:${txTradeType.value}`,
      transactions: [
        {
          symbol: txSymbol.value,
          trade_type: txTradeType.value,
          quantity: txQuantity.value,
          price: txPrice.value,
          trade_date: txTradeDate.value,
        },
      ],
    })
    await refreshPortfolio()
  } finally {
    loading.value = false
  }
}

async function refreshPortfolio() {
  if (!portfolioId.value) return
  const [detailResp, holdingsResp, transactionsResp, snapshotsResp, exportResp] = await Promise.all([
    portfolioLedgerApi.getDetail(portfolioId.value),
    portfolioLedgerApi.getHoldings(portfolioId.value),
    portfolioLedgerApi.getTransactions(portfolioId.value),
    portfolioLedgerApi.getSnapshots(portfolioId.value),
    portfolioLedgerApi.exportPortfolio(portfolioId.value),
  ])
  portfolio.value = detailResp
  holdings.value = holdingsResp.items
  transactions.value = transactionsResp.items
  snapshots.value = snapshotsResp.items
  exportPayload.value = exportResp

  const [varCvarResp, positionSizingResp, benchmarkMetricsResp] = await Promise.allSettled([
    portfolioLedgerApi.getVarCvar(portfolioId.value),
    portfolioLedgerApi.getPositionSizing(portfolioId.value),
    portfolioLedgerApi.getBenchmarkMetrics(portfolioId.value),
  ])
  varCvar.value = varCvarResp.status === 'fulfilled' ? varCvarResp.value : null
  positionSizing.value = positionSizingResp.status === 'fulfilled' ? positionSizingResp.value : null
  benchmarkMetrics.value = benchmarkMetricsResp.status === 'fulfilled' ? benchmarkMetricsResp.value : null
}

async function loadInitialPortfolio() {
  loading.value = true
  try {
    const response = await portfolioLedgerApi.list()
    const first = response.items[0]
    if (first) {
      portfolioId.value = first.id
      await refreshPortfolio()
    }
  } finally {
    loading.value = false
  }
}

async function backfillOnly() {
  if (!portfolioId.value) return
  loading.value = true
  try {
    await portfolioLedgerApi.backfillSnapshots(portfolioId.value)
    await refreshPortfolio()
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadInitialPortfolio()
})
</script>
